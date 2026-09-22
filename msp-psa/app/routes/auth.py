from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import login_user, logout_user, verify_password
from app.templating import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(func.lower(User.email) == email.strip().lower())
    )
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "That email and password don't match an active account."},
            status_code=401,
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    login_user(request, user)
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=303)
