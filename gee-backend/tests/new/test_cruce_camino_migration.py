"""Real-PG tests for migration ``0022_add_cruce_camino``.

Same shape as ``test_red_vial_migration`` (the ``0021`` precedent, itself the
``0020`` one): the DDL lives as module constants on the migration, each test
class builds a throwaway schema and runs the real statements against it.

What matters beyond "the table exists":

* **``area_id`` is ``VARCHAR(100)``, not ``UUID``.** It mirrors
  ``GeoLayer.area_id``'s ``String(100)`` (``geo/models.py:155-159``); ``geo_jobs``
  has no area column at all. A ``UUID`` here would make the staleness comparison
  a cast that can raise on a perfectly legal non-UUID area identifier.
* **``canal_ref`` is ``TEXT`` with a real FK** to ``canal_consorcio(id)``, whose
  PK is ``TEXT`` (``0020_add_canal_consorcio.py:65-66``). A ``UUID`` column could
  never have referenced it, so it would have accepted any value at all.
* **All FOUR CHECKs, by name.** The two per-``tipo`` rules plus the two one-sided
  closures: a ``flujo_natural`` row can carry no ``canal_ref`` and cannot be
  stored without its ``confianza`` band.
* **No view and no matview was created or redefined.** D1's whole point is that
  nothing is published; ``vt_puntos_conflicto`` and the dashboard matview are
  untouched, and this test is the standing proof.
"""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

MIGRATION = importlib.import_module("app.db.migrations.versions.0022_add_cruce_camino")
RED_VIAL_MIGRATION = importlib.import_module("app.db.migrations.versions.0021_add_red_vial")
CANAL_MIGRATION = importlib.import_module("app.db.migrations.versions.0020_add_canal_consorcio")

SCHEMA = "cruce_camino_mig_test"

#: The four per-``tipo`` CHECKs, by name. Named rather than counted: a rename is
#: a silent behaviour change for anyone reading a constraint-violation error.
EXPECTED_CHECKS: tuple[str, ...] = (
    "ck_cruce_flujo_completo",
    "ck_cruce_canal_sin_rank",
    "ck_cruce_flujo_sin_canal",
    "ck_cruce_flujo_confianza",
)

EXPECTED_INDEXES: tuple[str, ...] = (
    "ix_cruce_camino_geom",
    "ix_cruce_camino_area",
    "ix_cruce_camino_tramo",
)

#: The enum value the crossing job carries. ``ADD VALUE IF NOT EXISTS`` puts it
#: on the shared ``tipo_geo_job`` type, which is why the down-migration cannot
#: take it back off again.
ENUM_VALUE = "road_flow_crossings"


def _run(conn, statements) -> None:
    for statement in statements:
        conn.execute(text(statement))


def _seed_dependencies(conn) -> None:
    """The three FK targets: ``red_vial``, ``canal_consorcio`` and ``geo_jobs``.

    ``geo_jobs`` is created as a minimal stand-in rather than by running its own
    (long) migration chain: this test is about ``cruce_camino``'s DDL, and what
    it needs from ``geo_jobs`` is a UUID primary key to point at.
    """
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
    conn.execute(text("INSERT INTO geo_jobs (id) VALUES ('11111111-1111-1111-1111-111111111111')"))


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


def _columns(conn) -> dict[str, tuple[str, str, object]]:
    rows = conn.execute(
        text(
            "SELECT column_name, data_type, is_nullable, character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = 'cruce_camino'"
        ),
        {"s": SCHEMA},
    ).all()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


class TestCruceCaminoTable:
    def test_table_exists(self, migrated):
        exists = migrated.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :s AND table_name = 'cruce_camino'"
            ),
            {"s": SCHEMA},
        ).scalar()
        assert exists == 1

    def test_area_id_is_varchar_100_not_uuid(self, migrated):
        """``geo_layer.area_id`` is ``String(100)`` — this column mirrors it exactly."""
        data_type, nullable, max_length = _columns(migrated)["area_id"]
        assert data_type == "character varying", (
            f"area_id must be VARCHAR to match GeoLayer.area_id — got {data_type}"
        )
        assert max_length == 100
        assert nullable == "NO"

    def test_tramo_ref_is_text_and_not_null(self, migrated):
        data_type, nullable, _ = _columns(migrated)["tramo_ref"]
        assert data_type == "text"
        assert nullable == "NO"

    def test_canal_ref_is_text(self, migrated):
        """``canal_consorcio.id`` is ``TEXT PRIMARY KEY`` — a UUID could not reference it."""
        data_type, nullable, _ = _columns(migrated)["canal_ref"]
        assert data_type == "text"
        assert nullable == "YES"

    @pytest.mark.parametrize(
        "column",
        [
            "direccion_flujo_deg",
            "rumbo_camino_deg",
            "lado_cruce",
            "area_aporte_ha",
            "orden_ranking",
            "confianza",
            "nota",
        ],
    )
    def test_derived_columns_are_nullable(self, migrated, column: str):
        """Every derived value is nullable at the column level.

        The per-``tipo`` requirement is expressed by the CHECKs, not by
        ``NOT NULL``: a ``canal`` row legitimately carries none of them.
        """
        _, nullable, _ = _columns(migrated)[column]
        assert nullable == "YES", f"{column} must be nullable — the CHECKs carry the per-tipo rule"

    @pytest.mark.parametrize("column", ["geo_job_id", "calculada_en", "geometria"])
    def test_provenance_columns_are_not_null(self, migrated, column: str):
        _, nullable, _ = _columns(migrated)[column]
        assert nullable == "NO"

    def test_geometria_is_point_4326(self, migrated):
        srid, geom_type = migrated.execute(
            text(
                "SELECT srid, type FROM geometry_columns "
                "WHERE f_table_schema = :s AND f_table_name = 'cruce_camino' "
                "AND f_geometry_column = 'geometria'"
            ),
            {"s": SCHEMA},
        ).one()
        assert srid == 4326
        assert geom_type == "POINT"


