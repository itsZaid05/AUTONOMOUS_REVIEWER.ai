import json,uuid,smtplib
from pathlib import Path
from email.message import EmailMessage
from pydantic import BaseModel,Field
from fastapi import Depends,HTTPException,UploadFile,File
from fastapi.responses import FileResponse,HTMLResponse
from itsdangerous import URLSafeTimedSerializer,BadSignature,SignatureExpired
from sqlalchemy import select
from .settings import settings
from .db import Session,Paper,Version,Audit,Message,now
from .main import app,admin,record,register
from .reports import report
from .mail import send_smtp
serializer=URLSafeTimedSerializer(settings.signing_key,salt='paperflow-revision')
class Approval(BaseModel):
    acknowledge_review:bool=False
class ProfileConfig(BaseModel):
    name:str
    version:str
    source:str
    requirements:dict[str,float|int|str]=Field(default_factory=dict)
    note:str=''
@app.get('/profiles',dependencies=[Depends(admin)])
def profiles():
    from .review import profile_path
    return {p:json.loads(profile_path(p).read_text()) for p in ['ieee','lncs','ccis']}
@app.put('/profiles/{name}',dependencies=[Depends(admin)])
def save_profile(name:str,body:ProfileConfig):
    if name not in {'ieee','lncs','ccis'}:raise HTTPException(404)
    allowed={'width_mm','height_mm','max_pages','tolerance_mm','top_mm','bottom_mm','left_mm','right_mm','columns'}
    if set(body.requirements)-allowed:raise HTTPException(400,'Unsupported numeric rule. Unsupported checks require human review.')
    if any(not isinstance(v,(int,float)) or v<=0 or v>10000 for v in body.requirements.values()):raise HTTPException(400,'Rules must be positive bounded numbers')
    from .review import profile_path
    old=json.loads(profile_path(name).read_text())
    if old['version']==body.version:raise HTTPException(409,'Use a new profile version')
    root=settings.storage/'profiles';root.mkdir(exist_ok=True)
    archive=root/(name+'-'+uuid.uuid4().hex+'.json');archive.write_text(json.dumps(old,indent=2))
    (root/(name+'.json')).write_text(body.model_dump_json(indent=2))
    with Session() as s:record(s,'profiles','profile_updated',{'profile':name,'version':body.version,'source':body.source});s.commit()
    return {'saved':name,'version':body.version}
@app.get('/versions/{vid}/report',dependencies=[Depends(admin)])
def get_report(vid:str,format:str='pdf'):
    with Session() as s:
        v=s.get(Version,vid)
        if not v or v.state!='Complete':raise HTTPException(409,'Completed validation required')
        p=s.get(Paper,v.paper_id);html,pdf=report(p,v)
        return FileResponse(pdf if format=='pdf' else html,filename='correction-report.'+('pdf' if format=='pdf' else 'html'))
@app.get('/versions/{vid}/preview',dependencies=[Depends(admin)])
def preview(vid:str):
    with Session() as s:
        v=s.get(Version,vid)
        path=(v.result or {}).get('document',{}).get('rendered_pdf') if v else None
        if not path or not Path(path).exists():raise HTTPException(409,'No rendered PDF available')
        return FileResponse(path,media_type='application/pdf',filename='manuscript.pdf')
@app.post('/papers/{pid}/approve',dependencies=[Depends(admin)])
def approve(pid:str,body:Approval):
    with Session() as s:
        p=s.get(Paper,pid,with_for_update=True)
        if not p:raise HTTPException(404)
        v=s.scalar(select(Version).where(Version.paper_id==pid,Version.number==p.latest))
        if not v or v.state!='Complete' or not v.result.get('document',{}).get('rendered_pdf'):raise HTTPException(409,'Successful validation and rendering required')
        if not body.acknowledge_review:raise HTTPException(400,'Editor must acknowledge all unresolved findings and skipped checks')
        p.approved_version=v.number;p.status='Approved';record(s,pid,'editor_approved',{'version':v.number,'acknowledged_findings':len(v.result.get('issues',[]))});s.commit()
        return {'approved_version':v.number}
