"""Real-PG tests for the soils ETL (PR A1b).

``suelos_catastro`` and ``mv_suelos_por_zona`` are migration-only objects: they
have no ORM model, so the metadata-built test schema does not contain them.
This module therefore builds both — the table with 0015's shape, the view from
migration 0017's own constants, so a change to the view can never drift away
from what these tests exercise — and drops them again in teardown.

Two consequences shape the fixtures:

* the loader COMMITs, and ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` opens its
  own AUTOCOMMIT connection, so the shared ``db`` fixture (transaction-per-test
  rollback, one connection) is unusable here. Isolation comes from owning the
  table outright and dropping it in teardown;
* ``zonas_operativas`` *is* in the metadata, so the view's other side already
  exists — the fixture only adds one zone, and deletes it afterwards.
"""

from __future__ import annotations

import importlib
import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domains.geo.etl import load_suelos_catastro as loader

# ``zonas_operativas`` lives in the intelligence models module; without this
# import a standalone run of this file finds no such table (same trap conftest
# documents for ``EmailCode``).
from app.domains.geo.intelligence import models as _intelligence_models  # noqa: F401
from tests.new._suelos_fixtures import SOURCE_FEATURE_COUNT, SOURCE_NULL_CAP_COUNT

MIGRATION = importlib.import_module("app.db.migrations.versions.0017_ficha_territorial_prep")

# 0015's shape, verbatim — including ``ip VARCHAR(50)``, the column that makes
# the int→str coercion (assertion 5) mandatory.
CREATE_SUELOS = """
    CREATE TABLE suelos_catastro (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        simbolo VARCHAR(50) NOT NULL,
        cap VARCHAR(10),
        ip VARCHAR(50),
        geometria GEOMETRY(MULTIPOLYGON, 4326) NOT NULL
    )
"""

#: Covers both the synthetic fixtures below and the real source extent
#: (lon -62.79..-62.29, lat -32.70..-32.40), so the view has rows either way.
ZONA_WKT = "POLYGON((-63 -33, -62 -33, -62 -32, -63 -32, -63 -33))"


