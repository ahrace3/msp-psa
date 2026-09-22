from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import crypto
from app.db import get_db
from app.models import (
    Company, Configuration, Contact, Credential, Document, Domain, Location,
    SSLCertificate, User,
)
from app.security import current_user
from app.templating import templates

router = APIRouter()

# Suggestions only — both fields stay free text so nothing is hardcoded.
DOCUMENT_CATEGORIES = [
    "Network", "Procedure", "Vendor", "Software License", "Onboarding",
    "Disaster Recovery", "Other",
]
CREDENTIAL_CATEGORIES = [
    "Network Device", "Server", "Workstation Local Admin", "Email / M365",
    "Wi-Fi", "Application", "Vendor Portal", "Other",
]


def _company_or_redirect(db: Session, company_id: int):
    company = db.get(Company, company_id)
    return company


# -------------------------------------------------------------- locations --

@router.get("/locations/new", response_class=HTMLResponse)
def new_location(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    company = _company_or_redirect(db, company_id)
    if not company:
        return RedirectResponse("/companies", status_code=303)
    return templates.TemplateResponse(
        request, "locations/form.html",
        {"user": user, "company": company, "location": None},
    )


@router.post("/locations/new")
async def create_location(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    form = await request.form()
    company_id = int(form["company_id"])
    loc = Location(
        company_id=company_id,
        name=(form.get("name") or "").strip() or "Unnamed location",
        is_primary=form.get("is_primary") == "on",
        address_line1=(form.get("address_line1") or "").strip() or None,
        address_line2=(form.get("address_line2") or "").strip() or None,
        city=(form.get("city") or "").strip() or None,
        state=(form.get("state") or "").strip() or None,
        postal_code=(form.get("postal_code") or "").strip() or None,
        phone=(form.get("phone") or "").strip() or None,
        notes=(form.get("notes") or "").strip() or None,
    )
    db.add(loc)
    db.commit()
    return RedirectResponse(f"/companies/{company_id}#locations", status_code=303)


@router.get("/locations/{location_id}/edit", response_class=HTMLResponse)
def edit_location(
    location_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    loc = db.get(Location, location_id)
    return templates.TemplateResponse(
        request, "locations/form.html",
        {"user": user, "company": loc.company, "location": loc},
    )


@router.post("/locations/{location_id}/edit")
async def update_location(
    location_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    loc = db.get(Location, location_id)
    form = await request.form()
    loc.name = (form.get("name") or "").strip() or loc.name
    loc.is_primary = form.get("is_primary") == "on"
    for field in ["address_line1", "address_line2", "city", "state", "postal_code", "phone", "notes"]:
        setattr(loc, field, (form.get(field) or "").strip() or None)
    db.commit()
    return RedirectResponse(f"/companies/{loc.company_id}#locations", status_code=303)


# --------------------------------------------------------------- documents --

@router.get("/documents", response_class=HTMLResponse)
def list_documents(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(Document, Company).join(Company, Document.company_id == Company.id)
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Document.title).like(term),
                func.lower(Document.category).like(term),
                func.lower(Company.name).like(term),
            )
        )
    rows = db.execute(
        stmt.order_by(Document.is_pinned.desc(), Document.updated_at.desc())
    ).all()

    template = "documents/_rows.html" if request.headers.get("HX-Request") else "documents/list.html"
    return templates.TemplateResponse(request, template, {"user": user, "rows": rows, "q": q})


@router.get("/documents/new", response_class=HTMLResponse)
def new_document(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    company = _company_or_redirect(db, company_id)
    if not company:
        return RedirectResponse("/companies", status_code=303)
    return templates.TemplateResponse(
        request, "documents/form.html",
        {"user": user, "company": company, "document": None, "categories": DOCUMENT_CATEGORIES},
    )


@router.post("/documents/new")
async def create_document(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    form = await request.form()
    company_id = int(form["company_id"])
    doc = Document(
        company_id=company_id,
        title=(form.get("title") or "").strip() or "Untitled",
        category=(form.get("category") or "").strip() or None,
        body=form.get("body") or "",
        is_pinned=form.get("is_pinned") == "on",
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(doc)
    db.commit()
    return RedirectResponse(f"/documents/{doc.id}", status_code=303)


@router.get("/documents/{document_id}", response_class=HTMLResponse)
def view_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    doc = db.get(Document, document_id)
    if not doc:
        return RedirectResponse("/documents", status_code=303)
    return templates.TemplateResponse(
        request, "documents/detail.html", {"user": user, "document": doc}
    )


@router.get("/documents/{document_id}/edit", response_class=HTMLResponse)
def edit_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    doc = db.get(Document, document_id)
    return templates.TemplateResponse(
        request, "documents/form.html",
        {"user": user, "company": doc.company, "document": doc, "categories": DOCUMENT_CATEGORIES},
    )


@router.post("/documents/{document_id}/edit")
async def update_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    doc = db.get(Document, document_id)
    form = await request.form()
    doc.title = (form.get("title") or "").strip() or doc.title
    doc.category = (form.get("category") or "").strip() or None
    doc.body = form.get("body") or ""
    doc.is_pinned = form.get("is_pinned") == "on"
    doc.updated_by_id = user.id
    db.commit()
    return RedirectResponse(f"/documents/{doc.id}", status_code=303)


# ------------------------------------------------------------- credentials --

def _masked(cred: Credential) -> dict:
    return {
        "id": cred.id, "name": cred.name, "category": cred.category,
        "username": cred.username, "url": cred.url, "notes": cred.notes,
        "company": cred.company, "location": cred.location,
        "configuration": cred.configuration, "contact": cred.contact,
    }


@router.get("/credentials", response_class=HTMLResponse)
def list_credentials(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(Credential, Company).join(Company, Credential.company_id == Company.id)
    if q:
        term = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Credential.name).like(term),
                func.lower(Credential.username).like(term),
                func.lower(Credential.category).like(term),
                func.lower(Company.name).like(term),
            )
        )
    rows = db.execute(stmt.order_by(Company.name, Credential.name)).all()

    template = "credentials/_rows.html" if request.headers.get("HX-Request") else "credentials/list.html"
    return templates.TemplateResponse(request, template, {"user": user, "rows": rows, "q": q})


@router.get("/credentials/new", response_class=HTMLResponse)
def new_credential(
    request: Request,
    company_id: int,
    error: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    company = _company_or_redirect(db, company_id)
    if not company:
        return RedirectResponse("/companies", status_code=303)
    locations = db.scalars(select(Location).where(Location.company_id == company_id)).all()
    configs = db.scalars(select(Configuration).where(Configuration.company_id == company_id)).all()
    contacts = db.scalars(select(Contact).where(Contact.company_id == company_id)).all()
    return templates.TemplateResponse(
        request, "credentials/form.html",
        {
            "user": user, "company": company, "credential": None,
            "locations": locations, "configurations": configs, "contacts": contacts,
            "categories": CREDENTIAL_CATEGORIES,
            "error": "A password or secret value is required." if error == "missing_secret" else None,
        },
    )


@router.post("/credentials/new")
async def create_credential(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    form = await request.form()
    company_id = int(form["company_id"])
    secret = form.get("secret") or ""

    if not secret:
        return RedirectResponse(
            f"/credentials/new?company_id={company_id}&error=missing_secret", status_code=303
        )

    def _fk(field: str) -> int | None:
        val = form.get(field)
        return int(val) if val else None

    cred = Credential(
        company_id=company_id,
        location_id=_fk("location_id"),
        configuration_id=_fk("configuration_id"),
        contact_id=_fk("contact_id"),
        name=(form.get("name") or "").strip() or "Untitled credential",
        category=(form.get("category") or "").strip() or None,
        username=(form.get("username") or "").strip() or None,
        secret_encrypted=crypto.encrypt_secret(secret),
        url=(form.get("url") or "").strip() or None,
        notes=(form.get("notes") or "").strip() or None,
    )
    db.add(cred)
    db.commit()
    return RedirectResponse(f"/companies/{company_id}#credentials", status_code=303)


@router.get("/credentials/{credential_id}/edit", response_class=HTMLResponse)
def edit_credential(
    credential_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    cred = db.get(Credential, credential_id)
    locations = db.scalars(select(Location).where(Location.company_id == cred.company_id)).all()
    configs = db.scalars(select(Configuration).where(Configuration.company_id == cred.company_id)).all()
    contacts = db.scalars(select(Contact).where(Contact.company_id == cred.company_id)).all()
    return templates.TemplateResponse(
        request, "credentials/form.html",
        {
            "user": user, "company": cred.company, "credential": cred,
            "locations": locations, "configurations": configs, "contacts": contacts,
            "categories": CREDENTIAL_CATEGORIES, "error": None,
        },
    )


@router.post("/credentials/{credential_id}/edit")
async def update_credential(
    credential_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    cred = db.get(Credential, credential_id)
    form = await request.form()

    def _fk(field: str) -> int | None:
        val = form.get(field)
        return int(val) if val else None

    cred.name = (form.get("name") or "").strip() or cred.name
    cred.category = (form.get("category") or "").strip() or None
    cred.username = (form.get("username") or "").strip() or None
    cred.url = (form.get("url") or "").strip() or None
    cred.notes = (form.get("notes") or "").strip() or None
    cred.location_id = _fk("location_id")
    cred.configuration_id = _fk("configuration_id")
    cred.contact_id = _fk("contact_id")

    new_secret = form.get("secret")
    if new_secret:  # blank means "leave the stored secret unchanged"
        cred.secret_encrypted = crypto.encrypt_secret(new_secret)

    db.commit()
    return RedirectResponse(f"/companies/{cred.company_id}#credentials", status_code=303)


@router.get("/credentials/{credential_id}/reveal", response_class=HTMLResponse)
def reveal_credential(
    credential_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Decrypts only on this explicit request — the value is never present
    in the normal company/credential page render."""
    cred = db.get(Credential, credential_id)
    try:
        value = crypto.decrypt_secret(cred.secret_encrypted)
    except (crypto.EncryptionNotConfigured, ValueError) as exc:
        value = f"[{exc}]"
    return templates.TemplateResponse(
        request, "credentials/_revealed.html", {"value": value}
    )


# ------------------------------------------------------------------ domains

def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@router.get("/domains/new", response_class=HTMLResponse)
def new_domain(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    company = _company_or_redirect(db, company_id)
    if not company:
        return RedirectResponse("/companies", status_code=303)
    return templates.TemplateResponse(
        request, "domains/form.html", {"user": user, "company": company, "domain": None}
    )


@router.post("/domains/new")
async def create_domain(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    form = await request.form()
    company_id = int(form["company_id"])
    domain = Domain(
        company_id=company_id,
        domain_name=(form.get("domain_name") or "").strip(),
        registrar=(form.get("registrar") or "").strip() or None,
        dns_provider=(form.get("dns_provider") or "").strip() or None,
        expires_on=_parse_date(form.get("expires_on")),
        auto_renew=form.get("auto_renew") == "on",
        notes=(form.get("notes") or "").strip() or None,
    )
    db.add(domain)
    db.commit()
    return RedirectResponse(f"/companies/{company_id}#domains", status_code=303)


@router.get("/domains/{domain_id}/edit", response_class=HTMLResponse)
def edit_domain(
    domain_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    domain = db.get(Domain, domain_id)
    return templates.TemplateResponse(
        request, "domains/form.html", {"user": user, "company": domain.company, "domain": domain}
    )


@router.post("/domains/{domain_id}/edit")
async def update_domain(
    domain_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    domain = db.get(Domain, domain_id)
    form = await request.form()
    domain.domain_name = (form.get("domain_name") or "").strip() or domain.domain_name
    domain.registrar = (form.get("registrar") or "").strip() or None
    domain.dns_provider = (form.get("dns_provider") or "").strip() or None
    domain.expires_on = _parse_date(form.get("expires_on"))
    domain.auto_renew = form.get("auto_renew") == "on"
    domain.notes = (form.get("notes") or "").strip() or None
    db.commit()
    return RedirectResponse(f"/companies/{domain.company_id}#domains", status_code=303)


# ------------------------------------------------------------ certificates

@router.get("/ssl-certificates/new", response_class=HTMLResponse)
def new_ssl_certificate(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    company = _company_or_redirect(db, company_id)
    if not company:
        return RedirectResponse("/companies", status_code=303)
    return templates.TemplateResponse(
        request, "ssl_certificates/form.html", {"user": user, "company": company, "cert": None}
    )


@router.post("/ssl-certificates/new")
async def create_ssl_certificate(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    form = await request.form()
    company_id = int(form["company_id"])
    cert = SSLCertificate(
        company_id=company_id,
        common_name=(form.get("common_name") or "").strip(),
        issued_by=(form.get("issued_by") or "").strip() or None,
        installed_location=(form.get("installed_location") or "").strip() or None,
        expires_on=_parse_date(form.get("expires_on")),
        notes=(form.get("notes") or "").strip() or None,
    )
    db.add(cert)
    db.commit()
    return RedirectResponse(f"/companies/{company_id}#ssl-certificates", status_code=303)


@router.get("/ssl-certificates/{cert_id}/edit", response_class=HTMLResponse)
def edit_ssl_certificate(
    cert_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    cert = db.get(SSLCertificate, cert_id)
    return templates.TemplateResponse(
        request, "ssl_certificates/form.html", {"user": user, "company": cert.company, "cert": cert}
    )


@router.post("/ssl-certificates/{cert_id}/edit")
async def update_ssl_certificate(
    cert_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    cert = db.get(SSLCertificate, cert_id)
    form = await request.form()
    cert.common_name = (form.get("common_name") or "").strip() or cert.common_name
    cert.issued_by = (form.get("issued_by") or "").strip() or None
    cert.installed_location = (form.get("installed_location") or "").strip() or None
    cert.expires_on = _parse_date(form.get("expires_on"))
    cert.notes = (form.get("notes") or "").strip() or None
    db.commit()
    return RedirectResponse(f"/companies/{cert.company_id}#ssl-certificates", status_code=303)
