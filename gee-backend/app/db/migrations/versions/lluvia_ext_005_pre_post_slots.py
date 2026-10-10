"""lluvia_ext_005: pre/post scene slots beside the ranked shortlist.

Revision ID: lluvia_ext_005
Revises: lluvia_ext_004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "lluvia_ext_005"
down_revision: Union[str, None] = "lluvia_ext_004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "rainfall_event_imagery_candidate"
UQ = "uq_rainfall_imagery_candidate_rank"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("slot", sa.String(length=16), nullable=False, server_default="ranked"),
    )
    op.create_check_constraint(
        "ck_rainfall_imagery_candidate_slot",
        TABLE,
        "slot IN ('ranked', 'pre', 'post')",
    )
    op.drop_constraint(UQ, TABLE, type_="unique")
    op.create_unique_constraint(UQ, TABLE, ["event_key", "slot", "rank"])


def downgrade() -> None:
    op.drop_constraint(UQ, TABLE, type_="unique")
    op.drop_constraint("ck_rainfall_imagery_candidate_slot", TABLE, type_="check")
    op.drop_column(TABLE, "slot")
    op.create_unique_constraint(UQ, TABLE, ["event_key", "rank"])
