import io,json,uuid
from pathlib import Path
import pytest
from docx import Document
from docx.shared import Pt
from app.documents import inspect_document
from app.lncs import check
from app.settings import settings

def test_effective_heading_format_reports_real_defect_not_compliant_text(tmp_path):
    d=Document();p=d.add_paragraph('Methods','Heading 1');p.runs[0].font.size=Pt(18);p.runs[0].font.bold=True
    q=d.add_paragraph('Results','Heading 1');q.runs[0].font.size=Pt(12);q.runs[0].font.bold=True
    path=tmp_path/'headings.docx';d.save(path);doc=inspect_document(path)
    issues,_=check(doc,'test',{'name':'Springer LNCS'})
    assert any(i['location']=='paragraph 1' and i['category']=='headings' for i in issues)
    assert not any(i['location']=='paragraph 2' and i['category']=='headings' for i in issues)
    assert all(i.get('rule',{}).get('source') for i in issues)

def test_compiler_has_no_docker_socket_or_network_and_preserves_checksum(tmp_path):
    from app.compile_client import compile_source
    import hashlib
    source=tmp_path/'main.tex';source.write_text(r'\documentclass{article}\begin{document}Restricted actual compilation.\end{document}')
    pdf,result=compile_source(source)
    assert pdf.read_bytes().startswith(b'%PDF')
    assert result['source_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    assert result['isolation']['host_docker_socket'] is False and result['isolation']['network']=='none'
    assert result['isolation']['per_job_uid']>=10000

def test_draft_is_generated_from_current_verified_eligible_paper_without_release(monkeypatch):
    from app.main import register
    from app.processing import process
    from app.db import Base,engine,Session,Conference,Enrollment,Paper,Version,PublicationDraft
    from app.agent import update_draft
    Base.metadata.create_all(engine);monkeypatch.setattr('app.main.validate.delay',lambda vid:None)
    d=Document();d.add_paragraph('Unique '+uuid.uuid4().hex);d.add_paragraph('Abstract');d.add_paragraph('A real document-processing integration test.');d.add_paragraph('Keywords: document testing');d.add_paragraph('References');b=io.BytesIO();d.save(b)
    r=register(b.getvalue(),'source.docx',{'title':'Draft test','authors':'Test Author','affiliation':'Test University','email':'test@example.test'},enqueue=False)
    assert process(r['version_id'])['state']=='Complete'
    with Session() as s:
        conf=Conference(id='draft-'+uuid.uuid4().hex,enabled=True,config={'name':'Draft integration test','expected_papers':['one','pending'],'coordinator_email':'editor@example.test','demo_mode':True,'deadline_seconds':30,'reminder_seconds':[10],'require_ai':False,'profile':{'name':'Test contract','source':'Test fixture','requirements':{'max_pages':8}}});s.add(conf)
        p=s.get(Paper,r['paper_id']);p.status='Publication Ready';v=s.get(Version,r['version_id']);doc=dict(v.result['document']);doc['verified_metadata']={'title':'Draft test','authors':'Test Author','affiliation':'Test University','abstract':'A real document-processing integration test.','keywords':'document testing'};v.result={**v.result,'document':doc}
        s.add(Enrollment(id=uuid.uuid4().hex,conference_id=conf.id,paper_id=p.id,external_id='one',state='Publication Ready',handled_version=1));s.commit()
        output=update_draft(s,conf)
        assert output['draft'] and output['included']==[{'paper_id':p.id,'version':1}] and not conf.publication
        root=settings.storage/'publications'/output['publication_id'];assert (root/'book-of-abstracts.pdf').read_bytes().startswith(b'%PDF')
        assert json.loads((root/'audit.json').read_text())['papers'][0]['metadata_verified'] is True
        pagination=json.loads((root/'pagination.json').read_text())
        assert pagination['pdf'][p.id]>=3 and pagination['docx'][p.id]>=3
        import zipfile
        with zipfile.ZipFile(root/'book-of-abstracts.docx') as archive:
            xml=archive.read('word/document.xml').decode()
            assert 'PAGEREF paper_'+p.id in xml and '>3<' in xml
        from pypdf import PdfReader
        pdf=PdfReader(root/'book-of-abstracts.pdf')
        assert 'Draft test' in pdf.pages[pagination['pdf'][p.id]-1].extract_text()
        assert '3' in pdf.pages[1].extract_text() and 'Test Author' in pdf.pages[-1].extract_text()
        assert update_draft(s,conf)['publication_id']==output['publication_id']

def test_five_file_bulk_is_idempotent_and_n8n_is_the_only_intake_trigger(monkeypatch):
    import hashlib
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import Base,engine
    Base.metadata.create_all(engine)
    c=TestClient(app);h={'Authorization':'Bearer '+settings.admin_token};cid='bulk-'+uuid.uuid4().hex
    policy={'name':'Bulk contract test','expected_papers':['paper-'+str(i) for i in range(5)],'coordinator_email':'editor@example.test','demo_mode':True,'real_paper_mode':True,'require_ai':True,'enabled':True,'deadline_seconds':30,'reminder_seconds':[10,20],'profile':{'name':'Test contract','version':'1','source':'unit-test contract','requirements':{'max_pages':8}}}
    assert c.put('/agent/conferences/'+cid,headers=h,json=policy).status_code==200
    called=[];monkeypatch.setattr('app.agent.validate.delay',lambda vid:called.append(vid))
    uploads=[];manifest=[];hashes={}
    for i in range(5):
        d=Document();d.add_paragraph('Bulk contract '+str(i)+' '+uuid.uuid4().hex);b=io.BytesIO();d.save(b);data=b.getvalue();name=f'paper-{i}.docx'
        uploads.append(('files',(name,data)));manifest.append({'paper_key':f'paper-{i}','path':name,'metadata':{'title':f'Contract {i}','authors':'Test Author','email':'author@example.test'}});hashes[name]=hashlib.sha256(data).hexdigest()
    r=c.post('/agent/conferences/'+cid+'/bulk',headers=h,files=uploads,data={'manifest':json.dumps({'papers':manifest})})
    assert r.status_code==200,r.text
    assert len(r.json()['files'])==5 and called==[]
    assert c.get('/agent/conferences/'+cid,headers=h).json()['papers']==[]
    assert all(p['status']=='Duplicate' for p in c.post('/agent/conferences/'+cid+'/bulk',headers=h,files=uploads,data={'manifest':json.dumps(manifest)}).json()['files'])
    assert c.post('/agent/'+cid+'/intake',headers=h).status_code==200
    state=c.get('/agent/conferences/'+cid,headers=h).json();assert len(state['papers'])==5
    for paper in state['papers']:
        version=c.get('/papers/'+paper['paper_id'],headers=h).json()['versions'][0]
        assert version['sha256']==hashes[version['filename']]
    assert len(set(called))==5

def test_real_paper_policy_cannot_disable_ai_dependency():
    from app.agent import ConferencePolicy
    from pydantic import ValidationError
    with pytest.raises(ValidationError,match='requires successful AI review'):
        ConferencePolicy(name='Real batch',expected_papers=['one'],coordinator_email='editor@example.test',profile={'source':'Test contract','requirements':{'max_pages':8}},real_paper_mode=True,require_ai=False)

def test_compilation_failure_can_request_real_correction_without_fake_ai_pass():
    from app.db import Base,engine,Session,Conference,Enrollment,Paper,Version,Dispatch
    from app.agent import completed
    from sqlalchemy import select
    Base.metadata.create_all(engine)
    with Session() as s:
        cid='compile-failure-'+uuid.uuid4().hex
        conf=Conference(id=cid,enabled=True,config={'name':'Technical failure test','expected_papers':['one'],'coordinator_email':'editor@example.test','demo_mode':True,'real_paper_mode':True,'require_ai':True,'deadline_seconds':30,'reminder_seconds':[10,20],'profile':{'name':'Test contract','source':'Unit-test contract','requirements':{'max_pages':8}}});s.add(conf)
        p=Paper(id=uuid.uuid4().hex,title='Technical test',authors='Verified Test Author',affiliation='Test University',email='author@example.test');s.add(p);s.flush()
        v=Version(id=uuid.uuid4().hex,paper_id=p.id,number=1,filename='broken.zip',path='/not-compiled',digest=uuid.uuid4().hex,state='Failed',error='Missing source asset figure.pdf (source line 21)');s.add(v)
        enrollment=Enrollment(id=uuid.uuid4().hex,conference_id=cid,external_id='one',paper_id=p.id,details={'metadata_verified':True});s.add(enrollment);s.commit()
        completed(s,conf)
        assert enrollment.state=='Awaiting Revision'
        assert s.scalar(select(Dispatch).where(Dispatch.paper_id==p.id)).state=='Pending'
        assert any(i['category']=='compilation' and 'figure.pdf' in i['evidence'] for i in v.result['issues'])
        assert not any(i['category']=='metadata' and 'abstract' in i['observed_problem'] for i in v.result['issues'])
        assert any(c['check']=='AI proofreading' and c['status']=='skipped' for c in v.result['checks'])
        assert p.status!='Publication Ready'
