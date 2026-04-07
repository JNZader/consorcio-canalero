"""add territorial tables (suelos_catastro, canales_geo, materialized views)

Revision ID: 0015_add_territorial_tables
Revises: 0014_add_canal_dimensions
Create Date: 2026-04-06
"""

from typing import Sequence, Union

import geoalchemy2
from alembic import op
import sqlalchemy as sa

revision: str = "0015_add_territorial_tables"
down_revision: Union[str, None] = "0014_add_canal_dimensions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── suelos_catastro ──────────────────────────────────────────────────────
    op.create_table(
        "suelos_catastro",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "simbolo",
            sa.String(50),
            nullable=False,
            comment="Soil unit symbol (e.g. CaB)",
        ),
        sa.Column(
            "cap",
            sa.String(10),
            nullable=True,
            comment="Land capability class (I–VIII)",
        ),
        sa.Column(
            "ip", sa.String(50), nullable=True, comment="Índice de productividad"
        ),
        sa.Column(
            "geometria",
            geoalchemy2.types.Geometry(geometry_type="MULTIPOLYGON", srid=4326),
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
        "CREATE INDEX ix_suelos_catastro_geometria ON suelos_catastro USING GIST (geometria)"
    )
    op.execute("CREATE INDEX ix_suelos_catastro_simbolo ON suelos_catastro (simbolo)")

    # ── canales_geo ──────────────────────────────────────────────────────────
    op.create_table(
        "canales_geo",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("nombre", sa.String(255), nullable=True),
        sa.Column(
            "tipo",
            sa.String(100),
            nullable=True,
            comment="Canal type (principal, secundario, etc.)",
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
        "CREATE INDEX ix_canales_geo_geometria ON canales_geo USING GIST (geometria)"
    )

    # ── materialized view: suelos por zona ───────────────────────────────────
    # ST_CollectionExtract(..., 3) extracts only polygons from the intersection
    # result (needed when Polygon ∩ MultiPolygon → GeometryCollection).
    # ST_Transform(..., 32720) converts to UTM 20S for metric area calculation.
    op.execute("""
        CREATE MATERIALIZED VIEW mv_suelos_por_zona AS
        SELECT
            z.id                       AS zona_id,
            z.nombre                   AS zona_nombre,
            z.cuenca,
            s.cap,
            s.simbolo,
            s.ip,
            ST_Area(ST_Transform(
                ST_CollectionExtract(ST_Intersection(s.geometria, z.geometria), 3),
                32720
            )) / 10000.0               AS ha_suelo
        FROM zonas_operativas z
        JOIN suelos_catastro s ON ST_Intersects(s.geometria, z.geometria)
        WHERE NOT ST_IsEmpty(
            ST_CollectionExtract(ST_Intersection(s.geometria, z.geometria), 3)
        )
        WITH DATA
    """)
    op.execute(
        "CREATE UNIQUE INDEX uix_mv_suelos_zona_simbolo ON mv_suelos_por_zona (zona_id, simbolo)"
    )
    op.execute("CREATE INDEX ix_mv_suelos_cuenca ON mv_suelos_por_zona (cuenca)")

    # ── materialized view: canales por zona ──────────────────────────────────
    # ST_Length on ST_Transform(..., 32720) gives length in metres; / 1000 → km.
    op.execute("""
        CREATE MATERIALIZED VIEW mv_canales_por_zona AS
        SELECT
            z.id        AS zona_id,
            z.nombre    AS zona_nombre,
            z.cuenca,
            SUM(
                ST_Length(ST_Transform(
                    ST_Intersection(c.geometria, z.geometria),
                    32720
                ))
            ) / 1000.0  AS km_canales
        FROM zonas_operativas z
        JOIN canales_geo c ON ST_Intersects(c.geometria, z.geometria)
        GROUP BY z.id, z.nombre, z.cuenca
        WITH DATA
    """)
    op.execute(
        "CREATE UNIQUE INDEX uix_mv_canales_zona ON mv_canales_por_zona (zona_id)"
    )
    op.execute("CREATE INDEX ix_mv_canales_cuenca ON mv_canales_por_zona (cuenca)")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_canales_por_zona")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_suelos_por_zona")
    op.drop_table("canales_geo")
    op.drop_table("suelos_catastro")
