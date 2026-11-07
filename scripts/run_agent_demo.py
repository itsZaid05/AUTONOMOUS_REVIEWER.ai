"""Execute real five-paper lifecycle with an isolated, actively scheduled n8n runtime.
Only the simulated authors write/revise files; no Python loop triggers lifecycle endpoints.
"""
import io,json,os,subprocess,sys,time,uuid,zipfile
from pathlib import Path
import httpx
from dotenv import dotenv_values
from agent_samples import place,manuscript
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
local_ip=subprocess.check_output(['hostname','-I'],text=True).split()[0]
run='agent-'+uuid.uuid4().hex[:8];runtime=ROOT/'data'/'agent-runs'/run;runtime.mkdir(parents=True)
cfg=dotenv_values('.env');env={**os.environ,**{k:v for k,v in cfg.items() if v is not None},'PYTHONPATH':str(ROOT),'PUBLIC_URL':'http://127.0.0.1:18080'}
api_log=(runtime/'api.log').open('w')
api=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','0.0.0.0','--port','18080'],env=env,stdout=api_log,stderr=api_log)
container='paperflow-'+run
keep_running='--keep-running' in sys.argv
demo_completed=False
client=httpx.Client(base_url='http://127.0.0.1:18080',headers={'Authorization':'Bearer '+cfg['ADMIN_TOKEN']},timeout=90)
def request(method,path,**kwargs):
 r=client.request(method,path,**kwargs);r.raise_for_status();return r

def wait_for(fn,timeout=120):
 start=time.monotonic()
 while time.monotonic()-start<timeout:
  try:value=fn()
  except httpx.TransportError:value=None
  if value:return value
  time.sleep(1)
 raise TimeoutError('Condition not reached; inspect '+str(runtime))

