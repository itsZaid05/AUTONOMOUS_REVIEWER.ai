import io,uuid
from docx import Document
from fastapi.testclient import TestClient
from app.main import app
from app.settings import settings
from app.processing import process
from app.db import Session,Paper,Version
from sqlalchemy import select

def test_report_approval_revision_and_publication(monkeypatch):
    monkeypatch.setattr('app.main.validate.delay',lambda vid:None)
    c=TestClient(app);h={'Authorization':'Bearer '+settings.admin_token}
    d=Document();d.add_heading('Integration manuscript '+uuid.uuid4().hex,0);d.add_paragraph('Abstract');d.add_paragraph('The the experiment tests reporting.');d.add_paragraph('Keywords: workflow');d.add_heading('References',1)
    b=io.BytesIO();d.save(b)
    r=c.post('/submissions',headers=h,files={'file':('integration.docx',b.getvalue())},data={'title':'Integration paper','authors':'Test Author','email':'author@example.test'})
    assert r.status_code==200,r.text
    p=r.json();pid=p['paper_id'];vid=p['version_id'];assert process(vid)['state']=='Complete'
    assert c.get('/versions/'+vid+'/report',headers=h).content.startswith(b'%PDF')
    assert c.post('/papers/'+pid+'/approve',headers=h,json={}).status_code==400
    assert c.post('/papers/'+pid+'/approve',headers=h,json={'acknowledge_review':True}).status_code==200
    pub=c.post('/publications',headers=h,json={'conference':'Test Conference','paper_ids':[pid],'confirm_editorial_approval':True})
    assert pub.status_code==200,pub.text
    assert c.get('/publications/'+pub.json()['publication_id']+'/book-of-abstracts.pdf',headers=h).content.startswith(b'%PDF')
    link=c.post('/papers/'+pid+'/revision-link',headers=h).json()['url'];token=link.rsplit('/',1)[1]
    assert c.post('/revise/invalid',files={'file':('rev.docx',b.getvalue())}).status_code==403
    d.add_paragraph('Revised version');b=io.BytesIO();d.save(b)
    r=c.post('/revise/'+token,files={'file':('rev.docx',b.getvalue())})
    assert r.status_code==200
    assert c.get('/papers/'+pid,headers=h).json()['paper']['approved_version'] is None
    assert c.post('/publications',headers=h,json={'conference':'Test','paper_ids':[pid],'confirm_editorial_approval':True}).status_code==409