class TestChecks:
    @pytest.mark.parametrize("name", EXPECTED_CHECKS)
    def test_check_exists_by_name(self, migrated, name: str):
        found = migrated.execute(
            text(
                "SELECT 1 FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = :s AND t.relname = 'cruce_camino' "
                "AND c.contype = 'c' AND c.conname = :name"
            ),
            {"s": SCHEMA, "name": name},
        ).scalar()
        assert found == 1, f"CHECK {name} is missing"

    def test_tipo_is_constrained_to_the_two_kinds(self, migrated):
        with pytest.raises(Exception) as exc:
            migrated.execute(
                text(
                    "INSERT INTO cruce_camino "
                    "(id, area_id, tramo_ref, tipo, geometria, geo_job_id) VALUES "
                    "(gen_random_uuid(), 'a', '28188', 'camino_drenaje', "
                    "ST_SetSRID(ST_MakePoint(-62, -32.5), 4326), "
                    "'11111111-1111-1111-1111-111111111111')"
                )
            )
        assert "ck_cruce_tipo" in str(exc.value) or "check" in str(exc.value).lower()


class TestIndexes:
    @pytest.mark.parametrize("name", EXPECTED_INDEXES)
    def test_index_exists(self, migrated, name: str):
        found = migrated.execute(
            text("SELECT 1 FROM pg_indexes WHERE schemaname = :s AND indexname = :name"),
            {"s": SCHEMA, "name": name},
        ).scalar()
        assert found == 1, f"index {name} is missing"

    def test_geom_index_is_gist(self, migrated):
        method = migrated.execute(
            text(
                "SELECT am.amname FROM pg_index i "
                "JOIN pg_class idx ON idx.oid = i.indexrelid "
                "JOIN pg_am am ON am.oid = idx.relam "
                "JOIN pg_namespace n ON n.oid = idx.relnamespace "
                "WHERE n.nspname = :s AND idx.relname = 'ix_cruce_camino_geom'"
            ),
            {"s": SCHEMA},
        ).scalar()
        assert method == "gist"

    def test_area_index_is_keyed_on_area_and_tipo(self, migrated):
        definition = migrated.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = :s AND indexname = 'ix_cruce_camino_area'"
            ),
            {"s": SCHEMA},
        ).scalar()
        assert "area_id" in definition and "tipo" in definition


class TestForeignKeys:
    def _fk(self, conn, column: str) -> tuple[str, str]:
        return conn.execute(
            text(
                "SELECT ccu.table_name, rc.delete_rule "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON kcu.constraint_name = tc.constraint_name "
                " AND kcu.constraint_schema = tc.constraint_schema "
                "JOIN information_schema.constraint_column_usage ccu "
                "  ON ccu.constraint_name = tc.constraint_name "
                " AND ccu.constraint_schema = tc.constraint_schema "
                "JOIN information_schema.referential_constraints rc "
                "  ON rc.constraint_name = tc.constraint_name "
                " AND rc.constraint_schema = tc.constraint_schema "
                "WHERE tc.table_schema = :s AND tc.table_name = 'cruce_camino' "
                "AND tc.constraint_type = 'FOREIGN KEY' AND kcu.column_name = :col"
            ),
            {"s": SCHEMA, "col": column},
        ).one()

    def test_tramo_ref_restricts(self, migrated):
        target, rule = self._fk(migrated, "tramo_ref")
        assert target == "red_vial"
        assert rule == "RESTRICT", "the database must refuse to orphan a crossing"

    def test_canal_ref_restricts(self, migrated):
        target, rule = self._fk(migrated, "canal_ref")
        assert target == "canal_consorcio"
        assert rule == "RESTRICT"

    def test_geo_job_id_references_geo_jobs(self, migrated):
        target, _ = self._fk(migrated, "geo_job_id")
        assert target == "geo_jobs"


