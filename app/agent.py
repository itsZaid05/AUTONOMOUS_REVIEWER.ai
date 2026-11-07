"""Durable conference lifecycle. Called by five n8n scheduled workflows, never by a UI timer."""
import hashlib,io,json,re,shutil,smtplib,uuid,zipfile,time
from pathlib import Path
from datetime import timedelta
from email.message import EmailMessage
from pydantic import BaseModel,Field,model_validator
from fastapi import Depends,HTTPException
from sqlalchemy import select,text
from .main import app,admin,register,record
from .db import Session,Conference,Enrollment,Receipt,Dispatch,Paper,Version,now
from .settings import settings
from .jobs import validate
from .editorial import serializer,verify
from .reports import report
from .mail import send_smtp

class ConferencePolicy(BaseModel):
    name:str
    expected_papers:list[str]=Field(min_length=1,max_length=100)
    coordinator_email:str
    notifications_enabled:bool=False
    publication_authorized:bool=False
    enabled:bool=False
    demo_mode:bool=False
    deadline_seconds:int=Field(default=7*86400,ge=10)
    reminder_seconds:list[int]=Field(default_factory=lambda:[2*86400,5*86400])
    max_versions:int=Field(default=4,ge=1,le=20)
    profile:dict
    require_ai:bool=True
    normalize_nonbreaking_spaces:bool=True
    acknowledged_manual_checks:list[str]=Field(default_factory=list)
    @model_validator(mode='after')
    def valid(self):
        if len(set(self.expected_papers))!=len(self.expected_papers):raise ValueError('Duplicate paper keys')
        if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,60}',x) for x in self.expected_papers):raise ValueError('Unsafe paper key')
        if not email_ok(self.coordinator_email):raise ValueError('Invalid coordinator email')
        if self.reminder_seconds!=sorted(set(self.reminder_seconds)) or any(x<=0 or x>=self.deadline_seconds for x in self.reminder_seconds):raise ValueError('Reminders must be unique increasing offsets before deadline')
        if not self.demo_mode and (self.deadline_seconds<86400 or any(x<86400 for x in self.reminder_seconds)):raise ValueError('Accelerated clock is demo only')
        if not self.profile.get('source') or not self.profile.get('requirements'):raise ValueError('A source-attributed profile with requirements is required')
        return self

def email_ok(value):return bool(re.fullmatch(r'[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+',value or ''))
def inbox(cid):return settings.storage/'conferences'/cid/'inbox'
def cfg(c):return ConferencePolicy.model_validate(c.config)
def latest(s,p):return s.scalar(select(Version).where(Version.paper_id==p.id,Version.number==p.latest))
def issue(pid,category,problem,expected,evidence,location='document',severity='error',correction=''):
    return dict(paper_id=pid,category=category,severity=severity,location=location,observed_problem=problem,expected_requirement=expected,evidence=str(evidence)[:2000],suggested_correction=correction or 'Correct the reported property and submit a revision.',confidence=1,fingerprint=hashlib.sha256((category+'|'+problem+'|'+location).encode()).hexdigest()[:16])

@app.put('/agent/conferences/{cid}',dependencies=[Depends(admin)])
def configure(cid:str,body:ConferencePolicy):
    if not re.fullmatch('[a-zA-Z0-9_-]{1,60}',cid):raise HTTPException(400,'Unsafe conference ID')
    # Production requires a locally retained official template, not merely a URL string.
    if not body.demo_mode and not (settings.storage/'conference-template.docx').exists() and not (settings.storage/'conference-template.zip').exists():
        raise HTTPException(409,'Retain the verified official template as data/conference-template.docx or .zip before production enablement')
    with Session() as s:
        c=s.get(Conference,cid)
        if c and s.scalar(select(Enrollment).where(Enrollment.conference_id==cid)):
            old=cfg(c)
            if old.profile!=body.profile or old.expected_papers!=body.expected_papers:raise HTTPException(409,'Freeze template and batch membership after first intake; create a new batch for changed rules')
        if not c:c=Conference(id=cid);s.add(c)
        c.config=body.model_dump();c.enabled=body.enabled;s.commit()
    inbox(cid).mkdir(parents=True,exist_ok=True)
    return {'conference_id':cid,'enabled':body.enabled,'source_folder':str(inbox(cid).resolve())}

