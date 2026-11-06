from pydantic import BaseModel,Field
from fastapi import Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .main import app,admin
from .db import Session,Event,Version
from .jobs import validate
from .editorial import prepare_message,send_message,due
from .publication import publish,PublicationRequest
class AutomationEvent(BaseModel):
    event_id:str=Field(min_length=8,max_length=200,pattern=r'^[A-Za-z0-9._:-]+$')
    paper_id:str|None=None
    message_id:str|None=None
    version_ids:list[str]=Field(default_factory=list,max_length=100)
    publication:PublicationRequest|None=None
@app.post('/automation/{kind}',dependencies=[Depends(admin)])
def automation(kind:str,body:AutomationEvent):
    if kind not in ['intake','complete','communicate','reminders','publication']:raise HTTPException(404)
    if kind=='intake' and not body.version_ids:raise HTTPException(422,'version_ids required')
    if kind=='complete' and not body.paper_id:raise HTTPException(422,'paper_id required')
    if kind=='communicate' and not body.message_id:raise HTTPException(422,'message_id required')
    if kind=='publication' and not body.publication:raise HTTPException(422,'publication required')
    key=kind+':'+body.event_id
    with Session() as s:
        e=Event(id=key)
        s.add(e)
        try:s.commit()
        except IntegrityError:
            s.rollback();e=s.get(Event,key)
            return {'duplicate':True,'state':e.state,'result':e.result}
        try:
            if kind=='intake':
                versions=[s.get(Version,vid) for vid in body.version_ids]
                if any(v is None for v in versions):raise HTTPException(404,'Unknown version ID')
                for v in versions:
                    if v.state not in ['Complete','Processing']:validate.delay(v.id)
                result={'queued':body.version_ids}
            elif kind=='complete':result=prepare_message(body.paper_id)
            elif kind=='communicate':result=send_message(body.message_id)
            elif kind=='reminders':result={'due':due(),'approval_required':True}
            else:result=publish(body.publication)
            e.state='Complete';e.result=result;s.commit();return {'duplicate':False,'state':e.state,'result':result}
        except Exception:
            e.state='Failed or uncertain';s.commit();raise
