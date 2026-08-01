"""add precip_normal to tipo_geo_layer enum

Revision ID: 0018_add_precip_normal_geo_layer
Revises: 0017_ficha_territorial_prep
Create Date: 2026-08-01

Adds the ``precip_normal`` value to the ``tipo_geo_layer`` enum so CHIRPS
monthly precipitation normals can be registered as ``geo_layers`` rows
(see ``etl/generate_chirps_normals.py``).

PostgreSQL gotcha: ``ALTER TYPE ... ADD VALUE`` cannot be used in the *same*
transaction that adds it. This migration only ADDS the value — nothing here
references ``precip_normal`` — so it is safe inside Alembic's transaction on
PostgreSQL 12+, exactly like the existing enum-value migrations
(``r2m9n8o9p038_add_composite_analysis``). ``IF NOT EXISTS`` keeps the upgrade
idempotent.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_add_precip_normal_geo_layer"
down_revision: Union[str, None] = "0017_ficha_territorial_prep"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE tipo_geo_layer ADD VALUE IF NOT EXISTS 'precip_normal'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # The value remains but is unused after downgrade.
    pass
