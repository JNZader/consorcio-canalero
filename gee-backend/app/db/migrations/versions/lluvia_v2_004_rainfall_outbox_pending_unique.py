"""rainfall_outbox_pending_unique

Revision ID: lluvia_v2_004
Revises: lluvia_v2_003
Create Date: 2026-08-07 16:11:50.723701

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "lluvia_v2_004"
down_revision: Union[str, Sequence[str], None] = "lluvia_v2_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add partial unique index to prevent duplicate pending outbox rows."""
    op.add_column(
        "rainfall_backfill_checkpoint",
        sa.Column("role", sa.String(64), nullable=False, server_default=sa.text("'historical'")),
    )
    op.drop_constraint(
        "uq_rainfall_backfill_source_scope_version_year",
        "rainfall_backfill_checkpoint",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_rainfall_backfill_source_scope_version_year",
        "rainfall_backfill_checkpoint",
        ["source_id", "role", "scope_kind", "scope_id", "scope_version", "year"],
    )
    op.create_index(
        "ix_rainfall_outbox_pending_unique",
        "rainfall_outbox",
        ["source_id", "role", "scope_kind", "scope_id", "scope_version", "year"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    """Drop partial unique index and checkpoint role column."""
    op.drop_index("ix_rainfall_outbox_pending_unique", table_name="rainfall_outbox")
    op.drop_constraint(
        "uq_rainfall_backfill_source_scope_version_year",
        "rainfall_backfill_checkpoint",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_rainfall_backfill_source_scope_version_year",
        "rainfall_backfill_checkpoint",
        ["source_id", "scope_kind", "scope_id", "scope_version", "year"],
    )
    op.drop_column("rainfall_backfill_checkpoint", "role")
