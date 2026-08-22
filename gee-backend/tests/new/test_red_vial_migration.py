"""Real-PG tests for migration ``0021_add_red_vial``.

Same shape as ``test_canal_catchment_migration`` (the ``0020`` precedent): the
migration DDL is exposed as module constants, each test class builds a throwaway
schema, runs the real statements against it and inspects the result.

What matters beyond "the table exists":

* the **partial** unique index ``ux_red_vial_source_activo`` on
  ``(source_id, parte)`` — a *plain* unique index would forbid the lineage split
  D1 requires (a retired row and its replacement share one ``source_id``), so the
  test asserts ``pg_index.indpred IS NOT NULL``, not merely that the index is
  unique; and the key must include ``parte``, because the N disconnected parts of
  one source feature are all active at the same time (owner decision,
  2026-08-22);
* the ``activo`` / ``parte`` / ``ultima_carga_en`` defaults, which the
  retire-only load rule depends on;
* ``downgrade()`` really removes the table (run from the migration's own
  ``DOWNGRADE_STATEMENTS``, not re-typed here).
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

MIGRATION = importlib.import_module("app.db.migrations.versions.0021_add_red_vial")

SCHEMA = "red_vial_mig_test"

#: The eleven IDECOR source attributes: ten TEXT plus ``lzn`` as a float.
TEXT_ATTRIBUTES: tuple[str, ...] = (
    "fna",
    "gna",
    "rtn",
    "fun",
    "rst",
    "hct",
    "ccn",
    "ccc",
    "rcc",
    "red",
)

_INSERT = text(
    "INSERT INTO red_vial (id, source_id, parte, geom, geom_hash) VALUES "
    "(:id, :source_id, :parte, "
    "ST_GeomFromText('LINESTRING(-62 -32.5, -62.01 -32.51)', 4326), :h)"
)


def _insert(conn, row_id: str, source_id: str, *, parte: int = 1, geom_hash: str = "h") -> None:
    conn.execute(_INSERT, {"id": row_id, "source_id": source_id, "parte": parte, "h": geom_hash})


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
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = 'red_vial'"
        ),
        {"s": SCHEMA},
    ).all()
    return {r[0]: (r[1], r[2]) for r in rows}


class TestRedVialTable:
    def test_table_exists(self, migrated):
        assert (
            migrated.execute(text(f"SELECT to_regclass('{SCHEMA}.red_vial')")).scalar() is not None
        )

    def test_id_is_text_primary_key(self, migrated):
        columns = _columns(migrated)
        assert columns["id"] == ("text", "NO")
        pk = (
            migrated.execute(
                text(
                    "SELECT a.attname FROM pg_index i "
                    "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                    f"WHERE i.indrelid = '{SCHEMA}.red_vial'::regclass AND i.indisprimary"
                )
            )
            .scalars()
            .all()
        )
        assert pk == ["id"]

    def test_source_id_is_text_not_null(self, migrated):
        assert _columns(migrated)["source_id"] == ("text", "NO")

    def test_eleven_idecor_attributes_are_nullable(self, migrated):
        columns = _columns(migrated)
        for attribute in TEXT_ATTRIBUTES:
            assert columns[attribute] == ("text", "YES"), attribute
        assert columns["lzn"] == ("double precision", "YES")

    def test_geom_is_linestring_4326_not_null(self, migrated):
        assert _columns(migrated)["geom"][1] == "NO"
        row = migrated.execute(
            text(
                "SELECT type, srid, coord_dimension FROM geometry_columns "
                "WHERE f_table_schema = :s AND f_table_name = 'red_vial' "
                "AND f_geometry_column = 'geom'"
            ),
            {"s": SCHEMA},
        ).one()
        assert row.type == "LINESTRING"
        assert row.srid == 4326

    def test_geom_hash_is_not_null(self, migrated):
        assert _columns(migrated)["geom_hash"] == ("text", "NO")

    def test_activo_parte_and_ultima_carga_en_defaults(self, migrated):
        migrated.execute(
            text(
                "INSERT INTO red_vial (id, source_id, geom, geom_hash) VALUES "
                "('defaults-1', 'defaults-1', "
                "ST_GeomFromText('LINESTRING(-62 -32.5, -62.01 -32.51)', 4326), 'abc')"
            )
        )
        row = migrated.execute(
            text("SELECT activo, parte, ultima_carga_en FROM red_vial WHERE id = 'defaults-1'")
        ).one()
        assert row.activo is True
        assert row.parte == 1  # a single-line feature is part 1 without saying so
        assert row.ultima_carga_en is not None
        migrated.execute(text("DELETE FROM red_vial WHERE id = 'defaults-1'"))

    def test_parte_is_a_not_null_smallint(self, migrated):
        assert _columns(migrated)["parte"] == ("smallint", "NO")

    def test_expected_indexes_exist(self, migrated):
        names = {
            r[0]
            for r in migrated.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = :s AND tablename = :t"),
                {"s": SCHEMA, "t": "red_vial"},
            )
        }
        assert {
            "ix_red_vial_geom",
            "ix_red_vial_ccc",
            "ix_red_vial_hct",
            "ux_red_vial_source_activo",
        } <= names

    def test_geom_index_is_gist(self, migrated):
        method = migrated.execute(
            text(
                "SELECT am.amname FROM pg_class c "
                "JOIN pg_am am ON am.oid = c.relam "
                "WHERE c.relname = 'ix_red_vial_geom' "
                "AND c.relnamespace = CAST(:s AS regnamespace)"
            ),
            {"s": SCHEMA},
        ).scalar_one()
        assert method == "gist"


class TestPartialUniqueIndex:
    """``ux_red_vial_source_activo`` must be UNIQUE, partial, and keyed on the part."""

    def test_index_is_unique_and_partial(self, migrated):
        row = migrated.execute(
            text(
                "SELECT i.indisunique, i.indpred IS NOT NULL AS is_partial "
                "FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relname = 'ux_red_vial_source_activo' "
                "AND c.relnamespace = CAST(:s AS regnamespace)"
            ),
            {"s": SCHEMA},
        ).one()
        assert row.indisunique is True
        # A plain unique index here would forbid the D1 lineage split.
        assert row.is_partial is True

    def test_the_key_is_source_id_and_parte(self, migrated):
        """Keyed on ``(source_id, parte)``: the N parts of one feature coexist."""
        columns = (
            migrated.execute(
                text(
                    "SELECT a.attname FROM pg_index i "
                    "JOIN pg_class c ON c.oid = i.indexrelid "
                    "JOIN pg_attribute a ON a.attrelid = i.indrelid "
                    " AND a.attnum = ANY(i.indkey) "
                    "WHERE c.relname = 'ux_red_vial_source_activo' "
                    "AND c.relnamespace = CAST(:s AS regnamespace) "
                    "ORDER BY a.attname"
                ),
                {"s": SCHEMA},
            )
            .scalars()
            .all()
        )
        assert columns == ["parte", "source_id"]

    def test_two_active_rows_for_the_same_source_id_and_parte_are_refused(self, migrated):
        _insert(migrated, "28188", "28188", geom_hash="h1")
        with pytest.raises(Exception, match="ux_red_vial_source_activo|duplicate key"):
            _insert(migrated, "28188#2", "28188", geom_hash="h2")
        migrated.execute(text("DELETE FROM red_vial WHERE source_id = '28188'"))

    def test_several_parts_of_one_source_feature_may_be_active_at_once(self, migrated):
        """The whole point of the owner's exit (B): a disconnected feature is N rows."""
        _insert(migrated, "13680", "13680", parte=1, geom_hash="h1")
        _insert(migrated, "13680#2", "13680", parte=2, geom_hash="h2")
        _insert(migrated, "13680#3", "13680", parte=3, geom_hash="h3")
        rows = migrated.execute(
            text(
                "SELECT id, parte FROM red_vial WHERE source_id = '13680' AND activo ORDER BY parte"
            )
        ).all()
        assert [(r.id, r.parte) for r in rows] == [("13680", 1), ("13680#2", 2), ("13680#3", 3)]
        migrated.execute(text("DELETE FROM red_vial WHERE source_id = '13680'"))

    def test_a_retired_row_leaves_room_for_a_new_active_one(self, migrated):
        _insert(migrated, "27371", "27371", geom_hash="h1")
        migrated.execute(text("UPDATE red_vial SET activo = false WHERE id = '27371'"))
        _insert(migrated, "27371#2", "27371", geom_hash="h2")
        rows = migrated.execute(
            text("SELECT id, activo FROM red_vial WHERE source_id = '27371' ORDER BY id")
        ).all()
        assert [(r.id, r.activo) for r in rows] == [("27371", False), ("27371#2", True)]
        migrated.execute(text("DELETE FROM red_vial WHERE source_id = '27371'"))


