"""Phase 0: users, companies, contacts, configurations, jobs, sync runs

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="admin"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", TS),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("identifier", sa.String(32), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("phone", sa.String(40)),
        sa.Column("website", sa.String(255)),
        sa.Column("address_line1", sa.String(200)),
        sa.Column("address_line2", sa.String(200)),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(40)),
        sa.Column("postal_code", sa.String(20)),
        sa.Column("ninja_org_id", sa.String(64)),
        sa.Column("m365_tenant_id", sa.String(64)),
        sa.Column("gsuite_domain", sa.String(255)),
        sa.Column("qbo_customer_id", sa.String(64)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_companies_ninja_org_id", "companies", ["ninja_org_id"])
    op.create_index("ix_companies_m365_tenant_id", "companies", ["m365_tenant_id"])
    op.create_index("ix_companies_gsuite_domain", "companies", ["gsuite_domain"])
    op.create_index("ix_companies_qbo_customer_id", "companies", ["qbo_customer_id"])

    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer,
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("first_name", sa.String(80), nullable=False),
        sa.Column("last_name", sa.String(80), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(40)),
        sa.Column("title", sa.String(120)),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_licensed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("billable_user", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("license_source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("external_id", sa.String(128)),
        sa.Column("upn", sa.String(255)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "email", name="uq_contact_company_email"),
    )
    op.create_index("ix_contacts_company_id", "contacts", ["company_id"])
    op.create_index("ix_contacts_email", "contacts", ["email"])
    op.create_index("ix_contacts_upn", "contacts", ["upn"])
    op.create_index("ix_contacts_external", "contacts", ["license_source", "external_id"])

    op.create_table(
        "configurations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer,
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            sa.Integer,
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("config_type", sa.String(32), nullable=False, server_default="workstation"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("manufacturer", sa.String(80)),
        sa.Column("model", sa.String(120)),
        sa.Column("serial_number", sa.String(120)),
        sa.Column("operating_system", sa.String(160)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("last_logged_in_user", sa.String(255)),
        sa.Column("billable", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("ninja_device_id", sa.String(64)),
        sa.Column("last_seen_at", TS),
        sa.Column("warranty_expires_on", sa.Date),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("ninja_device_id", name="uq_config_ninja_device"),
    )
    op.create_index("ix_configurations_company_id", "configurations", ["company_id"])
    op.create_index("ix_configurations_contact_id", "configurations", ["contact_id"])
    op.create_index("ix_configurations_serial_number", "configurations", ["serial_number"])
    op.create_index("ix_configurations_ninja_device_id", "configurations", ["ninja_device_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("run_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("locked_at", TS),
        sa.Column("locked_by", sa.String(64)),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", TS),
    )
    op.create_index("ix_jobs_claimable", "jobs", ["status", "run_at"])

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column(
            "company_id",
            sa.Integer,
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
        ),
        sa.Column("started_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", TS),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("created_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text),
    )
    op.create_index("ix_sync_runs_source", "sync_runs", ["source"])


def downgrade() -> None:
    op.drop_table("sync_runs")
    op.drop_table("jobs")
    op.drop_table("configurations")
    op.drop_table("contacts")
    op.drop_table("companies")
    op.drop_table("users")