def _feature(gid: int, simbolo: str, ring: list[list[float]], *, cap=None, ip=None) -> dict:
    return {
        "type": "Feature",
        "properties": {"gid": gid, "simbolo": simbolo, "cap": cap, "ip": ip},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def _box(x: float, y: float, size: float = 0.1) -> list[list[float]]:
    return [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]


#: A square, and a "polygon" whose vertices are collinear — ``ST_MakeValid``
#: turns the latter into a LINESTRING, ``ST_CollectionExtract(…, 3)`` leaves
#: nothing, and the load must abort naming its gid.
SANE_FEATURES = [
    _feature(1, "S1", _box(-62.9, -32.9), cap="IVws", ip=39),
    _feature(2, "S2", _box(-62.6, -32.6), cap=None, ip=None),
]
DEGENERATE_FEATURE = _feature(
    666, "DEGENERADO", [[-62.5, -32.5], [-62.4, -32.4], [-62.3, -32.3], [-62.5, -32.5]]
)


def _collection(features: list[dict]) -> list[loader.SourceFeature]:
    return loader.parse_features({"type": "FeatureCollection", "features": features})


@pytest.fixture(scope="module")
def etl_db(test_engine):
    """Build the migration-only objects, yield a committing session."""
    admin = test_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    session = Session(bind=test_engine)
    zona_id = None
    try:
        admin.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_suelos_por_zona"))
        admin.execute(text("DROP TABLE IF EXISTS suelos_catastro"))
        admin.execute(text(CREATE_SUELOS))
        zona_id = admin.execute(
            text("""
                INSERT INTO zonas_operativas (id, nombre, cuenca, geometria, superficie_ha)
                VALUES (gen_random_uuid(), 'zona-etl-test', 'cuenca-etl-test',
                        ST_GeomFromText(:wkt, 4326), 0)
                RETURNING id
            """),
            {"wkt": ZONA_WKT},
        ).scalar_one()
        # The view + its indexes exactly as migration 0017 creates them.
        for statement in MIGRATION.RECREATE_MV_STATEMENTS:
            admin.execute(text(statement))

        yield session
    finally:
        session.close()
        admin.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_suelos_por_zona"))
        admin.execute(text("DROP TABLE IF EXISTS suelos_catastro"))
        if zona_id is not None:
            admin.execute(text("DELETE FROM zonas_operativas WHERE id = :id"), {"id": zona_id})
        admin.close()


def _row_count(db: Session) -> int:
    return int(db.execute(text("SELECT count(*) FROM suelos_catastro")).scalar_one())


def _seed_sentinel(db: Session) -> None:
    """A committed row whose survival proves the abort really rolled back."""
    db.execute(text("DELETE FROM suelos_catastro"))
    db.execute(
        text("""
            INSERT INTO suelos_catastro (simbolo, cap, ip, geometria)
            VALUES ('CENTINELA', 'I', '1', ST_Multi(ST_GeomFromGeoJSON(:geom)))
        """),
        {"geom": json.dumps({"type": "Polygon", "coordinates": [_box(-62.95, -32.95)]})},
    )
    db.commit()


class TestFirstRun:
    """spec soils-etl › "First run populates the table"."""

    @pytest.fixture(scope="class")
    def loaded(self, etl_db):
        features = loader.read_source(loader.resolve_source(None))
        result = loader.load(etl_db, features)
        return etl_db, features, result

    def test_row_count_equals_source_feature_count(self, loaded):
        db, features, result = loaded
        assert len(features) == SOURCE_FEATURE_COUNT
        assert result.rows_after == len(features)
        assert _row_count(db) == len(features)

    def test_total_hectares_within_one_percent_of_source(self, loaded):
        db, features, result = loaded
        source_ha = loader.source_total_hectares(db, features)
        assert result.hectares > 0
        assert abs(result.hectares - source_ha) / source_ha <= loader.HECTARE_TOLERANCE

    def test_every_geometry_is_valid_multipolygon_4326(self, loaded):
        db, _features, _result = loaded
        bad = db.execute(
            text("""
                SELECT count(*) FROM suelos_catastro
                WHERE NOT ST_IsValid(geometria)
                   OR ST_SRID(geometria) <> 4326
                   OR GeometryType(geometria) <> 'MULTIPOLYGON'
            """)
        ).scalar_one()
        assert bad == 0

    def test_ip_is_stored_as_text_not_as_an_int(self, loaded):
        """Assertion 5 — the source ships ``ip`` as an int, the column is String(50)."""
        db, _features, _result = loaded
        column_type = db.execute(
            text("""
                SELECT data_type FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'suelos_catastro'
                  AND column_name = 'ip'
            """)
        ).scalar_one()
        assert column_type == "character varying"

        stored = db.execute(
            text("SELECT ip FROM suelos_catastro WHERE simbolo = 'Sr3'")
        ).scalar_one()
        assert stored == "39"
        assert isinstance(stored, str)

    def test_null_cap_rows_are_preserved_not_dropped(self, loaded):
        """Assertion 6 — some features have no ``cap`` and must survive."""
        db, _features, _result = loaded
        assert (
            db.execute(text("SELECT count(*) FROM suelos_catastro WHERE cap IS NULL")).scalar_one()
            == SOURCE_NULL_CAP_COUNT
        )

    def test_materialized_view_is_non_empty_after_refresh(self, loaded):
        """spec soils-etl › "ETL refreshes the view"."""
        db, _features, _result = loaded
        assert loader.refresh_materialized_view(db) > 0


class TestIdempotence:
    """spec soils-etl › "Re-run is idempotent"."""

    def test_rerun_over_an_out_of_band_load_converges(self, etl_db):
        """Prod already holds these rows, loaded out-of-band — converge over them."""
        features = _collection(SANE_FEATURES)
        first = loader.load(etl_db, features)
        second = loader.load(etl_db, features)

        assert second.rows_before == first.rows_after == len(features)
        assert second.rows_after == len(features)

    def test_no_duplicate_rows_for_any_source_feature(self, etl_db):
        loader.load(etl_db, _collection(SANE_FEATURES))
        loader.load(etl_db, _collection(SANE_FEATURES))

        duplicates = etl_db.execute(
            text("""
                SELECT count(*) FROM (
                    SELECT simbolo FROM suelos_catastro
                    GROUP BY simbolo HAVING count(*) > 1
                ) dup
            """)
        ).scalar_one()
        assert duplicates == 0


class TestLoadAborts:
    """spec soils-etl › "Invalid source geometry aborts the load" + row-count mismatch."""

    def test_unrepairable_geometry_aborts_naming_the_gid(self, etl_db):
        _seed_sentinel(etl_db)

        with pytest.raises(loader.EtlAssertionError, match="gid=666"):
            loader.load(etl_db, _collection([*SANE_FEATURES, DEGENERATE_FEATURE]))

        assert _row_count(etl_db) == 1
        assert (
            etl_db.execute(text("SELECT simbolo FROM suelos_catastro")).scalar_one() == "CENTINELA"
        )

    def test_row_count_mismatch_rolls_the_load_back(self, etl_db, monkeypatch):
        _seed_sentinel(etl_db)

        def _mismatch(db, expected):
            raise loader.EtlAssertionError(f"filas insertadas 0 != features del origen {expected}")

        monkeypatch.setattr(loader, "assert_row_count", _mismatch)

        with pytest.raises(loader.EtlAssertionError, match="filas insertadas"):
            loader.load(etl_db, _collection(SANE_FEATURES))

        assert _row_count(etl_db) == 1

    def test_assert_row_count_rejects_a_mismatch(self, etl_db):
        loader.load(etl_db, _collection(SANE_FEATURES))

        assert loader.assert_row_count(etl_db, len(SANE_FEATURES)) == len(SANE_FEATURES)
        with pytest.raises(loader.EtlAssertionError, match="se aborta la carga"):
            loader.assert_row_count(etl_db, len(SANE_FEATURES) + 1)

    def test_hectare_drift_is_rejected(self, etl_db):
        loader.load(etl_db, _collection(SANE_FEATURES))

        stored = float(etl_db.execute(loader._STORED_AREA_SQL).scalar_one())
        loader.assert_total_hectares(etl_db, stored)  # exact match must pass
        with pytest.raises(loader.EtlAssertionError, match="desvío"):
            loader.assert_total_hectares(etl_db, stored * 2)

    def test_dry_run_writes_nothing(self, etl_db):
        _seed_sentinel(etl_db)

        result = loader.load(etl_db, _collection(SANE_FEATURES), dry_run=True)

        assert result.committed is False
        assert result.rows_after == len(SANE_FEATURES)
        assert _row_count(etl_db) == 1


def _write_source(tmp_path, features: list[dict]) -> str:
    """A ``--source`` file on disk — the guard only gates the explicit source."""
    path = tmp_path / "origen.geojson"
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
    )
    return str(path)