try:
 wait_for(lambda: httpx.get('http://127.0.0.1:18080/health').is_success,30)
 profile=json.loads((ROOT/'profiles/conference-demo.json').read_text())
 policy={'name':'Controlled Springer Agent Demonstration '+run,'expected_papers':['paper-'+str(i) for i in range(1,6)],'coordinator_email':'coordinator@example.test','notifications_enabled':True,'publication_authorized':True,'enabled':True,'demo_mode':True,'deadline_seconds':360,'reminder_seconds':[120,300],'max_versions':4,'profile':profile,'require_ai':False,'acknowledged_manual_checks':['font','font_size_pt','headings','paragraph_spacing','figures','tables','captions','citations','affiliations']}
 r=request('PUT','/agent/conferences/'+run,json=policy).json();source=Path(r['source_folder'])
 credential={'id':'paperflowAgentDemoCredential','name':'Local demo policy credential','type':'httpHeaderAuth','data':{'name':'Authorization','value':'Bearer '+cfg['ADMIN_TOKEN']}}
 (runtime/'credentials.json').write_text(json.dumps([credential]));(runtime/'credentials.json').chmod(0o600)
 workflows=[]
 for p in sorted((ROOT/'workflows').glob('0*.json')):
  d=json.loads(p.read_text())
  for n in d['nodes']:
   if n['type']=='n8n-nodes-base.httpRequest':n['credentials']={'httpHeaderAuth':{'id':credential['id'],'name':credential['name']}}
  workflows.append(d)
 (runtime/'workflows.json').write_text(json.dumps(workflows))
 cmd=['docker','run','-d','--name',container,'-p','127.0.0.1:15679:5678','--add-host','host.docker.internal:'+local_ip,'-v',str(runtime)+':/seed:ro','-e','PAPERFLOW_API_URL=http://host.docker.internal:18080','-e','PAPERFLOW_CONFERENCE_ID='+run,'-e','NO_PROXY=host.docker.internal,'+local_ip+',127.0.0.1,localhost','-e','no_proxy=host.docker.internal,'+local_ip+',127.0.0.1,localhost','-e','N8N_SECURE_COOKIE=false','-e','N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true','-e','N8N_DIAGNOSTICS_ENABLED=false','-e','N8N_VERSION_NOTIFICATIONS_ENABLED=false','-e','N8N_ENCRYPTION_KEY='+uuid.uuid4().hex,'--entrypoint','sh','n8nio/n8n:1.123.0','-c','n8n import:credentials --input=/seed/credentials.json && n8n import:workflow --input=/seed/workflows.json && n8n start']
 started=subprocess.run(cmd,capture_output=True)
 if started.returncode:raise RuntimeError('Disposable n8n container could not start; inspect Docker port availability')
 # Save and activate via n8n's supported owner API. CLI import alone does not create publishable version history.
 n8n=httpx.Client(base_url='http://127.0.0.1:15679',timeout=30)
 wait_for(lambda:n8n.get('/rest/settings').is_success,90)
 password='Demo-'+uuid.uuid4().hex+'-A1!'
 response=n8n.post('/rest/owner/setup',json={'email':'demo@example.test','firstName':'Demo','lastName':'Coordinator','password':password})
 response.raise_for_status()
 n8n.post('/rest/login',json={'emailOrLdapLoginId':'demo@example.test','password':password}).raise_for_status()
 for workflow in workflows:
  saved=n8n.patch('/rest/workflows/'+workflow['id'],json={'name':workflow['name'],'nodes':workflow['nodes'],'connections':workflow['connections'],'settings':workflow['settings'],'versionId':workflow['versionId']})
  saved.raise_for_status()
  version=saved.json()['data']['versionId']
  activation=n8n.post('/rest/workflows/'+workflow['id']+'/activate',json={'versionId':version})
  activation.raise_for_status()
 print('All five n8n schedules activated through the owner API',flush=True)
 # n8n runs as node; only this controlled container needs read access to generated seed.
 # Parent mode is inherited from the development workspace and must be traversable by its uid.
 for i in range(1,6):place(source,i)
 start=time.monotonic();history=[]
 def snapshot():
  state=request('GET','/agent/conferences/'+run).json()
  history.append({'observed_at':time.time(),'state':state})
  return state
 initial=wait_for(lambda:(lambda x:x if len(x['papers'])==5 and all(p['state'] in ['Publication Ready','Awaiting Revision','Exception'] for p in x['papers']) else None)(snapshot()),180)
 (runtime/'initial.json').write_text(json.dumps(initial,indent=2))
 print('Initial states:',[(p['external_id'],p['state']) for p in initial['papers']],flush=True)
 assert next(p for p in initial['papers'] if p['external_id']=='paper-1')['state']=='Publication Ready'
 assert all(p['state']=='Awaiting Revision' for p in initial['papers'] if p['external_id']!='paper-1'),initial
 # Authors 2–4 respond through new source bundles; n8n detects the revision-token manifests.
 for i in [2,3,4]:
  paper=next(p for p in initial['papers'] if p['external_id']==f'paper-{i}')
  link=request('POST','/papers/'+paper['paper_id']+'/revision-link').json()['url']
  place(source,i,True,link.rsplit('/',1)[1])
 reminded=wait_for(lambda:(lambda x:x if any(m['kind']=='reminder-120' and m['state']=='Sent' for p in x['papers'] if p['external_id']=='paper-5' for m in p['messages']) else None)(snapshot()),180)
 print('Real scheduled two-minute reminder sent',flush=True)
 paper=next(p for p in reminded['papers'] if p['external_id']=='paper-5')
 token=request('POST','/papers/'+paper['paper_id']+'/revision-link').json()['url'].rsplit('/',1)[1]
 name,content=manuscript(5,True)
 request('POST','/revise/'+token,files={'file':(name,content)})
 final=wait_for(lambda:(lambda x:x if x['publication'].get('publication_id') and any(m['kind']=='publication' and m['state']=='Sent' for m in request('GET','/agent/'+run+'/dispatches').json()) else None)(snapshot()),120)
 for p in final['papers']:
  assert p['state']=='Publication Ready',p
  if p['external_id']!='paper-1':assert p['version']==2 and p['comparison']['resolved'],p
  assert not any(m['kind']=='reminder-300' and m['state']=='Sent' for m in p['messages'])
 pub=final['publication'];outputs=runtime/'outputs';outputs.mkdir()
 for name in pub['files']:
  content=request('GET','/publications/'+pub['publication_id']+'/'+name).content
  (outputs/name).write_bytes(content)
  if name.endswith('.pdf'):assert content.startswith(b'%PDF')
 mailbox=httpx.get('http://127.0.0.1:8025/api/v1/messages').json()
 (runtime/'mailpit.json').write_text(json.dumps(mailbox,indent=2))
 # Confirm real Mailpit receipt, not just an SMTP call returning.
 expected=[m for m in request('GET','/agent/'+run+'/dispatches').json() if m['state']=='Sent']
 actual=[]
 for m in mailbox.get('messages',[]):
  detail=httpx.get('http://127.0.0.1:8025/api/v1/message/'+m['ID']).json();actual.append(detail)
 (runtime/'received-emails.json').write_text(json.dumps(actual,indent=2))
 for m in expected:
  message_id=m['smtp_message_id'].strip('<>')
  assert any(message_id in json.dumps(mail) for mail in actual),message_id
 (runtime/'timeline.json').write_text(json.dumps(history,indent=2))
 result={'run':run,'seconds':round(time.monotonic()-start,2),'papers':final['papers'],'publication':pub,'sent_messages':expected,'received_count':len(expected),'profile_source':profile,'ai_check':'skipped: no provider credentials configured','evidence_path':str(runtime)}
 (ROOT/'AGENT_DEMO_RESULTS.json').write_text(json.dumps(result,indent=2));print(json.dumps({'run':run,'seconds':result['seconds'],'received_emails':len(expected),'publication':pub['publication_id']},indent=2),flush=True)
 demo_completed=True
finally:
 subprocess.run(['docker','logs',container],stdout=(runtime/'n8n.log').open('w'),stderr=subprocess.STDOUT)
 if not (keep_running and demo_completed):
  subprocess.run(['docker','stop',container],capture_output=True)
  api.terminate();api.wait(timeout=20)
 else:print('Live verification services retained: API 18080, n8n 15679; conference '+run,flush=True)
 api_log.close()
 # Never leave a plaintext n8n credential export in the run artifacts.
 (runtime/'credentials.json').unlink(missing_ok=True)

if (ROOT/'AGENT_DEMO_RESULTS.json').exists() and json.loads((ROOT/'AGENT_DEMO_RESULTS.json').read_text()).get('run')==run:
 subprocess.run([sys.executable,'scripts/verify_agent_evidence.py'],env=env,check=True)
