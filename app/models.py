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
    locations: Mapped[list["Location"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="Location.is_primary.desc()"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="Document.is_pinned.desc()"
    )
    credentials: Mapped[list["Credential"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="Credential.name"
    )
    domains: Mapped[list["Domain"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="Domain.expires_on"
    )
    ssl_certificates: Mapped[list["SSLCertificate"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="SSLCertificate.expires_on"
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


class Board(TimestampMixin, Base):
    """A ticket board (CW-style). Seeded by migration; editing boards/statuses
    through the UI is not in Phase 1 — change the seed migration for now."""

    __tablename__ = "boards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    statuses: Mapped[list["Status"]] = relationship(
        back_populates="board",
        cascade="all, delete-orphan",
        order_by="Status.sort_order",
    )


class Status(Base):
    __tablename__ = "statuses"
    __table_args__ = (
        UniqueConstraint("board_id", "name", name="uq_status_board_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    board_id: Mapped[int] = mapped_column(
        ForeignKey("boards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Closed statuses stop counting as open work and are what the Phase 2
    # self-heal logic looks for before it will auto-close a ticket.
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    board: Mapped[Board] = relationship(back_populates="statuses")


class TicketCounter(Base):
    """One row per year. Ticket numbers are claimed with an atomic upsert so
    two tickets created at once never collide, without needing a lock."""

    __tablename__ = "ticket_counters"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    next_seq: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class TicketType(Base):
    """Top of the Type > Subtype > Item categorization tree (CW/ITIL-style
    incident classification). Seeded by migration; no admin UI yet."""

    __tablename__ = "ticket_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    subtypes: Mapped[list["TicketSubtype"]] = relationship(
        back_populates="type", cascade="all, delete-orphan", order_by="TicketSubtype.sort_order"
    )


class TicketSubtype(Base):
    __tablename__ = "ticket_subtypes"
    __table_args__ = (
        UniqueConstraint("type_id", "name", name="uq_subtype_type_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type_id: Mapped[int] = mapped_column(
        ForeignKey("ticket_types.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    type: Mapped[TicketType] = relationship(back_populates="subtypes")
    items: Mapped[list["TicketItem"]] = relationship(
        back_populates="subtype", cascade="all, delete-orphan", order_by="TicketItem.sort_order"
    )


class TicketItem(Base):
    __tablename__ = "ticket_items"
    __table_args__ = (
        UniqueConstraint("subtype_id", "name", name="uq_item_subtype_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subtype_id: Mapped[int] = mapped_column(
        ForeignKey("ticket_subtypes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    subtype: Mapped[TicketSubtype] = relationship(back_populates="items")


class Ticket(TimestampMixin, Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # e.g. "26001". Display/reference number; id stays the join key.
    number: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    configuration_id: Mapped[int | None] = mapped_column(
        ForeignKey("configurations.id", ondelete="SET NULL"), index=True
    )
    board_id: Mapped[int] = mapped_column(
        ForeignKey("boards.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status_id: Mapped[int] = mapped_column(
        ForeignKey("statuses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assigned_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    # ITIL-style categorization. All optional — a ticket doesn't have to be
    # fully categorized to exist, but reporting is much better when it is.
    type_id: Mapped[int | None] = mapped_column(
        ForeignKey("ticket_types.id", ondelete="SET NULL"), index=True
    )
    subtype_id: Mapped[int | None] = mapped_column(
        ForeignKey("ticket_subtypes.id", ondelete="SET NULL"), index=True
    )
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("ticket_items.id", ondelete="SET NULL"), index=True
    )

    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    # email | rmm | manual | portal
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)

    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Correlation for the RMM self-heal flow in Phase 2 and the email
    # threading flow below. Nullable; only set when source needs it.
    rmm_alert_uid: Mapped[str | None] = mapped_column(String(128), index=True)
    email_thread_token: Mapped[str | None] = mapped_column(String(64), index=True)

    company: Mapped[Company] = relationship()
    contact: Mapped[Contact | None] = relationship()
    configuration: Mapped[Configuration | None] = relationship()
    board: Mapped[Board] = relationship()
    status: Mapped[Status] = relationship()
    assigned_user: Mapped[User | None] = relationship()
    type: Mapped[TicketType | None] = relationship()
    subtype: Mapped[TicketSubtype | None] = relationship()
    item: Mapped[TicketItem | None] = relationship()

    notes: Mapped[list["TicketNote"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketNote.created_at"
    )
    time_entries: Mapped[list["TimeEntry"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TimeEntry.work_date"
    )


class TicketNote(Base):
    """A note is not one type — a tech can flag it as discussion, internal,
    and/or resolution all at once (CW's model). Discussion defaults on;
    the other two are opt-in flags, not an exclusive choice."""

    __tablename__ = "ticket_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    is_discussion: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Internal notes are never meant to reach a client-facing view (portal,
    # outbound email) — that filtering happens wherever client-facing output
    # is built; this flag is the source of truth for it.
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_resolution: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_inbound_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ticket: Mapped[Ticket] = relationship(back_populates="notes")
    user: Mapped[User | None] = relationship()

    @property
    def author_label(self) -> str:
        if self.is_inbound_email:
            return "Client (email)"
        return self.user.full_name if self.user else "System"


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    billable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    invoiced_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ticket: Mapped[Ticket] = relationship(back_populates="time_entries")
    user: Mapped[User] = relationship()

    @property
    def hours(self) -> float:
        return round(self.minutes / 60, 2)


class EmailMessage(TimestampMixin, Base):
    """One row per inbound message pulled from the shared mailbox. graph_id
    is the dedupe key so a re-poll never creates a duplicate ticket."""

    __tablename__ = "email_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    graph_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    mailbox: Mapped[str] = mapped_column(String(255), nullable=False)

    from_email: Mapped[str | None] = mapped_column(String(255), index=True)
    from_name: Mapped[str | None] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(500))
    internet_message_id: Mapped[str | None] = mapped_column(String(500))
    in_reply_to: Mapped[str | None] = mapped_column(String(500), index=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ticket_id: Mapped[int | None] = mapped_column(
        ForeignKey("tickets.id", ondelete="SET NULL"), index=True
    )
    # matched | created_ticket | no_contact_match | error
    outcome: Mapped[str] = mapped_column(String(32), default="matched", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    ticket: Mapped[Ticket | None] = relationship()


class Location(TimestampMixin, Base):
    """A physical site for a company. IT Glue calls this the same thing —
    where equipment lives, who's onsite, what the network closet looks like."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(40))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(40))

    notes: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="locations")


class Document(TimestampMixin, Base):
    """Free-form documentation — procedures, network notes, vendor info,
    anything that isn't a credential. Body is plain text; no markdown
    rendering yet, whitespace is preserved on display.
    embed_code stores a raw iframe snippet (Lucidchart, draw.io, etc.)
    rendered on the document's own view page."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    embed_code: Mapped[str | None] = mapped_column(Text)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    company: Mapped[Company] = relationship(back_populates="documents")
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])
    updated_by: Mapped[User | None] = relationship(foreign_keys=[updated_by_id])
    attachments: Mapped[list["DocumentAttachment"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentAttachment.filename"
    )


class Credential(TimestampMixin, Base):
    """A stored secret. secret_encrypted is a Fernet token, never plaintext —
    see app/crypto.py. Decrypted only on an explicit reveal request, never
    included in a normal page render."""

    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    configuration_id: Mapped[int | None] = mapped_column(
        ForeignKey("configurations.id", ondelete="SET NULL")
    )
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL")
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80))
    username: Mapped[str | None] = mapped_column(String(255))
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="credentials")
    location: Mapped[Location | None] = relationship()
    configuration: Mapped[Configuration | None] = relationship()
    contact: Mapped[Contact | None] = relationship()


class Domain(TimestampMixin, Base):
    """IT Glue's Domain Tracker. Structured (not free-text) because the
    expiration date needs to be queryable for the "expiring soon" report.
    created_on/updated_on/name_servers/status/raw_whois are filled by the
    best-effort WHOIS lookup in app/integrations/lookups.py — every field
    stays hand-editable regardless of where it came from."""

    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    domain_name: Mapped[str] = mapped_column(String(255), nullable=False)
    registrar: Mapped[str | None] = mapped_column(String(120))
    dns_provider: Mapped[str | None] = mapped_column(String(120))
    expires_on: Mapped[date | None] = mapped_column(Date, index=True)
    created_on: Mapped[date | None] = mapped_column(Date)
    updated_on: Mapped[date | None] = mapped_column(Date)
    name_servers: Mapped[str | None] = mapped_column(Text)
    registry_status: Mapped[str | None] = mapped_column(Text)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_whois_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_whois: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="domains")


class SSLCertificate(TimestampMixin, Base):
    """IT Glue's SSL Certificate Tracker. Same reasoning as Domain — the
    expiration date drives the report, so it's a real column, not prose.
    Filled by a live TLS handshake in app/integrations/lookups.py when
    possible; every field stays hand-editable."""

    __tablename__ = "ssl_certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    common_name: Mapped[str] = mapped_column(String(255), nullable=False)
    issued_by: Mapped[str | None] = mapped_column(String(120))
    installed_location: Mapped[str | None] = mapped_column(String(255))
    issued_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date, index=True)
    serial_number: Mapped[str | None] = mapped_column(String(120))
    signature_algorithm: Mapped[str | None] = mapped_column(String(80))
    subject_alt_names: Mapped[str | None] = mapped_column(Text)
    fingerprint_sha256: Mapped[str | None] = mapped_column(String(80))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="ssl_certificates")


class RelatedItem(Base):
    """A generic link between two documentation-layer items — a config
    tied to the credential that logs into it, a document tied to the site
    it describes, and so on. Stored once per pair with a canonical
    ordering (a is always the lexicographically smaller of the two
    (type, id) pairs) so a link can't be saved twice in reversed order.

    a_type / b_type are one of: configuration, credential, document,
    location, domain, ssl_certificate.
    """

    __tablename__ = "related_items"
    __table_args__ = (
        UniqueConstraint("a_type", "a_id", "b_type", "b_id", name="uq_related_item_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    a_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    a_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    b_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    b_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentAttachment(Base):
    """A file attached to a Document, stored on the QNAP attachments volume.
    stored_filename is the name on disk (UUID-prefixed to avoid collisions);
    filename is what the user sees and downloads as."""

    __tablename__ = "document_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="attachments")


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
