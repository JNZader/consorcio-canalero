"""Add the durable Celery publication outbox.

Revision ID: zz_celery_task_outbox
Revises: zz_email_code_exchange_id
Create Date: 2026-07-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "zz_celery_task_outbox"
down_revision = "zz_email_code_exchange_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "celery_task_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("celery_task_id", sa.String(length=36), nullable=False),
        sa.Column("task_key", sa.String(length=128), nullable=False),
        sa.Column(
            "task_args",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "task_kwargs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_celery_task_outbox_attempts_nonnegative",
        ),
        sa.CheckConstraint(
            "((lease_id IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_id IS NOT NULL AND lease_expires_at IS NOT NULL))",
            name="ck_celery_task_outbox_lease_pair",
        ),
        sa.CheckConstraint(
            "published_at IS NULL OR (lease_id IS NULL AND lease_expires_at IS NULL)",
            name="ck_celery_task_outbox_published_unleased",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "celery_task_id",
            name="uq_celery_task_outbox_celery_task_id",
        ),
    )
    op.create_index(
        "ix_celery_task_outbox_due",
        "celery_task_outbox",
        ["next_attempt_at", "lease_expires_at", "created_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_index(
        "ix_celery_task_outbox_published_at",
        "celery_task_outbox",
        ["published_at"],
        unique=False,
        postgresql_where=sa.text("published_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_celery_task_outbox_published_at",
        table_name="celery_task_outbox",
    )
    op.drop_index("ix_celery_task_outbox_due", table_name="celery_task_outbox")
    op.drop_table("celery_task_outbox")
