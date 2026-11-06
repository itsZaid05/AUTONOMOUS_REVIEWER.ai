import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.settings import settings
from app.db import Base,engine

def test_automation_invalid_valid_duplicate():
    Base.metadata.create_all(engine)
    c=TestClient(app);h={'Authorization':'Bearer '+settings.admin_token}
    assert c.post('/automation/intake',headers=h,json={'event_id':'valid-id'}).status_code==422
    e={'event_id':uuid.uuid4().hex}
    r=c.post('/automation/reminders',headers=h,json=e)
    assert r.status_code==200 and r.json()['duplicate'] is False
    assert c.post('/automation/reminders',headers=h,json=e).json()['duplicate'] is True
