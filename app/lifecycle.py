"""Audited editorial phases, independent of legacy scheduler states."""
from .db import Audit,now
PHASES={'Ingested','Processing','Corrections Required','Awaiting Revision','Revalidation','Automated Checks Passed','Editorial Exception','Eligible for Draft Book','Final Publication Authorized'}
def transition(session,enrollment,phase,version=None,reason=''):
    if phase not in PHASES:raise ValueError('Unknown editorial phase')
    details=dict(enrollment.details or {})
    if details.get('lifecycle_state')==phase and details.get('lifecycle_version')==version:return
    event={'phase':phase,'version':version,'at':now().isoformat(),'reason':reason}
    details.update(lifecycle_state=phase,lifecycle_version=version,phase_history=[*details.get('phase_history',[]),event])
    enrollment.details=details
    session.add(Audit(paper_id=enrollment.paper_id,action='lifecycle_transition',details=event))