@app.post('/papers/{pid}/revision-link',dependencies=[Depends(admin)])
def revision_link(pid:str):
    with Session() as s:
        if not s.get(Paper,pid):raise HTTPException(404)
    token=serializer.dumps({'paper':pid,'scope':'revision'})
    return {'url':settings.public_url+'/revise/'+token,'expires_in_days':14}
@app.get('/revise/{token}',response_class=HTMLResponse)
def revision_form(token:str):
    verify(token)
    return '<h1>Submit revised manuscript</h1><form method="post" enctype="multipart/form-data"><input type="file" name="file" accept=".docx,.pdf,.tex,.zip" required><button>Submit revision</button></form>'
def verify(token):
    try:
        payload=serializer.loads(token,max_age=14*86400)
        if payload.get('scope')!='revision':raise BadSignature('scope')
        return payload['paper']
    except (BadSignature,SignatureExpired,KeyError):raise HTTPException(403,'Invalid or expired revision link')
@app.post('/revise/{token}')
async def revision(token:str,file:UploadFile=File(...)):
    pid=verify(token)
    return register(await file.read(30*1024*1024+1),file.filename or '',{},pid)
@app.post('/papers/{pid}/correction',dependencies=[Depends(admin)])
def correction(pid:str):
    from docx import Document
    with Session() as s:
        p=s.get(Paper,pid)
        if not p:raise HTTPException(404)
        v=s.scalar(select(Version).where(Version.paper_id==pid,Version.number==p.latest))
        if Path(v.path).suffix!='.docx':raise HTTPException(400,'Safe corrections currently support DOCX only')
        d=Document(v.path);changes=[]
        for pi,para in enumerate(d.paragraphs):
            for ri,run in enumerate(para.runs):
                before=run.text;after=before.replace('\u00a0',' ')
                if before!=after:run.text=after;changes.append({'paragraph':pi+1,'run':ri+1,'before':before,'after':after})
        if not changes:return {'changed':False,'reason':'No supported nonbreaking-space normalization found'}
        import io
        out=io.BytesIO();d.save(out)
        # Assert no change beyond the declared whitespace normalization.
        verifydoc=Document(io.BytesIO(out.getvalue()))
        assert [p.text for p in verifydoc.paragraphs]==[p.text for p in d.paragraphs]
        result=register(out.getvalue(),'corrected.docx',{},pid)
        record(s,pid,'safe_correction',{'changes':changes,'version':result['version'],'verification':'round-trip text verified; full revalidation queued; no compliance fix claimed'});s.commit()
        return {**result,'changed':True,'changes':changes}
@app.post('/papers/{pid}/messages',dependencies=[Depends(admin)])
def prepare_message(pid:str):
    with Session() as s:
        p=s.get(Paper,pid)
        if not p:raise HTTPException(404)
        if not p.email or '\n' in p.email or '\r' in p.email:raise HTTPException(400,'Valid author email required')
        v=s.scalar(select(Version).where(Version.paper_id==pid,Version.number==p.latest))
        if v.state!='Complete':raise HTTPException(409,'Validation incomplete')
        existing=s.scalar(select(Message).where(Message.paper_id==pid,Message.version==p.latest))
        if existing:return {'message_id':existing.id,'state':existing.state}
        link=revision_link(pid)['url']
        report(p,v)
        msg=Message(id=uuid.uuid4().hex,paper_id=pid,version=p.latest,subject='Revision requested: '+(p.title or p.id),body=f'Dear author,\n\nPlease review the attached correction report for manuscript {p.id}, version {p.latest}. Findings require author and editor judgment.\n\nSubmit a revision within 14 days using this secure link:\n{link}\n\nKind regards,\nConference Editorial Team')
        s.add(msg);record(s,pid,'email_prepared',{'message_id':msg.id});s.commit();return {'message_id':msg.id,'state':msg.state}