class TestNothingIsPublished:
    """D1: no view, no matview. The public surface does not move."""

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
        """Read the DDL itself: no ``CREATE``/``DROP``/``REFRESH`` of a view."""
        all_ddl = " ".join(MIGRATION.UPGRADE_STATEMENTS + MIGRATION.DOWNGRADE_STATEMENTS).upper()
        for forbidden in (
            "CREATE VIEW",
            "CREATE OR REPLACE VIEW",
            "MATERIALIZED VIEW",
            "DROP VIEW",
        ):
            assert forbidden not in all_ddl, f"migration must not contain {forbidden!r}"


class TestEnumValue:
    def test_enum_value_is_added(self, test_engine):
        """``road_flow_crossings`` lands on the shared ``tipo_geo_job`` type.

        Run against the real (public) type rather than the throwaway schema:
        the enum is global, which is exactly why the downgrade cannot undo it.
        """
        with test_engine.connect() as conn:
            conn.execute(text(MIGRATION.ADD_ENUM_VALUE))
            conn.commit()
            labels = (
                conn.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = 'tipo_geo_job'"
                    )
                )
                .scalars()
                .all()
            )
        assert ENUM_VALUE in labels

    def test_add_enum_value_is_idempotent(self, test_engine):
        """``ADD VALUE IF NOT EXISTS`` — a re-upgrade after a downgrade is a no-op."""
        with test_engine.connect() as conn:
            conn.execute(text(MIGRATION.ADD_ENUM_VALUE))
            conn.execute(text(MIGRATION.ADD_ENUM_VALUE))
            conn.commit()


class TestDowngrade:
    def test_downgrade_drops_the_table_and_keeps_the_enum_residue(self, test_engine):
        """The residue is asserted PRESENT, not absent.

        PostgreSQL cannot remove an enum value (precedent:
        ``q1l8m7n8o927``'s ``downgrade()`` is a documented ``pass``). Asserting
        it is gone would be asserting a fiction; asserting it stays is what stops
        someone reporting it as corruption later.
        """
        schema = f"{SCHEMA}_down"
        conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}, public"))
            _seed_dependencies(conn)
            _run(conn, MIGRATION.UPGRADE_STATEMENTS)
            _run(conn, MIGRATION.DOWNGRADE_STATEMENTS)

            still_there = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = :s AND table_name = 'cruce_camino'"
                ),
                {"s": schema},
            ).scalar()
            assert still_there is None, "downgrade must drop cruce_camino"

            labels = (
                conn.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = 'tipo_geo_job'"
                    )
                )
                .scalars()
                .all()
            )
            assert ENUM_VALUE in labels, (
                "the enum residue is PERMANENT — PostgreSQL cannot remove an enum value"
            )
        finally:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("SET search_path TO public"))
            conn.close()

    def test_downgrade_statements_do_not_touch_the_enum(self):
        joined = " ".join(MIGRATION.DOWNGRADE_STATEMENTS).upper()
        assert "DROP TYPE" not in joined
        assert "ALTER TYPE" not in joined


# ---------------------------------------------------------------------------
# The public surface does not move — asserted against REAL objects
# ---------------------------------------------------------------------------

MATVIEW_MIGRATION = importlib.import_module(
    "app.db.migrations.versions.k5f2g1h2i361_add_geo_materialized_views"
)

#: ``vt_puntos_conflicto``'s DDL is inline in ``v6q3r4s5t482``'s ``upgrade()``
#: rather than a module constant, so it is restated here verbatim. The
#: byte-comparison below is of ``pg_get_viewdef`` before vs after, so a drift
#: between this copy and the migration would change both sides equally and the
#: test would still do its job: it proves *this* migration did not redefine the
#: view, which is exactly the claim.
CREATE_VT_PUNTOS_CONFLICTO = """
    CREATE OR REPLACE VIEW vt_puntos_conflicto AS
    SELECT
        id,
        tipo,
        severidad,
        descripcion,
        acumulacion_valor,
        pendiente_valor,
        geometria
    FROM puntos_conflicto;
"""

