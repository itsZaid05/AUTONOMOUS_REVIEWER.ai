"""Verify/stamp an actually completed demo from its retained DB, audit log and generated files."""
import hashlib,json,sqlite3,subprocess
from pathlib import Path
from pypdf import PdfReader
from sqlalchemy import select
from app.db import Session,Audit
root=Path(__file__).resolve().parents[1]
p=root/'AGENT_DEMO_RESULTS.json';summary=json.loads(p.read_text());run=summary['run'];folder=Path(summary['evidence_path'])
db=folder/'n8n-executions.sqlite'
subprocess.run(['docker','cp','paperflow-'+run+':/home/node/.n8n/database.sqlite',str(db)],check=True,capture_output=True);db.chmod(0o600)
c=sqlite3.connect(db)
stats=[{'workflow':r[0],'status':r[1],'executions':r[2]} for r in c.execute('select workflowId,status,count(*) from execution_entity group by workflowId,status')]
assert len({r['workflow'] for r in stats if r['status']=='success'})==5,stats
assert not any(r['status']=='error' for r in stats),stats
initial=json.loads((folder/'initial.json').read_text())
categories={paper['external_id']:{i['category'] for i in paper['issues']} for paper in initial['papers']}
assert {'font','layout'}<=categories['paper-2']
assert 'compilation' in categories['paper-3']
assert {'metadata','writing'}<=categories['paper-4']
assert 'writing' in categories['paper-5']
with Session() as s:
 ids=[paper['paper_id'] for paper in initial['papers']]+[run]
 events=[{'paper_id':a.paper_id,'action':a.action,'at':a.created.isoformat(),'details':a.details} for a in s.scalars(select(Audit).where(Audit.paper_id.in_(ids)).order_by(Audit.id))]
(folder/'events.json').write_text(json.dumps(events,indent=2))
summary['n8n_executions']=stats;summary['artifact_hashes']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (folder/'outputs').iterdir()}
summary['book_pages']=len(PdfReader(folder/'outputs/book-of-abstracts.pdf').pages);summary['proceedings_pages']=len(PdfReader(folder/'outputs/proceedings.pdf').pages)
p.write_text(json.dumps(summary,indent=2)+'\n');print('Verified five successful scheduled workflows, issue evidence, audit records and artifact hashes')
