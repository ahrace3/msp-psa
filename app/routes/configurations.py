from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import relations
from app.db import get_db
from app.models import Company, Configuration, Contact, User
from app.security import current_user
from app.templating import templates

router = APIRouter(prefix="/configurations")

CONFIG_TYPES = [
    "workstation", "laptop", "server", "firewall", "switch",
    "access_point", "nas", "printer", "ups", "other",
]
STATUSES = ["active", "spare", "retired"]

TEXT_FIELDS = [
    "name", "config_type", "status", "manufacturer", "model", "serial_number",
    "operating_system", "ip_address", "last_logged_in_user", "notes",
]


def _form_values(form) -> dict:
    values = {k: (form.get(k) or "").strip() or None for k in TEXT_FIELDS}
    values["billable"] = form.get("billable") == "on"
    values["company_id"] = int(form.get("company_id"))
    contact_id = form.get("contact_id")
    values["contact_id"] = int(contact_id) if contact_id else None
    warranty = form.get("warranty_expires_on")
    values["warranty_expires_on"] = date.fromisoformat(warranty) if warranty else None
    values["config_type"] = values["config_type"] or "workstation"
    values["status"] = values["status"] or "active"
    return values


@router.get("", response_class=HTMLResponse)
def list_configurations(
    request: Request,
    q: str = "",
    company_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = (
        select(Configuration, Company)
        .join(Company, Configuration.company_id == Company.id)
        .order_by(Company.name, Configuration.name)
    )
    if company_id:
        stmt = stmt.where(Configuration.company_id == company_id)
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Configuration.name).like(term),
                func.lower(Configuration.serial_number).like(term),
                func.lower(Configuration.last_logged_in_user).like(term),
                func.lower(Company.name).like(term),
            )
        )
    rows = db.execute(stmt).all()

    template = (
        "configurations/_rows.html"
        if request.headers.get("HX-Request")
        else "configurations/list.html"
    )
    return templates.TemplateResponse(
        request, template, {"user": user, "rows": rows, "q": q}
    )


@router.get("/new", response_class=HTMLResponse)
def new_configuration(
    request: Request,
    company_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    companies = db.scalars(select(Company).order_by(Company.name)).all()
    contacts = []
    if company_id:
        contacts = db.scalars(
            select(Contact)
            .where(Contact.company_id == company_id)
            .order_by(Contact.last_name)
        ).all()
    return templates.TemplateResponse(
        request,
        "configurations/form.html",
        {
            "user": user, "configuration": None, "companies": companies,
            "contacts": contacts, "preselect": company_id,
            "config_types": CONFIG_TYPES, "statuses": STATUSES,
        },
    )


@router.post("/new")
async def create_configuration(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    config = Configuration(**_form_values(await request.form()))
    db.add(config)
    db.commit()
    return RedirectResponse(f"/companies/{config.company_id}", status_code=303)


@router.get("/{config_id}/edit", response_class=HTMLResponse)
def edit_configuration(
    config_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    config = db.get(Configuration, config_id)
    companies = db.scalars(select(Company).order_by(Company.name)).all()
    contacts = db.scalars(
        select(Contact)
        .where(Contact.company_id == config.company_id)
        .order_by(Contact.last_name)
    ).all()
    return templates.TemplateResponse(
        request,
        "configurations/form.html",
        {
            "user": user, "configuration": config, "companies": companies,
            "contacts": contacts, "preselect": config.company_id,
            "config_types": CONFIG_TYPES, "statuses": STATUSES,
            "related_items": relations.get_related(db, "configuration", config.id, config.company_id),
            "pickable_items": relations.pickable_items(db, config.company_id),
            "self_type": "configuration", "self_id": config.id,
            "company": config.company,
            "return_to": f"/configurations/{config.id}/edit",
        },
    )


@router.post("/{config_id}/edit")
async def update_configuration(
    config_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    config = db.get(Configuration, config_id)
    for key, value in _form_values(await request.form()).items():
        setattr(config, key, value)
    db.commit()
    return RedirectResponse(f"/companies/{config.company_id}", status_code=303)
