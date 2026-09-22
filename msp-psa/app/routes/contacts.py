from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, Contact, User
from app.security import current_user
from app.templating import templates

router = APIRouter(prefix="/contacts")

TEXT_FIELDS = ["first_name", "last_name", "email", "phone", "title", "upn", "notes"]
BOOL_FIELDS = ["is_primary", "is_active", "is_licensed", "billable_user"]


def _form_values(form) -> dict:
    values = {k: (form.get(k) or "").strip() or None for k in TEXT_FIELDS}
    for k in BOOL_FIELDS:
        values[k] = form.get(k) == "on"
    values["company_id"] = int(form.get("company_id"))
    return values


@router.get("", response_class=HTMLResponse)
def list_contacts(
    request: Request,
    q: str = "",
    company_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = (
        select(Contact, Company)
        .join(Company, Contact.company_id == Company.id)
        .order_by(Company.name, Contact.last_name)
    )
    if company_id:
        stmt = stmt.where(Contact.company_id == company_id)
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Contact.first_name).like(term),
                func.lower(Contact.last_name).like(term),
                func.lower(Contact.email).like(term),
                func.lower(Company.name).like(term),
            )
        )
    rows = db.execute(stmt).all()

    template = "contacts/_rows.html" if request.headers.get("HX-Request") else "contacts/list.html"
    return templates.TemplateResponse(
        request, template, {"user": user, "rows": rows, "q": q}
    )


@router.get("/new", response_class=HTMLResponse)
def new_contact(
    request: Request,
    company_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    companies = db.scalars(select(Company).order_by(Company.name)).all()
    return templates.TemplateResponse(
        request,
        "contacts/form.html",
        {
            "user": user,
            "contact": None,
            "companies": companies,
            "preselect": company_id,
        },
    )


@router.post("/new")
async def create_contact(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    values = _form_values(await request.form())
    values["license_source"] = "manual"
    contact = Contact(**values)
    db.add(contact)
    db.commit()
    return RedirectResponse(f"/companies/{contact.company_id}", status_code=303)


@router.get("/{contact_id}/edit", response_class=HTMLResponse)
def edit_contact(
    contact_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    contact = db.get(Contact, contact_id)
    companies = db.scalars(select(Company).order_by(Company.name)).all()
    return templates.TemplateResponse(
        request,
        "contacts/form.html",
        {
            "user": user,
            "contact": contact,
            "companies": companies,
            "preselect": contact.company_id,
        },
    )


@router.post("/{contact_id}/edit")
async def update_contact(
    contact_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    contact = db.get(Contact, contact_id)
    for key, value in _form_values(await request.form()).items():
        setattr(contact, key, value)
    db.commit()
    return RedirectResponse(f"/companies/{contact.company_id}", status_code=303)
