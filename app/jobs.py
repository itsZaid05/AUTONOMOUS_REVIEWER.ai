from celery import Celery
from redis.exceptions import RedisError
from .settings import settings
queue=Celery('paperflow',broker=settings.redis_url,backend=settings.redis_url)
queue.conf.update(task_track_started=True,worker_prefetch_multiplier=1,task_acks_late=True,task_time_limit=180)
@queue.task(name='paperflow.validate',autoretry_for=(ConnectionError,RedisError,),retry_backoff=True,max_retries=3)
def validate(version_id):
    from .processing import process
    from redis import Redis
    lock=Redis.from_url(settings.redis_url).lock('validation:'+version_id,timeout=240,blocking_timeout=1)
    if not lock.acquire(blocking=False):return {'already_processing':version_id}
    try:return process(version_id)
    finally:lock.release()