@app.get('/messages',dependencies=[Depends(admin)])
def messages():
    with Session() as s:return [{'id':m.id,'paper_id':m.paper_id,'version':m.version,'state':m.state,'subject':m.subject,'body':m.body,'error':m.error} for m in s.scalars(select(Message))]
@app.post('/messages/{mid}/approve',dependencies=[Depends(admin)])
def approve_message(mid:str):
    with Session() as s:
        m=s.get(Message,mid,with_for_update=True)
        if not m:raise HTTPException(404)
        if m.state not in ['Pending approval','Approved']:raise HTTPException(409,'Message already sent or delivery uncertain')
        p=s.get(Paper,m.paper_id)
        if p.latest!=m.version:raise HTTPException(409,'Message refers to an obsolete version')
        m.approved=True;m.state='Approved';record(s,m.paper_id,'email_approved',{'message_id':mid});s.commit()
    return {'approved':mid}
@app.post('/messages/{mid}/send',dependencies=[Depends(admin)])
def send_message(mid:str):
    with Session() as s:
        m=s.get(Message,mid,with_for_update=True)
        if not m:raise HTTPException(404)
        if m.state=='Sent':return {'state':'Sent','duplicate':True}
        if not m.approved or m.state!='Approved':raise HTTPException(409,'Explicit approval required, or prior delivery is uncertain')
        p=s.get(Paper,m.paper_id)
        if p.latest!=m.version:raise HTTPException(409,'Obsolete version')
        v=s.scalar(select(Version).where(Version.paper_id==p.id,Version.number==m.version))
        _,pdf=report(p,v)
        mail=EmailMessage();mail['From']=settings.mail_from;mail['To']=p.email;mail['Subject']=m.subject;mail['Message-ID']=f'<{mid}@paperflow.local>';mail.set_content(m.body)
        mail.add_attachment(pdf.read_bytes(),maintype='application',subtype='pdf',filename='correction-report.pdf')
        m.state='Sending';s.commit()
        try:
            send_smtp(mail)
            m.state='Sent';m.sent=now();record(s,p.id,'email_sent',{'message_id':mid});s.commit()
        except Exception as e:
            m.state='Delivery uncertain';m.error=type(e).__name__;s.commit();raise HTTPException(502,'Delivery uncertain; inspect SMTP before retrying to avoid duplicates')
        return {'state':m.state}
@app.get('/reminders/due',dependencies=[Depends(admin)])
def due():
    from datetime import timedelta
    with Session() as s:
        return [{'paper_id':m.paper_id,'message_id':m.id,'action':'escalate','reason':'Revision overdue; editor approval required for further contact'} for m in s.scalars(select(Message).where(Message.state=='Sent',Message.sent<now()-timedelta(days=14))) if s.get(Paper,m.paper_id).status=='Needs Correction']
@app.post('/profiles/{name}/template',dependencies=[Depends(admin)])
async def template(name:str,file:UploadFile=File(...)):
    if name not in {'ieee','lncs','ccis'}:raise HTTPException(404)
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in ['.docx','.pdf','.tex','.zip']:raise HTTPException(400,'Unsupported template')
    data=await file.read(30*1024*1024+1)
    if len(data)>30*1024*1024:raise HTTPException(413)
    target=settings.storage/'templates';target.mkdir(exist_ok=True)
    fid=uuid.uuid4().hex;path=target/(name+'-'+fid+suffix);path.write_bytes(data)
    with Session() as s:record(s,'profiles','official_template_uploaded',{'profile':name,'template':fid,'original_name':Path(file.filename).name,'note':'Editor must configure numeric rules; template is preserved as evidence, not automatically authoritative.'});s.commit()
    return {'template_id':fid,'note':'Template retained. Configure verified numeric requirements in the profile.'}
