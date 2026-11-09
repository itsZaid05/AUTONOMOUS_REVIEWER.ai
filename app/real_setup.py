"""One-time setup status and real bulk intake. Never accepts credentials in request bodies."""
import hashlib,json,os,uuid
from pathlib import Path
from fastapi import Depends,HTTPException,UploadFile,File,Form
from sqlalchemy import select
from .main import app,admin
from .db import Session,Conference,engine
from .settings import settings
from .agent import inbox,cfg
_gemini_probe={}

@app.get('/setup/status',dependencies=[Depends(admin)])
def setup_status():
    import httpx
    from sqlalchemy import text
    statuses={'fastapi':'Connected'}
    try:
        from .jobs import queue
        statuses['celery']='Connected' if queue.control.ping(timeout=2) else 'Unavailable'
    except Exception:statuses['celery']='Unavailable'
    try:
        response=httpx.get(settings.n8n_url.rstrip('/')+'/healthz/readiness',timeout=5,trust_env=False)
        response.raise_for_status();statuses['n8n']='Connected'
    except Exception:statuses['n8n']='Unavailable'
    try:
        with engine.connect() as c:c.execute(text('SELECT 1'))
        statuses['postgresql']='Connected'
    except Exception:statuses['postgresql']='Unavailable'
    try:
        from redis import Redis
        Redis.from_url(settings.redis_url).ping();statuses['redis']='Connected'
    except Exception:statuses['redis']='Unavailable'
    try:
        from urllib.parse import urlparse
        endpoint=urlparse(settings.mailpit_api_url)
        if endpoint.hostname not in ['mailpit','localhost','127.0.0.1'] or endpoint.scheme!='http' or endpoint.port!=8025:raise ValueError('Local Mailpit endpoint required')
        response=httpx.get(settings.mailpit_api_url.rstrip('/')+'/api/v1/info',timeout=5,trust_env=False);response.raise_for_status();statuses['mailpit']='Connected'
    except Exception:statuses['mailpit']='Unavailable'
    statuses['gemini']='Configured' if settings.ai_provider=='gemini' and settings.ai_api_key and settings.ai_model else 'Unavailable'
    import time
    if _gemini_probe.get('model')==settings.ai_model and time.time()-_gemini_probe.get('at',0)<600:
        statuses['gemini']=_gemini_probe['status']
    try:
        import time
        heartbeat=json.loads((settings.compile_queue/'service.json').read_text())
        statuses['compiler']='Connected' if time.time()-heartbeat['observed_at']<10 and heartbeat.get('network')=='none' and heartbeat.get('host_docker_socket') is False else 'Unavailable'
    except (OSError,ValueError,KeyError):statuses['compiler']='Unavailable'
    from .lncs import template_verified
    statuses['official_template']='Connected' if template_verified() else 'Unavailable'
    statuses['languagetool']='Configured' if settings.languagetool_url else 'Optional'
    return {'dependencies':statuses,'ai_model':settings.ai_model,'mail_mode':settings.mail_mode,'live_ready':all(statuses[k] in (['Connected'] if k=='gemini' else ['Connected','Configured']) for k in ['fastapi','postgresql','redis','celery','n8n','mailpit','gemini','compiler','official_template'])}

@app.post('/setup/verify-gemini',dependencies=[Depends(admin)])
def verify_gemini():
    if settings.ai_provider!='gemini' or not settings.ai_api_key or not settings.ai_model:raise HTTPException(409,'Configure Gemini key/model securely in environment settings')
    from .whole_review import Chunk,_call_ai
    try:
        findings,invocation=_call_ai(Chunk(0,0,56,'Connectivity verification','This is a short connectivity test, not a manuscript.'))
        import time
        _gemini_probe.update(model=settings.ai_model,status='Connected',at=time.time())
        return {'status':'Connected','invocation':invocation,'findings_count':len(findings)}
    except Exception as exc:
        import time
        _gemini_probe.update(model=settings.ai_model,status='Failed',at=time.time())
        raise HTTPException(502,{'status':'Failed','error_type':type(exc).__name__})