def _seed_rows(db: Session, count: int) -> None:
    """Leave exactly ``count`` committed rows in the table."""
    db.execute(text("DELETE FROM suelos_catastro"))
    for index in range(count):
        db.execute(
            text("""
                INSERT INTO suelos_catastro (simbolo, cap, ip, geometria)
                VALUES (:simbolo, 'I', '1', ST_Multi(ST_GeomFromGeoJSON(:geom)))
            """),
            {
                "simbolo": f"PREEXISTENTE-{index}",
                "geom": json.dumps(
                    {"type": "Polygon", "coordinates": [_box(-62.95 + index * 0.01, -32.95)]}
                ),
            },
        )
    db.commit()


class TestDestructiveSourceGuard:
    """R1-002: a truncated ``--source`` must not wipe the table by accident."""

    def test_source_with_less_than_half_the_rows_is_refused(self, etl_db, tmp_path, capsys):
        _seed_rows(etl_db, 10)

        code = loader.run_load(etl_db, source=_write_source(tmp_path, SANE_FEATURES))

        assert code == loader.EXIT_LOAD_FAILED
        assert _row_count(etl_db) == 10, "la tabla tiene que quedar intacta"
        assert "Refusing to destroy data silently" in capsys.readouterr().err

    def test_force_lets_the_small_source_through(self, etl_db, tmp_path):
        _seed_rows(etl_db, 10)

        code = loader.run_load(etl_db, source=_write_source(tmp_path, SANE_FEATURES), force=True)

        assert code == loader.EXIT_OK
        assert _row_count(etl_db) == len(SANE_FEATURES)

    def test_guard_ignores_the_packaged_source(self, etl_db, tmp_path):
        """Only ``--source`` is gated — the packaged copy *is* the reference set."""
        _seed_rows(etl_db, 10)

        loader.assert_source_is_not_destructive(
            etl_db, _collection(SANE_FEATURES), explicit_source=False, force=False
        )


