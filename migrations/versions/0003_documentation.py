"""Documentation layer: locations, documents, credentials

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "company_id", sa.Integer,
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("address_line1", sa.String(200)),
        sa.Column("address_line2", sa.String(200)),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(40)),
        sa.Column("postal_code", sa.String(20)),
        sa.Column("phone", sa.String(40)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_locations_company_id", "locations", ["company_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "company_id", sa.Integer,
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category", sa.String(80)),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("is_pinned", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_by_id", sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "updated_by_id", sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_documents_company_id", "documents", ["company_id"])

    op.create_table(
        "credentials",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "company_id", sa.Integer,
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "location_id", sa.Integer,
            sa.ForeignKey("locations.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "configuration_id", sa.Integer,
            sa.ForeignKey("configurations.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "contact_id", sa.Integer,
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(80)),
        sa.Column("username", sa.String(255)),
        sa.Column("secret_encrypted", sa.Text, nullable=False),
        sa.Column("url", sa.String(500)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_credentials_company_id", "credentials", ["company_id"])
    op.create_index("ix_credentials_location_id", "credentials", ["location_id"])
    op.create_index("ix_credentials_configuration_id", "credentials", ["configuration_id"])
    op.create_index("ix_credentials_contact_id", "credentials", ["contact_id"])

    op.create_table(
        "domains",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "company_id", sa.Integer,
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("domain_name", sa.String(255), nullable=False),
        sa.Column("registrar", sa.String(120)),
        sa.Column("dns_provider", sa.String(120)),
        sa.Column("expires_on", sa.Date),
        sa.Column("auto_renew", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_domains_company_id", "domains", ["company_id"])
    op.create_index("ix_domains_expires_on", "domains", ["expires_on"])

    op.create_table(
        "ssl_certificates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "company_id", sa.Integer,
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("common_name", sa.String(255), nullable=False),
        sa.Column("issued_by", sa.String(120)),
        sa.Column("installed_location", sa.String(255)),
        sa.Column("expires_on", sa.Date),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ssl_certificates_company_id", "ssl_certificates", ["company_id"])
    op.create_index("ix_ssl_certificates_expires_on", "ssl_certificates", ["expires_on"])


def downgrade() -> None:
    op.drop_table("ssl_certificates")
    op.drop_table("domains")
    op.drop_table("credentials")
    op.drop_table("documents")
    op.drop_table("locations")
