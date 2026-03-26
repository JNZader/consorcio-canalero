"""add dem pipeline enum values

Revision ID: q1l8m7n8o927
Revises: p0k7l6m7n816
Create Date: 2026-03-26

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q1l8m7n8o927"
down_revision: Union[str, None] = "p0k7l6m7n816"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new values to tipo_geo_layer enum
    op.execute("ALTER TYPE tipo_geo_layer ADD VALUE IF NOT EXISTS 'dem_raw'")
    op.execute("ALTER TYPE tipo_geo_layer ADD VALUE IF NOT EXISTS 'basins'")

    # Add new values to tipo_geo_job enum
    # NOTE: gee_flood and gee_classification were missing from DB enum too
    op.execute("ALTER TYPE tipo_geo_job ADD VALUE IF NOT EXISTS 'gee_flood'")
    op.execute("ALTER TYPE tipo_geo_job ADD VALUE IF NOT EXISTS 'gee_classification'")
    op.execute("ALTER TYPE tipo_geo_job ADD VALUE IF NOT EXISTS 'dem_full_pipeline'")
    op.execute("ALTER TYPE tipo_geo_job ADD VALUE IF NOT EXISTS 'basin_delineation'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # The values will remain but be unused after downgrade.
    pass
