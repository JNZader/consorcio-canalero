"""drop rainfall_records table

Revision ID: 7e25b857692b
Revises: 510100cc64ea
Create Date: 2026-04-22 13:58:39.309361

Rainfall feature was removed from the code in commit 1829a3e. The table
has 0 rows in prod and no code references. This migration cleans up the
dead schema.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7e25b857692b"
down_revision: Union[str, Sequence[str], None] = "510100cc64ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the dead rainfall_records table and its auxiliary indexes."""
    op.drop_index("ix_rainfall_records_date", table_name="rainfall_records")
    op.drop_index("ix_rainfall_records_zona_date", table_name="rainfall_records")
    op.drop_index(
        "ix_rainfall_records_zona_operativa_id", table_name="rainfall_records"
    )
    op.drop_constraint(
        "uq_rainfall_zona_date_source", "rainfall_records", type_="unique"
    )
    op.drop_table("rainfall_records")


def downgrade() -> None:
    """Downgrade is intentionally unsupported."""
    raise NotImplementedError(
        "Downgrade not supported - rainfall feature was removed in commit 1829a3e. "
        "To restore, revert 1829a3e AND this migration AND re-run the create migration."
    )
