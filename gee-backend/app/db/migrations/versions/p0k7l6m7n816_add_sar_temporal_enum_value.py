"""add sar_temporal to tipo_analisis_geo enum

Revision ID: p0k7l6m7n816
Revises: o9j6k5l6m705
Create Date: 2026-03-26 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p0k7l6m7n816"
down_revision: Union[str, None] = "o9j6k5l6m705"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE tipo_analisis_geo ADD VALUE IF NOT EXISTS 'sar_temporal'"
    )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # The value will remain but be unused after downgrade.
    pass
