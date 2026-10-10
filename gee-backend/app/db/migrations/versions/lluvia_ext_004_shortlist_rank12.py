"""lluvia_ext_004: allow up to 12 ranked GEE scenes per extreme event.

Revision ID: lluvia_ext_004
Revises: lluvia_ext_003
"""

from typing import Sequence, Union

from alembic import op

revision: str = "lluvia_ext_004"
down_revision: Union[str, None] = "lluvia_ext_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "rainfall_event_imagery_candidate"
CK = "ck_rainfall_imagery_candidate_rank"


def upgrade() -> None:
    op.drop_constraint(CK, TABLE, type_="check")
    op.create_check_constraint(CK, TABLE, "rank >= 1 AND rank <= 12")


def downgrade() -> None:
    op.drop_constraint(CK, TABLE, type_="check")
    op.create_check_constraint(CK, TABLE, "rank >= 1 AND rank <= 3")
