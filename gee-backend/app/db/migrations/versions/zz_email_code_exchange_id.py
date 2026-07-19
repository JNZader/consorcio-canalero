"""Add idempotency digest to email code exchange.

Revision ID: zz_email_code_exchange_id
Revises: zz_users_fk_nullable
Create Date: 2026-07-19
"""

import sqlalchemy as sa
from alembic import op


revision = "zz_email_code_exchange_id"
down_revision = "zz_users_fk_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_codes",
        sa.Column("exchange_id_digest", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_codes", "exchange_id_digest")
