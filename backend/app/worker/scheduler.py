"""Periodic jobs. Run one instance: `python -m app.worker.scheduler`."""

import logging
import time

from ..logging_setup import configure_logging
from . import tasks

JOBS = [  # (every seconds, job)
    (300, tasks.settle_rewards),
    (3600, tasks.expire_demands),
    (3600, tasks.freshness_sweep),
    (6 * 3600, tasks.recompute_all),
]


def main() -> None:
    configure_logging()
    log = logging.getLogger("bizyukti.scheduler")
    last = {job.__name__: 0.0 for _, job in JOBS}
    log.info("scheduler started")
    while True:
        now = time.time()
        for every, job in JOBS:
            if now - last[job.__name__] >= every:
                last[job.__name__] = now
                try:
                    log.info("job %s -> %s", job.__name__, job())
                except Exception:
                    log.exception("job %s failed", job.__name__)
        time.sleep(15)


if __name__ == "__main__":
    main()
