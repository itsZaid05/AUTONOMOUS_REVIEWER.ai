from sqlalchemy import select
from .db import Session,Paper,Version,Audit

def process(vid):
    with Session() as s:
        v=s.get(Version,vid)
        if not v:return {'missing':vid}
        if v.state=='Complete':return {'complete':vid}
        v.state='Processing';p=s.get(Paper,v.paper_id)
        if p.latest==v.number:p.status='Processing'
        s.commit()
        try:
            from .documents import inspect_document
            from .review import review
            document=inspect_document(v.path)
            issues,checks=review(document,p.profile,p.id)
            previous=s.scalar(select(Version).where(Version.paper_id==p.id,Version.number==v.number-1))
            old={i['fingerprint'] for i in (previous.result or {}).get('issues',[])} if previous else set()
            current={i['fingerprint'] for i in issues}
            from .review import profile_path
            import json
            p=s.get(Paper,v.paper_id,populate_existing=True,with_for_update=True)
            v.result={'profile_snapshot':json.loads(profile_path(p.profile).read_text()),'document':document,'issues':issues,'checks':checks,'comparison':{'resolved':sorted(old-current),'new':sorted(current-old),'remaining':sorted(old&current)}}
            v.state='Complete';v.error=''
            if p.latest==v.number:p.status='Needs Correction' if any(i['severity']=='error' for i in issues) else 'Under Review'
            s.add(Audit(paper_id=p.id,action='validated',details={'version':v.number,'issues':len(issues)}))
        except Exception as e:
            p=s.get(Paper,v.paper_id,populate_existing=True,with_for_update=True)
            v.state='Failed';v.error=str(e)[:2000]
            if p.latest==v.number:p.status='Needs Correction'
        s.commit()
        return {'version_id':vid,'state':v.state}