#: The count sources the dashboard matview reads. Minimal stand-ins — the
#: matview's *definition* is what is under test, not its data.
MATVIEW_DEPENDENCIES: tuple[str, ...] = (
    """
    CREATE TABLE puntos_conflicto (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tipo TEXT NOT NULL,
        severidad TEXT NOT NULL,
        descripcion TEXT NOT NULL DEFAULT '',
        acumulacion_valor DOUBLE PRECISION NOT NULL DEFAULT 0,
        pendiente_valor DOUBLE PRECISION NOT NULL DEFAULT 0,
        geometria geometry(Point, 4326) NOT NULL
    )
    """,
    "CREATE TABLE geo_layers (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tipo TEXT)",
    "CREATE TABLE geo_analisis_gee (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
    "tipo TEXT, estado TEXT)",
    "CREATE TABLE zonas_operativas (id UUID PRIMARY KEY DEFAULT gen_random_uuid())",
    "CREATE TABLE alertas_geo (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
    "activa BOOLEAN NOT NULL DEFAULT true)",
)


class TestUntouchedPublicObjects:
    """``vt_puntos_conflicto`` and the dashboard matview survive up AND down.

    Not "the migration text mentions neither" (asserted separately above) but the
    stronger property: with both objects really present, running this migration's
    upgrade and then its downgrade leaves their definitions **byte-identical**.
    That is the standing proof D1's whole pivot rests on — nothing was written
    where the four unfiltered aggregate readers read, so none of them had to gain
    a synchronized exclusion predicate.
    """

    @staticmethod
    def _definitions(conn, schema: str) -> tuple[str, str]:
        view_def = conn.execute(
            text(
                "SELECT pg_get_viewdef(c.oid, true) FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :s AND c.relname = 'vt_puntos_conflicto'"
            ),
            {"s": schema},
        ).scalar_one()
        matview_def = conn.execute(
            text("SELECT definition FROM pg_matviews WHERE schemaname = :s AND matviewname = :m"),
            {"s": schema, "m": "mv_dashboard_geo_stats"},
        ).scalar_one()
        return view_def, matview_def

    def test_view_and_matview_are_byte_identical_across_up_and_down(self, test_engine):
        schema = f"{SCHEMA}_untouched"
        conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}, public"))

            _run(conn, RED_VIAL_MIGRATION.UPGRADE_STATEMENTS)
            conn.execute(text(CANAL_MIGRATION.CREATE_CANAL_CONSORCIO))
            conn.execute(
                text(
                    "CREATE TABLE geo_jobs (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
                    "tipo TEXT, estado TEXT)"
                )
            )
            _run(conn, MATVIEW_DEPENDENCIES)
            conn.execute(text(CREATE_VT_PUNTOS_CONFLICTO))
            conn.execute(text(MATVIEW_MIGRATION.MV_DASHBOARD_GEO_STATS))
            conn.execute(text(MATVIEW_MIGRATION.IX_DASHBOARD_GEO_STATS))

            before = self._definitions(conn, schema)

            _run(conn, MIGRATION.UPGRADE_STATEMENTS)
            after_up = self._definitions(conn, schema)
            assert after_up == before, "the upgrade must not redefine either published object"

            _run(conn, MIGRATION.DOWNGRADE_STATEMENTS)
            after_down = self._definitions(conn, schema)
            assert after_down == before, "the downgrade must not redefine either published object"
        finally:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("SET search_path TO public"))
            conn.close()

    def test_the_concurrently_unique_index_survives(self, test_engine):
        """``REFRESH MATERIALIZED VIEW CONCURRENTLY`` depends on it.

        Re-creating the matview would mean re-creating this index; getting that
        wrong turns a dashboard refresh into a table lock. The dedicated table
        means neither is re-created, and this asserts it.
        """
        schema = f"{SCHEMA}_ccidx"
        conn = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}, public"))
            _run(conn, RED_VIAL_MIGRATION.UPGRADE_STATEMENTS)
            conn.execute(text(CANAL_MIGRATION.CREATE_CANAL_CONSORCIO))
            conn.execute(
                text(
                    "CREATE TABLE geo_jobs (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
                    "tipo TEXT, estado TEXT)"
                )
            )
            _run(conn, MATVIEW_DEPENDENCIES)
            conn.execute(text(MATVIEW_MIGRATION.MV_DASHBOARD_GEO_STATS))
            conn.execute(text(MATVIEW_MIGRATION.IX_DASHBOARD_GEO_STATS))

            _run(conn, MIGRATION.UPGRADE_STATEMENTS)
            conn.execute(
                text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {schema}.mv_dashboard_geo_stats")
            )

            still_unique = conn.execute(
                text(
                    "SELECT i.indisunique FROM pg_index i "
                    "JOIN pg_class idx ON idx.oid = i.indexrelid "
                    "JOIN pg_namespace n ON n.oid = idx.relnamespace "
                    "WHERE n.nspname = :s AND idx.relname = 'ix_mv_dashboard_geo_stats_id'"
                ),
                {"s": schema},
            ).scalar_one()
            assert still_unique is True
        finally:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text("SET search_path TO public"))
            conn.close()
