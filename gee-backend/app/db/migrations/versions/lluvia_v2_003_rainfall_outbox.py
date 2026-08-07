"""Add RainfallOutbox table for durable missing-work queue.

Revision ID: lluvia_v2_003
Revises: lluvia_v2_002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "lluvia_v2_003"
down_revision = "lluvia_v2_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rainfall_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("scope_kind", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(128), nullable=False),
        sa.Column("scope_version", sa.String(128), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column(
            "work_labels", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'done', 'failed')",
            name="ck_rainfall_outbox_status",
        ),
        sa.CheckConstraint(
            "retry_count >= 0",
            name="ck_rainfall_outbox_retry_count",
        ),
    )
    op.create_index(
        "ix_rainfall_outbox_status_next_attempt",
        "rainfall_outbox",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_rainfall_outbox_status_next_attempt", table_name="rainfall_outbox")
    op.drop_table("rainfall_outbox")
