import io,json,uuid
from pathlib import Path
from fastapi.testclient import TestClient
from docx import Document
from sqlalchemy import select
from app.main import app
from app.settings import settings
from app.db import Base,engine,Session,Enrollment,Dispatch,Conference
from app.agent import inbox,ConferencePolicy

def policy():return {'name':'Test batch','expected_papers':['one'],'coordinator_email':'editor@example.test','demo_mode':True,'enabled':True,'require_ai':False,'deadline_seconds':30,'reminder_seconds':[10,20],'profile':{'name':'Test-only contract','version':'1','source':'https://example.test/test-contract','requirements':{'max_pages':8}},'acknowledged_manual_checks':[]}
def test_invalid_policy_and_durable_intake(monkeypatch):
    Base.metadata.create_all(engine);cid='test-'+uuid.uuid4().hex
    c=TestClient(app);h={'Authorization':'Bearer '+settings.admin_token}
    assert c.put('/agent/conferences/'+cid,headers=h,json={}).status_code==422
    p=policy();p['reminder_seconds']=[20,10]
    assert c.put('/agent/conferences/'+cid,headers=h,json=p).status_code==422
    assert c.put('/agent/conferences/'+cid,headers=h,json=policy()).status_code==200
    folder=inbox(cid)/'event';folder.mkdir(parents=True)
    doc=Document();doc.add_paragraph('Title: Unique '+cid);doc.add_paragraph('Authors: Test Author');doc.add_paragraph('Email: author@example.test');doc.add_paragraph('Affiliation: Test University')
    doc.save(folder/'paper.docx');(folder/'submission.json').write_text(json.dumps({'paper_key':'one','source':'paper.docx'}))
    monkeypatch.setattr('app.agent.validate.delay',lambda vid:None)
    assert c.post('/agent/'+cid+'/intake').status_code==401
    assert c.post('/agent/'+cid+'/intake',headers=h).status_code==200
    assert c.post('/agent/'+cid+'/intake',headers=h).status_code==200
    state=c.get('/agent/conferences/'+cid,headers=h).json()
    assert len(state['papers'])==1 and len(state['receipts'])==1
    assert '/papers/' in str(next((settings.storage/'papers'/state['papers'][0]['paper_id']).rglob('*.docx')))
    bad=inbox(cid)/'bad';bad.mkdir();(bad/'submission.json').write_text(json.dumps({'paper_key':'one','source':'../escape.docx'}))
    c.post('/agent/'+cid+'/intake',headers=h)
    state=c.get('/agent/conferences/'+cid,headers=h).json()
    assert any(r['state']=='Exception' for r in state['receipts'])
    assert len(state['papers'])==1

def test_notifications_require_enabled_policy_and_duplicate_mail_keys():
    from app.agent import enqueue_mail,deliver
    Base.metadata.create_all(engine)
    with Session() as s:
        cid='policy-'+uuid.uuid4().hex;conf=Conference(id=cid,config=policy(),enabled=True);s.add(conf);s.commit()
        enqueue_mail(s,conf,None,None,'publication','editor@example.test','Test','Test body')
        enqueue_mail(s,conf,None,None,'publication','editor@example.test','Test','Test body');s.commit()
        assert len(list(s.scalars(select(Dispatch).where(Dispatch.conference_id==cid))))==1
        assert deliver(s,conf)==[]
        assert s.scalar(select(Dispatch).where(Dispatch.conference_id==cid)).state=='Pending'

def test_reminders_are_durable_and_cancel_on_revision():
    from datetime import timedelta
    from app.db import Paper,Version,now
    from app.agent import reminders,deliver
    with Session() as s:
        cid='reminder-'+uuid.uuid4().hex;conf=Conference(id=cid,config=policy(),enabled=True);s.add(conf)
        p=__import__('app.db',fromlist=['Paper']).Paper(id=uuid.uuid4().hex,email='author@example.test',title='Test',authors='Test');s.add(p);s.flush()
        v=Version(id=uuid.uuid4().hex,paper_id=p.id,number=1,filename='test.docx',digest=uuid.uuid4().hex,path='/not-used');s.add(v)
        e=Enrollment(id=uuid.uuid4().hex,conference_id=cid,external_id='one',paper_id=p.id,handled_version=1,state='Awaiting Revision',deadline=now()+timedelta(seconds=15));s.add(e)
        msg=Dispatch(id=f'{cid}:{p.id}:1:correction',conference_id=cid,paper_id=p.id,version=1,kind='correction',recipient=p.email,subject='Test',body='Test',state='Sent',sent=now()-timedelta(seconds=15));s.add(msg);s.commit()
        reminders(s,conf);reminders(s,conf)
        drafts=list(s.scalars(select(Dispatch).where(Dispatch.conference_id==cid,Dispatch.kind=='reminder-10')))
        assert len(drafts)==1
        p.latest=2;s.commit()
        # Enable delivery to prove stale reminder cancellation happens before SMTP is attempted.
        conf.config={**conf.config,'notifications_enabled':True};s.commit()
        assert deliver(s,conf)==[]
        s.refresh(drafts[0]);assert drafts[0].state=='Cancelled'

