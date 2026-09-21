"""Phase 1: boards, statuses, tickets, notes, time entries, email connector

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)

# (name, slug) — order here is display order.
BOARDS = [
    ("Triage", "triage"),
    ("MS Board", "ms"),
    ("Project Board", "project"),
    ("Alerts Board", "alerts"),
    ("Backups Board", "backups"),
    ("Admin Board", "admin"),
]

# Same status set on every board for now. (name, is_closed)
STATUSES = [
    ("New", False),
    ("In Progress", False),
    ("Waiting", False),
    ("Resolved", False),
    ("Closed", True),
]


def upgrade() -> None:
    op.create_table(
        "boards",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("slug", sa.String(40), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "statuses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "board_id", sa.Integer,
            sa.ForeignKey("boards.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_closed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("board_id", "name", name="uq_status_board_name"),
    )
    op.create_index("ix_statuses_board_id", "statuses", ["board_id"])

    op.create_table(
        "ticket_counters",
        sa.Column("year", sa.Integer, primary_key=True),
        sa.Column("next_seq", sa.Integer, nullable=False, server_default="1"),
    )

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("number", sa.String(12), nullable=False, unique=True),
        sa.Column(
            "company_id", sa.Integer,
            sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "contact_id", sa.Integer,
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "configuration_id", sa.Integer,
            sa.ForeignKey("configurations.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "board_id", sa.Integer,
            sa.ForeignKey("boards.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column(
            "status_id", sa.Integer,
            sa.ForeignKey("statuses.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column(
            "assigned_user_id", sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("closed_at", TS),
        sa.Column("rmm_alert_uid", sa.String(128)),
        sa.Column("email_thread_token", sa.String(64)),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tickets_company_id", "tickets", ["company_id"])
    op.create_index("ix_tickets_contact_id", "tickets", ["contact_id"])
    op.create_index("ix_tickets_configuration_id", "tickets", ["configuration_id"])
    op.create_index("ix_tickets_board_id", "tickets", ["board_id"])
    op.create_index("ix_tickets_status_id", "tickets", ["status_id"])
    op.create_index("ix_tickets_assigned_user_id", "tickets", ["assigned_user_id"])
    op.create_index("ix_tickets_rmm_alert_uid", "tickets", ["rmm_alert_uid"])
    op.create_index("ix_tickets_email_thread_token", "tickets", ["email_thread_token"])

    op.create_table(
        "ticket_notes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "ticket_id", sa.Integer,
            sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("note_type", sa.String(16), nullable=False, server_default="discussion"),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("is_inbound_email", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ticket_notes_ticket_id", "ticket_notes", ["ticket_id"])

    op.create_table(
        "time_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "ticket_id", sa.Integer,
            sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", sa.Integer,
            sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("minutes", sa.Integer, nullable=False),
        sa.Column("billable", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("note", sa.Text),
        sa.Column("invoiced_on", sa.Date),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_time_entries_ticket_id", "time_entries", ["ticket_id"])
    op.create_index("ix_time_entries_user_id", "time_entries", ["user_id"])

    op.create_table(
        "email_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("graph_id", sa.String(255), nullable=False, unique=True),
        sa.Column("mailbox", sa.String(255), nullable=False),
        sa.Column("from_email", sa.String(255)),
        sa.Column("from_name", sa.String(255)),
        sa.Column("subject", sa.String(500)),
        sa.Column("internet_message_id", sa.String(500)),
        sa.Column("in_reply_to", sa.String(500)),
        sa.Column("received_at", TS),
        sa.Column(
            "ticket_id", sa.Integer,
            sa.ForeignKey("tickets.id", ondelete="SET NULL"),
        ),
        sa.Column("outcome", sa.String(32), nullable=False, server_default="matched"),
        sa.Column("error", sa.Text),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_email_messages_from_email", "email_messages", ["from_email"])
    op.create_index("ix_email_messages_in_reply_to", "email_messages", ["in_reply_to"])
    op.create_index("ix_email_messages_ticket_id", "email_messages", ["ticket_id"])

    # --- seed boards + statuses ---
    boards_t = sa.table(
        "boards", sa.column("id", sa.Integer), sa.column("name", sa.String),
        sa.column("slug", sa.String), sa.column("sort_order", sa.Integer),
    )
    statuses_t = sa.table(
        "statuses", sa.column("board_id", sa.Integer), sa.column("name", sa.String),
        sa.column("sort_order", sa.Integer), sa.column("is_closed", sa.Boolean),
    )

    conn = op.get_bind()
    for order, (name, slug) in enumerate(BOARDS):
        board_id = conn.execute(
            boards_t.insert()
            .values(name=name, slug=slug, sort_order=order)
            .returning(boards_t.c.id)
        ).scalar_one()
        for s_order, (s_name, is_closed) in enumerate(STATUSES):
            conn.execute(
                statuses_t.insert().values(
                    board_id=board_id, name=s_name, sort_order=s_order, is_closed=is_closed
                )
            )


def downgrade() -> None:
    op.drop_table("email_messages")
    op.drop_table("time_entries")
    op.drop_table("ticket_notes")
    op.drop_table("tickets")
    op.drop_table("ticket_counters")
    op.drop_table("statuses")
    op.drop_table("boards")
