"""add composite analysis

Revision ID: r2m9n8o9p038
Revises: q1l8m7n8o927
Create Date: 2026-03-29

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "r2m9n8o9p038"
down_revision: Union[str, None] = "q1l8m7n8o927"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new values to tipo_geo_layer enum
    op.execute("ALTER TYPE tipo_geo_layer ADD VALUE IF NOT EXISTS 'flood_risk'")
    op.execute("ALTER TYPE tipo_geo_layer ADD VALUE IF NOT EXISTS 'drainage_need'")

    # Add new value to tipo_geo_job enum
    op.execute(
        "ALTER TYPE tipo_geo_job ADD VALUE IF NOT EXISTS 'composite_analysis'"
    )

    # ── composite_zonal_stats ──
    op.create_table(
        "composite_zonal_stats",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "zona_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("zonas_operativas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tipo",
            sa.String(30),
            nullable=False,
            comment="flood_risk | drainage_need",
        ),
        sa.Column("fecha_calculo", sa.Date, nullable=False),
        sa.Column(
            "mean_score",
            sa.Float,
            nullable=False,
            comment="Mean composite score for the zone",
        ),
        sa.Column(
            "max_score",
            sa.Float,
            nullable=False,
            comment="Maximum composite score for the zone",
        ),
        sa.Column(
            "p90_score",
            sa.Float,
            nullable=False,
            comment="90th percentile composite score",
        ),
        sa.Column(
            "area_high_risk_ha",
            sa.Float,
            nullable=False,
            server_default="0",
            comment="Area in hectares where score > 70",
        ),
        sa.Column(
            "weights_used",
            postgresql.JSON,
            nullable=True,
            comment="Snapshot of weights at computation time",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_composite_zonal_stats_zona_id",
        "composite_zonal_stats",
        ["zona_id"],
    )
    op.create_index(
        "ix_composite_zonal_stats_tipo",
        "composite_zonal_stats",
        ["tipo"],
    )
    op.create_index(
        "ix_composite_zonal_stats_fecha",
        "composite_zonal_stats",
        ["fecha_calculo"],
    )
    op.create_unique_constraint(
        "uq_composite_zonal_stats_zona_tipo",
        "composite_zonal_stats",
        ["zona_id", "tipo"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_composite_zonal_stats_zona_tipo", "composite_zonal_stats")
    op.drop_index("ix_composite_zonal_stats_fecha")
    op.drop_index("ix_composite_zonal_stats_tipo")
    op.drop_index("ix_composite_zonal_stats_zona_id")
    op.drop_table("composite_zonal_stats")
    # PostgreSQL does not support removing enum values.
    # The values will remain but be unused after downgrade.
