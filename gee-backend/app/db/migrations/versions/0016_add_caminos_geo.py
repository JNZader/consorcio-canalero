"""add caminos_geo table and mv_caminos_por_zona materialized view

Revision ID: 0016_add_caminos_geo
Revises: 0015_add_territorial_tables
Create Date: 2026-04-09
"""

from typing import Sequence, Union

import geoalchemy2
from alembic import op
import sqlalchemy as sa

revision: str = "0016_add_caminos_geo"
down_revision: Union[str, None] = "0015_add_territorial_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── caminos_geo ──────────────────────────────────────────────────────────
    op.create_table(
        "caminos_geo",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("nombre", sa.String(255), nullable=True),
        sa.Column(
            "consorcio_codigo",
            sa.String(20),
            nullable=True,
            comment="Consorcio caminero code (e.g. CC027)",
        ),
        sa.Column(
            "consorcio_nombre",
            sa.String(255),
            nullable=True,
            comment="Consorcio caminero name (e.g. C.C. 027 - LEONES)",
        ),
        sa.Column(
            "jerarquia",
            sa.String(50),
            nullable=True,
            comment="Road hierarchy: Primaria, Secundaria, Terciaria",
        ),
        sa.Column(
            "geometria",
            geoalchemy2.types.Geometry(geometry_type="MULTILINESTRING", srid=4326),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute(
        "CREATE INDEX ix_caminos_geo_geometria ON caminos_geo USING GIST (geometria)"
    )
    op.execute(
        "CREATE INDEX ix_caminos_geo_consorcio ON caminos_geo (consorcio_codigo)"
    )

    # ── materialized view: caminos por zona ────────────────────────────────
    # Groups by (zona, consorcio_caminero OR jerarquia as fallback).
    # COALESCE handles GeoJSON without consorcio fields (uses tipo/jerarquia).
    # cuenca_padre derived from sub-basin prefix (same CASE as 0015).
    op.execute("""
        CREATE MATERIALIZED VIEW mv_caminos_por_zona AS
        SELECT
            z.id                AS zona_id,
            z.nombre            AS zona_nombre,
            z.cuenca,
            COALESCE(c.consorcio_codigo, c.jerarquia, 'sin_tipo') AS consorcio_codigo,
            COALESCE(c.consorcio_nombre, c.jerarquia, 'Sin tipo') AS consorcio_nombre,
            SUM(
                ST_Length(ST_Transform(
                    ST_Intersection(c.geometria, z.geometria),
                    32720
                ))
            ) / 1000.0          AS km_caminos
        FROM zonas_operativas z
        JOIN caminos_geo c ON ST_Intersects(c.geometria, z.geometria)
        GROUP BY z.id, z.nombre, z.cuenca,
            COALESCE(c.consorcio_codigo, c.jerarquia, 'sin_tipo'),
            COALESCE(c.consorcio_nombre, c.jerarquia, 'Sin tipo')
        WITH DATA
    """)
    op.execute(
        "CREATE INDEX ix_mv_caminos_zona ON mv_caminos_por_zona (zona_id)"
    )
    op.execute(
        "CREATE INDEX ix_mv_caminos_cuenca ON mv_caminos_por_zona (cuenca)"
    )
    op.execute(
        "CREATE INDEX ix_mv_caminos_consorcio ON mv_caminos_por_zona (consorcio_codigo)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_caminos_por_zona")
    op.drop_table("caminos_geo")
