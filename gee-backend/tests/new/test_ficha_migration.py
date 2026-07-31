"""Real-PG tests for migration ``0017_ficha_territorial_prep`` (ficha territorial, phase 0).

The shared test schema is built from ``Base.metadata``, not from migrations, so
``suelos_catastro`` / ``canales_geo`` / the materialized views simply do not
exist there — asserting against it would prove nothing. Instead each of these
tests rebuilds the *pre-migration* world (the relevant slice of ``0015`` plus
``canal_network`` from ``w7r4s5t6u593``) inside a throwaway schema, runs the
migration's real SQL against it, and inspects the result.

Two consequences shape the fixture:

* ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` cannot run inside a transaction
  block, so the connection is AUTOCOMMIT — the ``db`` fixture's
  transaction-per-test rollback is unusable here. Isolation comes from the
  throwaway schema being dropped in teardown.
* ``search_path`` points at the throwaway schema first, so the migration's
  unqualified identifiers resolve there and never touch the shared schema.
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

# ``parcelas_catastro`` lives in the intelligence models module, which nothing in
# conftest imports eagerly. Without this import the session-scoped ``create_all``
# skips the table whenever this file runs on its own — same trap conftest
# documents for ``EmailCode``.
from app.domains.geo.intelligence import models as _intelligence_models  # noqa: F401

MIGRATION = importlib.import_module("app.db.migrations.versions.0017_ficha_territorial_prep")

SCHEMA = "ficha_mig_test"

# A 1° box and two disjoint soil polygons inside it that share ``simbolo``.
# That duplication is the whole reason the migration needs a surrogate key:
# ``(zona_id, simbolo)`` is not a candidate key, so it cannot back the unique
# index that ``REFRESH ... CONCURRENTLY`` requires.
_ZONA_WKT = "MULTIPOLYGON(((-64 -32, -63 -32, -63 -31, -64 -31, -64 -32)))"
_SUELO_A_WKT = "MULTIPOLYGON(((-63.9 -31.9, -63.7 -31.9, -63.7 -31.7, -63.9 -31.7, -63.9 -31.9)))"
_SUELO_B_WKT = "MULTIPOLYGON(((-63.4 -31.4, -63.2 -31.4, -63.2 -31.2, -63.4 -31.2, -63.4 -31.4)))"

_PRE_MIGRATION_WORLD: tuple[str, ...] = (
    # ── the 0015 slice the migration touches ─────────────────────────────────
    """
    CREATE TABLE zonas_operativas (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        nombre VARCHAR(255),
        cuenca VARCHAR(100),
        geometria GEOMETRY(MULTIPOLYGON, 4326) NOT NULL
    )
    """,
    """
    CREATE TABLE suelos_catastro (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        simbolo VARCHAR(50) NOT NULL,
        cap VARCHAR(10),
        ip VARCHAR(50),
        geometria GEOMETRY(MULTIPOLYGON, 4326) NOT NULL
    )
    """,
    """
    CREATE TABLE canales_geo (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        nombre VARCHAR(255),
        tipo VARCHAR(100),
        geometria GEOMETRY(MULTILINESTRING, 4326) NOT NULL
    )
    """,
    # ── the canonical canal table, which must survive ────────────────────────
    """
    CREATE TABLE canal_network (
        id SERIAL PRIMARY KEY,
        geom GEOMETRY(LINESTRING, 4326)
    )
    """,
    f"""
    INSERT INTO zonas_operativas (nombre, cuenca, geometria)
    VALUES ('zona-test', 'cuenca-test', ST_GeomFromText('{_ZONA_WKT}', 4326))
    """,
    f"""
    INSERT INTO suelos_catastro (simbolo, cap, ip, geometria) VALUES
        ('Sr3', 'IVws', '39', ST_GeomFromText('{_SUELO_A_WKT}', 4326)),
        ('Sr3', NULL,   '39', ST_GeomFromText('{_SUELO_B_WKT}', 4326))
    """,
    # ── the pre-migration MVs, verbatim from 0015 (no ``mv_id``) ─────────────
    """
    CREATE MATERIALIZED VIEW mv_suelos_por_zona AS
    SELECT
        z.id AS zona_id, z.nombre AS zona_nombre, z.cuenca, s.cap, s.simbolo, s.ip,
        ST_Area(ST_Transform(
            ST_CollectionExtract(ST_Intersection(s.geometria, z.geometria), 3), 32720
        )) / 10000.0 AS ha_suelo
    FROM zonas_operativas z
    JOIN suelos_catastro s ON ST_Intersects(s.geometria, z.geometria)
    WHERE NOT ST_IsEmpty(
        ST_CollectionExtract(ST_Intersection(s.geometria, z.geometria), 3)
    )
    WITH DATA
    """,
    "CREATE INDEX ix_mv_suelos_cuenca ON mv_suelos_por_zona (cuenca)",
    "CREATE INDEX ix_mv_suelos_zona ON mv_suelos_por_zona (zona_id)",
    """
    CREATE MATERIALIZED VIEW mv_canales_por_zona AS
    SELECT z.id AS zona_id, z.nombre AS zona_nombre, z.cuenca,
        SUM(ST_Length(ST_Transform(ST_Intersection(c.geometria, z.geometria), 32720))) / 1000.0
            AS km_canales
    FROM zonas_operativas z
    JOIN canales_geo c ON ST_Intersects(c.geometria, z.geometria)
    GROUP BY z.id, z.nombre, z.cuenca
    WITH DATA
    """,
)


def _relation_exists(conn, name: str) -> bool:
    """``to_regclass`` is the non-throwing existence probe for any relation."""
    return (
        conn.execute(text("SELECT to_regclass(:rel)"), {"rel": f"{SCHEMA}.{name}"}).scalar()
        is not None
    )


@pytest.fixture(scope="module")
def migrated(test_engine):
    """Build the pre-migration world, run the migration SQL, yield the connection."""
    conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    # Cleanup via try/finally, NOT statements after yield: a failure while
    # building the world (or in the migration under test) must still drop the
    # schema and reset search_path — the connection returns to the POOL, and a
    # leaked search_path makes later tests resolve unqualified names against
    # the shadow schema (false passes, not just failures).
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(f"SET search_path TO {SCHEMA}, public"))

        for statement in _PRE_MIGRATION_WORLD:
            conn.execute(text(statement))

        pre_state = {
            name: _relation_exists(conn, name)
            for name in (
                "canales_geo",
                "mv_canales_por_zona",
                "canal_network",
                "mv_suelos_por_zona",
            )
        }
        assert all(pre_state.values()), f"pre-migration world incomplete: {pre_state}"

        # The guard must pass on the empty pre-migration world (the fixture
        # seeds no canales_geo rows), mirroring what upgrade() runs first.
        MIGRATION.assert_canales_geo_empty(conn)

        for statement in MIGRATION.UPGRADE_STATEMENTS:
            conn.execute(text(statement))

        yield conn
    finally:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text("SET search_path TO public"))
        conn.close()


class TestDeadTwinRemoval:
    """spec soils-etl › "Twins are gone after upgrade"."""

    def test_twins_are_gone(self, migrated):
        assert not _relation_exists(migrated, "mv_canales_por_zona")
        assert not _relation_exists(migrated, "canales_geo")

    def test_canonical_relations_survive(self, migrated):
        assert _relation_exists(migrated, "canal_network")
        assert _relation_exists(migrated, "mv_suelos_por_zona")

    def test_view_is_dropped_before_its_table(self):
        """Reversing these two statements fails on the MV → table dependency."""
        statements = MIGRATION.DROP_TWIN_STATEMENTS
        view_idx = next(i for i, s in enumerate(statements) if "mv_canales_por_zona" in s)
        table_idx = next(i for i, s in enumerate(statements) if "canales_geo" in s)
        assert view_idx < table_idx


class TestConcurrentRefreshKey:
    """spec soils-etl › "Materialized view refresh strategy" delta (JDB-028)."""

    def test_unique_index_on_surrogate_key_exists(self, migrated):
        row = migrated.execute(
            text("""
                SELECT i.indisunique
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_index i ON i.indexrelid = c.oid
                WHERE c.relname = 'ux_mv_suelos_por_zona_id' AND n.nspname = :schema
            """),
            {"schema": SCHEMA},
        ).first()
        assert row is not None, "ux_mv_suelos_por_zona_id was not created"
        assert row[0] is True, "the index exists but is not UNIQUE"

    def test_legacy_indexes_are_recreated(self, migrated):
        names = {
            r[0]
            for r in migrated.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = :s AND tablename = :t"),
                {"s": SCHEMA, "t": "mv_suelos_por_zona"},
            )
        }
        assert {"ix_mv_suelos_cuenca", "ix_mv_suelos_zona"} <= names

    def test_zona_simbolo_is_not_a_candidate_key(self, migrated):
        """The reason the surrogate exists: one symbol, two disjoint polygons, one zone."""
        duplicates = migrated.execute(
            text("""
                SELECT count(*) FROM (
                    SELECT zona_id, simbolo FROM mv_suelos_por_zona
                    GROUP BY zona_id, simbolo HAVING count(*) > 1
                ) dup
            """)
        ).scalar_one()
        assert duplicates >= 1

        distinct_ids = migrated.execute(
            text("SELECT count(DISTINCT mv_id), count(*) FROM mv_suelos_por_zona")
        ).first()
        assert distinct_ids[0] == distinct_ids[1] > 1, "mv_id is not unique per row"

    def test_refresh_concurrently_succeeds(self, migrated):
        """The whole point of the recreate — this raised before the unique index."""
        migrated.execute(
            text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {SCHEMA}.mv_suelos_por_zona")
        )
        assert migrated.execute(text("SELECT count(*) FROM mv_suelos_por_zona")).scalar_one() == 2


class TestDowngrade:
    """spec soils-etl › "Downgrade is explicit"."""

    def test_downgrade_raises_instead_of_passing(self):
        with pytest.raises(RuntimeError, match="downgrade unsupported"):
            MIGRATION.downgrade()


class TestCheckPrereqs:
    """spec soils-etl › "Empty catastro reported" (A1a.4 / JDB-019)."""

    def test_empty_parcelas_catastro_is_a_blocker(self, db):
        from app.domains.geo.etl.load_suelos_catastro import EXIT_PREREQ_FAILED, run_check_prereqs

        db.execute(text("DELETE FROM parcelas_catastro"))
        assert run_check_prereqs(db) == EXIT_PREREQ_FAILED

    def test_report_names_both_tables_and_the_blocker(self, db):
        from app.domains.geo.etl.load_suelos_catastro import check_prereqs, format_report

        db.execute(text("DELETE FROM parcelas_catastro"))
        rendered = format_report(check_prereqs(db))
        assert "parcelas_catastro" in rendered
        assert "suelos_catastro" in rendered
        assert "BLOQUEANTE" in rendered

    def test_missing_table_reports_none_not_an_exception(self, db):
        from app.domains.geo.etl.load_suelos_catastro import table_row_count

        # ``suelos_catastro`` is migration-only: it has no ORM model, so the
        # metadata-built test schema does not contain it.
        assert table_row_count(db, "suelos_catastro") is None

    def test_unknown_table_is_refused(self, db):
        from app.domains.geo.etl.load_suelos_catastro import table_row_count

        with pytest.raises(ValueError, match="unknown table"):
            table_row_count(db, "users; DROP TABLE users")

    def test_populated_parcelas_catastro_passes(self, db):
        from app.domains.geo.etl.load_suelos_catastro import EXIT_OK, run_check_prereqs

        db.execute(
            text("""
                INSERT INTO parcelas_catastro (nomenclatura, geometria)
                VALUES ('test-1', ST_GeomFromText(
                    'POLYGON((-64 -32, -63 -32, -63 -31, -64 -31, -64 -32))', 4326))
            """)
        )
        assert run_check_prereqs(db) == EXIT_OK

    def test_non_prereq_mode_is_rejected(self):
        from app.domains.geo.etl.load_suelos_catastro import EXIT_USAGE, main

        assert main([]) == EXIT_USAGE


class TestNonEmptyGuard:
    """R3-001: the DROP must refuse when canales_geo holds rows."""

    def test_guard_raises_on_populated_canales_geo(self, test_engine):
        schema = "ficha_mig_guard"
        conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}, public"))
            conn.execute(
                text(
                    "CREATE TABLE canales_geo ("
                    "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
                    "nombre varchar(255), "
                    "geometria geometry(MultiLineString, 4326) NOT NULL)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO canales_geo (nombre, geometria) VALUES ("
                    "'Canal Legua Viejo', "
                    "ST_GeomFromText('MULTILINESTRING((0 0, 1 1))', 4326))"
                )
            )
            with pytest.raises(RuntimeError, match="still holds 1 rows"):
                MIGRATION.assert_canales_geo_empty(conn)
        finally:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("SET search_path TO public"))
            conn.close()

    def test_guard_passes_when_table_absent(self, test_engine):
        # public schema has no canales_geo (Base.metadata never had it)
        conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text("SET search_path TO public"))
            MIGRATION.assert_canales_geo_empty(conn)  # must not raise
        finally:
            conn.close()


class TestProjectionContract:
    """R3-004: the recreated view must be 0015's projection plus mv_id."""

    # Exactly 0015:96-106's projection (zona_id, zona_nombre, cuenca, cap,
    # simbolo, ip, ha_suelo — NO geometria: 0015 never projected it) plus the
    # surrogate mv_id. If the recreate ever drops or renames a column, this
    # is the assertion that catches it.
    EXPECTED_COLUMNS = {
        "mv_id",
        "zona_id",
        "zona_nombre",
        "cuenca",
        "cap",
        "simbolo",
        "ip",
        "ha_suelo",
    }

    def test_recreated_view_matches_0015_projection_plus_mv_id(self, migrated):
        rows = migrated.execute(
            text(
                "SELECT attname FROM pg_attribute "
                "WHERE attrelid = (SELECT oid FROM pg_class WHERE relname = 'mv_suelos_por_zona' "
                "  AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = :s)) "
                "AND attnum > 0 AND NOT attisdropped"
            ),
            {"s": SCHEMA},
        ).fetchall()
        assert {r[0] for r in rows} == self.EXPECTED_COLUMNS