@app.post('/agent/conferences/{cid}/bulk',dependencies=[Depends(admin)])
async def real_bulk(cid:str,files:list[UploadFile]=File(...),manifest:str=Form(''),metadata_csv:UploadFile|None=File(None)):
    import csv,io
    from sqlalchemy import text
    from .db import Enrollment,Version
    if not files or len(files)>100:raise HTTPException(422,'Upload one to 100 sources')
    if len(manifest)>1024*1024:raise HTTPException(413,'Metadata manifest limit')
    warnings=[];rows=[]
    if manifest.strip():
        try:rows=json.loads(manifest)
        except ValueError:raise HTTPException(422,'Manifest must be JSON')
        if isinstance(rows,dict):rows=rows.get('papers')
        if not isinstance(rows,list):raise HTTPException(422,'Manifest must contain paper records')
    if metadata_csv:
        raw=await metadata_csv.read(1024*1024+1)
        try:
            if len(raw)>1024*1024:raise ValueError('CSV size limit')
            for row in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
                rows.append({'filename':row.get('filename',''),'paper_key':row.get('paper_key') or row.get('paper_id'),
                             'metadata':{k:row[k] for k in ['title','authors','affiliation','email','abstract','keywords','track'] if row.get(k)},
                             'metadata_verified':row.get('metadata_verified','').lower()=='true'})
        except (ValueError,UnicodeError,csv.Error):warnings.append('CSV could not be read; source extraction and per-paper exception handling will be used')
    entries={Path(row.get('filename') or row.get('path','')).name:row for row in rows if isinstance(row,dict)}
    buffered=[];total=0
    for upload in files:
        if total>150*1024*1024:
            buffered.append((upload.filename or '',b'',True));await upload.close();continue
        content=await upload.read(30*1024*1024+1);total+=len(content)
        buffered.append((Path((upload.filename or '').replace('\\','/')).name,content,total>150*1024*1024))
    results=[]
    with Session() as s:
        key=int(hashlib.sha256(cid.encode()).hexdigest()[:15],16)
        s.execute(text("SET LOCAL lock_timeout='20s'"));s.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':key})
        conference=s.get(Conference,cid)
        if not conference:raise HTTPException(404,'Configure the conference first')
        policy=cfg(conference);inbox(cid).mkdir(parents=True,exist_ok=True)
        mapping={};used=set()
        for e in s.scalars(select(Enrollment).where(Enrollment.conference_id==cid)):
            used.add(e.external_id)
            for v in s.scalars(select(Version).where(Version.paper_id==e.paper_id)):mapping[v.digest]=e.external_id
        for ready in inbox(cid).glob('*/submission.json'):
            try:
                previous=json.loads(ready.read_text());used.add(previous['paper_key'])
                digest=previous.get('source_sha256') or ready.parent.name.rsplit('-',1)[-1]
                if len(digest)==64:mapping[digest]=previous['paper_key']
            except (OSError,ValueError,KeyError):continue
        for name,content,over_total in buffered:
            suffix=Path(name).suffix.lower();entry=entries.get(name,{})
            if suffix not in ['.docx','.tex','.zip'] or not content or len(content)>30*1024*1024 or over_total:
                results.append({'filename':name,'status':'Rejected','reason':'Unsupported source or file/batch size limit'});continue
            digest=hashlib.sha256(content).hexdigest();paper_key=entry.get('paper_key') or mapping.get(digest)
            if paper_key is None:paper_key=next((key for key in policy.expected_papers if key not in used),None)
            if paper_key not in policy.expected_papers:
                results.append({'filename':name,'status':'Rejected','reason':'No available configured paper key'});continue
            folder=inbox(cid)/('upload-'+paper_key+'-'+digest)
            if digest in mapping and not entry.get('revision_token'):
                results.append({'filename':name,'paper_key':mapping[digest],'status':'Duplicate','sha256':digest});continue
            folder.mkdir(parents=True,exist_ok=True);(folder/name).write_bytes(content)
            record={'paper_key':paper_key,'source':name,'source_sha256':digest,'metadata':entry.get('metadata',{}),'provenance':entry.get('provenance',{}),'metadata_verified':entry.get('metadata_verified') is True}
            if entry.get('revision_token'):record['revision_token']=entry['revision_token']
            temporary=folder/'submission.tmp';temporary.write_text(json.dumps(record));temporary.replace(folder/'submission.json')
            used.add(paper_key);mapping[digest]=paper_key
            results.append({'filename':name,'paper_key':paper_key,'status':'Awaiting n8n intake','sha256':digest})
        s.commit()
    return {'conference':cid,'files':results,'metadata_warnings':warnings}

