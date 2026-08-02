"""Real-PG tests for migration ``0020_add_canal_consorcio``.

The shared test schema is built from ``Base.metadata``; ``canal_consorcio`` and
``canal_catchment`` are migration-only (no ORM model, like ``canal_network``), so
they do not exist there. Each test builds a throwaway schema, provides a minimal
``geo_layers`` (the target of the ``flow_dir_layer_id`` FK), runs the migration's
real DDL against it, and inspects the result — the same pattern
``test_ficha_migration`` uses.

``0020`` retargets the ``canal_cuenca`` engine from ``canal_network`` to the 60
curated consorcio canals: it creates ``canal_consorcio`` and REDEFINES
``canal_catchment`` to be keyed on ``canal_ref`` (a real FK to
``canal_consorcio(id)``) instead of the old ``canal_id INTEGER``.
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

MIGRATION = importlib.import_module("app.db.migrations.versions.0020_add_canal_consorcio")

SCHEMA = "canal_consorcio_mig_test"

_PRE_WORLD: tuple[str, ...] = (
    # Minimal FK target so ``flow_dir_layer_id REFERENCES geo_layers(id)`` resolves
    # inside the throwaway schema.
    "CREATE TABLE geo_layers (id UUID PRIMARY KEY DEFAULT gen_random_uuid())",
)


@pytest.fixture(scope="module")
def migrated(test_engine):
    conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(f"SET search_path TO {SCHEMA}, public"))
        for statement in _PRE_WORLD:
            conn.execute(text(statement))
        for statement in MIGRATION.UPGRADE_STATEMENTS:
            conn.execute(text(statement))
        yield conn
    finally:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text("SET search_path TO public"))
        conn.close()


def _seed_layer(conn) -> str:
    return conn.execute(text("INSERT INTO geo_layers DEFAULT VALUES RETURNING id")).scalar_one()


def _seed_canal(conn, canal_id: str, estado: str = "relevado") -> None:
    conn.execute(
        text(
            "INSERT INTO canal_consorcio (id, nombre, estado, geom) "
            "VALUES (:id, :n, :estado, "
            "ST_GeomFromText('LINESTRING(-62 -33, -62.01 -33.01)', 4326)) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": canal_id, "n": f"canal {canal_id}", "estado": estado},
    )


class TestCanalConsorcioTable:
    def test_table_exists(self, migrated):
        assert (
            migrated.execute(text(f"SELECT to_regclass('{SCHEMA}.canal_consorcio')")).scalar()
            is not None
        )

    def test_geom_gist_index_exists(self, migrated):
        names = {
            r[0]
            for r in migrated.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = :s AND tablename = :t"),
                {"s": SCHEMA, "t": "canal_consorcio"},
            )
        }
        assert "ix_canal_consorcio_geom" in names

    def test_string_id_primary_key(self, migrated):
        _seed_canal(migrated, "canal-ne-sin-intervencion")
        stored = migrated.execute(
            text("SELECT id FROM canal_consorcio WHERE id = 'canal-ne-sin-intervencion'")
        ).scalar_one()
        assert stored == "canal-ne-sin-intervencion"
        migrated.execute(text("DELETE FROM canal_consorcio WHERE id = 'canal-ne-sin-intervencion'"))

    def test_estado_check_constraint_rejects_bad_value(self, migrated):
        with pytest.raises(Exception, match="ck_canal_consorcio_estado|check constraint"):
            migrated.execute(
                text(
                    "INSERT INTO canal_consorcio (id, nombre, estado, geom) "
                    "VALUES ('bad', 'bad', 'inventado', "
                    "ST_GeomFromText('LINESTRING(0 0, 1 1)', 4326))"
                )
            )

    def test_prioridad_and_longitud_nullable(self, migrated):
        migrated.execute(
            text(
                "INSERT INTO canal_consorcio (id, nombre, estado, geom) "
                "VALUES ('nullable-check', 'n', 'propuesto', "
                "ST_GeomFromText('LINESTRING(0 0, 1 1)', 4326))"
            )
        )
        row = migrated.execute(
            text("SELECT prioridad, longitud_m FROM canal_consorcio WHERE id = 'nullable-check'")
        ).one()
        assert row.prioridad is None
        assert row.longitud_m is None
        migrated.execute(text("DELETE FROM canal_consorcio WHERE id = 'nullable-check'"))


class TestCanalCatchmentTable:
    def test_table_exists(self, migrated):
        assert (
            migrated.execute(text(f"SELECT to_regclass('{SCHEMA}.canal_catchment')")).scalar()
            is not None
        )

    def test_canal_ref_index_exists(self, migrated):
        names = {
            r[0]
            for r in migrated.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = :s AND tablename = :t"),
                {"s": SCHEMA, "t": "canal_catchment"},
            )
        }
        assert "ix_canal_catchment_canal_ref" in names

    def test_old_canal_id_column_is_gone(self, migrated):
        cols = {
            r[0]
            for r in migrated.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = 'canal_catchment'"
                ),
                {"s": SCHEMA},
            )
        }
        assert "canal_ref" in cols
        assert "canal_id" not in cols  # the retarget dropped the int key

    def test_geometria_is_nullable(self, migrated):
        layer_id = _seed_layer(migrated)
        _seed_canal(migrated, "cat-null")
        migrated.execute(
            text(
                "INSERT INTO canal_catchment "
                "(canal_ref, variante, geometria, area_ha, flow_dir_layer_id, version) "
                "VALUES ('cat-null', 'relevado', NULL, 12.5, :lid, 'v1')"
            ),
            {"lid": layer_id},
        )
        row = migrated.execute(
            text(
                "SELECT geometria, oversized FROM canal_catchment "
                "WHERE canal_ref = 'cat-null' AND variante = 'relevado'"
            )
        ).one()
        assert row.geometria is None
        assert row.oversized is False  # defaults to false when not supplied
        migrated.execute(text("DELETE FROM canal_catchment WHERE canal_ref = 'cat-null'"))
        migrated.execute(text("DELETE FROM canal_consorcio WHERE id = 'cat-null'"))

    def test_canal_ref_fk_rejects_unknown_canal(self, migrated):
        layer_id = _seed_layer(migrated)
        with pytest.raises(Exception, match="foreign key|violates"):
            migrated.execute(
                text(
                    "INSERT INTO canal_catchment "
                    "(canal_ref, variante, flow_dir_layer_id, version) "
                    "VALUES ('does-not-exist', 'relevado', :lid, 'v1')"
                ),
                {"lid": layer_id},
            )

    def test_fk_cascade_delete(self, migrated):
        layer_id = _seed_layer(migrated)
        _seed_canal(migrated, "cat-cascade")
        migrated.execute(
            text(
                "INSERT INTO canal_catchment "
                "(canal_ref, variante, flow_dir_layer_id, version) "
                "VALUES ('cat-cascade', 'relevado', :lid, 'v1')"
            ),
            {"lid": layer_id},
        )
        # Deleting the canal cascades to its catchment (ON DELETE CASCADE).
        migrated.execute(text("DELETE FROM canal_consorcio WHERE id = 'cat-cascade'"))
        remaining = migrated.execute(
            text("SELECT count(*) FROM canal_catchment WHERE canal_ref = 'cat-cascade'")
        ).scalar_one()
        assert remaining == 0

    def test_unique_canal_ref_variante(self, migrated):
        layer_id = _seed_layer(migrated)
        _seed_canal(migrated, "cat-uq")
        insert = text(
            "INSERT INTO canal_catchment (canal_ref, variante, flow_dir_layer_id, version) "
            "VALUES ('cat-uq', 'relevado', :lid, 'v1')"
        )
        migrated.execute(insert, {"lid": layer_id})
        with pytest.raises(Exception, match="uq_canal_catchment_canal_ref_variante|duplicate key"):
            migrated.execute(insert, {"lid": layer_id})
        migrated.execute(text("DELETE FROM canal_catchment WHERE canal_ref = 'cat-uq'"))
        migrated.execute(text("DELETE FROM canal_consorcio WHERE id = 'cat-uq'"))


class TestDowngrade:
    def test_downgrade_restores_0019_schema(self, test_engine):
        schema = "canal_consorcio_mig_down"
        conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}, public"))
            conn.execute(
                text("CREATE TABLE geo_layers (id UUID PRIMARY KEY DEFAULT gen_random_uuid())")
            )
            for statement in MIGRATION.UPGRADE_STATEMENTS:
                conn.execute(text(statement))
            assert conn.execute(text(f"SELECT to_regclass('{schema}.canal_consorcio')")).scalar()

            # Emulate downgrade(): drop the curated tables, rebuild 0019's int-keyed
            # canal_catchment, drop canal_consorcio.
            conn.execute(text("DROP TABLE IF EXISTS canal_catchment"))
            conn.execute(text("DROP TABLE IF EXISTS canal_consorcio"))
            conn.execute(
                text(
                    "CREATE TABLE canal_catchment ("
                    "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
                    "canal_id INTEGER NOT NULL, variante TEXT NOT NULL, "
                    "geometria geometry(MultiPolygon, 4326), area_ha DOUBLE PRECISION, "
                    "oversized BOOLEAN NOT NULL DEFAULT false, "
                    "flow_dir_layer_id UUID REFERENCES geo_layers(id) ON DELETE SET NULL, "
                    "version TEXT NOT NULL, "
                    "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                    "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                    "CONSTRAINT uq_canal_catchment_canal_variante UNIQUE (canal_id, variante))"
                )
            )
            # canal_consorcio gone, canal_catchment back to the int-keyed shape.
            assert (
                conn.execute(text(f"SELECT to_regclass('{schema}.canal_consorcio')")).scalar()
                is None
            )
            cols = {
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = :s AND table_name = 'canal_catchment'"
                    ),
                    {"s": schema},
                )
            }
            assert "canal_id" in cols
            assert "canal_ref" not in cols
        finally:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("SET search_path TO public"))
            conn.close()
