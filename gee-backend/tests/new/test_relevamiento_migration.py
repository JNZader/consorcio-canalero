"""Real-PG tests for migration ``0023_add_relevamiento_tramo``.

Same shape as ``test_cruce_camino_migration`` (the ``0022`` precedent, itself the
``0021`` / ``0020`` one): the DDL lives as module constants on the migration, and
each test builds a throwaway schema and runs the real statements against it.

What matters beyond "the tables exist":

* **``version BIGSERIAL NOT NULL UNIQUE`` is the ordering key.** ``relevado_en``
  defaults to ``now()``, which in PostgreSQL is **transaction-start** time, so two
  surveys of the same segment written from overlapping transactions can carry the
  same stamp or the opposite order to their commits — and ``id`` is a random
  UUIDv4, so a tie-break on it picks a winner by lexicographic accident. The
  sequence is assigned at INSERT and is unique by construction, so "current" is a
  genuine total order (design D4).
* **The cuneta rule is a table-level CHECK, not a service rule.** ``estado_cuneta``
  is NULL **iff** ``tiene_cuneta = 'no'``. A rule enforced only in the service is a
  rule psql and any future ETL bypass, so it is asserted here in both directions.
* **The candidate table is keyed ``(tramo_ref, geo_job_id)``, never on
  ``dem_layer_id``.** ``upsert_layer`` mutates a layer row in place keeping the
  same UUID (``geo_repository_jobs_layers.py:207-243``) and
  ``delete_layers_by_area_id`` wipes those rows outright (``:245-250``), so
  ``dem_layer_id`` is not a run identifier at all. It stays as informational
  provenance **with no FK**, allowed to dangle (design D4).
* **No dimension column exists on either table** — asserted by column-name
  absence, which is the mechanical form of "dimensioning is outside this
  capability" (RSS-R6).
* **No view over survey data is published.** ``relevamiento_tramo_vigente`` is an
  internal current-state query; nothing here is added to Martin, and survey rows
  carry ``relevado_por``, which never reaches a public surface.
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

MIGRATION = importlib.import_module("app.db.migrations.versions.0023_add_relevamiento_tramo")
RED_VIAL_MIGRATION = importlib.import_module("app.db.migrations.versions.0021_add_red_vial")

SCHEMA = "relevamiento_mig_test"

USER_ID = "22222222-2222-2222-2222-222222222222"
JOB_ID = "11111111-1111-1111-1111-111111111111"
TRAMO = "28188"

#: The three domain CHECKs plus the combination rule, by name. Named rather than
#: counted: a rename is a silent behaviour change for anyone reading a
#: constraint-violation error.
EXPECTED_CHECKS: tuple[str, ...] = (
    "ck_relevamiento_nivel_relativo",
    "ck_relevamiento_tiene_cuneta",
    "ck_relevamiento_estado_cuneta_valores",
    "ck_relevamiento_cuneta_combinacion",
)

#: Anything that would turn an observation into a measurement. RSS-R6: this
#: capability records what the operator SEES, never what it MEASURES.
FORBIDDEN_COLUMN_FRAGMENTS: tuple[str, ...] = ("ancho", "profundidad", "capacidad", "seccion")


def _run(conn, statements) -> None:
    for statement in statements:
        conn.execute(text(statement))


def _seed_dependencies(conn) -> None:
    """The three FK targets: ``red_vial``, ``users`` and ``geo_jobs``.

    ``users`` and ``geo_jobs`` are minimal stand-ins rather than their own (long)
    migration chains: what this migration needs from each is a UUID primary key
    to point at, and this test is about ``relevamiento_tramo``'s own DDL.
    """
    _run(conn, RED_VIAL_MIGRATION.UPGRADE_STATEMENTS)
    conn.execute(text("CREATE TABLE users (id UUID PRIMARY KEY)"))
    conn.execute(text("CREATE TABLE geo_jobs (id UUID PRIMARY KEY)"))
    conn.execute(
        text(
            "INSERT INTO red_vial (id, source_id, geom, geom_hash) VALUES "
            "(:t, :t, ST_GeomFromText('LINESTRING(-62 -32.5, -62.01 -32.51)', 4326), 'h')"
        ),
        {"t": TRAMO},
    )
    conn.execute(text("INSERT INTO users (id) VALUES (:u)"), {"u": USER_ID})
    conn.execute(text("INSERT INTO geo_jobs (id) VALUES (:j)"), {"j": JOB_ID})


@pytest.fixture(scope="module")
def migrated(test_engine):
    conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(f"SET search_path TO {SCHEMA}, public"))
        _seed_dependencies(conn)
        _run(conn, MIGRATION.UPGRADE_STATEMENTS)
        yield conn
    finally:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text("SET search_path TO public"))
        conn.close()


def _columns(conn, table: str) -> dict[str, tuple[str, str, object]]:
    rows = conn.execute(
        text(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = :t"
        ),
        {"s": SCHEMA, "t": table},
    ).all()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def _insert_survey(conn, **overrides) -> None:
    payload = {
        "tramo_ref": TRAMO,
        "nivel_relativo": "menor",
        "tiene_cuneta": "si",
        "estado_cuneta": "limpia",
        "observaciones": None,
        "relevado_por": USER_ID,
    }
    payload.update(overrides)
    conn.execute(
        text(
            "INSERT INTO relevamiento_tramo "
            "(tramo_ref, nivel_relativo, tiene_cuneta, estado_cuneta, observaciones, relevado_por) "
            "VALUES (:tramo_ref, :nivel_relativo, :tiene_cuneta, :estado_cuneta, "
            ":observaciones, :relevado_por)"
        ),
        payload,
    )


class TestRelevamientoTramoTable:
    def test_table_exists(self, migrated):
        exists = migrated.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :s AND table_name = 'relevamiento_tramo'"
            ),
            {"s": SCHEMA},
        ).scalar()
        assert exists == 1

    def test_tramo_ref_is_text_not_null(self, migrated):
        data_type, nullable, _ = _columns(migrated, "relevamiento_tramo")["tramo_ref"]
        assert data_type == "text"
        assert nullable == "NO"

    def test_relevado_por_is_uuid_not_null(self, migrated):
        """RSS-R1: no record without an identified author."""
        data_type, nullable, _ = _columns(migrated, "relevamiento_tramo")["relevado_por"]
        assert data_type == "uuid"
        assert nullable == "NO"

    def test_relevado_en_is_timestamptz_with_a_now_default(self, migrated):
        data_type, nullable, default = _columns(migrated, "relevamiento_tramo")["relevado_en"]
        assert data_type == "timestamp with time zone"
        assert nullable == "NO"
        assert default is not None and "now()" in default

    def test_version_is_a_bigserial(self, migrated):
        """``BIGSERIAL`` = ``bigint`` + a sequence default. Both are asserted."""
        data_type, nullable, default = _columns(migrated, "relevamiento_tramo")["version"]
        assert data_type == "bigint"
        assert nullable == "NO"
        assert default is not None and "nextval" in default

    def test_nivel_desde_candidata_defaults_to_false(self, migrated):
        """Pre-fill provenance is a stored fact — and its default is the honest one."""
        data_type, nullable, default = _columns(migrated, "relevamiento_tramo")[
            "nivel_desde_candidata"
        ]
        assert data_type == "boolean"
        assert nullable == "NO"
        assert default is not None and "false" in default.lower()

    @pytest.mark.parametrize("check", EXPECTED_CHECKS)
    def test_the_check_exists_by_name(self, migrated, check: str):
        found = migrated.execute(
            text(
                "SELECT 1 FROM pg_constraint c "
                "JOIN pg_namespace n ON n.oid = c.connamespace "
                "WHERE n.nspname = :s AND c.conname = :c AND c.contype = 'c'"
            ),
            {"s": SCHEMA, "c": check},
        ).scalar()
        assert found == 1, f"missing CHECK {check}"

    def test_the_tramo_version_index_exists_and_is_descending(self, migrated):
        definition = migrated.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = :s AND indexname = 'ix_relevamiento_tramo_version'"
            ),
            {"s": SCHEMA},
        ).scalar()
        assert definition is not None, "missing ix_relevamiento_tramo_version"
        assert "version DESC" in definition

    def test_version_is_unique(self, migrated):
        found = migrated.execute(
            text(
                "SELECT 1 FROM pg_constraint c "
                "JOIN pg_namespace n ON n.oid = c.connamespace "
                "WHERE n.nspname = :s AND c.conname = 'uq_relevamiento_version' "
                "AND c.contype = 'u'"
            ),
            {"s": SCHEMA},
        ).scalar()
        assert found == 1

    @pytest.mark.parametrize("fragment", FORBIDDEN_COLUMN_FRAGMENTS)
    def test_no_dimension_column_exists(self, migrated, fragment: str):
        names = " ".join(_columns(migrated, "relevamiento_tramo"))
        assert fragment not in names, (
            f"a dimension column naming {fragment!r} would contradict RSS-R6"
        )


class TestTheCunetaCombinationRule:
    """``estado_cuneta`` is NULL **iff** ``tiene_cuneta = 'no'`` — both directions."""

    def test_no_cuneta_with_a_state_is_refused(self, migrated):
        with pytest.raises((IntegrityError, DBAPIError)):
            _insert_survey(migrated, tiene_cuneta="no", estado_cuneta="limpia")

    def test_a_cuneta_without_a_state_is_refused(self, migrated):
        with pytest.raises((IntegrityError, DBAPIError)):
            _insert_survey(migrated, tiene_cuneta="si", estado_cuneta=None)

    def test_a_partial_cuneta_without_a_state_is_refused(self, migrated):
        with pytest.raises((IntegrityError, DBAPIError)):
            _insert_survey(migrated, tiene_cuneta="parcial", estado_cuneta=None)

    def test_no_cuneta_with_no_state_is_accepted(self, migrated):
        _insert_survey(migrated, tiene_cuneta="no", estado_cuneta=None)
        migrated.execute(text("DELETE FROM relevamiento_tramo"))

    @pytest.mark.parametrize("value", ["mediana", "", "SI"])
    def test_an_out_of_domain_tiene_cuneta_is_refused(self, migrated, value: str):
        with pytest.raises((IntegrityError, DBAPIError)):
            _insert_survey(migrated, tiene_cuneta=value, estado_cuneta="limpia")

    @pytest.mark.parametrize("value", ["alto", "bajo", ""])
    def test_an_out_of_domain_nivel_relativo_is_refused(self, migrated, value: str):
        with pytest.raises((IntegrityError, DBAPIError)):
            _insert_survey(migrated, nivel_relativo=value)

    def test_an_out_of_domain_estado_cuneta_is_refused(self, migrated):
        with pytest.raises((IntegrityError, DBAPIError)):
            _insert_survey(migrated, estado_cuneta="sucia")


class TestForeignKeys:
    def test_a_survey_of_an_unknown_segment_is_refused(self, migrated):
        with pytest.raises((IntegrityError, DBAPIError)):
            _insert_survey(migrated, tramo_ref="no-existe")

    def test_a_road_with_a_survey_cannot_be_deleted(self, migrated):
        """``ON DELETE RESTRICT``: roads are retired, never deleted (design D1)."""
        _insert_survey(migrated)
        try:
            with pytest.raises((IntegrityError, DBAPIError)):
                migrated.execute(text("DELETE FROM red_vial WHERE id = :t"), {"t": TRAMO})
        finally:
            migrated.execute(text("DELETE FROM relevamiento_tramo"))

    def test_an_unknown_author_is_refused(self, migrated):
        with pytest.raises((IntegrityError, DBAPIError)):
            _insert_survey(migrated, relevado_por="33333333-3333-3333-3333-333333333333")


class TestVigenteView:
    def test_the_view_exists(self, migrated):
        exists = migrated.execute(
            text(
                "SELECT 1 FROM information_schema.views "
                "WHERE table_schema = :s AND table_name = 'relevamiento_tramo_vigente'"
            ),
            {"s": SCHEMA},
        ).scalar()
        assert exists == 1

    def test_the_view_returns_the_highest_version(self, migrated):
        _insert_survey(migrated, nivel_relativo="menor")
        _insert_survey(migrated, nivel_relativo="mayor")
        try:
            row = migrated.execute(
                text(
                    "SELECT nivel_relativo, version FROM relevamiento_tramo_vigente "
                    "WHERE tramo_ref = :t"
                ),
                {"t": TRAMO},
            ).one()
            assert row[0] == "mayor"
            assert (
                row[1]
                == migrated.execute(text("SELECT max(version) FROM relevamiento_tramo")).scalar()
            )
        finally:
            migrated.execute(text("DELETE FROM relevamiento_tramo"))

    def test_the_view_orders_by_version_and_not_by_time(self, migrated):
        """The definition itself is the assertion: ``relevado_en`` must not order it."""
        definition = migrated.execute(
            text("SELECT pg_get_viewdef(cast(:v AS regclass), true)"),
            {"v": f"{SCHEMA}.relevamiento_tramo_vigente"},
        ).scalar()
        assert "DISTINCT ON" in definition.upper()
        ordering = definition.upper().split("ORDER BY", 1)[1]
        assert "VERSION DESC" in ordering
        assert "RELEVADO_EN" not in ordering, (
            "relevado_en is transaction-START time and must never decide which record wins"
        )


class TestCandidataTable:
    def test_table_exists(self, migrated):
        exists = migrated.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :s AND table_name = 'tramo_clasificacion_candidata'"
            ),
            {"s": SCHEMA},
        ).scalar()
        assert exists == 1

    def test_the_primary_key_is_tramo_ref_plus_geo_job_id(self, migrated):
        columns = migrated.execute(
            text(
                "SELECT a.attname FROM pg_constraint c "
                "JOIN pg_namespace n ON n.oid = c.connamespace "
                "JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true "
                "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum "
                "WHERE n.nspname = :s AND c.contype = 'p' "
                "AND c.conrelid = cast(:t AS regclass) ORDER BY k.ord"
            ),
            {"s": SCHEMA, "t": f"{SCHEMA}.tramo_clasificacion_candidata"},
        ).scalars().all()
        assert columns == ["tramo_ref", "geo_job_id"]

    def test_geo_job_id_carries_a_real_fk(self, migrated):
        found = migrated.execute(
            text(
                "SELECT 1 FROM pg_constraint c "
                "WHERE c.conrelid = cast(:t AS regclass) AND c.contype = 'f' "
                "AND c.confrelid = 'geo_jobs'::regclass"
            ),
            {"t": f"{SCHEMA}.tramo_clasificacion_candidata"},
        ).scalar()
        assert found == 1

    def test_dem_layer_id_is_a_uuid_with_no_foreign_key(self, migrated):
        """Informational provenance, allowed to dangle (design D4).

        A FK here would delete or block on a layer row the DEM pipeline is free to
        wipe (``delete_layers_by_area_id``), destroying the only record of what the
        DEM once suggested.
        """
        data_type, nullable, _ = _columns(migrated, "tramo_clasificacion_candidata")["dem_layer_id"]
        assert data_type == "uuid"
        assert nullable == "YES"

        fk_columns = migrated.execute(
            text(
                "SELECT a.attname FROM pg_constraint c "
                "JOIN unnest(c.conkey) AS k(attnum) ON true "
                "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum "
                "WHERE c.conrelid = cast(:t AS regclass) AND c.contype = 'f'"
            ),
            {"t": f"{SCHEMA}.tramo_clasificacion_candidata"},
        ).scalars().all()
        assert "dem_layer_id" not in fk_columns

    def test_two_runs_over_the_same_segment_coexist(self, migrated):
        """The whole reason the key is ``geo_job_id`` and not ``dem_layer_id``."""
        other_job = "44444444-4444-4444-4444-444444444444"
        migrated.execute(text("INSERT INTO geo_jobs (id) VALUES (:j)"), {"j": other_job})
        for job in (JOB_ID, other_job):
            migrated.execute(
                text(
                    "INSERT INTO tramo_clasificacion_candidata "
                    "(tramo_ref, geo_job_id, clasificacion_candidata, confianza_m, calculada_en) "
                    "VALUES (:t, :j, 'terraplen', 1.4, now())"
                ),
                {"t": TRAMO, "j": job},
            )
        try:
            count = migrated.execute(
                text("SELECT count(*) FROM tramo_clasificacion_candidata WHERE tramo_ref = :t"),
                {"t": TRAMO},
            ).scalar()
            assert count == 2
        finally:
            migrated.execute(text("DELETE FROM tramo_clasificacion_candidata"))
            migrated.execute(text("DELETE FROM geo_jobs WHERE id = :j"), {"j": other_job})

    def test_the_classification_domain_is_checked(self, migrated):
        with pytest.raises((IntegrityError, DBAPIError)):
            migrated.execute(
                text(
                    "INSERT INTO tramo_clasificacion_candidata "
                    "(tramo_ref, geo_job_id, clasificacion_candidata, confianza_m, calculada_en) "
                    "VALUES (:t, :j, 'bajo', 1.4, now())"
                ),
                {"t": TRAMO, "j": JOB_ID},
            )

    @pytest.mark.parametrize("fragment", FORBIDDEN_COLUMN_FRAGMENTS)
    def test_no_dimension_column_exists(self, migrated, fragment: str):
        names = " ".join(_columns(migrated, "tramo_clasificacion_candidata"))
        assert fragment not in names


class TestDowngrade:
    def test_the_downgrade_drops_the_view_before_the_tables(self, migrated):
        """A ``DROP TABLE`` under a dependent view fails; ordering is the contract."""
        statements = MIGRATION.DOWNGRADE_STATEMENTS
        view_index = next(i for i, s in enumerate(statements) if "VIEW" in s.upper())
        table_index = next(
            i for i, s in enumerate(statements) if "DROP TABLE" in s.upper()
        )
        assert view_index < table_index

    def test_the_downgrade_never_cascades(self):
        """A CASCADE would silently take field-collected survey data with it."""
        for statement in MIGRATION.DOWNGRADE_STATEMENTS:
            assert "CASCADE" not in statement.upper()

    def test_upgrade_and_downgrade_round_trip(self, test_engine):
        schema = f"{SCHEMA}_roundtrip"
        conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}, public"))
            _seed_dependencies(conn)
            _run(conn, MIGRATION.UPGRADE_STATEMENTS)
            _run(conn, MIGRATION.DOWNGRADE_STATEMENTS)
            left = conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = :s AND table_name IN "
                    "('relevamiento_tramo', 'tramo_clasificacion_candidata')"
                ),
                {"s": schema},
            ).scalar()
            assert left == 0
        finally:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("SET search_path TO public"))
            conn.close()


class TestNothingIsPublished:
    def test_the_migration_creates_no_materialized_view(self):
        for statement in MIGRATION.UPGRADE_STATEMENTS:
            assert "MATERIALIZED VIEW" not in statement.upper()

    def test_the_only_view_created_is_the_internal_current_state_one(self):
        created_views = [
            s for s in MIGRATION.UPGRADE_STATEMENTS if "CREATE" in s.upper() and "VIEW" in s.upper()
        ]
        assert len(created_views) == 1
        assert "relevamiento_tramo_vigente" in created_views[0]

    def test_no_grant_is_issued_to_the_martin_reader(self):
        """Survey rows carry ``relevado_por``; Martin's hostname is public."""
        for statement in MIGRATION.UPGRADE_STATEMENTS:
            assert "GRANT" not in statement.upper()
