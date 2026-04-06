"""add ndwi_baselines table

Revision ID: a1b2c3d4e5f6
Revises: z0u7v8w9x826
Create Date: 2026-04-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "0012_add_flood_flow_results"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ndwi_baselines",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "zona_operativa_id",
            UUID(as_uuid=True),
            sa.ForeignKey("zonas_operativas.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            comment="One baseline per zona",
        ),
        sa.Column(
            "ndwi_mean",
            sa.Float,
            nullable=False,
            comment="Mean NDWI across dry-season images",
        ),
        sa.Column(
            "ndwi_std",
            sa.Float,
            nullable=False,
            comment="Std dev of NDWI across dry-season images",
        ),
        sa.Column(
            "sample_count",
            sa.Integer,
            nullable=False,
            comment="Number of S2 images used for baseline",
        ),
        sa.Column(
            "dry_season_months",
            JSON,
            nullable=False,
            comment="Month numbers used [6,7,8]",
        ),
        sa.Column(
            "years_back",
            sa.Integer,
            nullable=False,
            comment="Years of history used",
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the baseline was last computed",
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
        "ix_ndwi_baselines_zona_operativa_id",
        "ndwi_baselines",
        ["zona_operativa_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ndwi_baselines_zona_operativa_id", table_name="ndwi_baselines")
    op.drop_table("ndwi_baselines")
