"""add intelligence tables

Revision ID: h2c9d7e8f038
Revises: g1b8c5d6e927
Create Date: 2026-03-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = "h2c9d7e8f038"
down_revision: Union[str, None] = "g1b8c5d6e927"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure PostGIS is available
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # ── zonas_operativas ──
    op.create_table(
        "zonas_operativas",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column(
            "geometria",
            Geometry("POLYGON", srid=4326),
            nullable=False,
            comment="Zone boundary polygon",
        ),
        sa.Column(
            "cuenca",
            sa.String(100),
            nullable=False,
            comment="Parent watershed name",
        ),
        sa.Column(
            "superficie_ha",
            sa.Float,
            nullable=False,
            server_default="0",
            comment="Area in hectares",
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
    op.create_index("ix_zonas_operativas_cuenca", "zonas_operativas", ["cuenca"])

    # ── indices_hidricos ──
    op.create_table(
        "indices_hidricos",
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
        sa.Column("fecha_calculo", sa.Date, nullable=False),
        sa.Column("pendiente_media", sa.Float, nullable=False),
        sa.Column("acumulacion_media", sa.Float, nullable=False),
        sa.Column("twi_medio", sa.Float, nullable=False),
        sa.Column(
            "proximidad_canal_m",
            sa.Float,
            nullable=False,
            comment="Average distance to nearest canal in meters",
        ),
        sa.Column(
            "historial_inundacion",
            sa.Float,
            nullable=False,
            comment="Flood history factor 0-1",
        ),
        sa.Column(
            "indice_final",
            sa.Float,
            nullable=False,
            comment="Final HCI score 0-100",
        ),
        sa.Column(
            "nivel_riesgo",
            sa.String(20),
            nullable=False,
            comment="bajo / medio / alto / critico",
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
    op.create_index("ix_indices_hidricos_zona_id", "indices_hidricos", ["zona_id"])
    op.create_index("ix_indices_hidricos_fecha", "indices_hidricos", ["fecha_calculo"])
    op.create_index("ix_indices_hidricos_nivel", "indices_hidricos", ["nivel_riesgo"])

    # ── puntos_conflicto ──
    op.create_table(
        "puntos_conflicto",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tipo",
            sa.String(50),
            nullable=False,
            comment="canal_camino / canal_drenaje / camino_drenaje",
        ),
        sa.Column(
            "geometria",
            Geometry("POINT", srid=4326),
            nullable=False,
            comment="Conflict location",
        ),
        sa.Column("descripcion", sa.String(500), nullable=False, server_default=""),
        sa.Column(
            "severidad",
            sa.String(20),
            nullable=False,
            comment="baja / media / alta",
        ),
        sa.Column(
            "infraestructura_ids",
            postgresql.JSON,
            nullable=True,
            comment="Related asset IDs",
        ),
        sa.Column(
            "acumulacion_valor",
            sa.Float,
            nullable=False,
            server_default="0",
            comment="Flow accumulation at conflict point",
        ),
        sa.Column(
            "pendiente_valor",
            sa.Float,
            nullable=False,
            server_default="0",
            comment="Slope at conflict point",
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
    op.create_index("ix_puntos_conflicto_tipo", "puntos_conflicto", ["tipo"])
    op.create_index("ix_puntos_conflicto_severidad", "puntos_conflicto", ["severidad"])

    # ── alertas_geo ──
    op.create_table(
        "alertas_geo",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tipo",
            sa.String(50),
            nullable=False,
            comment="umbral_superado / lluvia_reciente / cambio_sar",
        ),
        sa.Column(
            "zona_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("zonas_operativas.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("mensaje", sa.Text, nullable=False),
        sa.Column(
            "nivel",
            sa.String(20),
            nullable=False,
            comment="info / advertencia / critico",
        ),
        sa.Column(
            "datos",
            postgresql.JSON,
            nullable=True,
            comment="Additional alert data payload",
        ),
        sa.Column("activa", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_alertas_geo_tipo", "alertas_geo", ["tipo"])
    op.create_index("ix_alertas_geo_zona_id", "alertas_geo", ["zona_id"])
    op.create_index("ix_alertas_geo_activa", "alertas_geo", ["activa"])


def downgrade() -> None:
    op.drop_index("ix_alertas_geo_activa")
    op.drop_index("ix_alertas_geo_zona_id")
    op.drop_index("ix_alertas_geo_tipo")
    op.drop_table("alertas_geo")

    op.drop_index("ix_puntos_conflicto_severidad")
    op.drop_index("ix_puntos_conflicto_tipo")
    op.drop_table("puntos_conflicto")

    op.drop_index("ix_indices_hidricos_nivel")
    op.drop_index("ix_indices_hidricos_fecha")
    op.drop_index("ix_indices_hidricos_zona_id")
    op.drop_table("indices_hidricos")

    op.drop_index("ix_zonas_operativas_cuenca")
    op.drop_table("zonas_operativas")
