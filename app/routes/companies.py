from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, Configuration, Contact, User
from app.security import current_user
from app.templating import templates

router = APIRouter(prefix="/companies")

STATUSES = ["active", "prospect", "inactive"]


def _form_values(form) -> dict:
    keys = [
        "name", "identifier", "status", "phone", "website",
        "address_line1", "address_line2", "city", "state", "postal_code",
        "ninja_org_id", "m365_tenant_id", "gsuite_domain", "qbo_customer_id",
        "notes",
    ]
    return {k: (form.get(k) or "").strip() or None for k in keys}


@router.get("", response_class=HTMLResponse)
def list_companies(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(Company).order_by(Company.name)
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Company.name).like(term),
                func.lower(Company.identifier).like(term),
                func.lower(Company.city).like(term),
            )
        )
    rows = db.scalars(stmt).all()

    template = "companies/_rows.html" if request.headers.get("HX-Request") else "companies/list.html"
    return templates.TemplateResponse(
        request, template, {"user": user, "companies": rows, "q": q}
    )


@router.get("/new", response_class=HTMLResponse)
def new_company(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse(
        request,
        "companies/form.html",
        {"user": user, "company": None, "statuses": STATUSES, "error": None},
    )


@router.post("/new", response_class=HTMLResponse)
async def create_company(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    values = _form_values(await request.form())
    if not values["name"] or not values["identifier"]:
        return templates.TemplateResponse(
            request,
            "companies/form.html",
            {
                "user": user, "company": values, "statuses": STATUSES,
                "error": "Name and identifier are both required.",
            },
            status_code=400,
        )

    values["identifier"] = values["identifier"].upper()
    exists = db.scalar(
        select(Company).where(Company.identifier == values["identifier"])
    )
    if exists:
        return templates.TemplateResponse(
            request,
            "companies/form.html",
            {
                "user": user, "company": values, "statuses": STATUSES,
                "error": f"{values['identifier']} is already used by {exists.name}.",
            },
            status_code=400,
        )

    company = Company(**{**values, "status": values["status"] or "active"})
    db.add(company)
    db.commit()
    return RedirectResponse(f"/companies/{company.id}", status_code=303)


@router.get("/{company_id}", response_class=HTMLResponse)
def company_detail(
    company_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    company = db.get(Company, company_id)
    if not company:
        return RedirectResponse("/companies", status_code=303)

    contacts = db.scalars(
        select(Contact)
        .where(Contact.company_id == company_id)
        .order_by(Contact.is_primary.desc(), Contact.last_name)
    ).all()
    configs = db.scalars(
        select(Configuration)
        .where(Configuration.company_id == company_id)
        .order_by(Configuration.name)
    ).all()

    return templates.TemplateResponse(
        request,
        "companies/detail.html",
        {
            "user": user,
            "company": company,
            "contacts": contacts,
            "configurations": configs,
            "licensed_count": sum(1 for c in contacts if c.is_licensed),
            "billable_configs": sum(1 for c in configs if c.billable),
        },
    )


@router.get("/{company_id}/edit", response_class=HTMLResponse)
def edit_company(
    company_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    company = db.get(Company, company_id)
    return templates.TemplateResponse(
        request,
        "companies/form.html",
        {"user": user, "company": company, "statuses": STATUSES, "error": None},
    )


@router.post("/{company_id}/edit", response_class=HTMLResponse)
async def update_company(
    company_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    company = db.get(Company, company_id)
    values = _form_values(await request.form())
    values["identifier"] = (values["identifier"] or "").upper() or company.identifier
    for key, value in values.items():
        setattr(company, key, value)
    company.status = values["status"] or "active"
    db.commit()
    return RedirectResponse(f"/companies/{company.id}", status_code=303)