def test_loose_source_detection_is_stable_and_idempotent(tmp_path,monkeypatch):
    import os,time
    from app.agent import discover_loose
    monkeypatch.setattr('app.agent.inbox',lambda cid:tmp_path)
    p=tmp_path/'one.docx';p.write_bytes(b'file snapshot')
    discover_loose('batch');assert not list(tmp_path.glob('*/submission.json'))
    os.utime(p,(time.time()-3,time.time()-3));discover_loose('batch');discover_loose('batch')
    markers=list(tmp_path.glob('*/submission.json'));assert len(markers)==1
    assert json.loads(markers[0].read_text())['paper_key']=='one'

def test_all_simultaneous_n8n_stages_get_a_turn():
    from concurrent.futures import ThreadPoolExecutor
    cid='schedule-'+uuid.uuid4().hex;c=TestClient(app);h={'Authorization':'Bearer '+settings.admin_token}
    assert c.put('/agent/conferences/'+cid,headers=h,json=policy()).status_code==200
    stages=['intake','completed','reminders','revisions','publication']
    with ThreadPoolExecutor(max_workers=5) as pool:
        responses=list(pool.map(lambda stage:c.post('/agent/'+cid+'/'+stage,headers=h),stages))
    assert all(r.status_code==200 for r in responses),[r.text for r in responses]
    assert [r.json()['stage'] for r in responses]==stages

def test_real_lncs_compilation_uses_declared_template_geometry(tmp_path):
    from app.documents import inspect_document
    from scripts.agent_samples import manuscript
    name,content=manuscript(3,True);path=tmp_path/name;path.write_bytes(content)
    doc=inspect_document(path)
    assert abs(doc['text_width_mm']-122)<.2
    assert abs(doc['text_height_mm']-193)<.2
    assert doc['unresolved_references']==[]
    assert not doc.get('latex_warnings'),doc.get('latex_warnings')
    assert Path(doc['rendered_pdf']).exists()

def test_automatic_safe_normalization_preserves_original_and_requeues(monkeypatch):
    import hashlib
    from app.main import register
    from app.processing import process
    from app.agent import completed
    from app.db import Paper,Version
    monkeypatch.setattr('app.main.validate.delay',lambda vid:None)
    doc=Document();doc.add_paragraph('Unique '+uuid.uuid4().hex);doc.add_paragraph('Abstract');doc.add_paragraph('Measured 10\u00a0kg with unchanged scientific results.');doc.add_paragraph('Keywords: test');doc.add_paragraph('References')
    content=io.BytesIO();doc.save(content);original=content.getvalue()
    submitted=register(original,'source.docx',{'title':'Safe correction','authors':'Test Author','email':'author@example.test','affiliation':'University','profile':'lncs'},enqueue=False)
    with Session() as s:
        conf=Conference(id='safe-'+uuid.uuid4().hex,config=policy(),enabled=True);s.add(conf);s.add(Enrollment(id=uuid.uuid4().hex,conference_id=conf.id,external_id='one',paper_id=submitted['paper_id']));s.commit()
        assert process(submitted['version_id'])['state']=='Complete'
        completed(s,conf)
        p=s.get(Paper,submitted['paper_id'],populate_existing=True);assert p.latest==2
        versions=list(s.scalars(select(Version).where(Version.paper_id==p.id).order_by(Version.number)))
        assert Path(versions[0].path).read_bytes()==original
        revised=Document(versions[1].path)
        assert any('10 kg' in para.text for para in revised.paragraphs)
        assert versions[1].state=='Queued'

def test_portal_revision_stops_reminders_and_defers_validation_to_n8n(monkeypatch):
    from app.main import register
    from app.editorial import serializer
    from app.db import Paper,now
    from datetime import timedelta
    called=[];monkeypatch.setattr('app.main.validate.delay',lambda vid:called.append(vid))
    doc=Document();doc.add_paragraph(uuid.uuid4().hex);content=io.BytesIO();doc.save(content)
    r=register(content.getvalue(),'first.docx',{'title':'Portal','authors':'Author','email':'author@example.test'},enqueue=False)
    cid='portal-'+uuid.uuid4().hex
    with Session() as s:
        s.add(Conference(id=cid,config=policy(),enabled=True));s.add(Enrollment(id=uuid.uuid4().hex,conference_id=cid,external_id='one',paper_id=r['paper_id'],handled_version=1,state='Awaiting Revision',deadline=now()+timedelta(seconds=30)));s.commit()
    doc.add_paragraph('A genuinely revised file');content=io.BytesIO();doc.save(content)
    token=serializer.dumps({'paper':r['paper_id'],'scope':'revision'})
    response=TestClient(app).post('/revise/'+token,files={'file':('revision.docx',content.getvalue())})
    assert response.status_code==200,response.text
    assert called==[]
    with Session() as s:
        e=s.scalar(select(Enrollment).where(Enrollment.conference_id==cid));assert e.deadline is None and e.state=='Revision Received'

def test_shared_smtp_transport_reaches_local_mailpit():
    import httpx,pytest
    from email.message import EmailMessage
    from app.mail import send_smtp
    if settings.smtp_host not in ['127.0.0.1','localhost','mailpit']:pytest.skip('Controlled local SMTP only')
    marker='transport-'+uuid.uuid4().hex
    mail=EmailMessage();mail['From']='test@example.test';mail['To']='controlled-inbox@example.test';mail['Subject']=marker;mail['Message-ID']='<'+marker+'@paperflow.test>';mail.set_content('A real local SMTP transport verification.')
    send_smtp(mail)
    response=httpx.get(settings.mailpit_api_url.rstrip('/')+'/api/v1/messages',trust_env=False);response.raise_for_status()
    assert any(m['Subject']==marker for m in response.json()['messages'])
