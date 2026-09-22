from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import (
    Board, Company, Configuration, Contact, Status, Ticket, TicketNote,
    TimeEntry, User,
)
from app.security import current_user
from app.templating import templates
from app.ticketing import create_ticket, default_status_for_board, type_tree

router = APIRouter()

PRIORITIES = ["low", "normal", "high", "urgent"]


def _boards_with_open_counts(db: Session):
    open_counts = dict(
        db.execute(
            select(Ticket.board_id, func.count(Ticket.id))
            .join(Status, Ticket.status_id == Status.id)
            .where(Status.is_closed.is_(False))
            .group_by(Ticket.board_id)
        ).all()
    )
    boards = db.scalars(
        select(Board).where(Board.is_active.is_(True)).order_by(Board.sort_order)
    ).all()
    return [(b, open_counts.get(b.id, 0)) for b in boards]


# ---------------------------------------------------------------- boards --

@router.get("/boards", response_class=HTMLResponse)
def list_boards(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return templates.TemplateResponse(
        request, "boards/index.html",
        {"user": user, "boards": _boards_with_open_counts(db)},
    )


@router.get("/boards/{slug}", response_class=HTMLResponse)
def board_view(
    slug: str,
    request: Request,
    show_closed: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    board = db.scalar(select(Board).where(Board.slug == slug))
    if not board:
        return RedirectResponse("/boards", status_code=303)

    stmt = (
        select(Ticket)
        .options(joinedload(Ticket.company), joinedload(Ticket.status), joinedload(Ticket.assigned_user))
        .where(Ticket.board_id == board.id)
    )
    if not show_closed:
        stmt = stmt.join(Status, Ticket.status_id == Status.id).where(Status.is_closed.is_(False))
    tickets = db.scalars(stmt.order_by(Ticket.updated_at.desc())).all()

    columns: dict[int, list[Ticket]] = {s.id: [] for s in board.statuses}
    for t in tickets:
        columns.setdefault(t.status_id, []).append(t)

    return templates.TemplateResponse(
        request, "boards/detail.html",
        {
            "user": user, "board": board, "columns": columns,
            "boards": _boards_with_open_counts(db), "show_closed": show_closed,
        },
    )


# --------------------------------------------------------------- tickets --

@router.get("/tickets", response_class=HTMLResponse)
def list_tickets(
    request: Request,
    q: str = "",
    board_id: int | None = None,
    show_closed: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = (
        select(Ticket)
        .options(
            joinedload(Ticket.company), joinedload(Ticket.board),
            joinedload(Ticket.status), joinedload(Ticket.assigned_user),
        )
    )
    if board_id:
        stmt = stmt.where(Ticket.board_id == board_id)
    if not show_closed:
        stmt = stmt.join(Status, Ticket.status_id == Status.id).where(Status.is_closed.is_(False))
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.join(Company, Ticket.company_id == Company.id).where(
            or_(
                func.lower(Ticket.subject).like(term),
                func.lower(Ticket.number).like(term),
                func.lower(Company.name).like(term),
                Ticket.notes.any(func.lower(TicketNote.body).like(term)),
            )
        )
    tickets = db.scalars(stmt.order_by(Ticket.updated_at.desc()).limit(200)).all()
    boards = db.scalars(select(Board).order_by(Board.sort_order)).all()

    template = "tickets/_rows.html" if request.headers.get("HX-Request") else "tickets/list.html"
    return templates.TemplateResponse(
        request, template,
        {"user": user, "tickets": tickets, "boards": boards, "q": q,
         "board_id": board_id, "show_closed": show_closed},
    )


@router.get("/tickets/new", response_class=HTMLResponse)
def new_ticket(
    request: Request,
    company_id: int | None = None,
    board_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    companies = db.scalars(select(Company).order_by(Company.name)).all()
    boards = db.scalars(select(Board).where(Board.is_active.is_(True)).order_by(Board.sort_order)).all()
    contacts = configs = []
    if company_id:
        contacts = db.scalars(
            select(Contact).where(Contact.company_id == company_id).order_by(Contact.last_name)
        ).all()
        configs = db.scalars(
            select(Configuration).where(Configuration.company_id == company_id).order_by(Configuration.name)
        ).all()
    return templates.TemplateResponse(
        request, "tickets/form.html",
        {
            "user": user, "companies": companies, "boards": boards,
            "contacts": contacts, "configurations": configs,
            "preselect_company": company_id, "preselect_board": board_id,
            "priorities": PRIORITIES, "types": type_tree(db),
        },
    )


@router.post("/tickets/new")
async def create_ticket_route(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    form = await request.form()
    contact_id = form.get("contact_id")
    configuration_id = form.get("configuration_id")
    type_id = form.get("type_id")
    subtype_id = form.get("subtype_id")
    item_id = form.get("item_id")

    ticket = create_ticket(
        db,
        company_id=int(form["company_id"]),
        board_id=int(form["board_id"]),
        subject=form.get("subject", "").strip() or "(no subject)",
        source="manual",
        contact_id=int(contact_id) if contact_id else None,
        configuration_id=int(configuration_id) if configuration_id else None,
        priority=form.get("priority") or "normal",
        initial_note=(form.get("initial_note") or "").strip() or None,
        type_id=int(type_id) if type_id else None,
        subtype_id=int(subtype_id) if subtype_id else None,
        item_id=int(item_id) if item_id else None,
    )
    ticket.assigned_user_id = user.id
    db.commit()
    return RedirectResponse(f"/tickets/{ticket.id}", status_code=303)


@router.get("/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_detail(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    ticket = db.scalar(
        select(Ticket)
        .options(
            joinedload(Ticket.company), joinedload(Ticket.contact),
            joinedload(Ticket.configuration), joinedload(Ticket.board),
            joinedload(Ticket.status), joinedload(Ticket.assigned_user),
        )
        .where(Ticket.id == ticket_id)
    )
    if not ticket:
        return RedirectResponse("/tickets", status_code=303)

    notes = db.scalars(
        select(TicketNote).where(TicketNote.ticket_id == ticket_id).order_by(TicketNote.created_at)
    ).all()
    time_entries = db.scalars(
        select(TimeEntry).where(TimeEntry.ticket_id == ticket_id).order_by(TimeEntry.work_date.desc())
    ).all()
    total_minutes = sum(t.minutes for t in time_entries)

    techs = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)).all()
    board_statuses = ticket.board.statuses

    return templates.TemplateResponse(
        request, "tickets/detail.html",
        {
            "user": user, "ticket": ticket, "notes": notes,
            "time_entries": time_entries, "total_minutes": total_minutes,
            "techs": techs, "statuses": board_statuses,
            "priorities": PRIORITIES, "today": date.today().isoformat(),
            "types": type_tree(db),
        },
    )


@router.post("/tickets/{ticket_id}/notes")
async def add_note(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    form = await request.form()
    body = (form.get("body") or "").strip()
    if body:
        db.add(
            TicketNote(
                ticket_id=ticket_id,
                user_id=user.id,
                is_discussion=form.get("is_discussion") == "on",
                is_internal=form.get("is_internal") == "on",
                is_resolution=form.get("is_resolution") == "on",
                body=body,
            )
        )
        ticket = db.get(Ticket, ticket_id)
        ticket.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)


@router.post("/tickets/{ticket_id}/time")
async def add_time_entry(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    form = await request.form()
    hours = float(form.get("hours") or 0)
    minutes = round(hours * 60)
    if minutes > 0:
        db.add(
            TimeEntry(
                ticket_id=ticket_id,
                user_id=user.id,
                work_date=date.fromisoformat(form.get("work_date")) if form.get("work_date") else date.today(),
                minutes=minutes,
                billable=form.get("billable") == "on",
                note=(form.get("note") or "").strip() or None,
            )
        )
        db.commit()
    return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)


@router.post("/tickets/{ticket_id}/update")
async def update_ticket(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    ticket = db.get(Ticket, ticket_id)
    form = await request.form()

    status_id = int(form["status_id"])
    new_status = db.get(Status, status_id)
    ticket.status_id = status_id
    ticket.closed_at = datetime.utcnow() if new_status and new_status.is_closed else None

    ticket.priority = form.get("priority") or ticket.priority
    assigned = form.get("assigned_user_id")
    ticket.assigned_user_id = int(assigned) if assigned else None

    type_id = form.get("type_id")
    subtype_id = form.get("subtype_id")
    item_id = form.get("item_id")
    ticket.type_id = int(type_id) if type_id else None
    ticket.subtype_id = int(subtype_id) if subtype_id else None
    ticket.item_id = int(item_id) if item_id else None

    db.commit()
    return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)
