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
    # Backfill caveat: pre-2.2 revocations used SQLAlchemy Core
    # ``update(...).values(revoked=True)`` which does NOT trigger the
    # ORM-level ``TimestampMixin.onupdate`` for ``updated_at``. So for
    # most legacy revoked rows, ``updated_at == created_at`` — meaning
    # this backfill effectively sets ``revoked_at = created_at``, NOT
    # the real revocation time. Two practical consequences:
    #
    #   1. ``cleanup_tasks.purge_stale_refresh_tokens`` may delete
    #      legacy revoked rows up to (token-lifetime) days earlier
    #      than the intended 30-day forensic window. Acceptable —
    #      forensic data on pre-2.2 revocations is already low-fidelity.
    #
    #   2. ``refresh_tokens.rotate()`` will see legacy rows as
    #      ``now - revoked_at >> RACE_WINDOW`` and treat any replay
    #      attempt against them as a real replay (conservative).
    #
    # New revocations (post-2.2) populate ``revoked_at`` synchronously
    # with ``revoked=True`` in the CAS UPDATE, so this caveat applies
    # only to the one-time backfill.
    op.execute(
        "UPDATE refresh_tokens SET revoked_at = updated_at "
        "WHERE revoked = TRUE AND revoked_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "revoked_at")
