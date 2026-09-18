"""Real-PG tests for migration ``0024_add_cruce_conduccion``.

Applies the 0022 DDL in a throwaway schema, then the 0024 ALTER statements, so
the CHECK widening is exercised against the same constants the migration runs.
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

BASE = importlib.import_module("app.db.migrations.versions.0022_add_cruce_camino")
MIGRATION = importlib.import_module("app.db.migrations.versions.0024_add_cruce_conduccion")
RED_VIAL_MIGRATION = importlib.import_module("app.db.migrations.versions.0021_add_red_vial")
CANAL_MIGRATION = importlib.import_module("app.db.migrations.versions.0020_add_canal_consorcio")

SCHEMA = "cruce_conduccion_mig_test"
JOB_ID = "11111111-1111-1111-1111-111111111111"


def _run(conn, statements) -> None:
    for statement in statements:
        conn.execute(text(statement))


def _seed_dependencies(conn) -> None:
    _run(conn, RED_VIAL_MIGRATION.UPGRADE_STATEMENTS)
    conn.execute(text(CANAL_MIGRATION.CREATE_CANAL_CONSORCIO))
    conn.execute(text("CREATE TABLE geo_jobs (id UUID PRIMARY KEY)"))
    conn.execute(
        text(
            "INSERT INTO red_vial (id, source_id, geom, geom_hash) VALUES "
            "('28188', '28188', ST_GeomFromText('LINESTRING(-62 -32.5, -62.01 -32.51)', 4326), 'h')"
        )
    )
    conn.execute(
        text(
            "INSERT INTO canal_consorcio (id, nombre, estado, geom) VALUES "
            "('c-1', 'Canal 1', 'relevado', "
            "ST_GeomFromText('LINESTRING(-62 -32.6, -62.01 -32.61)', 4326))"
        )
    )
    conn.execute(text(f"INSERT INTO geo_jobs (id) VALUES ('{JOB_ID}')"))


@pytest.fixture(scope="module")
def migrated(test_engine):
    conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(f"SET search_path TO {SCHEMA}, public"))
        _seed_dependencies(conn)
        _run(conn, BASE.UPGRADE_STATEMENTS)
        _run(conn, MIGRATION.UPGRADE_STATEMENTS)
        yield conn
    finally:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text("SET search_path TO public"))
        conn.close()


def _insert(conn, *, tipo: str) -> None:
    conn.execute(
        text(
            "INSERT INTO cruce_camino "
            "(id, area_id, tramo_ref, tipo, geometria, geo_job_id"
            ", direccion_flujo_deg, rumbo_camino_deg, orden_ranking) VALUES "
            "(gen_random_uuid(), 'a', '28188', :tipo, "
            "ST_SetSRID(ST_MakePoint(-62, -32.5), 4326), "
            f"'{JOB_ID}', 90, 90, NULL)"
        ),
        {"tipo": tipo},
    )


class TestConduccionCheck:
    def test_conduccion_row_is_storable(self, migrated):
        _insert(migrated, tipo="conduccion")
        n = migrated.execute(
            text("SELECT count(*) FROM cruce_camino WHERE tipo = 'conduccion'")
        ).scalar()
        assert n == 1

    def test_ck_cruce_conduccion_exists(self, migrated):
        found = migrated.execute(
            text(
                "SELECT 1 FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "WHERE t.relname = 'cruce_camino' AND c.conname = 'ck_cruce_conduccion'"
            )
        ).scalar()
        assert found == 1

    def test_ranked_conduccion_is_rejected(self, migrated):
        with pytest.raises(Exception) as exc:
            migrated.execute(
                text(
                    "INSERT INTO cruce_camino "
                    "(id, area_id, tramo_ref, tipo, geometria, geo_job_id, "
                    "direccion_flujo_deg, rumbo_camino_deg, orden_ranking) VALUES "
                    f"(gen_random_uuid(), 'a', '28188', 'conduccion', "
                    f"ST_SetSRID(ST_MakePoint(-62, -32.5), 4326), '{JOB_ID}', "
                    "90, 90, 1)"
                )
            )
        assert "ck_cruce_conduccion" in str(exc.value) or "check" in str(exc.value).lower()

    def test_unknown_tipo_is_still_rejected(self, migrated):
        with pytest.raises(Exception) as exc:
            migrated.execute(
                text(
                    "INSERT INTO cruce_camino "
                    "(id, area_id, tramo_ref, tipo, geometria, geo_job_id) VALUES "
                    f"(gen_random_uuid(), 'a', '28188', 'camino_drenaje', "
                    f"ST_SetSRID(ST_MakePoint(-62, -32.5), 4326), '{JOB_ID}')"
                )
            )
        assert "ck_cruce_tipo" in str(exc.value) or "check" in str(exc.value).lower()
