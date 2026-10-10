"""lluvia_ext_003: replaceable GEE scene shortlist per extreme event.

Hand-run CLI writes top-3 scored scenes. Re-runs DELETE+INSERT per event_key.
Not part of the append-only rainfall_extreme_event catalog.

Revision ID: lluvia_ext_003
Revises: 0028_add_canal_publicacion_sr_pa
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "lluvia_ext_003"
down_revision: Union[str, None] = "0028_add_canal_publicacion_sr_pa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "rainfall_event_imagery_candidate"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_key", sa.String(length=64), nullable=False),
        sa.Column("scorer_revision", sa.String(length=64), nullable=False),
        sa.Column("sensor", sa.String(length=16), nullable=False),
        sa.Column("scene_id", sa.String(length=256), nullable=False),
        sa.Column("scene_date", sa.Date(), nullable=False),
        sa.Column("days_from_peak", sa.Integer(), nullable=False),
        sa.Column("cloud_pct", sa.Float(), nullable=True),
        sa.Column("cloud_basis", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("visualization", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("event_key", "rank", name="uq_rainfall_imagery_candidate_rank"),
        sa.CheckConstraint("rank >= 1 AND rank <= 3", name="ck_rainfall_imagery_candidate_rank"),
        sa.CheckConstraint(
            "sensor IN ('sentinel2', 'sentinel1', 'landsat8', 'landsat7', 'landsat5')",
            name="ck_rainfall_imagery_candidate_sensor",
        ),
    )
    op.create_index("ix_rainfall_imagery_candidate_event", TABLE, ["event_key"])


def downgrade() -> None:
    op.drop_index("ix_rainfall_imagery_candidate_event", table_name=TABLE)
    op.drop_table(TABLE)