from pydantic import BaseModel,model_validator
class VerifiedMetadata(BaseModel):
    title:str
    authors:str
    affiliation:str
    email:str
    abstract:str
    keywords:str
    track:str='General'
    verified:bool
    @model_validator(mode='after')
    def complete(self):
        from .agent import email_ok
        if any(not getattr(self,k).strip() for k in ['title','authors','affiliation','abstract','keywords']) or not email_ok(self.email):raise ValueError('Complete manuscript metadata and a valid corresponding-author email are required')
        return self
@app.post('/agent/{cid}/metadata/{pid}',dependencies=[Depends(admin)])
def verify_metadata(cid:str,pid:str,body:VerifiedMetadata):
    from .db import Enrollment,Paper
    from .main import record
    if not body.verified:raise HTTPException(400,'Explicit metadata verification required')
    with Session() as s:
        e=s.scalar(select(Enrollment).where(Enrollment.conference_id==cid,Enrollment.paper_id==pid))
        if not e:raise HTTPException(404)
        p=s.get(Paper,pid,with_for_update=True)
        for key in ['title','authors','affiliation','email','track']:setattr(p,key,getattr(body,key))
        p.approved_version=None;p.status='Under Review'
        e.details={**e.details,'metadata_manifest':body.model_dump(exclude={'verified'}),'metadata_verified':True};e.handled_version=0
        record(s,pid,'metadata_verified',{'conference':cid,'version':p.latest});s.commit()
    return {'recheck':'next n8n completion schedule'}

@app.post('/papers/{pid}/metadata/verify',dependencies=[Depends(admin)])
def verify_standalone_metadata(pid:str,body:VerifiedMetadata):
    from .db import Paper,Version,Enrollment
    from .main import record
    if not body.verified:raise HTTPException(422,'Explicit metadata verification is required')
    with Session() as session:
        p=session.get(Paper,pid,with_for_update=True)
        if not p:raise HTTPException(404)
        if session.scalar(select(Enrollment).where(Enrollment.paper_id==pid)):
            raise HTTPException(409,'Use conference metadata verification for an enrolled paper')
        version=session.scalar(select(Version).where(Version.paper_id==pid,Version.number==p.latest))
        document=dict(version.result.get('document',{}))
        normalized=' '.join(document.get('text','').split()).casefold()
        if not normalized or not all(' '.join(getattr(body,k).split()).casefold() in normalized for k in ['abstract','keywords']):raise HTTPException(422,'Abstract and keywords must match the current extracted manuscript')
        for field in ['title','authors','affiliation','email','track']:setattr(p,field,getattr(body,field))
        document['verified_metadata']=body.model_dump(exclude={'verified'})
        version.result={**version.result,'document':document};p.approved_version=None;p.status='Under Review'
        record(session,pid,'metadata_verified',{'version':p.latest,'actor':'authenticated coordinator'});session.commit()
    return {'verified_version':p.latest}
