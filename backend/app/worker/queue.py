"""Job dispatch. Eager mode (dev/tests) runs jobs inline after the request commits;
otherwise jobs go to RQ on Redis and run in the worker container."""

import logging

from ..config import settings

log = logging.getLogger("bizyukti.queue")
_queue = None


def _rq():
    global _queue
    if _queue is None:
        from redis import Redis
        from rq import Queue

        _queue = Queue("default", connection=Redis.from_url(settings.redis_url))
    return _queue


def enqueue(func, *args, **kwargs) -> None:
    if settings.tasks_eager or not settings.redis_url:
        try:
            func(*args, **kwargs)
        except Exception:
            log.exception("eager job %s failed", getattr(func, "__name__", func))
            if settings.env == "test":
                raise
        return
    _rq().enqueue(func, *args, **kwargs, job_timeout=300)
