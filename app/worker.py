"""Background worker.

Phase 0 ships the loop, the handler registry and a heartbeat so the plumbing
is proven before real syncs depend on it. Phase 2 registers ninja_device_sync
and ninja_alert_poll here; Phase 3 adds m365_user_sync and gsuite_user_sync.
"""

import logging
import os
import signal
import socket
import time
from datetime import datetime, timezone

from app.config import settings
from app.db import SessionLocal
from app.models import Job
from app.queue import claim_next, complete, enqueue, fail

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
log = logging.getLogger("worker")

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"

HANDLERS: dict[str, callable] = {}

# Recurring jobs: job_type -> interval seconds. The worker re-enqueues each
# one after it runs, so there is no separate scheduler process.
RECURRING: dict[str, int] = {
    "heartbeat": 300,
}

_running = True


def handler(job_type: str):
    def wrap(fn):
        HANDLERS[job_type] = fn
        return fn

    return wrap


@handler("heartbeat")
def _heartbeat(db, payload: dict) -> None:
    log.info("heartbeat ok at %s", datetime.now(timezone.utc).isoformat())


def _stop(signum, frame):
    global _running
    log.info("shutdown signal received, finishing current job")
    _running = False


def _seed_recurring(db) -> None:
    """Make sure each recurring job has exactly one pending row on boot."""
    for job_type, _ in RECURRING.items():
        pending = (
            db.query(Job)
            .filter(Job.job_type == job_type, Job.status.in_(["queued", "running"]))
            .count()
        )
        if pending == 0:
            enqueue(db, job_type)
            log.info("seeded recurring job %s", job_type)


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("worker %s starting", WORKER_ID)
    db = SessionLocal()
    try:
        _seed_recurring(db)
    finally:
        db.close()

    while _running:
        db = SessionLocal()
        try:
            job = claim_next(db, WORKER_ID)
            if job is None:
                time.sleep(settings.worker_poll_seconds)
                continue

            fn = HANDLERS.get(job.job_type)
            if fn is None:
                fail(db, job, f"no handler registered for {job.job_type}", 1)
                continue

            job_type = job.job_type
            try:
                fn(db, job.payload)
                complete(db, job)
                log.info("job %s (%s) done", job.id, job_type)
            except Exception as exc:  # noqa: BLE001 - worker must not die
                log.exception("job %s (%s) failed", job.id, job_type)
                fail(db, job, repr(exc), settings.worker_max_attempts)

            if job_type in RECURRING:
                enqueue(db, job_type, delay_seconds=RECURRING[job_type])
        finally:
            db.close()

    log.info("worker stopped")


if __name__ == "__main__":
    main()
