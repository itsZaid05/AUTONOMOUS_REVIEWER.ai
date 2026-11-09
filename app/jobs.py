from celery import Celery
from redis.exceptions import RedisError
from .settings import settings
queue=Celery('paperflow',broker=settings.redis_url,backend=settings.redis_url)
queue.conf.update(task_track_started=True,worker_prefetch_multiplier=1,task_acks_late=True,task_time_limit=settings.job_timeout_seconds)
@queue.task(bind=True,name='paperflow.validate',autoretry_for=(ConnectionError,RedisError,),retry_backoff=True,max_retries=3)
def validate(self,version_id):
    from .processing import process
    from redis import Redis
    lock=Redis.from_url(settings.redis_url).lock('validation:'+version_id,timeout=settings.job_timeout_seconds+60,blocking_timeout=1)
    if not lock.acquire(blocking=False):return {'already_processing':version_id}
    try:
        result=process(version_id)
        if result.get('retryable_review'):
            if self.request.retries<3:raise self.retry(countdown=30,max_retries=3)
            from .db import Session,Version
            with Session() as session:
                version=session.get(Version,version_id);version.state='Complete';session.commit()
            result['state']='Complete';result['ai_review_failed']=True
        return result
    finally:lock.release()