@app.get('/agent/conferences/{cid}',dependencies=[Depends(admin)])
def status(cid:str):
    with Session() as s:
        c=s.get(Conference,cid)
        if not c:raise HTTPException(404)
        entries=[]
        for e in s.scalars(select(Enrollment).where(Enrollment.conference_id==cid).order_by(Enrollment.external_id)):
            p=s.get(Paper,e.paper_id);v=latest(s,p)
            sent=[{'id':m.id,'kind':m.kind,'state':m.state,'recipient':m.recipient,'created':m.created,'sent':m.sent,'error':m.error} for m in s.scalars(select(Dispatch).where(Dispatch.paper_id==p.id).order_by(Dispatch.created))]
            next_reminder=None
            correction=next((m for m in sent if m['kind']=='correction' and m['state']=='Sent' and f':{p.latest}:' in m['id']),None)
            if correction and e.state=='Awaiting Revision' and p.latest==e.handled_version:
                remaining=[offset for offset in cfg(c).reminder_seconds if not any(m['kind']=='reminder-'+str(offset) and m['state'] in ['Sent','Sending','Delivery uncertain'] for m in sent)]
                if remaining:next_reminder=correction['sent']+timedelta(seconds=min(remaining))
            entries.append({'next_reminder':next_reminder,'external_id':e.external_id,'paper_id':p.id,'title':p.title,'state':e.state,'version':p.latest,'validation':v.state,'version_id':v.id,'issues':v.result.get('issues',[]),'comparison':v.result.get('comparison',{}),'deadline':e.deadline,'details':e.details,'messages':sent})
        return {'id':cid,'enabled':c.enabled,'policy':c.config,'exception':c.exception,'publication':c.publication,'papers':entries,'receipts':[{'id':r.id,'state':r.state,'details':r.details} for r in s.scalars(select(Receipt).where(Receipt.conference_id==cid))]}

