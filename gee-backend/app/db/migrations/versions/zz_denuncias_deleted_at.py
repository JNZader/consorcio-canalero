"""Add denuncias.deleted_at for ARCO soft-delete.

Phase 4 / F4-K. Ley 25.326 right to cancellation: the owner can
request deletion; we stamp ``deleted_at`` and a celery beat task
purges rows older than 1 year. The photo on disk is hard-deleted
synchronously when the DELETE endpoint fires.

Revision ID: zz_denuncias_deleted_at
Revises: zz_refresh_tokens_revoked_at
Create Date: 2026-05-19
"""

import sqlalchemy as sa
from alembic import op


revision = "zz_denuncias_deleted_at"
down_revision = "zz_refresh_tokens_revoked_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "denuncias",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_denuncias_deleted_at",
        "denuncias",
        ["deleted_at"],
        # Partial index: only rows pending purge are interesting for
        # the cleanup task; live rows (deleted_at IS NULL) make up 99%
        # of the table and don't need the index.
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_denuncias_deleted_at", table_name="denuncias")
    op.drop_column("denuncias", "deleted_at")
