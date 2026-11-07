"""Five inactive exports. Runtime deployment binds Header Auth in n8n, never in exports."""
import json,uuid
from pathlib import Path
stages=[('01-submission-intake','intake','Detect new bundles → segregate → queue validation'),('02-validation-completion','completed','Validation complete → report → policy-approved author email'),('03-author-communication','revisions','Detect revised bundle → match token → queue revalidation'),('04-reminders-escalation','reminders','Due revisions → policy-approved reminders → coordinator escalation'),('05-publication-assembly','publication','All ready → authorize batch → assemble → notify coordinator')]
for filename,stage,title in stages:
    p=Path('workflows')/(filename+'.json');old=json.loads(p.read_text())
    http=next(n for n in old['nodes'] if n['type']=='n8n-nodes-base.httpRequest')
    trigger=next((n for n in old['nodes'] if n['type']=='n8n-nodes-base.scheduleTrigger'),None) or {'id':str(uuid.uuid4())}
    trigger.update(name='Scheduled lifecycle check',type='n8n-nodes-base.scheduleTrigger',typeVersion=1.2,position=[0,0],parameters={'rule':{'interval':[{'field':'seconds','secondsInterval':5}]}})
    http.update(name='Execute '+stage,position=[320,0],parameters={'method':'POST','url':'={{ $env.PAPERFLOW_API_URL + "/agent/" + $env.PAPERFLOW_CONFERENCE_ID + "/'+stage+'" }}','authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth','options':{'timeout':120000}})
    http.pop('credentials',None);http.update(retryOnFail=True,maxTries=3,waitBetweenTries=2000)
    # Keep the stable workflow and existing HTTP node identity while replacing manual-only lifecycle paths.
    d={'id':old['id'],'versionId':str(uuid.uuid4()),'name':'PaperFlow Agent · '+title,'active':False,'nodes':[trigger,http],'connections':{trigger['name']:{'main':[[{'node':http['name'],'type':'main','index':0}]]}},'settings':{'executionOrder':'v1'},'pinData':{}}
    p.write_text(json.dumps(d,indent=2)+'\n')
