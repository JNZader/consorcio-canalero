"""Add refresh_tokens.revoked_at for replay-detection vs race-loss.

Phase 2.2 / post-3vr — distinguish concurrent-rotate race losses
(<30 s old revoke) from real replays (older revoke) without burning
the family in the former case.

Revision ID: zz_refresh_tokens_revoked_at
Revises: zz_refresh_tokens
Create Date: 2026-05-19
"""

import sqlalchemy as sa
from alembic import op


revision = "zz_refresh_tokens_revoked_at"
down_revision = "zz_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill: any row currently revoked gets its ``updated_at`` as a
    # conservative proxy for when the revocation happened. New rows
    # populated by the application going forward set ``revoked_at``
    # explicitly during the CAS UPDATE.
    op.execute(
        "UPDATE refresh_tokens SET revoked_at = updated_at "
        "WHERE revoked = TRUE AND revoked_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "revoked_at")
