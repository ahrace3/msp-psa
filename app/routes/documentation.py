from datetime import date, datetime, timezone
import os
import pathlib
import uuid

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import crypto, relations
from app.db import get_db
from app.integrations import lookups
from app.models import (
    Company, Configuration, Contact, Credential, Document, DocumentAttachment,
    Domain, Location, RelatedItem, SSLCertificate, User,
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
    return db.get(Company, company_id)


def _company_picker_or_target(db: Session, request: Request, user: User, company_id: int | None, target_path: str, title: str):
    """Shared "add without a company preselected" flow. Returns
    (company, response): if company_id is missing, response is the
    company-picker page and company is None — the caller returns response
    immediately. Otherwise company is set and response is None."""
    if company_id is None:
        companies = db.scalars(select(Company).order_by(Company.name)).all()
        return None, templates.TemplateResponse(
            request, "documentation/pick_company.html",
            {"user": user, "title": title, "target_path": target_path, "companies": companies},
        )
    company = db.get(Company, company_id)
    if not company:
        return None, RedirectResponse("/companies", status_code=303)
    return company, None


# -------------------------------------------------------------- locations --

@router.get("/locations/new", response_class=HTMLResponse)
def new_location(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    company = db.get(Company, company_id)
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
        {
            "user": user, "company": loc.company, "location": loc,
            "related_items": relations.get_related(db, "location", loc.id, loc.company_id),
            "pickable_items": relations.pickable_items(db, loc.company_id),
            "self_type": "location", "self_id": loc.id,
            "return_to": f"/locations/{loc.id}/edit",
        },
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

@router.get("/documents/new", response_class=HTMLResponse)
def new_document(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    company = db.get(Company, company_id)
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
        embed_code=(form.get("embed_code") or "").strip() or None,
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
        return RedirectResponse("/companies", status_code=303)
    return templates.TemplateResponse(
        request, "documents/detail.html",
        {
            "user": user, "document": doc, "company": doc.company,
            "related_items": relations.get_related(db, "document", doc.id, doc.company_id),
            "pickable_items": relations.pickable_items(db, doc.company_id),
            "self_type": "document", "self_id": doc.id,
            "return_to": f"/documents/{doc.id}",
        },
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
    doc.embed_code = (form.get("embed_code") or "").strip() or None
    doc.is_pinned = form.get("is_pinned") == "on"
    doc.updated_by_id = user.id
    db.commit()
    return RedirectResponse(f"/documents/{doc.id}", status_code=303)


# ---------------------------------------------------------- attachments --

ATTACHMENTS_ROOT = pathlib.Path(
    os.environ.get("ATTACHMENTS_DIR", "/attachments")
)
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


def _attachment_dir(company_id: int, document_id: int) -> pathlib.Path:
    p = ATTACHMENTS_ROOT / str(company_id) / str(document_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.post("/documents/{document_id}/attachments/upload")
async def upload_attachment(
    document_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    doc = db.get(Document, document_id)
    if not doc:
        return RedirectResponse("/companies", status_code=303)

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return RedirectResponse(f"/documents/{document_id}#attachments", status_code=303)

    ext = pathlib.Path(file.filename or "file").suffix
    stored = f"{uuid.uuid4().hex}{ext}"
    dest = _attachment_dir(doc.company_id, document_id) / stored
    dest.write_bytes(data)

    att = DocumentAttachment(
        document_id=document_id,
        company_id=doc.company_id,
        filename=file.filename or stored,
        stored_filename=stored,
        content_type=file.content_type,
        size_bytes=len(data),
    )
    db.add(att)
    db.commit()
    return RedirectResponse(f"/documents/{document_id}#attachments", status_code=303)


@router.get("/documents/{document_id}/attachments/{attachment_id}/download")
def download_attachment(
    document_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    att = db.get(DocumentAttachment, attachment_id)
    if not att or att.document_id != document_id:
        return RedirectResponse(f"/documents/{document_id}", status_code=303)
    path = _attachment_dir(att.company_id, document_id) / att.stored_filename
    if not path.exists():
        return RedirectResponse(f"/documents/{document_id}", status_code=303)
    return FileResponse(
        path=str(path),
        filename=att.filename,
        media_type=att.content_type or "application/octet-stream",
    )


@router.post("/documents/{document_id}/attachments/{attachment_id}/delete")
def delete_attachment(
    document_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    att = db.get(DocumentAttachment, attachment_id)
    if att and att.document_id == document_id:
        path = _attachment_dir(att.company_id, document_id) / att.stored_filename
        if path.exists():
            path.unlink()
        db.delete(att)
        db.commit()
    return RedirectResponse(f"/documents/{document_id}#attachments", status_code=303)


# ------------------------------------------------------------- credentials --

@router.get("/credentials/new", response_class=HTMLResponse)
def new_credential(
    request: Request,
    company_id: int,
    error: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    company = db.get(Company, company_id)
    if not company:
        return RedirectResponse("/companies", status_code=303)
    locations = db.scalars(select(Location).where(Location.company_id == company.id)).all()
    configs = db.scalars(select(Configuration).where(Configuration.company_id == company.id)).all()
    contacts = db.scalars(select(Contact).where(Contact.company_id == company.id)).all()
    error_messages = {
        "missing_secret": "A password or secret value is required.",
        "no_encryption_key": (
            "Credentials can't be saved yet — CREDENTIAL_ENCRYPTION_KEY isn't set on the "
            "server. Generate one and add it to the web service's environment variables, "
            "then try again."
        ),
    }
    return templates.TemplateResponse(
        request, "credentials/form.html",
        {
            "user": user, "company": company, "credential": None,
            "locations": locations, "configurations": configs, "contacts": contacts,
            "categories": CREDENTIAL_CATEGORIES,
            "error": error_messages.get(error),
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

    try:
        secret_encrypted = crypto.encrypt_secret(secret)
    except crypto.EncryptionNotConfigured:
        return RedirectResponse(
            f"/credentials/new?company_id={company_id}&error=no_encryption_key", status_code=303
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
        secret_encrypted=secret_encrypted,
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
    error: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    cred = db.get(Credential, credential_id)
    locations = db.scalars(select(Location).where(Location.company_id == cred.company_id)).all()
    configs = db.scalars(select(Configuration).where(Configuration.company_id == cred.company_id)).all()
    contacts = db.scalars(select(Contact).where(Contact.company_id == cred.company_id)).all()
    error_messages = {
        "no_encryption_key": (
            "The new password wasn't saved — CREDENTIAL_ENCRYPTION_KEY isn't set on the "
            "server. Everything else on this credential was updated."
        ),
    }
    return templates.TemplateResponse(
        request, "credentials/form.html",
        {
            "user": user, "company": cred.company, "credential": cred,
            "locations": locations, "configurations": configs, "contacts": contacts,
            "categories": CREDENTIAL_CATEGORIES, "error": error_messages.get(error),
            "related_items": relations.get_related(db, "credential", cred.id, cred.company_id),
            "pickable_items": relations.pickable_items(db, cred.company_id),
            "self_type": "credential", "self_id": cred.id,
            "return_to": f"/credentials/{cred.id}/edit",
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
    key_error = False
    if new_secret:  # blank means "leave the stored secret unchanged"
        try:
            cred.secret_encrypted = crypto.encrypt_secret(new_secret)
        except crypto.EncryptionNotConfigured:
            key_error = True

    db.commit()
    if key_error:
        return RedirectResponse(f"/credentials/{credential_id}/edit?error=no_encryption_key", status_code=303)
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


def _apply_whois(domain: Domain, result: dict, overwrite: bool) -> None:
    """overwrite=False (create flow): only fill fields the user left blank.
    overwrite=True (explicit refresh): always take the fresh values."""
    def set_if(attr, value):
        if value is None:
            return
        if overwrite or not getattr(domain, attr):
            setattr(domain, attr, value)

    set_if("registrar", result["registrar"])
    set_if("expires_on", result["expires_on"])
    set_if("created_on", result["created_on"])
    set_if("updated_on", result["updated_on"])
    set_if("name_servers", result["name_servers"])
    set_if("registry_status", result["status"])
    if result["raw"]:
        domain.raw_whois = result["raw"]
    domain.last_whois_check_at = datetime.now(timezone.utc)


@router.get("/domains/new", response_class=HTMLResponse)
def new_domain(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    company = db.get(Company, company_id)
    if not company:
        return RedirectResponse("/companies", status_code=303)
    return templates.TemplateResponse(
        request, "domains/form.html", {"user": user, "company": company, "domain": None, "error": None}
    )


@router.post("/domains/new")
async def create_domain(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    form = await request.form()
    company_id = int(form["company_id"])
    domain_name = (form.get("domain_name") or "").strip()
    domain = Domain(
        company_id=company_id,
        domain_name=domain_name,
        registrar=(form.get("registrar") or "").strip() or None,
        dns_provider=(form.get("dns_provider") or "").strip() or None,
        expires_on=_parse_date(form.get("expires_on")),
        created_on=_parse_date(form.get("created_on")),
        updated_on=_parse_date(form.get("updated_on")),
        name_servers=(form.get("name_servers") or "").strip() or None,
        registry_status=(form.get("registry_status") or "").strip() or None,
        auto_renew=form.get("auto_renew") == "on",
        notes=(form.get("notes") or "").strip() or None,
    )
    # Best-effort auto-fill: only runs when the user left the key fields
    # blank, and a failure here never blocks saving the record.
    if domain_name and not domain.expires_on and not domain.registrar:
        result = lookups.whois_lookup(domain_name)
        if not result["error"]:
            _apply_whois(domain, result, overwrite=False)
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
        request, "domains/form.html",
        {
            "user": user, "company": domain.company, "domain": domain, "error": None,
            "related_items": relations.get_related(db, "domain", domain.id, domain.company_id),
            "pickable_items": relations.pickable_items(db, domain.company_id),
            "self_type": "domain", "self_id": domain.id,
            "return_to": f"/domains/{domain.id}/edit",
        },
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
    domain.created_on = _parse_date(form.get("created_on"))
    domain.updated_on = _parse_date(form.get("updated_on"))
    domain.name_servers = (form.get("name_servers") or "").strip() or None
    domain.registry_status = (form.get("registry_status") or "").strip() or None
    domain.auto_renew = form.get("auto_renew") == "on"
    domain.notes = (form.get("notes") or "").strip() or None
    db.commit()
    return RedirectResponse(f"/companies/{domain.company_id}#domains", status_code=303)


@router.post("/domains/{domain_id}/refresh-whois")
def refresh_domain_whois(
    domain_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    domain = db.get(Domain, domain_id)
    result = lookups.whois_lookup(domain.domain_name)
    if result["error"]:
        domain.last_whois_check_at = datetime.now(timezone.utc)
        db.commit()
    else:
        _apply_whois(domain, result, overwrite=True)
        db.commit()
    return RedirectResponse(f"/domains/{domain_id}/edit", status_code=303)


# ------------------------------------------------------------ certificates

def _apply_ssl(cert: SSLCertificate, result: dict, overwrite: bool) -> None:
    def set_if(attr, value):
        if value is None:
            return
        if overwrite or not getattr(cert, attr):
            setattr(cert, attr, value)

    set_if("issued_by", result["issued_by"])
    set_if("issued_on", result["issued_on"])
    set_if("expires_on", result["expires_on"])
    set_if("serial_number", result["serial_number"])
    set_if("signature_algorithm", result["signature_algorithm"])
    set_if("subject_alt_names", result["subject_alt_names"])
    set_if("fingerprint_sha256", result["fingerprint_sha256"])
    cert.last_checked_at = datetime.now(timezone.utc)


@router.get("/ssl-certificates/new", response_class=HTMLResponse)
def new_ssl_certificate(
    request: Request,
    company_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    company = db.get(Company, company_id)
    if not company:
        return RedirectResponse("/companies", status_code=303)
    return templates.TemplateResponse(
        request, "ssl_certificates/form.html", {"user": user, "company": company, "cert": None, "error": None}
    )


@router.post("/ssl-certificates/new")
async def create_ssl_certificate(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    form = await request.form()
    company_id = int(form["company_id"])
    common_name = (form.get("common_name") or "").strip()
    cert = SSLCertificate(
        company_id=company_id,
        common_name=common_name,
        issued_by=(form.get("issued_by") or "").strip() or None,
        installed_location=(form.get("installed_location") or "").strip() or None,
        issued_on=_parse_date(form.get("issued_on")),
        expires_on=_parse_date(form.get("expires_on")),
        serial_number=(form.get("serial_number") or "").strip() or None,
        signature_algorithm=(form.get("signature_algorithm") or "").strip() or None,
        subject_alt_names=(form.get("subject_alt_names") or "").strip() or None,
        notes=(form.get("notes") or "").strip() or None,
    )
    if common_name and not cert.expires_on and not cert.issued_by:
        result = lookups.ssl_lookup(common_name)
        if not result["error"]:
            _apply_ssl(cert, result, overwrite=False)
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
        request, "ssl_certificates/form.html",
        {
            "user": user, "company": cert.company, "cert": cert, "error": None,
            "related_items": relations.get_related(db, "ssl_certificate", cert.id, cert.company_id),
            "pickable_items": relations.pickable_items(db, cert.company_id),
            "self_type": "ssl_certificate", "self_id": cert.id,
            "return_to": f"/ssl-certificates/{cert.id}/edit",
        },
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
    cert.issued_on = _parse_date(form.get("issued_on"))
    cert.expires_on = _parse_date(form.get("expires_on"))
    cert.serial_number = (form.get("serial_number") or "").strip() or None
    cert.signature_algorithm = (form.get("signature_algorithm") or "").strip() or None
    cert.subject_alt_names = (form.get("subject_alt_names") or "").strip() or None
    cert.notes = (form.get("notes") or "").strip() or None
    db.commit()
    return RedirectResponse(f"/companies/{cert.company_id}#ssl-certificates", status_code=303)


@router.post("/ssl-certificates/{cert_id}/refresh")
def refresh_ssl_certificate(
    cert_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    cert = db.get(SSLCertificate, cert_id)
    result = lookups.ssl_lookup(cert.common_name)
    if result["error"]:
        cert.last_checked_at = datetime.now(timezone.utc)
        db.commit()
    else:
        _apply_ssl(cert, result, overwrite=True)
        db.commit()
    return RedirectResponse(f"/ssl-certificates/{cert_id}/edit", status_code=303)


# ------------------------------------------------------------------ relations

@router.post("/relations/link")
async def create_relation(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    form = await request.form()
    company_id = int(form["company_id"])
    self_type = form["self_type"]
    self_id = int(form["self_id"])
    return_to = form.get("return_to") or f"/companies/{company_id}"
    target = form.get("target") or ""
    if ":" in target:
        target_type, target_id = target.split(":", 1)
        relations.link(db, company_id, self_type, self_id, target_type, int(target_id))
    return RedirectResponse(return_to, status_code=303)


@router.post("/relations/{relation_id}/unlink")
async def delete_relation(
    relation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    form = await request.form()
    return_to = form.get("return_to") or "/companies"
    relations.unlink(db, relation_id)
    return RedirectResponse(return_to, status_code=303)
