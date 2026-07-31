"""ficha territorial prep: drop dead canal twins + surrogate key on mv_suelos_por_zona

Phase 0 of the ficha territorial change. Two independent pieces of schema work:

1. **Dead twin removal.** ``canales_geo`` and ``mv_canales_por_zona`` (0015) are
   unreferenced outside their creating migration — ``canal_network``
   (``w7r4s5t6u593``) is the canonical canal table and the one the routing and
   vector-tile code actually reads. The view is dropped BEFORE the table: the
   reverse order fails on the dependency.

2. **Concurrent-refresh key for ``mv_suelos_por_zona``.** 0015 created only two
   non-unique indexes (``ix_mv_suelos_cuenca``, ``ix_mv_suelos_zona``), so
   ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` was illegal — a plain REFRESH takes
   an ACCESS EXCLUSIVE lock and blocks every zone dashboard read for its whole
   duration. ``(zona_id, simbolo)`` is NOT a candidate key either: the same soil
   symbol can intersect one zone as two disjoint polygons. The view is therefore
   recreated with a surrogate ``mv_id`` (``row_number()`` over a deterministic
   ordering) plus a unique index on it. The projection is otherwise byte-identical
   to 0015 — existing consumers keep working.

   **Refresh cadence**: the soils ETL
   (``python -m app.domains.geo.etl.load_suelos_catastro``) refreshes the view as
   its final step, in autocommit and OUTSIDE the load transaction, because
   PostgreSQL forbids ``REFRESH ... CONCURRENTLY`` inside a transaction block.
   There is no scheduled refresh: soils are static reference data. Recovery for
   a stale view is either re-running that ETL command or the operator action
   ``POST /api/v2/admin/geo/suelos/refresh-mv`` (admin-only).

The recreate deliberately does NOT guard ``suelos_catastro`` with ``IF EXISTS``:
if the table is missing the database never ran 0015 and silently skipping would
leave the view unrefreshable-concurrently, which only surfaces much later as an
ETL failure. Fail here instead.

Revision ID: 0017_ficha_territorial_prep
Revises: zz_capas_publicacion_fecha
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0017_ficha_territorial_prep"
down_revision: Union[str, None] = "zz_capas_publicacion_fecha"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── dead twin removal ────────────────────────────────────────────────────────
# View first, then table: dropping ``canales_geo`` while the MV still depends on
# it raises "cannot drop table canales_geo because other objects depend on it".
DROP_TWIN_STATEMENTS: tuple[str, ...] = (
    "DROP MATERIALIZED VIEW IF EXISTS mv_canales_por_zona",
    "DROP TABLE IF EXISTS canales_geo",
)

# ── mv_suelos_por_zona, recreated with a surrogate key ───────────────────────
# Same projection as 0015:94-113 plus ``mv_id``. ST_CollectionExtract(..., 3)
# keeps only polygons (Polygon ∩ MultiPolygon can yield a GeometryCollection);
# ST_Transform(..., 32720) gives UTM 20S metres for the area computation.
MV_SUELOS_POR_ZONA: str = """
    CREATE MATERIALIZED VIEW mv_suelos_por_zona AS
    SELECT
        row_number() OVER (ORDER BY z.id, s.id) AS mv_id,
        z.id           AS zona_id,
        z.nombre       AS zona_nombre,
        z.cuenca,
        s.cap,
        s.simbolo,
        s.ip,
        ST_Area(ST_Transform(
            ST_CollectionExtract(ST_Intersection(s.geometria, z.geometria), 3),
            32720
        )) / 10000.0   AS ha_suelo
    FROM zonas_operativas z
    JOIN suelos_catastro s ON ST_Intersects(s.geometria, z.geometria)
    WHERE NOT ST_IsEmpty(
        ST_CollectionExtract(ST_Intersection(s.geometria, z.geometria), 3)
    )
    WITH DATA
"""

RECREATE_MV_STATEMENTS: tuple[str, ...] = (
    # Dropping the view also drops its two indexes; they are recreated below.
    "DROP MATERIALIZED VIEW IF EXISTS mv_suelos_por_zona",
    MV_SUELOS_POR_ZONA,
    # The whole point of the recreate: REFRESH ... CONCURRENTLY needs this.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_mv_suelos_por_zona_id ON mv_suelos_por_zona (mv_id)",
    "CREATE INDEX IF NOT EXISTS ix_mv_suelos_cuenca ON mv_suelos_por_zona (cuenca)",
    "CREATE INDEX IF NOT EXISTS ix_mv_suelos_zona ON mv_suelos_por_zona (zona_id)",
)

UPGRADE_STATEMENTS: tuple[str, ...] = DROP_TWIN_STATEMENTS + RECREATE_MV_STATEMENTS


def assert_canales_geo_empty(conn) -> None:
    """Refuse to drop a ``canales_geo`` that still holds rows.

    "Unreferenced in the repo" is NOT "empty in this deployment": this very
    change found BOTH ``suelos_catastro`` (45 rows) and ``canales_geo``
    (20 rows) populated out-of-band in prod. The operator must export
    deliberately (ST_AsGeoJSON dump), TRUNCATE, then re-run the migration.
    Prod export done 2026-07-31: ``~/backups/canales_geo_export_*.geojson``.

    Standalone function (not inlined in ``upgrade``) so the real-PG migration
    test can exercise the refusal path directly.
    """
    exists = conn.exec_driver_sql("SELECT to_regclass('canales_geo') IS NOT NULL").scalar()
    if exists:
        count = conn.exec_driver_sql("SELECT count(*) FROM canales_geo").scalar()
        if count:
            raise RuntimeError(
                f"canales_geo still holds {count} rows; export them first, "
                "TRUNCATE deliberately, then re-run this migration. "
                "Refusing to destroy data silently."
            )


def upgrade() -> None:
    assert_canales_geo_empty(op.get_bind())
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    raise RuntimeError(
        "downgrade unsupported: canales_geo/mv_canales_por_zona were dead schema "
        "and mv_suelos_por_zona cannot lose its surrogate key without breaking "
        "concurrent refresh. Restore from a backup instead."
    )
