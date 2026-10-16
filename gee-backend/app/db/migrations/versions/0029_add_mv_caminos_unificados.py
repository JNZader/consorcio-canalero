"""add mv_caminos_unificados — continuous road aggregation materialized view

Aggregates the physical road segments in ``red_vial`` (381 rows, referenced with
RESTRICT by ``cruce_camino`` and ``relevamiento_tramo``) into their 83 continuous
routes by ``rtn`` (Ruta / Traza Número).

Preserves physical segment truth in ``red_vial`` while providing:
1. Fast, single-geometry lines per route for MapLibre and Martin Vector Tiles.
2. Continuous line geometry for elevation profile sampling without part jumps.
3. Summary metrics per route (tramos count, declared km, geodesic km, consorcios).
4. Concurrent refresh capability via UNIQUE index on ``ruta`` (``rtn``).

Revision ID: 0029_add_mv_caminos_unificados
Revises: zz_elevation_profile_cache
Create Date: 2026-10-16
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0029_add_mv_caminos_unificados"
down_revision: Union[str, None] = "zz_elevation_profile_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "consorcio_app"

CREATE_MV_CAMINOS_UNIFICADOS = """
CREATE MATERIALIZED VIEW mv_caminos_unificados AS
SELECT 
    row_number() OVER (ORDER BY rtn)::integer AS id,
    rtn AS ruta,
    min(fna) AS nombre,
    min(gna) AS tipo_generico,
    red,
    string_agg(DISTINCT ccn, ', ' ORDER BY ccn) 
        FILTER (WHERE ccn IS NOT NULL AND ccn NOT IN ('No aplica', 'No disponible')) AS consorcios,
    round(sum(lzn)::numeric, 2) AS longitud_declarada_km,
    round((sum(ST_Length(geom::geography)) / 1000.0)::numeric, 2) AS longitud_geodesica_km,
    count(*)::integer AS cantidad_tramos_fisicos,
    ST_Multi(ST_LineMerge(ST_Union(geom)))::geometry(MultiLineString, 4326) AS geom
FROM red_vial
WHERE activo = true
GROUP BY rtn, red;
"""

CREATE_UX_INDEX_RUTA = (
    "CREATE UNIQUE INDEX ux_mv_caminos_unificados_ruta ON mv_caminos_unificados (ruta);"
)

CREATE_UX_INDEX_ID = (
    "CREATE UNIQUE INDEX ux_mv_caminos_unificados_id ON mv_caminos_unificados (id);"
)

CREATE_GIST_INDEX = (
    "CREATE INDEX ix_mv_caminos_unificados_geom ON mv_caminos_unificados USING GIST (geom);"
)

OWNERSHIP_SQL = f"""
DO $own$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
        ALTER MATERIALIZED VIEW public.mv_caminos_unificados OWNER TO {APP_ROLE};
        ALTER INDEX public.ux_mv_caminos_unificados_ruta OWNER TO {APP_ROLE};
        ALTER INDEX public.ux_mv_caminos_unificados_id OWNER TO {APP_ROLE};
        ALTER INDEX public.ix_mv_caminos_unificados_geom OWNER TO {APP_ROLE};
    END IF;
END
$own$;
"""

DROP_MV = "DROP MATERIALIZED VIEW IF EXISTS mv_caminos_unificados CASCADE;"

UPGRADE_STATEMENTS: tuple[str, ...] = (
    CREATE_MV_CAMINOS_UNIFICADOS,
    CREATE_UX_INDEX_RUTA,
    CREATE_UX_INDEX_ID,
    CREATE_GIST_INDEX,
    OWNERSHIP_SQL,
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (DROP_MV,)


def upgrade() -> None:
    for stmt in UPGRADE_STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE_STATEMENTS:
        op.execute(stmt)
