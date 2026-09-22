"""Basic operational reporting. Nothing here is stored — every number is
computed live from current data, so there's no report table to keep in sync."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Board, Company, Configuration, Domain, SSLCertificate, Status, Ticket,
    TimeEntry, User,
)
from app.security import current_user
from app.templating import templates

router = APIRouter()

EXPIRING_WITHIN_DAYS = 60


@router.get("/reports", response_class=HTMLResponse)
def reports_index(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    horizon = today + timedelta(days=EXPIRING_WITHIN_DAYS)

    # Open tickets by board
    open_by_board = db.execute(
        select(Board.name, func.count(Ticket.id))
        .join(Ticket, Ticket.board_id == Board.id)
        .join(Status, Ticket.status_id == Status.id)
        .where(Status.is_closed.is_(False))
        .group_by(Board.name)
        .order_by(Board.sort_order)
    ).all()

    tickets_closed_7d = db.scalar(
        select(func.count(Ticket.id)).where(Ticket.closed_at >= week_ago)
    ) or 0
    tickets_closed_30d = db.scalar(
        select(func.count(Ticket.id)).where(Ticket.closed_at >= month_ago)
    ) or 0
    tickets_opened_7d = db.scalar(
        select(func.count(Ticket.id)).where(Ticket.created_at >= week_ago)
    ) or 0

    # Time logged this week, by tech: total vs billable minutes. Aggregated
    # in Python rather than SQL since the dataset is small and this avoids
    # a boolean-to-integer CAST that isn't portable across databases.
    week_entries = db.execute(
        select(User.full_name, TimeEntry.minutes, TimeEntry.billable)
        .join(User, TimeEntry.user_id == User.id)
        .where(TimeEntry.work_date >= week_ago)
    ).all()
    tech_totals: dict[str, dict[str, int]] = {}
    for full_name, minutes, billable in week_entries:
        row = tech_totals.setdefault(full_name, {"total": 0, "billable": 0})
        row["total"] += minutes
        if billable:
            row["billable"] += minutes
    time_by_tech = sorted(
        ({"name": name, **vals} for name, vals in tech_totals.items()),
        key=lambda r: r["name"],
    )

    # Unbilled billable hours by company
    unbilled_rows = db.execute(
        select(Company.name, func.sum(TimeEntry.minutes))
        .join(Ticket, TimeEntry.ticket_id == Ticket.id)
        .join(Company, Ticket.company_id == Company.id)
        .where(TimeEntry.billable.is_(True), TimeEntry.invoiced_on.is_(None))
        .group_by(Company.name)
        .order_by(Company.name)
    ).all()

    # Expiring soon: domains, SSL certs, configuration warranties
    expiring: list[dict] = []
    for name, company_name, expires_on in db.execute(
        select(Domain.domain_name, Company.name, Domain.expires_on)
        .join(Company, Domain.company_id == Company.id)
        .where(Domain.expires_on.is_not(None), Domain.expires_on <= horizon)
    ).all():
        expiring.append({"kind": "Domain", "name": name, "company": company_name, "expires_on": expires_on})
    for name, company_name, expires_on in db.execute(
        select(SSLCertificate.common_name, Company.name, SSLCertificate.expires_on)
        .join(Company, SSLCertificate.company_id == Company.id)
        .where(SSLCertificate.expires_on.is_not(None), SSLCertificate.expires_on <= horizon)
    ).all():
        expiring.append({"kind": "SSL Certificate", "name": name, "company": company_name, "expires_on": expires_on})
    for name, company_name, expires_on in db.execute(
        select(Configuration.name, Company.name, Configuration.warranty_expires_on)
        .join(Company, Configuration.company_id == Company.id)
        .where(
            Configuration.warranty_expires_on.is_not(None),
            Configuration.warranty_expires_on <= horizon,
        )
    ).all():
        expiring.append({"kind": "Warranty", "name": name, "company": company_name, "expires_on": expires_on})
    expiring.sort(key=lambda r: r["expires_on"])

    return templates.TemplateResponse(
        request, "reports/index.html",
        {
            "user": user,
            "open_by_board": open_by_board,
            "tickets_closed_7d": tickets_closed_7d,
            "tickets_closed_30d": tickets_closed_30d,
            "tickets_opened_7d": tickets_opened_7d,
            "time_by_tech": time_by_tech,
            "unbilled_rows": unbilled_rows,
            "expiring": expiring,
            "expiring_within_days": EXPIRING_WITHIN_DAYS,
            "today": today,
        },
    )
