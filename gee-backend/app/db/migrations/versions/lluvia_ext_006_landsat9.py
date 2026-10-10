"""lluvia_ext_006: allow Landsat 9 on the imagery shortlist.

Revision ID: lluvia_ext_006
Revises: lluvia_ext_005
"""

from typing import Sequence, Union

from alembic import op

revision: str = "lluvia_ext_006"
down_revision: Union[str, None] = "lluvia_ext_005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "rainfall_event_imagery_candidate"
CK = "ck_rainfall_imagery_candidate_sensor"


def upgrade() -> None:
    op.drop_constraint(CK, TABLE, type_="check")
    op.create_check_constraint(
        CK,
        TABLE,
        "sensor IN ('sentinel2', 'sentinel1', 'landsat9', 'landsat8', 'landsat7', 'landsat5')",
    )


def downgrade() -> None:
    op.drop_constraint(CK, TABLE, type_="check")
    op.create_check_constraint(
        CK,
        TABLE,
        "sensor IN ('sentinel2', 'sentinel1', 'landsat8', 'landsat7', 'landsat5')",
    )
