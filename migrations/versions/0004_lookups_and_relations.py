"""Domain/SSL lookup fields, related items (generic cross-entity linking)

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("domains", sa.Column("created_on", sa.Date))
    op.add_column("domains", sa.Column("updated_on", sa.Date))
    op.add_column("domains", sa.Column("name_servers", sa.Text))
    op.add_column("domains", sa.Column("registry_status", sa.Text))
    op.add_column("domains", sa.Column("last_whois_check_at", TS))
    op.add_column("domains", sa.Column("raw_whois", sa.Text))

    op.add_column("ssl_certificates", sa.Column("issued_on", sa.Date))
    op.add_column("ssl_certificates", sa.Column("serial_number", sa.String(120)))
    op.add_column("ssl_certificates", sa.Column("signature_algorithm", sa.String(80)))
    op.add_column("ssl_certificates", sa.Column("subject_alt_names", sa.Text))
    op.add_column("ssl_certificates", sa.Column("fingerprint_sha256", sa.String(80)))
    op.add_column("ssl_certificates", sa.Column("last_checked_at", TS))

    op.create_table(
        "related_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "company_id", sa.Integer,
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("a_type", sa.String(32), nullable=False),
        sa.Column("a_id", sa.Integer, nullable=False),
        sa.Column("b_type", sa.String(32), nullable=False),
        sa.Column("b_id", sa.Integer, nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("a_type", "a_id", "b_type", "b_id", name="uq_related_item_pair"),
    )
    op.create_index("ix_related_items_company_id", "related_items", ["company_id"])
    op.create_index("ix_related_items_a", "related_items", ["a_type", "a_id"])
    op.create_index("ix_related_items_b", "related_items", ["b_type", "b_id"])


def downgrade() -> None:
    op.drop_table("related_items")

    op.drop_column("ssl_certificates", "last_checked_at")
    op.drop_column("ssl_certificates", "fingerprint_sha256")
    op.drop_column("ssl_certificates", "subject_alt_names")
    op.drop_column("ssl_certificates", "signature_algorithm")
    op.drop_column("ssl_certificates", "serial_number")
    op.drop_column("ssl_certificates", "issued_on")

    op.drop_column("domains", "raw_whois")
    op.drop_column("domains", "last_whois_check_at")
    op.drop_column("domains", "registry_status")
    op.drop_column("domains", "name_servers")
    op.drop_column("domains", "updated_on")
    op.drop_column("domains", "created_on")
