"""Document embed_code field and file attachments table

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("documents", sa.Column("embed_code", sa.Text))

    op.create_table(
        "document_attachments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "document_id", sa.Integer,
            sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "company_id", sa.Integer,
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120)),
        sa.Column("size_bytes", sa.Integer),
        sa.Column("uploaded_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_document_attachments_document_id", "document_attachments", ["document_id"])
    op.create_index("ix_document_attachments_company_id", "document_attachments", ["company_id"])


def downgrade() -> None:
    op.drop_table("document_attachments")
    op.drop_column("documents", "embed_code")
