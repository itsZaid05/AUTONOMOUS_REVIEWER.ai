import json,uuid
from pathlib import Path
specs=[('01-submission-intake','intake','Submission Intake'),('02-validation-completion','complete','Validation Completion'),('03-author-communication','communicate','Author Communication'),('04-reminders-escalation','reminders','Reminders & Escalation'),('05-publication-assembly','publication','Publication Assembly')]
for slug,kind,title in specs:
    nodes=[];connections={}
    def node(name,type,version,params,x):
        nodes.append({'id':str(uuid.uuid4()),'name':name,'type':'n8n-nodes-base.'+type,'typeVersion':version,'parameters':params,'position':[x,0]})
    node('Receive event','webhook',2,{'httpMethod':'POST','path':'paperflow-'+kind,'responseMode':'lastNode','options':{}},0)
    # API enforces schema, durable business event identity, and editorial gates.
    node('Perform approved operation','httpRequest',4.2,{'method':'POST','url':'={{ $env.PAPERFLOW_API_URL + "/automation/'+kind+'" }}','authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth','sendBody':True,'specifyBody':'json','jsonBody':'={{ JSON.stringify($json.body) }}','options':{'timeout':120000}},320)
    connections['Receive event']={'main':[[{'node':'Perform approved operation','type':'main','index':0}]]}
    if kind=='reminders':
        node('Daily review','scheduleTrigger',1.2,{'rule':{'interval':[{'triggerAtHour':9}]}},0)
        node('Make scheduled event','set',3.4,{'assignments':{'assignments':[{'id':str(uuid.uuid4()),'name':'body','value':'={{ {event_id: "reminders-" + $now.toFormat("yyyy-MM-dd")} }}','type':'object'}]},'options':{}},160)
        connections['Daily review']={'main':[[{'node':'Make scheduled event','type':'main','index':0}]]};connections['Make scheduled event']={'main':[[{'node':'Perform approved operation','type':'main','index':0}]]}
    workflow={'id':'paperflow'+kind,'name':'PaperFlow · '+title,'versionId':str(uuid.uuid4()),'active':False,'nodes':nodes,'connections':connections,'settings':{'executionOrder':'v1'},'pinData':{},'tags':[]}
    Path('workflows',slug+'.json').write_text(json.dumps(workflow,indent=2))
