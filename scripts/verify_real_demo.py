"""Fail-closed acceptance runner. Requires real source/revision files and a real Gemini call.
It drives setup/upload and simulated author submission only; n8n drives all lifecycle transitions.
"""
import argparse,hashlib,io,json,os,re,sys,time,zipfile
from pathlib import Path
import httpx
from dotenv import dotenv_values
CRITERIA=['gemini_connectivity','real_ingestion','isolated_compilation','whole_document_analysis','lncs_rules','gemini_invocations','five_active_n8n_workflows','mailpit_isolation','correction_delivery','scheduled_reminder','revision_revalidation','draft_and_output_integrity','final_authorization','restart_deduplication']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True,type=Path);parser.add_argument('--conference',required=True);parser.add_argument('--api',default='http://127.0.0.1:8000');parser.add_argument('--n8n',default='http://127.0.0.1:5678');parser.add_argument('--mailpit',default='http://127.0.0.1:8025');parser.add_argument('--timeout',type=int,default=1800);parser.add_argument('--start',action='store_true');parser.add_argument('--restart-compose',action='store_true',help='Restart the isolated DEMO Compose project and verify durable idempotency');parser.add_argument('--backend-url',default='http://api:8000');parser.add_argument('--report',type=Path,default=Path('data/real-verification/report.json'));args=parser.parse_args()
    env={**dotenv_values('.env'),**os.environ};checks={k:{'status':'NOT TESTED','reason':'Not executed'} for k in CRITERIA};report={'external_inputs':{'manifest_present':args.manifest.is_file(),'gemini_key_configured':bool(env.get('AI_API_KEY') or env.get('GEMINI_API_KEY') or env.get('GOOGLE_API_KEY')),'gemini_model_configured':bool(env.get('AI_MODEL'))},'conference':args.conference,'started_at':time.time(),'acceptance':checks,'complete':False};args.report.parent.mkdir(parents=True,exist_ok=True)
    def save():args.report.write_text(json.dumps(report,indent=2,default=str)+'\n')
    def passed(key,**evidence):checks[key]={'status':'PASS','evidence':evidence};save()
    def request(client,method,path,**kwargs):
        response=client.request(method,path,**kwargs);response.raise_for_status();return response
    api=httpx.Client(base_url=args.api,headers={'Authorization':'Bearer '+(env.get('ADMIN_TOKEN') or '')},timeout=120)
    mailbox=httpx.Client(base_url=args.mailpit,timeout=30)
    try:
        if not args.manifest.is_file():raise ValueError('Five real manuscripts and their metadata/revision manifest have not been supplied')
        manifest=json.loads(args.manifest.read_text());papers=manifest.get('papers',[])
        if len(papers)!=5 or len({p['paper_key'] for p in papers})!=5:raise ValueError('Exactly five distinct real papers are required')
        files=[]
        for paper in papers:
            path=(args.manifest.parent/paper['path']).resolve()
            if not path.is_file() or path.suffix.lower() not in ['.docx','.tex','.zip']:raise ValueError('A supplied real manuscript file is missing or unsupported')
            if paper.get('real_manuscript') is not True or not paper.get('provenance',{}).get('origin'):raise ValueError('Real manuscript provenance/authorization must be declared; synthetic fixtures are not acceptance inputs')
            if not paper.get('metadata_verified') or any(not paper.get('metadata',{}).get(k) for k in ['title','authors','affiliation','email','abstract','keywords']):raise ValueError('Complete verified author metadata is required')
            files.append((paper,path))
        if len({path.name for _,path in files})!=5:raise ValueError('Each uploaded source requires a unique filename for manifest mapping')
        if not any(path.suffix=='.docx' for _,path in files) or not any(path.suffix in ['.tex','.zip'] for _,path in files):raise ValueError('The real-paper demonstration must exercise DOCX and LaTeX sources')
        revision=manifest.get('revision',{});revision_path=(args.manifest.parent/revision.get('path','')).resolve()
        if revision.get('paper_key') not in {p['paper_key'] for p in papers} or not revision_path.is_file():raise ValueError('Supply an actual corrected manuscript for the controlled author revision')
        if args.start:
            import subprocess
            with (args.report.parent/'compose-startup.log').open('w') as log:
                started=subprocess.run(['docker','compose','up','-d','--build','--wait'],stdout=log,stderr=log)
            if started.returncode:raise ValueError('Docker Compose startup failed; inspect the private startup log')
        setup=request(api,'GET','/setup/status').json();report['setup']=setup
        if setup.get('mail_mode')!='DEMO':raise ValueError('Verification is restricted to DEMO Mailpit mode')
        if setup['dependencies'].get('gemini') not in ['Connected','Configured']:raise ValueError('Gemini key/model missing; configure secrets securely in environment settings')
        try:verification=request(api,'POST','/setup/verify-gemini').json()
        except Exception:
            checks['gemini_connectivity']={'status':'FAIL','reason':'Actual configured Gemini request failed; see private setup status, no credentials or provider body recorded'};save();raise
        report['gemini_connectivity']=verification;passed('gemini_connectivity',**verification)
        info=request(mailbox,'GET','/api/v1/info').json()
        if not {'Version','Database','Messages'}<=set(info):raise ValueError('Not a verified local Mailpit API')
        passed('mailpit_isolation',version=info['Version'],mode='DEMO',transport='forced local Mailpit')
        state=request(api,'GET','/agent/conferences/'+args.conference).json();policy=state['policy']
        if not policy.get('real_paper_mode') or not policy.get('require_ai') or policy.get('publication_authorized'):raise ValueError('Use real_paper_mode=true, require_ai=true and publication_authorized=false for this verification')
        if policy.get('acknowledged_manual_checks'):raise ValueError('Runner does not auto-acknowledge unsupported publisher checks')
        if set(policy['expected_papers'])!={p['paper_key'] for p in papers}:raise ValueError('Configured conference membership differs from the five real uploads')
        if not policy.get('notifications_enabled'):raise ValueError('Coordinator must enable the approved test notification policy once')
        # Use existing n8n owner credentials supplied securely; never reset its database or users.
        owner_email=env.get('N8N_OWNER_EMAIL');owner_password=env.get('N8N_OWNER_PASSWORD')
        if not owner_email or not owner_password:raise ValueError('Configure the existing local n8n owner credentials securely as N8N_OWNER_EMAIL and N8N_OWNER_PASSWORD')
        n8n=httpx.Client(base_url=args.n8n,timeout=60)
        request(n8n,'POST','/rest/login',json={'emailOrLdapLoginId':owner_email,'password':owner_password})
        credentials=request(n8n,'GET','/rest/credentials').json()['data']
        credential=next((c for c in credentials if c['name']=='PaperFlow real-demo backend'),None)
        if credential is None:
            credential=request(n8n,'POST','/rest/credentials',json={'name':'PaperFlow real-demo backend','type':'httpHeaderAuth','data':{'name':'Authorization','value':'Bearer '+env['ADMIN_TOKEN']}}).json()['data']
        workflow_ids=[]
        for path in sorted(Path('workflows').glob('0*.json')):
            workflow=json.loads(path.read_text());wid=workflow['id']
            for node in workflow['nodes']:
                if node['type']=='n8n-nodes-base.httpRequest':
                    stage=path.stem.split('-',1)[-1]
                    stage={'new-submission':'intake','validation-completed':'completed','scheduled-reminders':'reminders','revised-submission':'revisions','publication-ready':'publication'}.get(stage,stage)
                    # Use the endpoint from the versioned export, replacing only its conference expression.
                    original=node['parameters']['url']
                    stage=next((name for name in ['intake','completed','reminders','revisions','publication'] if '/'+name in original),None)
                    if not stage:raise ValueError('Workflow export is missing an actual lifecycle endpoint')
                    node['parameters']['url']=args.backend_url.rstrip('/')+'/agent/'+args.conference+'/'+stage
                    node['credentials']={'httpHeaderAuth':{'id':credential['id'],'name':credential['name']}}
            listing=request(n8n,'GET','/rest/workflows').json()['data']
            items=listing.get('data',[]) if isinstance(listing,dict) else listing
            match=next((item for item in items if item['id']==wid or item['name']==workflow['name']),None)
            if match:wid=match['id']
            existing=n8n.get('/rest/workflows/'+wid)
            if existing.status_code==404:
                saved=request(n8n,'POST','/rest/workflows',json={**{k:workflow[k] for k in ['name','nodes','connections','settings']},'active':False,'versionId':workflow['versionId']}).json()['data'];wid=saved['id']
                saved=request(n8n,'PATCH','/rest/workflows/'+wid,json={**{k:workflow[k] for k in ['name','nodes','connections','settings']},'versionId':saved['versionId']}).json()['data']
            else:
                existing.raise_for_status();current=existing.json()['data']
                if current.get('active'):request(n8n,'POST','/rest/workflows/'+wid+'/deactivate')
                saved=request(n8n,'PATCH','/rest/workflows/'+wid,json={**{k:workflow[k] for k in ['name','nodes','connections','settings']},'versionId':current['versionId']}).json()['data']
            request(n8n,'POST','/rest/workflows/'+wid+'/activate',json={'versionId':saved['versionId']});workflow_ids.append(wid)
        listing=request(n8n,'GET','/rest/workflows').json()['data'];items=listing.get('data',listing) if isinstance(listing,dict) else listing
        if not all(any(w['id']==wid and w.get('active') for w in items) for wid in workflow_ids):raise ValueError('Not all five actual n8n workflows are active')
        # Schedule URL expressions use the existing n8n PAPERFLOW_API_URL / PAPERFLOW_CONFERENCE_ID settings.
        report['n8n_workflow_ids']=workflow_ids
        metadata=[{'filename':path.name,**{k:v for k,v in paper.items() if k not in ['path']}} for paper,path in files]
        uploaded=request(api,'POST','/agent/conferences/'+args.conference+'/bulk',files=[('files',(path.name,path.read_bytes())) for _,path in files],data={'manifest':json.dumps(metadata)}).json();report['uploaded']=uploaded;save()
        deadline=time.monotonic()+args.timeout;revision_sent=False;initial_versions={};last_state={};authorization_sent=False;restart_started=False;restart_snapshot=None;restart_at=None;restart_execution_baseline=set()
        observed_messages={};outputs_dir=args.report.parent/'outputs';outputs_dir.mkdir(exist_ok=True)
        while time.monotonic()<deadline:
            state=request(api,'GET','/agent/conferences/'+args.conference).json();last_state=state
            if len(state['papers'])==5:
                expected={p['paper_key']:hashlib.sha256(path.read_bytes()).hexdigest() for p,path in files}
                details={p['external_id']:request(api,'GET','/papers/'+p['paper_id']).json() for p in state['papers']}
                if all(d['versions'][0].get('sha256')==expected[key] for key,d in details.items()) and len({p['paper_id'] for p in state['papers']})==5:passed('real_ingestion',paper_ids=[p['paper_id'] for p in state['papers']],source_sha256=expected)
                complete_ai=[];rule_evidence=[];compiled=[]
                for paper in state['papers']:
                    version=details[paper['external_id']]['versions'][-1];initial_versions.setdefault(paper['external_id'],version['number'])
                    coverage=next((c for c in version['result'].get('checks',[]) if c.get('check')=='AI proofreading'),{})
                    if coverage.get('provider')=='gemini' and coverage.get('status')=='completed' and coverage.get('coverage_ratio')==1 and all(c.get('invocation',{}).get('response_id') for c in coverage.get('chunks',[])):complete_ai.append({'paper_key':paper['external_id'],'version':version['number'],'coverage':coverage})
                    compilation=version['result'].get('document',{}).get('compilation',{})
                    if compilation.get('isolation',{}).get('network')=='none' and compilation.get('isolation',{}).get('host_docker_socket') is False:compiled.append(compilation)
                    rule_evidence.extend(i.get('rule') for i in paper['issues'] if i.get('rule'))
                if len(complete_ai)==5:
                    passed('gemini_invocations',papers=complete_ai)
                    # A designated deliberately placed tail issue is mandatory evidence, not a fabricated finding.
                    tail=manifest.get('tail_issue',{});target=next((p for p in state['papers'] if p['external_id']==tail.get('paper_key')),None)
                    if target and any(i.get('category')=='ai_writing' and tail.get('evidence')==i.get('evidence') and any(int(n)>40000 for n in re.findall(r'character (\d+)',i.get('location',''))) for i in target['issues']):passed('whole_document_analysis',papers=5,coverage_ratio=1,late_issue_detected=True)
                if compiled:passed('isolated_compilation',actual_compilations=compiled)
                if rule_evidence:passed('lncs_rules',rules=rule_evidence)
                dispatch=request(api,'GET','/agent/'+args.conference+'/dispatches').json()
                messages=request(mailbox,'GET','/api/v1/messages',params={'limit':500}).json().get('messages',[])
                for message in messages:
                    if message['ID'] not in observed_messages:observed_messages[message['ID']]=request(mailbox,'GET','/api/v1/message/'+message['ID']).json()
                received=[]
                for sent in dispatch:
                    if sent['state']=='Sent' and any(sent['smtp_message_id'].strip('<>') in json.dumps(m) for m in observed_messages.values()):received.append(sent)
                corrections=[m for m in received if m['kind']=='correction']
                if corrections:
                    verified=[]
                    for message in corrections:
                        paper=next(p for p in state['papers'] if p['paper_id']==message['paper_id'])
                        mail=next(m for m in observed_messages.values() if message['smtp_message_id'].strip('<>') in json.dumps(m))
                        from email import policy as email_policy
                        from email.parser import BytesParser
                        captured=next((m for m in messages if m['ID'] in observed_messages and observed_messages[m['ID']]==mail),None)
                        if not captured:continue
                        raw=request(mailbox,'GET','/api/v1/message/'+captured['ID']+'/raw').content
                        mime=BytesParser(policy=email_policy.default).parsebytes(raw)
                        attachment=next((part.get_payload(decode=True) for part in mime.walk() if part.get_filename()=='correction-report.pdf'),None)
                        if not attachment:continue
                        expected_report=request(api,'GET','/agent/reports/'+paper['version_id']).content
                        # PDF creation metadata can vary on regeneration; compare page text and attachment validity.
                        from pypdf import PdfReader
                        actual_text=''.join(p.extract_text() for p in PdfReader(io.BytesIO(attachment)).pages)
                        report_text=''.join(p.extract_text() for p in PdfReader(io.BytesIO(expected_report)).pages)
                        if actual_text==report_text and any(i['observed_problem'] in mail.get('Text','') for i in paper['issues']):
                            verified.append({'dispatch_id':message['id'],'mailpit_id':captured['ID'],'attachment_sha256':hashlib.sha256(attachment).hexdigest(),'attachment_text_matches':True})
                    if verified:passed('correction_delivery',verified_messages=verified)
                reminders=[m for m in received if m['kind'].startswith('reminder-')]
                if reminders:passed('scheduled_reminder',messages=reminders)
                target=next((p for p in state['papers'] if p['external_id']==revision['paper_key']),None)
                if target and not revision_sent and any(m['paper_id']==target['paper_id'] for m in reminders):
                    correction=next(m for m in received if m['paper_id']==target['paper_id'] and m['kind']=='correction')
                    mail=next(m for m in observed_messages.values() if correction['smtp_message_id'].strip('<>') in json.dumps(m))
                    token=re.search(r'/revise/([A-Za-z0-9_.-]+)',json.dumps(mail)).group(1)
                    request(api,'POST','/revise/'+token,files={'file':(revision_path.name,revision_path.read_bytes())});revision_sent=True;report['revision_uploaded_at']=time.time()
                    if revision.get('metadata'):request(api,'POST','/agent/'+args.conference+'/metadata/'+target['paper_id'],json={**revision['metadata'],'verified':True})
                if target and revision_sent and target['version']>initial_versions[target['external_id']] and target['validation']=='Complete' and target.get('next_reminder') is None and target['comparison'].get('resolved'):
                    later=[m for m in dispatch if m['paper_id']==target['paper_id'] and m['version']==target['version'] and m['kind'].startswith('reminder-') and m['state']=='Sent']
                    if not later:passed('revision_revalidation',paper_id=target['paper_id'],version=target['version'],comparison=target['comparison'])
            draft=state.get('draft',{})
            if draft.get('publication_id'):
                hashes={}
                for filename in draft['files']:
                    data=request(api,'GET','/publications/'+draft['publication_id']+'/'+filename).content
                    if filename.endswith('.pdf'):
                        from pypdf import PdfReader
                        assert len(PdfReader(io.BytesIO(data)).pages)>0
                    elif filename.endswith(('.docx','.zip')):
                        with zipfile.ZipFile(io.BytesIO(data)) as archive:assert archive.testzip() is None
                    (outputs_dir/filename).write_bytes(data);hashes[filename]=hashlib.sha256(data).hexdigest()
                audit=json.loads((outputs_dir/'audit.json').read_text())
                assert all(p['metadata_verified'] for p in audit['papers'])
                passed('draft_and_output_integrity',included=draft['included'],excluded=draft.get('excluded'),sha256=hashes)
            final_decision=manifest.get('final_authorization',{})
            if final_decision.get('authorized') is True and final_decision.get('coordinator') and len(final_decision.get('reason',''))>=10:
                if not authorization_sent:
                    decisions=final_decision.get('check_decisions',{})
                    updated={**policy,'publication_authorized':True,'acknowledged_manual_checks':list(decisions),'check_decisions':decisions}
                    request(api,'PUT','/agent/conferences/'+args.conference,json=updated)
                    authorization_sent=True;report['final_authorization_recorded_at']=time.time()
                if state.get('publication'):
                    final=state['publication'];final_hashes={}
                    for filename in final['files']:
                        data=request(api,'GET','/publications/'+final['publication_id']+'/'+filename).content
                        if filename.endswith('.pdf'):
                            from pypdf import PdfReader
                            assert len(PdfReader(io.BytesIO(data)).pages)>0
                        if filename.endswith(('.zip','.docx')):
                            with zipfile.ZipFile(io.BytesIO(data)) as archive:assert archive.testzip() is None
                        (outputs_dir/('final-'+filename)).write_bytes(data);final_hashes[filename]=hashlib.sha256(data).hexdigest()
                    audit=json.loads((outputs_dir/'final-audit.json').read_text())
                    expected={p['paper_key']:p for p in papers}
                    for row in audit['papers']:
                        observed=next(p for p in state['papers'] if p['paper_id']==row['paper_id'])
                        reference=revision.get('metadata') if observed['external_id']==revision['paper_key'] and revision.get('metadata') else expected[observed['external_id']]['metadata']
                        assert all(row[k]==reference[k] for k in ['title','authors','affiliation','abstract','keywords'])
                    assert len(audit['papers'])==5
                    from docx import Document
                    from pypdf import PdfReader
                    import unicodedata
                    def normalized(value):return ' '.join(unicodedata.normalize('NFKC',value).split())
                    pdf_text=normalized(' '.join(page.extract_text() for page in PdfReader(outputs_dir/'final-book-of-abstracts.pdf').pages))
                    word_text=normalized(' '.join(p.text for p in Document(outputs_dir/'final-book-of-abstracts.docx').paragraphs))
                    for row in audit['papers']:
                        for field in ['title','authors','affiliation','abstract','keywords']:
                            assert normalized(row[field]) in pdf_text and normalized(row[field]) in word_text

                    passed('final_authorization',publication_id=final['publication_id'],sha256=final_hashes,metadata_verified=True)
            else:checks['final_authorization']={'status':'NOT TESTED','reason':'Explicit final_authorization object with coordinator and reason is required in the private manifest; the runner never infers release authorization'}
            executions=request(n8n,'GET','/rest/executions',params={'filter':json.dumps({'status':['success']})}).json()['data']
            results=executions.get('results',executions.get('data',[])) if isinstance(executions,dict) else executions
            actual=[]
            for execution in results:
                if execution.get('workflowId') not in workflow_ids:continue
                detail=request(n8n,'GET','/rest/executions/'+str(execution['id'])).json()
                if args.conference in json.dumps(detail):actual.append(execution)
            executed={e.get('workflowId') for e in actual}
            if set(workflow_ids)<=executed:passed('five_active_n8n_workflows',ids=workflow_ids,executions=[{'id':e['id'],'workflowId':e.get('workflowId'),'status':e.get('status')} for e in actual])
            if all(v['status']=='PASS' for k,v in checks.items() if k!='restart_deduplication') and args.restart_compose:
                if not restart_started:
                    import subprocess
                    restart_snapshot={'papers':sorted((p['paper_id'],p['version']) for p in state['papers']),'dispatch':sorted((d['id'],d['state']) for d in dispatch),'mail_ids':sorted(observed_messages),'publication':state['publication']['publication_id']}
                    with (args.report.parent/'restart.log').open('w') as log:
                        restarted=subprocess.run(['docker','compose','restart','api','worker','n8n'],stdout=log,stderr=log)
                    if restarted.returncode:raise ValueError('Compose restart failed')
                    recovery_until=time.monotonic()+60
                    while time.monotonic()<recovery_until:
                        try:
                            request(api,'GET','/health');request(n8n,'GET','/healthz/readiness');break
                        except (httpx.TransportError,httpx.HTTPStatusError):time.sleep(1)
                    else:raise ValueError('Services failed readiness after restart')
                    restart_started=True;restart_at=time.monotonic();restart_execution_baseline={str(e['id']) for e in actual};report['restart_started_at']=time.time()
                elif time.monotonic()-restart_at>=35 and set(workflow_ids)<={e.get('workflowId') for e in actual if str(e['id']) not in restart_execution_baseline}:
                    after={'papers':sorted((p['paper_id'],p['version']) for p in state['papers']),'dispatch':sorted((d['id'],d['state']) for d in dispatch),'mail_ids':sorted(observed_messages),'publication':state['publication']['publication_id']}
                    assert after==restart_snapshot,'Restart created duplicate papers/messages or changed released versions'
                    passed('restart_deduplication',observed_seconds=time.monotonic()-restart_at,snapshot=after)

            if checks['final_authorization'].get('status')=='PASS' and not args.restart_compose:checks['restart_deduplication']={'status':'NOT TESTED','reason':'Pass --restart-compose to verify durable state after an isolated Compose restart'}
            report['last_observation']={'papers':[{'paper_key':p['external_id'],'version':p['version'],'state':p['state']} for p in state['papers']],'observed_at':time.time()};save()
            if all(c['status']=='PASS' for c in checks.values()):
                report['complete']=True;break
            time.sleep(3)
        if not report['complete']:raise TimeoutError('Acceptance criteria remain unverified; inspect the per-criterion report')
    except Exception as exc:
        # Never stringify HTTP/SDK errors: their bodies may contain credentials or manuscript text.
        report['blocker']={'type':type(exc).__name__,'reason':str(exc) if isinstance(exc,(ValueError,TimeoutError)) else 'Dependency or integration failure; inspect private service state without dumping secrets'}
    finally:
        report['finished_at']=time.time();save();print(json.dumps({'complete':report['complete'],'report':str(args.report),'acceptance':{k:v['status'] for k,v in checks.items()},'blocker':report.get('blocker')},indent=2))
    return 0 if report['complete'] else 1
if __name__=='__main__':sys.exit(main())
