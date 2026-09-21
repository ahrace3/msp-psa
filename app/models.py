"""Phase 0 schema.

Object names deliberately mirror ConnectWise Manage so the mental model
transfers: Company > Contact > Configuration. Tickets, agreements and
invoices arrive in later phases and hang off these same keys.
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(TimestampMixin, Base):
    """An internal tech. Named User rather than Tech because techs, dispatchers
    and (later) client portal logins all live here with different roles."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="admin", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Short code, CW-style. Used in ticket refs and invoice lines.
    identifier: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)

    phone: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(255))
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(40))
    postal_code: Mapped[str | None] = mapped_column(String(20))

    # Integration keys. Each one is the join point for a later phase.
    ninja_org_id: Mapped[str | None] = mapped_column(String(64), index=True)
    m365_tenant_id: Mapped[str | None] = mapped_column(String(64), index=True)
    gsuite_domain: Mapped[str | None] = mapped_column(String(255), index=True)
    qbo_customer_id: Mapped[str | None] = mapped_column(String(64), index=True)

    notes: Mapped[str | None] = mapped_column(Text)

    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    configurations: Mapped[list["Configuration"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class Contact(TimestampMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("company_id", "email", name="uq_contact_company_email"),
        Index("ix_contacts_external", "license_source", "external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    title: Mapped[str | None] = mapped_column(String(120))

    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Billing-relevant. is_licensed drives per-user agreement counts later;
    # billable_user lets you exclude shared mailboxes and service accounts.
    is_licensed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    billable_user: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # manual | m365 | gsuite
    license_source: Mapped[str] = mapped_column(
        String(16), default="manual", nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(String(128))
    upn: Mapped[str | None] = mapped_column(String(255), index=True)

    notes: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="contacts")

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Configuration(TimestampMixin, Base):
    """A managed device or system. Populated by hand now, by the NinjaRMM
    sync in Phase 2."""

    __tablename__ = "configurations"
    __table_args__ = (
        UniqueConstraint("ninja_device_id", name="uq_config_ninja_device"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # workstation | server | firewall | switch | nas | printer | other
    config_type: Mapped[str] = mapped_column(
        String(32), default="workstation", nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)

    manufacturer: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(120))
    serial_number: Mapped[str | None] = mapped_column(String(120), index=True)
    operating_system: Mapped[str | None] = mapped_column(String(160))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    last_logged_in_user: Mapped[str | None] = mapped_column(String(255))

    billable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    ninja_device_id: Mapped[str | None] = mapped_column(String(64), index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    warranty_expires_on: Mapped[date | None] = mapped_column(Date)

    notes: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="configurations")
    contact: Mapped[Contact | None] = relationship()


class Job(Base):
    """Postgres-backed job queue. Claimed with FOR UPDATE SKIP LOCKED so
    multiple workers stay safe without Redis."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claimable", "status", "run_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # queued | running | done | failed
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)

    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SyncRun(Base):
    """One row per integration sync attempt. This is your audit trail when a
    client asks why their user count changed."""

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
