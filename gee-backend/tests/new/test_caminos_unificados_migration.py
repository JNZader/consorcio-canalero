"""Real-PG tests for migration ``0029_add_mv_caminos_unificados``.

Verifies that the materialized view:
1. Creates cleanly over ``red_vial`` with its surrogate integer id, ruta, metadata, and PostGIS geom.
2. Supports ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` via the unique index on ``ruta``.
3. Correctly aggregates multiple physical tramos into a unified MultiLineString route.
4. Cleans up completely on ``downgrade()``.
"""

from __future__ import annotations

import importlib
import pytest
from sqlalchemy import text

RED_VIAL_MIGRATION = importlib.import_module("app.db.migrations.versions.0021_add_red_vial")
MIGRATION = importlib.import_module("app.db.migrations.versions.0029_add_mv_caminos_unificados")

SCHEMA = "caminos_unificados_mig_test"


def _run(conn, statements) -> None:
    for statement in statements:
        conn.execute(text(statement))


@pytest.fixture(scope="module")
def migrated(test_engine):
    conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(f"SET search_path TO {SCHEMA}, public"))
        # First build red_vial
        _run(conn, RED_VIAL_MIGRATION.UPGRADE_STATEMENTS)
        # Then build mv_caminos_unificados
        _run(conn, MIGRATION.UPGRADE_STATEMENTS)
        yield conn
    finally:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text("SET search_path TO public"))
        conn.close()


class TestCaminosUnificadosMaterializedView:
    def test_matview_exists(self, migrated):
        relkind = migrated.execute(
            text(
                "SELECT c.relkind FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                f"WHERE n.nspname = '{SCHEMA}' AND c.relname = 'mv_caminos_unificados'"
            )
        ).scalar()
        assert relkind == "m"

    def test_vt_view_exists(self, migrated):
        relkind = migrated.execute(
            text(
                "SELECT c.relkind FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                f"WHERE n.nspname = '{SCHEMA}' AND c.relname = 'vt_caminos_unificados'"
            )
        ).scalar()
        assert relkind == "v"

    def test_unique_indexes_exist(self, migrated):
        indexes = migrated.execute(
            text(
                "SELECT c.relname, i.indisunique FROM pg_index i "
                "JOIN pg_class c ON c.oid = i.indexrelid "
                "JOIN pg_class t ON t.oid = i.indrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                f"WHERE n.nspname = '{SCHEMA}' AND t.relname = 'mv_caminos_unificados'"
            )
        ).all()
        index_dict = {r[0]: r[1] for r in indexes}
        assert "ux_mv_caminos_unificados_ruta" in index_dict
        assert index_dict["ux_mv_caminos_unificados_ruta"] is True
        assert "ux_mv_caminos_unificados_id" in index_dict
        assert index_dict["ux_mv_caminos_unificados_id"] is True
        assert "ix_mv_caminos_unificados_geom" in index_dict

    def test_concurrent_refresh_and_aggregation(self, migrated):
        # Insert 2 segments of T269-03 and 1 segment of RP3
        migrated.execute(
            text(
                f"INSERT INTO {SCHEMA}.red_vial (id, source_id, parte, fna, gna, rtn, red, ccn, lzn, geom, geom_hash) VALUES "
                "('tramo-1', 's1', 1, 'Camino Provincial T269-03', 'Camino Provincial', 'T269-03', 'Terciaria', 'C.C. 269 - SAN MARCOS SUD', 2.5, "
                "ST_GeomFromText('LINESTRING(-62.5 -32.5, -62.5 -32.52)', 4326), 'h1'), "
                "('tramo-2', 's2', 1, 'Camino Provincial T269-03', 'Camino Provincial', 'T269-03', 'Terciaria', 'C.C. 269 - SAN MARCOS SUD', 3.0, "
                "ST_GeomFromText('LINESTRING(-62.5 -32.52, -62.5 -32.55)', 4326), 'h2'), "
                "('tramo-3', 's3', 1, 'Ruta Provincial 3', 'Ruta Provincial', 'RP3', 'Secundaria', 'C.C. 027 - LEONES', 10.0, "
                "ST_GeomFromText('LINESTRING(-62.4 -32.5, -62.4 -32.6)', 4326), 'h3')"
            )
        )

        # Refresh CONCURRENTLY must succeed without error
        migrated.execute(
            text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {SCHEMA}.mv_caminos_unificados")
        )

        rows = migrated.execute(
            text(
                f"SELECT ruta, nombre, red, consorcios, longitud_declarada_km, cantidad_tramos_fisicos, "
                f"ST_GeometryType(geom), ST_IsValid(geom) "
                f"FROM {SCHEMA}.mv_caminos_unificados ORDER BY ruta"
            )
        ).all()

        assert len(rows) == 2

        # RP3
        rp3 = rows[0]
        assert rp3[0] == "RP3"
        assert rp3[2] == "Secundaria"
        assert rp3[3] == "C.C. 027 - LEONES"
        assert rp3[4] == 10.0
        assert rp3[5] == 1
        assert rp3[7] is True

        # T269-03
        t269 = rows[1]
        assert t269[0] == "T269-03"
        assert t269[1] == "Camino Provincial T269-03"
        assert t269[2] == "Terciaria"
        assert t269[3] == "C.C. 269 - SAN MARCOS SUD"
        assert t269[4] == 5.5  # 2.5 + 3.0
        assert t269[5] == 2  # 2 tramos
        assert t269[6] == "ST_MultiLineString"
        assert t269[7] is True

    def test_downgrade_removes_matview(self, migrated):
        _run(migrated, MIGRATION.DOWNGRADE_STATEMENTS)
        rel_mv = migrated.execute(
            text(
                "SELECT 1 FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                f"WHERE n.nspname = '{SCHEMA}' AND c.relname = 'mv_caminos_unificados'"
            )
        ).scalar()
        assert rel_mv is None
        rel_vt = migrated.execute(
            text(
                "SELECT 1 FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                f"WHERE n.nspname = '{SCHEMA}' AND c.relname = 'vt_caminos_unificados'"
            )
        ).scalar()
        assert rel_vt is None
        # Re-upgrade to leave fixture clean for teardown
        _run(migrated, MIGRATION.UPGRADE_STATEMENTS)
