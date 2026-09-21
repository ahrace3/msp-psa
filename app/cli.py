"""Small admin CLI.

    docker compose exec web python -m app.cli create-admin adam@example.com 'Adam Hilton'
"""

import getpass
import sys

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import User
from app.security import hash_password


def create_admin(email: str, full_name: str) -> None:
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm: ")
    if password != confirm:
        sys.exit("Passwords don't match.")
    if len(password) < 12:
        sys.exit("Use at least 12 characters.")

    db = SessionLocal()
    try:
        existing = db.scalar(
            select(User).where(func.lower(User.email) == email.lower())
        )
        if existing:
            existing.password_hash = hash_password(password)
            existing.is_active = True
            db.commit()
            print(f"Reset password for {email}.")
            return
        db.add(
            User(
                email=email.lower(),
                full_name=full_name,
                password_hash=hash_password(password),
                role="admin",
            )
        )
        db.commit()
        print(f"Created admin {email}.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] != "create-admin":
        sys.exit("Usage: python -m app.cli create-admin <email> <full name>")
    create_admin(sys.argv[2], sys.argv[3])
