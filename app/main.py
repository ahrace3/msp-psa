from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.db import get_db
from app.models import Company, Configuration, Contact, User
from app.routes import auth, companies, configurations, contacts
from app.security import current_user
from app.templating import templates

app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="psa_session",
    max_age=60 * 60 * 12,
    same_site="lax",
    https_only=False,  # flip to True once behind Tailscale HTTPS or a proxy
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(contacts.router)
app.include_router(configurations.router)


@app.exception_handler(StarletteHTTPException)
async def redirect_unauthenticated(request: Request, exc: StarletteHTTPException):
    """current_user raises a 307 with a Location header when there is no
    session. Turn that into a real redirect."""
    location = (exc.headers or {}).get("Location")
    if exc.status_code == 307 and location:
        return RedirectResponse(location, status_code=303)
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status": exc.status_code, "detail": exc.detail},
        status_code=exc.status_code,
    )


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    counts = {
        "companies": db.scalar(
            select(func.count(Company.id)).where(Company.status == "active")
        ),
        "contacts": db.scalar(
            select(func.count(Contact.id)).where(Contact.is_active.is_(True))
        ),
        "licensed": db.scalar(
            select(func.count(Contact.id)).where(Contact.is_licensed.is_(True))
        ),
        "configurations": db.scalar(
            select(func.count(Configuration.id)).where(
                Configuration.status == "active"
            )
        ),
    }
    recent = db.scalars(
        select(Company).order_by(Company.created_at.desc()).limit(8)
    ).all()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user, "counts": counts, "recent": recent},
    )
