"""Minimal Postgres job queue.

Redis would work too, but on a 4GB NAS one less container matters more than
the throughput difference. At MSP volumes this handles far more than needed.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Job


def enqueue(
    db: Session,
    job_type: str,
    payload: dict | None = None,
    delay_seconds: int = 0,
) -> Job:
    job = Job(
        job_type=job_type,
        payload=payload or {},
        run_at=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
    )
    db.add(job)
    db.commit()
    return job


def claim_next(db: Session, worker_id: str) -> Job | None:
    """Claim one due job atomically. SKIP LOCKED means concurrent workers
    never fight over the same row."""
    row = db.execute(
        text(
            """
            SELECT id FROM jobs
            WHERE status = 'queued' AND run_at <= now()
            ORDER BY run_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        )
    ).first()
    if not row:
        db.rollback()
        return None

    job = db.scalar(select(Job).where(Job.id == row[0]))
    job.status = "running"
    job.locked_at = datetime.now(timezone.utc)
    job.locked_by = worker_id
    job.attempts += 1
    db.commit()
    return job


def complete(db: Session, job: Job) -> None:
    job.status = "done"
    job.finished_at = datetime.now(timezone.utc)
    job.last_error = None
    db.commit()


def fail(db: Session, job: Job, error: str, max_attempts: int) -> None:
    job.last_error = error[:4000]
    if job.attempts >= max_attempts:
        job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
    else:
        # Exponential backoff, capped at 10 minutes.
        backoff = min(600, 15 * (2 ** (job.attempts - 1)))
        job.status = "queued"
        job.run_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
        job.locked_at = None
        job.locked_by = None
    db.commit()