class TestRunLoadExitContract:
    """R3-101: the exit code is the operator's only signal — pin every branch."""

    @pytest.fixture
    def empty_table(self, etl_db):
        """Start from 0 rows so the destructive-source guard is a no-op here."""
        etl_db.execute(text("DELETE FROM suelos_catastro"))
        etl_db.commit()
        return etl_db

    def test_missing_source_is_an_invocation_error_not_a_load_abort(self, empty_table, capsys):
        code = loader.run_load(empty_table, source="/no/existe/suelos.geojson")

        assert code == loader.EXIT_USAGE
        err = capsys.readouterr().err
        assert "INVOCACIÓN INVÁLIDA" in err
        assert "rollback" not in err.lower(), "no hubo ninguna carga que revertir"

    def test_unparseable_source_is_an_infrastructure_failure(self, empty_table, tmp_path, capsys):
        corrupt = tmp_path / "roto.geojson"
        corrupt.write_text('{"type": "FeatureCollection", "features": [', encoding="utf-8")

        code = loader.run_load(empty_table, source=str(corrupt))

        assert code == loader.EXIT_INFRA_FAILED
        assert "FALLO DE INFRAESTRUCTURA" in capsys.readouterr().err

    def test_database_failure_during_the_load_is_an_infrastructure_failure(
        self, empty_table, tmp_path, monkeypatch, capsys
    ):
        def _boom(db, features, **kwargs):
            raise SQLAlchemyError("la conexión con la base se cayó")

        monkeypatch.setattr(loader, "load", _boom)

        code = loader.run_load(empty_table, source=_write_source(tmp_path, SANE_FEATURES))

        assert code == loader.EXIT_INFRA_FAILED
        err = capsys.readouterr().err
        assert "FALLO DE INFRAESTRUCTURA" in err
        assert "alembic upgrade head" in err, "el mensaje tiene que ser accionable"

    def test_refresh_failure_keeps_the_data_and_returns_its_own_code(
        self, empty_table, tmp_path, monkeypatch, capsys
    ):
        def _boom(db):
            raise RuntimeError("la vista no tiene índice único")

        monkeypatch.setattr(loader, "refresh_materialized_view", _boom)

        code = loader.run_load(empty_table, source=_write_source(tmp_path, SANE_FEATURES))

        assert code == loader.EXIT_REFRESH_FAILED
        assert _row_count(empty_table) == len(SANE_FEATURES), "la carga sí se commiteó"
        err = capsys.readouterr().err
        assert "DESACTUALIZADA" in err
        assert "/api/v2/admin/geo/suelos/refresh-mv" in err, "falta la recuperación"

    def test_dry_run_never_refreshes_the_view(self, empty_table, tmp_path, monkeypatch, capsys):
        calls: list[Session] = []
        monkeypatch.setattr(loader, "refresh_materialized_view", calls.append)

        code = loader.run_load(
            empty_table, source=_write_source(tmp_path, SANE_FEATURES), dry_run=True
        )

        assert code == loader.EXIT_OK
        assert calls == [], "un ensayo no puede tocar la vista materializada"
        assert _row_count(empty_table) == 0
        assert "no se refrescó" in capsys.readouterr().out


class TestSourceParsing:
    """Fail loudly at parse time — a skipped feature would surface as assertion 1."""

    def test_non_feature_collection_is_rejected(self):
        with pytest.raises(loader.EtlAssertionError, match="FeatureCollection"):
            loader.parse_features({"type": "Feature"})

    def test_empty_collection_is_rejected(self):
        with pytest.raises(loader.EtlAssertionError, match="no tiene features"):
            loader.parse_features({"type": "FeatureCollection", "features": []})

    def test_feature_without_geometry_is_rejected(self):
        payload = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"gid": 7, "simbolo": "X"}}],
        }
        with pytest.raises(loader.EtlAssertionError, match="gid=7"):
            loader.parse_features(payload)

    def test_feature_without_simbolo_is_rejected(self):
        payload = {"type": "FeatureCollection", "features": [_feature(8, "", _box(-62.9, -32.9))]}
        with pytest.raises(loader.EtlAssertionError, match="sin simbolo"):
            loader.parse_features(payload)


class TestAdminRefreshEndpoint:
    """spec soils-etl › "Stale view is recoverable" (JD-A-004 / JDB-016).

    The mount + admin gating contract is proven BEHAVIORALLY below
    (anonymous -> 401, authenticated operador -> 403) against the real
    ``app.main`` app. There is deliberately NO structural route-set
    assertion: two attempts (via ``app.main.routes`` and via
    ``app.api.v2.router.api_router.routes``) were green locally under the
    exact CI invocation but failed ONLY on the CI interpreter with
    impossible states (empty aggregator in the same process where the
    behavioral tests proved the route mounted) — a module-identity quirk
    of that environment, not a contract regression. Behavior is the
    contract; structure was the fragile proxy.
    """

    def test_refresh_mv_requires_authentication(self):
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)
        client.headers.update({"Host": "localhost"})

        # ``json={}`` on purpose: the CSRF middleware rejects a state-changing
        # request without ``Content-Type: application/json`` with 415 *before*
        # auth runs, which would mask whether the route is gated at all.
        resp = client.post("/api/v2/admin/geo/suelos/refresh-mv", json={})

        assert resp.status_code in (401, 403), (
            "el refresh de la vista materializada NO puede quedar abierto — "
            f"devolvió {resp.status_code}"
        )

    def test_refresh_mv_is_forbidden_for_an_authenticated_operator(self):
        """Admin-only: an operador is authenticated and still must not refresh.

        Same auth-mock style as ``test_gee_public_contract``: override
        ``current_active_user``, which is what ``require_admin`` depends on.
        """
        from types import SimpleNamespace

        from fastapi.testclient import TestClient

        from app.auth.dependencies import current_active_user
        from app.auth.models import UserRole
        from app.main import app

        app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(
            role=UserRole.OPERADOR
        )
        try:
            client = TestClient(app)
            client.headers.update({"Host": "localhost"})

            resp = client.post("/api/v2/admin/geo/suelos/refresh-mv", json={})
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 403, (
            f"un operador autenticado NO puede disparar el refresh — devolvió {resp.status_code}"
        )
