"""add flood_flow_results table and capacidad_m3s to zonas_operativas

Revision ID: 0012_add_flood_flow_results
Revises: z0u7v8w9x826
Create Date: 2026-04-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

revision: str = "0012_add_flood_flow_results"
down_revision: Union[str, None] = "z0u7v8w9x826"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "flood_flow_results",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "zona_id",
            UUID(as_uuid=True),
            sa.ForeignKey("zonas_operativas.id", ondelete="CASCADE"),
            nullable=False,
            comment="FK to zonas_operativas",
        ),
        sa.Column(
            "fecha_calculo",
            sa.Date(),
            nullable=False,
            comment="Date this computation was run",
        ),
        sa.Column(
            "fecha_lluvia",
            sa.Date(),
            nullable=False,
            comment="Rainfall event date (UNIQUE with zona_id)",
        ),
        sa.Column(
            "tc_minutos",
            sa.Float(),
            nullable=False,
            comment="Concentration time in minutes (Kirpich formula)",
        ),
        sa.Column(
            "c_escorrentia",
            sa.Float(),
            nullable=False,
            comment="Runoff coefficient C (dimensionless)",
        ),
        sa.Column(
            "c_source",
            sa.String(50),
            nullable=False,
            comment="How C was obtained: ndvi_sentinel2 | fallback_default | manual",
        ),
        sa.Column(
            "intensidad_mm_h",
            sa.Float(),
            nullable=False,
            comment="Rainfall intensity in mm/h",
        ),
        sa.Column(
            "area_km2",
            sa.Float(),
            nullable=False,
            comment="Zone drainage area in km²",
        ),
        sa.Column(
            "caudal_m3s",
            sa.Float(),
            nullable=False,
            comment="Estimated peak flow Q in m³/s (Rational Method)",
        ),
        sa.Column(
            "capacidad_m3s",
            sa.Float(),
            nullable=True,
            comment="Canal capacity in m³/s (nullable — may not be set yet)",
        ),
        sa.Column(
            "porcentaje_capacidad",
            sa.Float(),
            nullable=True,
            comment="Q / capacity * 100 (nullable when capacity is unknown)",
        ),
        sa.Column(
            "nivel_riesgo",
            sa.String(20),
            nullable=False,
            comment="bajo | moderado | alto | critico | sin_capacidad",
        ),
        sa.Column(
            "metadata",
            JSON,
            nullable=True,
            comment="Arbitrary extra metadata (JSONB)",
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
        sa.UniqueConstraint("zona_id", "fecha_lluvia", name="uq_flood_flow_zona_fecha"),
    )

    op.create_index(
        "ix_flood_flow_results_zona_id",
        "flood_flow_results",
        ["zona_id"],
    )

    op.add_column(
        "zonas_operativas",
        sa.Column(
            "capacidad_m3s",
            sa.Float(),
            nullable=True,
            comment="Canal capacity in m³/s for hydraulic risk classification",
        ),
    )


def downgrade() -> None:
    op.drop_column("zonas_operativas", "capacidad_m3s")
    op.drop_index("ix_flood_flow_results_zona_id", table_name="flood_flow_results")
    op.drop_table("flood_flow_results")
