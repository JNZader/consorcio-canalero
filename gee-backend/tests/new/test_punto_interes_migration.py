"""Real-PG tests for migration ``0025_add_punto_interes``.

Same shape as ``test_cruce_camino_migration``: the DDL lives as module constants
on the migration, each test class builds a throwaway schema and runs the real
statements against it. Skip if no PostGIS rather than invent sqlite — that skip
is the ``test_engine`` fixture (session exits when neither Docker nor
``TEST_DATABASE_URL`` is available).
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

MIGRATION = importlib.import_module("app.db.migrations.versions.0025_add_punto_interes")

SCHEMA = "punto_interes_mig_test"

EXPECTED_CHECKS: tuple[str, ...] = (
    "ck_punto_interes_titulo_len",
    "ck_punto_interes_nota_len",
    "ck_punto_interes_tipo",
)


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
        _run(conn, MIGRATION.UPGRADE_STATEMENTS)
        yield conn
    finally:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text("SET search_path TO public"))
        conn.close()


def _columns(conn) -> dict[str, tuple[str, str]]:
    rows = conn.execute(
        text(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = 'punto_interes'"
        ),
        {"s": SCHEMA},
    ).all()
    return {r[0]: (r[1], r[2]) for r in rows}


class TestPuntoInteresTable:
    def test_table_exists(self, migrated):
        exists = migrated.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :s AND table_name = 'punto_interes'"
            ),
            {"s": SCHEMA},
        ).scalar()
        assert exists == 1

    @pytest.mark.parametrize(
        "column", ["id", "geometria", "titulo", "tipo", "created_at", "updated_at"]
    )
    def test_required_columns_are_not_null(self, migrated, column: str):
        _, nullable = _columns(migrated)[column]
        assert nullable == "NO"

    @pytest.mark.parametrize("column", ["nota", "created_by"])
    def test_optional_columns_are_nullable(self, migrated, column: str):
        _, nullable = _columns(migrated)[column]
        assert nullable == "YES"

    def test_geometria_is_point_4326(self, migrated):
        srid, geom_type = migrated.execute(
            text(
                "SELECT srid, type FROM geometry_columns "
                "WHERE f_table_schema = :s AND f_table_name = 'punto_interes' "
                "AND f_geometry_column = 'geometria'"
            ),
            {"s": SCHEMA},
        ).one()
        assert srid == 4326
        assert geom_type == "POINT"

    def test_created_by_has_no_foreign_key(self, migrated):
        fks = (
            migrated.execute(
                text(
                    "SELECT kcu.column_name FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kcu "
                    "  ON kcu.constraint_name = tc.constraint_name "
                    " AND kcu.constraint_schema = tc.constraint_schema "
                    "WHERE tc.table_schema = :s AND tc.table_name = 'punto_interes' "
                    "AND tc.constraint_type = 'FOREIGN KEY'"
                ),
                {"s": SCHEMA},
            )
            .scalars()
            .all()
        )
        assert fks == []


class TestChecks:
    @pytest.mark.parametrize("name", EXPECTED_CHECKS)
    def test_check_exists_by_name(self, migrated, name: str):
        found = migrated.execute(
            text(
                "SELECT 1 FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = :s AND t.relname = 'punto_interes' "
                "AND c.contype = 'c' AND c.conname = :name"
            ),
            {"s": SCHEMA, "name": name},
        ).scalar()
        assert found == 1, f"CHECK {name} is missing"

    def test_tipo_rejects_unknown_values(self, migrated):
        with pytest.raises(Exception) as exc:
            migrated.execute(
                text(
                    "INSERT INTO punto_interes (titulo, tipo, geometria) VALUES "
                    "('x', 'cuneta', ST_SetSRID(ST_MakePoint(-62, -32.5), 4326))"
                )
            )
        assert "ck_punto_interes_tipo" in str(exc.value) or "check" in str(exc.value).lower()


class TestIndexes:
    def test_geom_index_is_gist(self, migrated):
        method = migrated.execute(
            text(
                "SELECT am.amname FROM pg_index i "
                "JOIN pg_class idx ON idx.oid = i.indexrelid "
                "JOIN pg_am am ON am.oid = idx.relam "
                "JOIN pg_namespace n ON n.oid = idx.relnamespace "
                "WHERE n.nspname = :s AND idx.relname = 'ix_punto_interes_geom'"
            ),
            {"s": SCHEMA},
        ).scalar()
        assert method == "gist"


class TestNothingIsPublished:
    def test_no_view_was_created(self, migrated):
        views = (
            migrated.execute(
                text("SELECT viewname FROM pg_views WHERE schemaname = :s"),
                {"s": SCHEMA},
            )
            .scalars()
            .all()
        )
        assert views == [], f"this migration must create no view — found {views}"

    def test_no_matview_was_created(self, migrated):
        matviews = (
            migrated.execute(
                text("SELECT matviewname FROM pg_matviews WHERE schemaname = :s"),
                {"s": SCHEMA},
            )
            .scalars()
            .all()
        )
        assert matviews == [], f"this migration must create no matview — found {matviews}"

    def test_migration_touches_no_view_or_matview_statement(self):
        all_ddl = " ".join(MIGRATION.UPGRADE_STATEMENTS + MIGRATION.DOWNGRADE_STATEMENTS).upper()
        for forbidden in (
            "CREATE VIEW",
            "CREATE OR REPLACE VIEW",
            "MATERIALIZED VIEW",
            "DROP VIEW",
        ):
            assert forbidden not in all_ddl, f"migration must not contain {forbidden!r}"


class TestDowngrade:
    def test_downgrade_drops_the_table(self, test_engine):
        schema = f"{SCHEMA}_down"
        conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}, public"))
            _run(conn, MIGRATION.UPGRADE_STATEMENTS)
            _run(conn, MIGRATION.DOWNGRADE_STATEMENTS)

            still_there = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = :s AND table_name = 'punto_interes'"
                ),
                {"s": schema},
            ).scalar()
            assert still_there is None, "downgrade must drop punto_interes"
        finally:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("SET search_path TO public"))
            conn.close()
