"""Real-PG tests for migration ``0019_add_canal_catchment``.

The shared test schema is built from ``Base.metadata``; ``canal_catchment`` is
migration-only (no ORM model, like ``canal_network``), so it does not exist there.
Each test builds a throwaway schema, provides a minimal ``geo_layers`` (the target
of the ``flow_dir_layer_id`` FK), runs the migration's real DDL against it, and
inspects the result — the same pattern ``test_ficha_migration`` uses.
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

MIGRATION = importlib.import_module("app.db.migrations.versions.0019_add_canal_catchment")

SCHEMA = "canal_catchment_mig_test"

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


class TestTableShape:
    def test_table_exists(self, migrated):
        assert (
            migrated.execute(text(f"SELECT to_regclass('{SCHEMA}.canal_catchment')")).scalar()
            is not None
        )

    def test_canal_id_index_exists(self, migrated):
        names = {
            r[0]
            for r in migrated.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = :s AND tablename = :t"),
                {"s": SCHEMA, "t": "canal_catchment"},
            )
        }
        assert "ix_canal_catchment_canal_id" in names

    def test_geometria_is_nullable(self, migrated):
        layer_id = _seed_layer(migrated)
        migrated.execute(
            text(
                "INSERT INTO canal_catchment "
                "(canal_id, variante, geometria, area_ha, flow_dir_layer_id, version) "
                "VALUES (:cid, 'natural', NULL, 12.5, :lid, 'v1')"
            ),
            {"cid": 9001, "lid": layer_id},
        )
        row = migrated.execute(
            text(
                "SELECT geometria, oversized FROM canal_catchment "
                "WHERE canal_id = 9001 AND variante = 'natural'"
            )
        ).one()
        assert row.geometria is None
        # oversized defaults to false when not supplied.
        assert row.oversized is False
        migrated.execute(text("DELETE FROM canal_catchment WHERE canal_id = 9001"))

    def test_unique_canal_variante(self, migrated):
        layer_id = _seed_layer(migrated)
        insert = text(
            "INSERT INTO canal_catchment (canal_id, variante, flow_dir_layer_id, version) "
            "VALUES (:cid, 'natural', :lid, 'v1')"
        )
        migrated.execute(insert, {"cid": 9100, "lid": layer_id})
        with pytest.raises(Exception, match="uq_canal_catchment_canal_variante|duplicate key"):
            migrated.execute(insert, {"cid": 9100, "lid": layer_id})
        migrated.execute(text("DELETE FROM canal_catchment WHERE canal_id = 9100"))

    def test_same_canal_different_variante_coexist(self, migrated):
        layer_id = _seed_layer(migrated)
        insert = text(
            "INSERT INTO canal_catchment (canal_id, variante, flow_dir_layer_id, version) "
            "VALUES (:cid, :v, :lid, 'v1')"
        )
        migrated.execute(insert, {"cid": 9200, "v": "natural", "lid": layer_id})
        migrated.execute(insert, {"cid": 9200, "v": "relevado", "lid": layer_id})
        count = migrated.execute(
            text("SELECT count(*) FROM canal_catchment WHERE canal_id = 9200")
        ).scalar_one()
        assert count == 2
        migrated.execute(text("DELETE FROM canal_catchment WHERE canal_id = 9200"))


class TestDowngrade:
    def test_downgrade_drops_the_table(self, test_engine):
        schema = "canal_catchment_mig_down"
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
            assert conn.execute(text(f"SELECT to_regclass('{schema}.canal_catchment')")).scalar()
            conn.execute(text("DROP TABLE IF EXISTS canal_catchment"))
            assert (
                conn.execute(text(f"SELECT to_regclass('{schema}.canal_catchment')")).scalar()
                is None
            )
        finally:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("SET search_path TO public"))
            conn.close()
