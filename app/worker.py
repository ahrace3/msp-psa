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

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.integrations import graph
from app.models import Company, Contact, EmailMessage, Status, Ticket, TicketNote
from app.queue import claim_next, complete, enqueue, fail
from app.ticketing import board_by_slug, create_ticket, default_status_for_board

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
    "email_poll": settings.email_poll_seconds,
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


@handler("email_poll")
def _email_poll(db, payload: dict) -> None:
    """Pull unread mail from the shared mailbox. New senders become new
    tickets on the Triage board; a subject carrying "[#26001]" threads onto
    that ticket instead. Every message is recorded in email_messages before
    being marked read, so a crash mid-batch just reprocesses safely."""
    if not (settings.graph_tenant_id and settings.graph_client_id and settings.graph_client_secret):
        log.debug("email_poll skipped: Graph credentials not configured")
        return

    token = graph.get_access_token()
    mailbox = settings.graph_mailbox
    messages = graph.fetch_unread(token, mailbox)
    if not messages:
        return

    log.info("email_poll: %d unread message(s) in %s", len(messages), mailbox)

    for msg in messages:
        graph_id = msg["id"]
        if db.scalar(select(EmailMessage).where(EmailMessage.graph_id == graph_id)):
            graph.mark_read(token, mailbox, graph_id)
            continue

        sender = (msg.get("from") or {}).get("emailAddress") or {}
        from_email = (sender.get("address") or "").strip().lower()
        from_name = sender.get("name")
        subject = msg.get("subject") or "(no subject)"
        body = graph.clean_body(msg)

        received_raw = msg.get("receivedDateTime")
        received_at = None
        if received_raw:
            try:
                received_at = datetime.fromisoformat(received_raw.replace("Z", "+00:00"))
            except ValueError:
                received_at = None

        record = EmailMessage(
            graph_id=graph_id,
            mailbox=mailbox,
            from_email=from_email or None,
            from_name=from_name,
            subject=subject,
            internet_message_id=msg.get("internetMessageId"),
            received_at=received_at,
        )

        ticket_number = graph.extract_ticket_number(subject)
        existing_ticket = None
        if ticket_number:
            existing_ticket = db.scalar(select(Ticket).where(Ticket.number == ticket_number))

        try:
            if existing_ticket:
                db.add(
                    TicketNote(
                        ticket_id=existing_ticket.id,
                        is_discussion=True,
                        body=body,
                        is_inbound_email=True,
                    )
                )
                # A reply on a closed ticket means the issue isn't actually
                # resolved — reopen it rather than silently losing the note.
                if existing_ticket.status.is_closed:
                    reopened = default_status_for_board(db, existing_ticket.board_id)
                    if reopened:
                        existing_ticket.status_id = reopened.id
                        existing_ticket.closed_at = None
                record.ticket_id = existing_ticket.id
                record.outcome = "matched"
            else:
                contact = None
                company = None
                if from_email:
                    contact = db.scalar(
                        select(Contact).where(Contact.email.ilike(from_email))
                    )
                    if contact:
                        company = contact.company

                if not company:
                    record.outcome = "no_contact_match"
                    record.error = f"No contact on file for {from_email or 'unknown sender'}"
                else:
                    board = board_by_slug(db, settings.default_ticket_board_slug)
                    if not board:
                        record.outcome = "error"
                        record.error = (
                            f"Default board '{settings.default_ticket_board_slug}' not found"
                        )
                    else:
                        ticket = create_ticket(
                            db,
                            company_id=company.id,
                            contact_id=contact.id,
                            board_id=board.id,
                            subject=subject,
                            source="email",
                            initial_note=body,
                            initial_note_is_email=True,
                        )
                        record.ticket_id = ticket.id
                        record.outcome = "created_ticket"

            db.add(record)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - one bad message shouldn't stop the batch
            db.rollback()
            record.outcome = "error"
            record.error = repr(exc)[:2000]
            db.add(record)
            db.commit()
            log.exception("email_poll: failed on message %s", graph_id)

        graph.mark_read(token, mailbox, graph_id)


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