def metadata_from_source(path):
    """Conservative extraction. Labelled fields or title/author paragraph styles; never guess author order."""
    from docx import Document
    result={}
    try:
        if path.suffix.lower()=='.docx':
            d=Document(path);txt='\n'.join(p.text for p in d.paragraphs)
            titles=[p.text for p in d.paragraphs if p.style.name=='Title' and p.text.strip()]
            if len(titles)==1:result['title']=titles[0]
        elif path.suffix.lower()=='.tex':txt=path.read_text(errors='replace')
        else:
            from .documents import safe_zip
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                safe_zip(path,Path(td));txt='\n'.join(p.read_text(errors='replace') for p in Path(td).rglob('*.tex'))
            for key,command in [('title','title'),('authors','author'),('affiliation','institute')]:
                values=re.findall(r'\\'+command+r'\{([^{}]+)\}',txt)
                if len(values)==1:result[key]=values[0]
        for key,label in [('title','Title'),('authors','Authors'),('affiliation','Affiliation'),('email','Email')]:
            values=re.findall(r'^'+label+r':\s*(.+)$',txt,re.M|re.I)
            if len(values)==1:result[key]=values[0].strip()
        emails=set(re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',txt))
        if 'email' not in result and len(emails)==1:result['email']=emails.pop()
    except Exception:pass
    return result

def discover_loose(cid):
    # Loose files are accepted only after a stability interval. Copy into an immutable ready bundle.
    for source in sorted(inbox(cid).iterdir()):
        if source.is_symlink() or not source.is_file() or source.suffix.lower() not in ['.docx','.tex','.zip']:continue
        info=source.stat()
        if info.st_size>30*1024*1024 or time.time()-info.st_mtime<2:continue
        content=source.read_bytes()
        if source.stat().st_mtime_ns!=info.st_mtime_ns or len(content)!=info.st_size:continue
        digest=hashlib.sha256(content).hexdigest()
        bundle=inbox(cid)/('detected-'+digest)
        if (bundle/'submission.json').exists():continue
        bundle.mkdir(exist_ok=True);(bundle/source.name).write_bytes(content)
        temporary=bundle/'submission.tmp';temporary.write_text(json.dumps({'paper_key':source.stem,'source':source.name}));temporary.replace(bundle/'submission.json')

def ingest(s,c,revisions=False):
    conf=cfg(c);out=[]
    if not revisions:discover_loose(c.id)
    for manifest in sorted(inbox(c.id).glob('*/submission.json')):
        if manifest.is_symlink() or manifest.parent.is_symlink():continue
        if manifest.stat().st_size>65536:continue
        raw=manifest.read_bytes();rid=hashlib.sha256((c.id+str(manifest.relative_to(inbox(c.id)))+hashlib.sha256(raw).hexdigest()).encode()).hexdigest()
        if s.get(Receipt,rid):continue
        try:
            m=json.loads(raw);is_revision=bool(m.get('revision_token'))
            if revisions!=is_revision:continue
            external=m['paper_key']
            if external not in conf.expected_papers:raise ValueError('Paper key is outside the configured batch')
            name=m['source']
            if Path(name).name!=name:raise ValueError('Source must be a filename inside its submission folder')
            source=manifest.parent/name
            if source.is_symlink() or not source.is_file() or source.stat().st_size>30*1024*1024:raise ValueError('Missing or oversized source')
            if source.suffix.lower() not in ['.docx','.tex','.zip']:raise ValueError('DOCX or LaTeX source required; PDF is an accompanying asset')
            e=s.scalar(select(Enrollment).where(Enrollment.conference_id==c.id,Enrollment.external_id==external))
            pid=None
            if revisions:
                pid=verify(m['revision_token'])
                if not e or e.paper_id!=pid:raise ValueError('Revision token does not match this conference paper')
            elif e:raise ValueError('Existing paper requires a secure revision token')
            extracted=metadata_from_source(source);provided=m.get('metadata',{})
            conflicts={k:[extracted[k],provided[k]] for k in extracted if provided.get(k) and extracted[k].strip()!=str(provided[k]).strip()}
            metadata={**extracted,**{k:v for k,v in provided.items() if k in ['title','authors','affiliation','email','track']}}
            metadata['profile']='lncs'
            try:r=register(source.read_bytes(),name,metadata,pid,enqueue=False)
            except HTTPException as exc:
                if exc.status_code==409:
                    s.add(Receipt(id=rid,conference_id=c.id,state='Duplicate',details={'paper_key':external,'reason':str(exc.detail)}));s.commit();continue
                raise
            if not e:
                e=Enrollment(id=uuid.uuid4().hex,conference_id=c.id,external_id=external,paper_id=r['paper_id']);s.add(e)
            else:
                p=s.get(Paper,pid,populate_existing=True)
                for k,vv in metadata.items():setattr(p,k,vv)
            e.state='Queued';e.deadline=None;e.details={'metadata_conflicts':conflicts,'source_manifest':str(manifest.relative_to(inbox(c.id)))}
            for companion in manifest.parent.glob('*.pdf'):
                if companion.is_symlink() or companion.stat().st_size>30*1024*1024:continue
                target=settings.storage/'papers'/r['paper_id']/str(r['version'])/'attachments';target.mkdir(parents=True,exist_ok=True);shutil.copyfile(companion,target/companion.name)
            s.add(Receipt(id=rid,conference_id=c.id,state='Revision received' if revisions else 'Received',details={'paper_key':external,**r}))
            record(s,r['paper_id'],'agent_revision_received' if revisions else 'agent_ingested',{'version':r['version'],'event_id':rid});s.commit()
            validate.delay(r['version_id']);out.append(r)
        except Exception as exc:
            s.rollback();s.add(Receipt(id=rid,conference_id=c.id,state='Exception',details={'manifest':str(manifest.relative_to(inbox(c.id))),'error':str(exc)[:600]}));s.commit()
    return out

def enqueue_mail(s,c,p,v,kind,recipient,subject,body,attachment=''):
    key=f'{c.id}:{p.id if p else "coordinator"}:{v.number if v else 0}:{kind}'
    if not s.get(Dispatch,key):s.add(Dispatch(id=key,conference_id=c.id,paper_id=p.id if p else '',version=v.number if v else 0,kind=kind,recipient=recipient,subject=subject,body=body,attachment=attachment))

def deliver(s,c):
    if not cfg(c).notifications_enabled:return []
    sent=[]
    for msg in s.scalars(select(Dispatch).where(Dispatch.conference_id==c.id,Dispatch.state=='Pending').order_by(Dispatch.created)):
        if msg.paper_id and msg.kind!='publication':
            p=s.get(Paper,msg.paper_id,populate_existing=True,with_for_update=True)
            e=s.scalar(select(Enrollment).where(Enrollment.paper_id==p.id))
            if p.latest!=msg.version or (msg.kind.startswith('reminder') and e.state!='Awaiting Revision'):
                msg.state='Cancelled';s.commit();continue
        if not email_ok(msg.recipient):msg.state='Exception';msg.error='Invalid recipient';s.commit();continue
        if msg.kind=='correction':
            enrollment=s.scalar(select(Enrollment).where(Enrollment.paper_id==msg.paper_id))
            enrollment.deadline=now()+timedelta(seconds=cfg(c).deadline_seconds)
            msg.body=re.sub(r'Deadline \(UTC\):[^\n]+','Deadline (UTC): '+enrollment.deadline.isoformat(),msg.body)
        mail=EmailMessage();mail['From']=settings.mail_from;mail['To']=msg.recipient;mail['Subject']=msg.subject;mail['Message-ID']='<'+hashlib.sha256(msg.id.encode()).hexdigest()+'@paperflow.local>';mail.set_content(msg.body)
        if msg.attachment:
            f=Path(msg.attachment);mail.add_attachment(f.read_bytes(),maintype='application',subtype='pdf',filename='correction-report.pdf')
        msg.state='Sending';s.commit() # A crash here is uncertain, never blindly resend.
        try:
            send_smtp(mail)
            msg.state='Sent';msg.sent=now();record(s,msg.paper_id,'agent_email_sent',{'dispatch_id':msg.id,'kind':msg.kind,'recipient':msg.recipient,'message_id':mail['Message-ID']});s.commit();sent.append(msg.id)
        except Exception as exc:
            msg.state='Delivery uncertain';msg.error=type(exc).__name__;s.commit()
    return sent

def completed(s,c):
    conf=cfg(c);handled=[]
    for e in s.scalars(select(Enrollment).where(Enrollment.conference_id==c.id)):
        p=s.get(Paper,e.paper_id,populate_existing=True);v=latest(s,p)
        if e.handled_version>=p.latest or v.state not in ['Complete','Failed']:continue
        if conf.normalize_nonbreaking_spaces and v.state=='Complete' and Path(v.path).suffix=='.docx' and '\u00a0' in v.result.get('document',{}).get('text',''):
            from .editorial import correction
            corrected=correction(p.id)
            if corrected.get('changed'):
                e.deadline=None;e.state='Safe correction revalidation';s.commit();continue
        extracted=metadata_from_source(Path(v.path))
        if v.number>1:
            for field,value in extracted.items():setattr(p,field,value)
            e.details={**e.details,'metadata_conflicts':{}}
        result=dict(v.result or {});issues=list(result.get('issues',[]));checks=list(result.get('checks',[]))
        if v.state=='Failed':issues.append(issue(p.id,'compilation',v.error,'Source must compile/render successfully',v.error,correction='Repair the reported LaTeX command or missing asset; include all required files.'))
        if not result.get('document',{}).get('rendered_pdf'):issues.append(issue(p.id,'rendering','Rendered PDF unavailable','A readable PDF must be generated',v.error or 'Rendering failed'))
        for field in ['title','authors','affiliation','email']:
            value=getattr(p,field)
            if not value or (field=='email' and not email_ok(value)):issues.append(issue(p.id,'metadata',field+' is missing or invalid','Complete corresponding-author metadata',value,correction='Include '+field+' in revision metadata or labelled source paragraphs.'))
        if e.details.get('metadata_conflicts'):issues.append(issue(p.id,'metadata','Submission metadata conflicts with source','Unambiguous metadata',e.details['metadata_conflicts']))
        for field in ['abstract','keywords']:
            if not result.get('document',{}).get('metadata',{}).get(field):issues.append(issue(p.id,'metadata',field+' was not extracted','A nonempty '+field,'Not detected'))
        if conf.require_ai and not any(x.get('check')=='AI proofreading' and x.get('status')=='completed' for x in checks):
            e.state='Exception';e.details={**e.details,'exception':'Configured AI analysis is required but unavailable'};s.commit();continue
        unknown=[x['check'] for x in checks if x.get('status')=='requires_review' and x['check'] not in conf.acknowledged_manual_checks]
        # Linguistic/reference findings may require author correction even when not layout errors.
        blocking=[i for i in issues if i['severity']=='error' or i['category'] in ['writing','grammar','ai_writing','references','structure']]
        previous=s.scalar(select(Version).where(Version.paper_id==p.id,Version.number==v.number-1))
        old={i['fingerprint'] for i in (previous.result or {}).get('issues',[])} if previous else set();current={i['fingerprint'] for i in issues}
        result.update(issues=issues,checks=checks,comparison={'resolved':sorted(old-current),'remaining':sorted(old&current),'new':sorted(current-old)})
        v.result=result
        html,pdf=report(p,v)
        e.handled_version=p.latest
        if not blocking and not unknown:
            e.state='Publication Ready';e.deadline=None;p.status='Publication Ready'
            record(s,p.id,'agent_publication_ready',{'version':p.latest,'not_publisher_certification':True})
        elif not blocking and unknown:
            e.state='Publication Ready';e.deadline=None;p.status='Publication Ready';e.details={**e.details,'final_review_checks':unknown}
        elif p.latest>=conf.max_versions:
            e.state='Exception';e.deadline=None;e.details={**e.details,'exception':'Maximum correction rounds reached'}
            enqueue_mail(s,c,p,v,'round-limit',conf.coordinator_email,'Correction limit reached: '+e.external_id,'Please resolve this submission in the exception queue.')
        elif not email_ok(p.email):
            e.state='Exception';e.details={**e.details,'exception':'No unambiguous corresponding-author email'}
        else:
            e.state='Awaiting Revision';e.deadline=now()+timedelta(seconds=conf.deadline_seconds);p.status='Needs Correction'
            token=serializer.dumps({'paper':p.id,'scope':'revision'})
            body=f'Dear {p.authors or "author"},\n\nYour paper {e.external_id} ({p.title}) requires corrections. Please see the attached evidence report.\nDeadline (UTC): {e.deadline.isoformat()}\nSecure resubmission: {settings.public_url}/revise/{token}\n\n'+'\n'.join('- '+i['observed_problem']+': '+i['suggested_correction'] for i in blocking[:12])+'\n\nConference Editorial Team'
            enqueue_mail(s,c,p,v,'correction',p.email,'Corrections required ['+e.external_id+'] v'+str(v.number),body,str(pdf.resolve()))
        record(s,p.id,'agent_review_completed',{'version':p.latest,'state':e.state,'blocking':len(blocking),'unverified':unknown});s.commit();handled.append(p.id)
    return handled

def reminders(s,c):
    conf=cfg(c);out=[]
    for e in s.scalars(select(Enrollment).where(Enrollment.conference_id==c.id,Enrollment.state=='Awaiting Revision')):
        p=s.get(Paper,e.paper_id,populate_existing=True)
        if p.latest!=e.handled_version:continue # Portal revisions stop reminders before validation finishes.
        v=latest(s,p)
        correction=s.get(Dispatch,f'{c.id}:{p.id}:{v.number}:correction')
        if not correction or correction.state!='Sent':continue
        elapsed=(now()-correction.sent).total_seconds()
        for offset in conf.reminder_seconds:
            if elapsed>=offset:
                enqueue_mail(s,c,p,v,'reminder-'+str(offset),p.email,'Revision reminder ['+e.external_id+']',correction.body,correction.attachment);out.append(e.external_id)
        if now()>=e.deadline:
            enqueue_mail(s,c,p,v,'overdue',conf.coordinator_email,'Overdue manuscript ['+e.external_id+']','The author has not submitted a valid revised manuscript. Please resolve this exception.')
            e.state='Overdue';record(s,p.id,'agent_escalated',{'deadline':e.deadline.isoformat()})
        s.commit()
    return out

def assembly(s,c):
    from .publication import publish,PublicationRequest
    conf=cfg(c)
    if c.publication:return c.publication
    entries=list(s.scalars(select(Enrollment).where(Enrollment.conference_id==c.id)))
    if {e.external_id for e in entries}!=set(conf.expected_papers):return {'waiting':'batch intake incomplete'}
    if any(e.state!='Publication Ready' for e in entries):return {'waiting':'papers not ready'}
    unverified=sorted({check for e in entries for check in e.details.get('final_review_checks',[]) if check not in conf.acknowledged_manual_checks})
    if unverified:
        c.exception='Final review required for unsupported checks: '+', '.join(unverified);s.commit();return {'exception':c.exception}
    if not conf.publication_authorized:
        c.exception='Final publication authorization required';s.commit();return {'exception':c.exception}
    for e in entries:
        p=s.get(Paper,e.paper_id,with_for_update=True,populate_existing=True)
        if p.latest!=e.handled_version:return {'waiting':'revision not reviewed'}
        p.status='Approved';p.approved_version=p.latest;record(s,p.id,'conference_policy_approved',{'conference':c.id,'version':p.latest})
    s.commit()
    # Persist intent before side effect; a crash is surfaced, never silently assembles twice.
    if c.exception=='Assembly in progress; inspect outputs before retry':return {'exception':c.exception}
    c.exception='Assembly in progress; inspect outputs before retry';s.commit()
    result=publish(PublicationRequest(conference=conf.name,information='Internally checked conference proceedings; not Springer certification.',paper_ids=[e.paper_id for e in entries],confirm_editorial_approval=True))
    root=settings.storage/'publications'/result['publication_id']
    with zipfile.ZipFile(root/'publication-package.zip','w',zipfile.ZIP_DEFLATED) as z:
        for f in root.iterdir():
            if f.name!='publication-package.zip':z.write(f,f.name)
        for e in entries:
            p=s.get(Paper,e.paper_id);v=latest(s,p);html,pdf=report(p,v)
            z.write(html,'reports/'+e.external_id+'.html');z.write(pdf,'reports/'+e.external_id+'.pdf')
    result['files']=sorted(p.name for p in root.iterdir());c.publication=result;c.exception=''
    enqueue_mail(s,c,None,None,'publication',conf.coordinator_email,'Publication outputs ready: '+conf.name,'Your publication package is ready.\nPublication ID: '+result['publication_id']+'\nDownload the book, proceedings and archive in the conference dashboard.');s.commit()
    return result

@app.post('/agent/{cid}/{stage}',dependencies=[Depends(admin)])
def tick(cid:str,stage:str):
    if stage not in ['intake','completed','reminders','revisions','publication']:raise HTTPException(404)
    with Session() as lock:
        key=int(hashlib.sha256(cid.encode()).hexdigest()[:15],16)
        lock.execute(text("SET LOCAL lock_timeout = '20s'"))
        lock.execute(text('SELECT pg_advisory_lock(:key)'),{'key':key})
        try:
            with Session() as s:
                c=s.get(Conference,cid)
                if not c:raise HTTPException(404,'Conference not configured')
                if not c.enabled:return {'disabled':True}
                if stage in ['intake','revisions']:result=ingest(s,c,stage=='revisions')
                elif stage=='completed':result=completed(s,c)
                elif stage=='reminders':result=reminders(s,c)
                else:result=assembly(s,c)
                if stage in ['intake','revisions']:
                    for enrollment in s.scalars(select(Enrollment).where(Enrollment.conference_id==cid)):
                        paper=s.get(Paper,enrollment.paper_id,populate_existing=True);version=latest(s,paper)
                        if version.state in ['Queued','Queue failed']:validate.delay(version.id)
                sent=deliver(s,c)
                record(s,cid,'n8n_stage',{'stage':stage,'sent':sent,'result':result});s.commit()
                return {'stage':stage,'result':result,'sent':sent}
        finally:lock.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':key});lock.commit()

@app.get('/agent/{cid}/dispatches',dependencies=[Depends(admin)])
def dispatches(cid:str):
    with Session() as s:return [{'id':d.id,'paper_id':d.paper_id,'version':d.version,'kind':d.kind,'recipient':d.recipient,'state':d.state,'created':d.created,'sent':d.sent,'smtp_message_id':'<'+hashlib.sha256(d.id.encode()).hexdigest()+'@paperflow.local>'} for d in s.scalars(select(Dispatch).where(Dispatch.conference_id==cid).order_by(Dispatch.created))]

@app.get('/agent/conferences',dependencies=[Depends(admin)])
def conferences():
    with Session() as s:return [{'id':c.id,'name':c.config['name'],'enabled':c.enabled} for c in sorted(s.scalars(select(Conference)),key=lambda row:(bool(row.publication),row.enabled,row.id),reverse=True)]

@app.get('/agent/reports/{vid}',dependencies=[Depends(admin)])
def agent_report(vid:str,format:str='pdf'):
    from fastapi.responses import FileResponse
    with Session() as s:
        v=s.get(Version,vid)
        if not v or v.state not in ['Complete','Failed']:raise HTTPException(409,'Report not yet available')
        p=s.get(Paper,v.paper_id);html,pdf=report(p,v)
        return FileResponse(html if format=='html' else pdf,filename='correction-report.'+('html' if format=='html' else 'pdf'))

@app.post('/agent/{cid}/recheck/{pid}',dependencies=[Depends(admin)])
def recheck(cid:str,pid:str):
    with Session() as s:
        e=s.scalar(select(Enrollment).where(Enrollment.conference_id==cid,Enrollment.paper_id==pid))
        if not e:raise HTTPException(404)
        p=s.get(Paper,pid)
        e.handled_version=max(0,p.latest-1);e.state='Recheck requested';e.details={**e.details,'metadata_conflicts':{}}
        record(s,pid,'coordinator_exception_recheck',{'conference':cid});s.commit()
    return {'scheduled_for_next_n8n_check':True}
