"""Suite A fixtures: contracts and real local tools, never real-paper acceptance evidence."""
import io,json,re,uuid
from pathlib import Path
from docx import Document
from fastapi.testclient import TestClient
from app.main import app
from app.settings import settings
from app.db import Base,engine,Session,Conference,Enrollment,Paper,Version,Audit
from sqlalchemy import select

def client_policy():
    Base.metadata.create_all(engine)
    c=TestClient(app);cid='repair-'+uuid.uuid4().hex;h={'Authorization':'Bearer '+settings.admin_token}
    policy={'name':'Test only','expected_papers':['one','two'],'coordinator_email':'editor@example.test','demo_mode':True,'real_paper_mode':True,'require_ai':True,'enabled':True,'deadline_seconds':30,'reminder_seconds':[10,20],'profile':{'name':'Test contract','source':'Unit test, not Springer rules','requirements':{'max_pages':8}}}
    assert c.put('/agent/conferences/'+cid,headers=h,json=policy).status_code==200
    return c,cid,h,policy

def test_optional_csv_bulk_preserves_good_upload_and_deduplicates_without_manifest():
    c,cid,h,_=client_policy();doc=Document();doc.add_paragraph(uuid.uuid4().hex);b=io.BytesIO();doc.save(b)
    files=[('files',('good.docx',b.getvalue())),('files',('bad.exe',b'bad'))]
    result=c.post('/agent/conferences/'+cid+'/bulk',headers=h,files=files)
    assert result.status_code==200,result.text
    assert [r['status'] for r in result.json()['files']]==['Awaiting n8n intake','Rejected']
    again=c.post('/agent/conferences/'+cid+'/bulk',headers=h,files=files).json()
    assert again['files'][0]['status']=='Duplicate' and again['files'][0]['paper_key']=='one'
    csv='filename,paper_key,title,authors,metadata_verified\nsecond.docx,two,Verified title,Author,true\n'
    d=Document();d.add_paragraph(uuid.uuid4().hex);b=io.BytesIO();d.save(b)
    result=c.post('/agent/conferences/'+cid+'/bulk',headers=h,files=[('files',('second.docx',b.getvalue())),('metadata_csv',('metadata.csv',csv))])
    assert result.json()['files'][0]['paper_key']=='two'
    marker=next((settings.storage/'conferences'/cid/'inbox').glob('upload-two-*/submission.json'))
    assert json.loads(marker.read_text())['metadata_verified'] is True
    assert c.get('/agent/conferences/'+cid,headers=h).json()['papers']==[]

def test_unsupported_check_decision_requires_per_check_reason_and_is_audited():
    c,cid,h,policy=client_policy();policy['acknowledged_manual_checks']=['Publisher fonts']
    assert c.put('/agent/conferences/'+cid,headers=h,json=policy).status_code==422
    policy['check_decisions']={'Publisher fonts':'Coordinator inspected the supplied template and rendered fonts.'}
    assert c.put('/agent/conferences/'+cid,headers=h,json=policy).status_code==200
    with Session() as s:
        event=s.scalar(select(Audit).where(Audit.paper_id==cid,Audit.action=='publisher_check_decision'))
        assert event and event.details['check']=='Publisher fonts'

def test_lifecycle_retains_order_and_version_and_does_not_duplicate_phase():
    from app.lifecycle import transition
    with Session() as s:
        p=Paper(id=uuid.uuid4().hex);s.add(p);s.flush()
        cid='phase-'+uuid.uuid4().hex;c=Conference(id=cid,config={});s.add(c)
        e=Enrollment(id=uuid.uuid4().hex,conference_id=cid,paper_id=p.id,external_id='one',details={});s.add(e)
        for phase in ['Ingested','Processing','Corrections Required','Awaiting Revision']:transition(s,e,phase,1)
        transition(s,e,'Awaiting Revision',1);transition(s,e,'Revalidation',2);s.commit()
        assert len(e.details['phase_history'])==5 and e.details['lifecycle_version']==2
        assert len(list(s.scalars(select(Audit).where(Audit.paper_id==p.id))))==5

def test_setup_lists_all_required_components_and_never_calls_key_configured_connected(monkeypatch):
    from app.real_setup import setup_status,_gemini_probe
    _gemini_probe.clear();monkeypatch.setattr(settings,'ai_provider','gemini');monkeypatch.setattr(settings,'ai_api_key','unit-test-only');monkeypatch.setattr(settings,'ai_model','unit-model')
    result=setup_status()
    assert set(['postgresql','redis','fastapi','celery','n8n','mailpit','gemini','compiler','official_template'])<=set(result['dependencies'])
    assert result['dependencies']['gemini']=='Configured' and result['live_ready'] is False

def test_required_ai_failure_and_unsupported_checks_cannot_become_eligible():
    from app.agent import completed
    for ai_status in ['failed','skipped','completed']:
        c,cid,h,policy=client_policy()
        metadata={'title':'Contract fixture','authors':'Test Author','affiliation':'Test University','email':'author@example.test','abstract':'Controlled unit test abstract.','keywords':'controlled fixture'}
        with Session() as s:
            p=Paper(id=uuid.uuid4().hex,**{k:v for k,v in metadata.items() if k not in ['abstract','keywords']});s.add(p);s.flush()
            # Constructed review outputs test the decision function only, never provider success.
            v=Version(id=uuid.uuid4().hex,paper_id=p.id,number=1,filename='test.zip',path='/unit-test.zip',digest=uuid.uuid4().hex,state='Complete',result={'document':{'text':metadata['abstract']+' '+metadata['keywords'],'metadata':metadata,'rendered_pdf':'/unit-test.pdf'},'issues':[],'checks':[{'check':'AI proofreading','status':ai_status,'coverage_ratio':1 if ai_status=='completed' else 0,'provider':'gemini'},{'check':'Unverifiable figure semantics','status':'requires_review'}]});s.add(v)
            e=Enrollment(id=uuid.uuid4().hex,conference_id=cid,paper_id=p.id,external_id='one',details={'metadata_verified':True,'metadata_manifest':metadata});s.add(e);s.commit()
            completed(s,s.get(Conference,cid))
            assert e.state=='Exception' and e.details['lifecycle_state']=='Editorial Exception'
            assert p.status!='Publication Ready'
            if ai_status=='completed':assert 'Unverifiable figure semantics' in e.details['final_review_checks']