class TestDowngrade:
    def test_downgrade_drops_the_table(self, test_engine):
        schema = "red_vial_mig_down"
        conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}, public"))
            _run(conn, MIGRATION.UPGRADE_STATEMENTS)
            assert conn.execute(text(f"SELECT to_regclass('{schema}.red_vial')")).scalar()

            _run(conn, MIGRATION.DOWNGRADE_STATEMENTS)
            assert conn.execute(text(f"SELECT to_regclass('{schema}.red_vial')")).scalar() is None
        finally:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("SET search_path TO public"))
            conn.close()

    def test_downgrade_is_refused_while_a_dependent_row_exists(self, test_engine):
        """``ON DELETE RESTRICT`` dependents make the drop fail loudly — by design.

        Slice 2 and 3 hang ``cruce_camino`` / ``relevamiento_tramo`` off
        ``red_vial(id)``; this stands in for one so the documented caveat on
        ``downgrade()`` is asserted rather than only narrated.
        """
        schema = "red_vial_mig_down_dep"
        conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}, public"))
            _run(conn, MIGRATION.UPGRADE_STATEMENTS)
            conn.execute(
                text(
                    "CREATE TABLE dependiente ("
                    "id SERIAL PRIMARY KEY, "
                    "tramo_ref TEXT NOT NULL REFERENCES red_vial(id) ON DELETE RESTRICT)"
                )
            )
            _insert(conn, "dep-1", "dep-1")
            conn.execute(text("INSERT INTO dependiente (tramo_ref) VALUES ('dep-1')"))

            with pytest.raises(Exception, match="depend|dependiente"):
                _run(conn, MIGRATION.DOWNGRADE_STATEMENTS)
        finally:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("SET search_path TO public"))
            conn.close()
