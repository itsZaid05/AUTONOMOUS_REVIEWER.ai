import io,uuid
from docx import Document
from fastapi.testclient import TestClient
from app.main import app
from app.settings import settings
from app.db import Base,engine

def test_upload_queue_and_permissions(monkeypatch):
    Base.metadata.create_all(engine)
    monkeypatch.setattr('app.main.validate.delay',lambda vid:None)
    c=TestClient(app); h={'Authorization':'Bearer '+settings.admin_token}
    assert c.get('/papers').status_code==401
    doc=Document();doc.add_paragraph('Test submission phase 1 '+uuid.uuid4().hex)
    b=io.BytesIO();doc.save(b)
    r=c.post('/submissions',headers=h,files={'file':('test.docx',b.getvalue())})
    assert r.status_code==200,r.text
    pid=r.json()['paper_id']
    assert c.get('/papers/'+pid,headers=h).json()['versions'][0]['state']=='Queued'
    assert c.post('/submissions',headers=h,files={'file':('test.docx',b.getvalue())}).status_code==409
    assert c.post('/submissions',headers=h,files={'file':('bad.exe',b'x')}).status_code==400
