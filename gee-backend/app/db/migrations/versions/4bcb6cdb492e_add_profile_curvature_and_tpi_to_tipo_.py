"""add profile_curvature and tpi to tipo_geo_layer enum

Revision ID: 4bcb6cdb492e
Revises: b9a3b291a4bd
Create Date: 2026-04-07 12:12:14.482324

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4bcb6cdb492e"
down_revision: Union[str, Sequence[str], None] = "b9a3b291a4bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add profile_curvature and tpi values to tipo_geo_layer enum."""
    op.execute("ALTER TYPE tipo_geo_layer ADD VALUE IF NOT EXISTS 'profile_curvature'")
    op.execute("ALTER TYPE tipo_geo_layer ADD VALUE IF NOT EXISTS 'tpi'")


def downgrade() -> None:
    """Postgres does not support removing enum values — no-op downgrade."""
    pass
