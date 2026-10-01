"""RQ worker entrypoint: `python -m app.worker.worker`."""

from redis import Redis
from rq import Queue, Worker

from ..config import settings
from ..logging_setup import configure_logging


def main() -> None:
    configure_logging()
    conn = Redis.from_url(settings.redis_url)
    Worker([Queue("default", connection=conn)], connection=conn).work(with_scheduler=False)


if __name__ == "__main__":
    main()
