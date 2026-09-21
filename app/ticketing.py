"""Ticket-creation helpers shared by the manual "New ticket" route, the
email connector, and (in Phase 2) the NinjaRMM alert poller.

Keeping this in one place means every ticket source gets the same number
format and the same default board/status resolution.
"""

from datetime import date, datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Board, Status, Ticket, TicketNote


def claim_ticket_number(db: Session, year: int | None = None) -> str:
    """Atomic upsert: never returns the same number twice, even under
    concurrent callers, without taking an explicit row lock."""
    year = year or datetime.now(timezone.utc).year
    seq = db.execute(
        text(
            """
            INSERT INTO ticket_counters (year, next_seq)
            VALUES (:year, 1)
            ON CONFLICT (year)
            DO UPDATE SET next_seq = ticket_counters.next_seq + 1
            RETURNING next_seq
            """
        ),
        {"year": year},
    ).scalar_one()
    db.commit()
    yy = str(year)[-2:]
    return f"{yy}{str(seq).zfill(3)}"


def default_status_for_board(db: Session, board_id: int) -> Status:
    return db.scalar(
        select(Status)
        .where(Status.board_id == board_id, Status.is_closed.is_(False))
        .order_by(Status.sort_order)
    )


def board_by_slug(db: Session, slug: str) -> Board | None:
    return db.scalar(select(Board).where(Board.slug == slug))


def create_ticket(
    db: Session,
    *,
    company_id: int,
    board_id: int,
    subject: str,
    source: str,
    contact_id: int | None = None,
    configuration_id: int | None = None,
    priority: str = "normal",
    initial_note: str | None = None,
    initial_note_is_email: bool = False,
    status_id: int | None = None,
) -> Ticket:
    status = None
    if status_id:
        status = db.get(Status, status_id)
    if status is None:
        status = default_status_for_board(db, board_id)
    if status is None:
        raise ValueError(f"board {board_id} has no open status to place a new ticket in")

    ticket = Ticket(
        number=claim_ticket_number(db),
        company_id=company_id,
        contact_id=contact_id,
        configuration_id=configuration_id,
        board_id=board_id,
        status_id=status.id,
        subject=subject[:255],
        priority=priority,
        source=source,
    )
    db.add(ticket)
    db.flush()  # assigns ticket.id for the note FK below

    if initial_note:
        db.add(
            TicketNote(
                ticket_id=ticket.id,
                note_type="discussion",
                body=initial_note,
                is_inbound_email=initial_note_is_email,
            )
        )

    db.commit()
    return ticket
