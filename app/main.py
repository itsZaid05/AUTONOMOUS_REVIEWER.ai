import hashlib,uuid,secrets
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI,Depends,Header,HTTPException,UploadFile,File,Form
from fastapi.responses import FileResponse
from sqlalchemy import select,text
from .settings import settings
from .db import Base,engine,Session,Paper,Version,Audit
from .jobs import validate
@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    yield
app=FastAPI(title='PaperFlow AI',lifespan=lifespan)
def admin(authorization: str=Header(default='')):
    if not secrets.compare_digest(authorization.encode(),('Bearer '+settings.admin_token).encode()): raise HTTPException(401,'Administrator token required')
def record(s,pid,action,details=None): s.add(Audit(paper_id=pid,action=action,details=details or {}))
@app.get('/health')
def health():
    with engine.connect() as c:
        from sqlalchemy import text
        c.execute(text('SELECT 1'))
    return {'status':'ok'}
@app.get('/papers',dependencies=[Depends(admin)])
def papers():
    with Session() as s: return [dict(id=p.id,title=p.title,authors=p.authors,email=p.email,track=p.track,profile=p.profile,status=p.status,latest=p.latest,approved_version=p.approved_version) for p in s.scalars(select(Paper).order_by(Paper.created.desc()))]
def register(content,filename,metadata,paper_id=None):
    suffix=Path(filename).suffix.lower()
    if suffix not in {'.docx','.pdf','.tex','.zip'}: raise HTTPException(400,'Supported formats: DOCX, PDF, TEX, ZIP')
    if not content or len(content)>30*1024*1024: raise HTTPException(413,'File must contain 1 byte to 30 MiB')
    digest=hashlib.sha256(content).hexdigest()
    with Session() as s:
        s.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':int(digest[:15],16)})
        if paper_id:
            p=s.get(Paper,paper_id,with_for_update=True)
            if not p: raise HTTPException(404,'Paper not found')
            if s.scalar(select(Version).where(Version.paper_id==paper_id,Version.digest==digest)): raise HTTPException(409,'Identical version already exists')
            p.latest+=1;p.approved_version=None;p.status='Resubmitted'
        else:
            duplicate=s.scalar(select(Version).where(Version.digest==digest))
            if duplicate: raise HTTPException(409,{'duplicate_of':duplicate.paper_id})
            p=Paper(id=uuid.uuid4().hex,**metadata);s.add(p);s.flush()
        vid=uuid.uuid4().hex
        path=settings.storage/(vid+suffix)
        path.write_bytes(content)
        v=Version(id=vid,paper_id=p.id,number=p.latest,filename=Path(filename).name,digest=digest,path=str(path.resolve()))
        s.add(v);record(s,p.id,'submission',{'version':p.latest,'sha256':digest});s.commit()
        try: validate.delay(vid)
        except Exception:
            v.state='Queue failed';v.error='Broker unavailable; use retry';s.commit()
        return {'paper_id':p.id,'version_id':vid,'version':p.latest,'state':v.state}
@app.post('/submissions',dependencies=[Depends(admin)])
async def upload(file: UploadFile=File(...),title: str=Form(''),authors: str=Form(''),email: str=Form(''),track: str=Form('General'),profile: str=Form('ieee'),affiliation: str=Form('')):
    if profile not in {'ieee','lncs','ccis'}: raise HTTPException(400,'Unknown profile')
    return register(await file.read(30*1024*1024+1),file.filename or '',dict(title=title,authors=authors,email=email,track=track,profile=profile,affiliation=affiliation))
@app.get('/papers/{pid}',dependencies=[Depends(admin)])
def detail(pid: str):
    with Session() as s:
        p=s.get(Paper,pid)
        if not p: raise HTTPException(404,'Paper not found')
        return {'paper':{k:getattr(p,k) for k in ['id','title','authors','email','affiliation','track','status','latest','approved_version','profile']},'versions':[{'id':v.id,'number':v.number,'filename':v.filename,'state':v.state,'result':v.result,'error':v.error} for v in s.scalars(select(Version).where(Version.paper_id==pid).order_by(Version.number))],'audit':[{'action':a.action,'details':a.details,'created':a.created} for a in s.scalars(select(Audit).where(Audit.paper_id==pid))]}
@app.post('/versions/{vid}/retry',dependencies=[Depends(admin)])
def retry(vid: str):
    with Session() as s:
        v=s.get(Version,vid)
        if not v: raise HTTPException(404)
        if v.state=='Processing': raise HTTPException(409,'Already processing')
        v.state='Queued';v.error='';s.commit()
    validate.delay(vid)
    return {'queued':vid}
@app.get('/versions/{vid}/download',dependencies=[Depends(admin)])
def download(vid: str):
    with Session() as s:
        v=s.get(Version,vid)
        if not v: raise HTTPException(404)
        return FileResponse(v.path,filename=v.filename)
from . import editorial
from . import publication
from . import automation
