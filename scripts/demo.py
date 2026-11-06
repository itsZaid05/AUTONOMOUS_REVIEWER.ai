"""Real local acceptance run. Uses only local Mailpit recipients; never production SMTP."""
import io,json,time,uuid,zipfile
from pathlib import Path
import httpx,pymupdf
from docx import Document
from dotenv import dotenv_values
cfg=dotenv_values('.env');run=uuid.uuid4().hex[:8]
c=httpx.Client(base_url='http://127.0.0.1:8000',headers={'Authorization':'Bearer '+cfg['ADMIN_TOKEN']},timeout=180)
def request(method,path,**kwargs):
    r=c.request(method,path,**kwargs);r.raise_for_status();return r

def wait(pids,limit=240):
    deadline=time.monotonic()+limit
    while time.monotonic()<deadline:
        details=[request('GET','/papers/'+p).json() for p in pids]
        if all(d['versions'][-1]['state'] in ['Complete','Failed','Queue failed'] for d in details):return details
        time.sleep(.5)
    raise TimeoutError('Jobs did not finish')
start=time.monotonic();ids=[]
for i,f in enumerate(sorted(Path('data/samples').iterdir())):
    content=f.read_bytes()
    # Unique bytes per run preserve genuine duplicates detection.
    if f.suffix=='.docx':
        d=Document(io.BytesIO(content));d.add_paragraph('Run '+run);b=io.BytesIO();d.save(b);content=b.getvalue()
    elif f.suffix=='.pdf':
        d=pymupdf.open(stream=content,filetype='pdf');d.set_metadata({'subject':run});content=d.tobytes();d.close()
    else:
        b=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(content)) as src,zipfile.ZipFile(b,'w') as out:
            for item in src.infolist():out.writestr(item.filename,src.read(item.filename)+('\n% run '+run).encode())
        content=b.getvalue()
    r=request('POST','/submissions',files={'file':(f.name,content)},data={'title':f'Demo paper {i} {run}','authors':f'Author {i}; Test Editor','email':f'author{i}@example.test','affiliation':'Demo University','track':'Demonstration'}).json();ids.append(r['paper_id'])
details=wait(ids);failed=[d for d in details if d['versions'][-1]['state']!='Complete']
result={'run':run,'mixed_format':{'submitted':len(ids),'completed':len(ids)-len(failed),'failed':len(failed),'seconds':round(time.monotonic()-start,2),'errors':[d['versions'][-1]['error'] for d in failed]}}
Path('data/demo-results.json').write_text(json.dumps(result,indent=2))
if failed:raise RuntimeError(result)
message_ids=[]
for d in details:
    pid=d['paper']['id'];vid=d['versions'][-1]['id']
    assert any(i['category']=='writing' for i in d['versions'][-1]['result']['issues'])
    assert request('GET','/versions/'+vid+'/report').content.startswith(b'%PDF')
    mid=request('POST','/papers/'+pid+'/messages').json()['message_id'];message_ids.append(mid)
    assert c.post('/messages/'+mid+'/send').status_code==409
    request('POST','/messages/'+mid+'/approve');request('POST','/messages/'+mid+'/send')
    assert request('POST','/messages/'+mid+'/send').json()['duplicate']
    token=request('POST','/papers/'+pid+'/revision-link').json()['url'].rsplit('/',1)[1]
    # Send an actually corrected, editable manuscript; version format may change.
    doc=Document()
    for t in [d['paper']['title'],'Abstract',f'The experiment {run} evaluates a reproducible workflow.','Keywords: publishing','Introduction','A corrected demonstration manuscript.','References']:
        doc.add_paragraph(t)
    b=io.BytesIO();doc.save(b)
    request('POST','/revise/'+token,files={'file':('revision.docx',b.getvalue())})
revised=wait(ids)
for d in revised:
    assert d['versions'][-1]['state']=='Complete',d
    assert not any(i['category']=='writing' for i in d['versions'][-1]['result']['issues'])
    assert d['versions'][-1]['result']['comparison']['resolved']
    request('POST','/papers/'+d['paper']['id']+'/approve',json={'acknowledge_review':True})
pub=request('POST','/publications',json={'conference':'PaperFlow Demo '+run,'information':'Synthetic manuscripts for functional testing.','paper_ids':ids,'confirm_editorial_approval':True}).json()
for filename in pub['files']:
    content=request('GET','/publications/'+pub['publication_id']+'/'+filename).content
    assert content
    if filename.endswith('.pdf'):assert content.startswith(b'%PDF')
result['cycle']={'revised':len(revised),'emails_sent':len(message_ids),'approved':len(ids),'publication':pub,'seconds':round(time.monotonic()-start,2)}
# Bulk benchmark uses 100 distinct PDFs, actual queue workers and deterministic inspection.
start=time.monotonic();bulk=[];rejected=0
for i in range(100):
    pdf=pymupdf.open();p=pdf.new_page();p.insert_text((60,60),f'Bulk {run} {i}\nAbstract\nThe the test measures ingestion.\nKeywords: bulk\nReferences');content=pdf.tobytes();pdf.close()
    r=c.post('/submissions',files={'file':(f'bulk-{i}.pdf',content)},data={'title':f'Bulk {i}','authors':'Benchmark Author'})
    if r.status_code==200:bulk.append(r.json()['paper_id'])
    else:rejected+=1
outcomes=wait(bulk,limit=240);success=sum(d['versions'][-1]['state']=='Complete' for d in outcomes)
result['bulk']={'attempted':100,'accepted':len(bulk),'rejected':rejected,'completed':success,'failed':len(bulk)-success,'seconds':round(time.monotonic()-start,2),'worker_concurrency':2}
Path('data/demo-results.json').write_text(json.dumps(result,indent=2));Path('DEMO_RESULTS.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
assert success==100
