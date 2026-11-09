from sqlalchemy import select
from .db import Session,Paper,Version,Audit,Enrollment,Conference

def process(vid):
    with Session() as s:
        v=s.get(Version,vid)
        if not v:return {'missing':vid}
        if v.state=='Complete':return {'complete':vid}
        v.state='Processing';v.result={};v.error='';p=s.get(Paper,v.paper_id)
        if p.latest==v.number:p.status='Processing'
        enrollment=s.scalar(select(Enrollment).where(Enrollment.paper_id==p.id))
        if enrollment:
            from .lifecycle import transition
            transition(s,enrollment,'Revalidation' if v.number>1 else 'Processing',v.number)
        s.commit()
        try:
            from .documents import inspect_document
            from .review import review
            document=inspect_document(v.path)
            enrollment=s.scalar(select(Enrollment).where(Enrollment.paper_id==p.id))
            conference=s.get(Conference,enrollment.conference_id) if enrollment else None
            config=conference.config['profile'] if conference else None
            issues,checks=review(document,p.profile,p.id,config)
            for item in issues:item['version']=v.number
            previous=s.scalar(select(Version).where(Version.paper_id==p.id,Version.number==v.number-1))
            old={i['fingerprint'] for i in (previous.result or {}).get('issues',[])} if previous else set()
            current={i['fingerprint'] for i in issues}
            from .review import profile_path
            import json
            p=s.get(Paper,v.paper_id,populate_existing=True,with_for_update=True)
            v.result={'profile_snapshot':config or json.loads(profile_path(p.profile).read_text()),'document':document,'issues':issues,'checks':checks,'comparison':{'resolved':sorted(old-current),'new':sorted(current-old),'remaining':sorted(old&current)}}
            retry_review=any(c.get('check')=='AI proofreading' and c.get('status')=='failed' for c in checks)
            v.state='Review Incomplete' if retry_review else 'Complete';v.error=''
            if p.latest==v.number:p.status='Needs Correction' if any(i['severity']=='error' for i in issues) else 'Under Review'
            s.add(Audit(paper_id=p.id,action='validated',details={'version':v.number,'issues':len(issues)}))
        except Exception as e:
            p=s.get(Paper,v.paper_id,populate_existing=True,with_for_update=True)
            v.state='Failed';v.error=(str(e)[:1500] if isinstance(e,(ValueError,TimeoutError)) else type(e).__name__)
            if p.latest==v.number:p.status='Needs Correction'
        s.commit()
        return {'version_id':vid,'state':v.state,'retryable_review':v.state=='Review Incomplete'}
