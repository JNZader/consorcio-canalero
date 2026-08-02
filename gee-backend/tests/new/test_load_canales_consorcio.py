"""Tests for the curated-canal seed ETL ``load_canales_consorcio``.

Two concerns, both pinned here:

* **Packaging** (no DB) — the loader ships its two GeoJSONs as package data and
  resolves them through ``importlib.resources``, never a repo-relative path (the
  JDB-002 regression), and the packaged copies stay byte-identical to the frontend
  artifacts they were copied from (JD-A-011 drift guard).
* **Load** (real PostgreSQL) — loading the 2 bundled GeoJSONs yields 60
  ``canal_consorcio`` rows (41 relevado + 19 propuesto) with the right
  ``id``/``estado``/geometry, and a re-run is idempotent (UPSERT converges on 60).

``canal_consorcio`` is migration-only (no ORM model), so the load fixture builds it
from ``0020``'s real DDL under a per-test savepoint that rolls back at teardown.
"""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.geo.etl import load_canales_consorcio as loader

_MIGRATION = importlib.import_module("app.db.migrations.versions.0020_add_canal_consorcio")

#: ``tests/new/x.py`` → ``tests/new`` → ``tests`` → ``gee-backend`` → repo root.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
FRONTEND_DIR = REPO_ROOT / "consorcio-web" / "public" / "capas" / "canales"

RELEVADO_COUNT = 41
PROPUESTO_COUNT = 19
TOTAL_COUNT = RELEVADO_COUNT + PROPUESTO_COUNT  # 60


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── packaging (no DB) ────────────────────────────────────────────────────────


class TestPackagedSources:
    def test_default_sources_resolve_inside_the_package(self):
        sources = loader.resolve_sources()
        assert len(sources) == 2
        package_dir = Path(loader.__file__).resolve().parent
        for path, _estado in sources:
            assert path.is_file(), f"la copia empaquetada no existe: {path}"
            assert path.resolve().is_relative_to(package_dir), (
                f"el origen quedó fuera de app/domains/geo/etl/ — no viajaría en la imagen: {path}"
            )

    def test_packaged_sources_parse_to_60_features(self):
        features = loader.read_all_sources(loader.resolve_sources())
        assert len(features) == TOTAL_COUNT
        assert sum(1 for f in features if f.estado == "relevado") == RELEVADO_COUNT
        assert sum(1 for f in features if f.estado == "propuesto") == PROPUESTO_COUNT
        # Every id is a non-empty string and unique.
        ids = [f.id for f in features]
        assert all(isinstance(i, str) and i for i in ids)
        assert len(set(ids)) == TOTAL_COUNT

    def test_module_runs_as_python_m(self):
        result = subprocess.run(
            [sys.executable, "-m", "app.domains.geo.etl.load_canales_consorcio", "--help"],
            cwd=BACKEND_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
        assert "--dry-run" in result.stdout

    def test_docstring_documents_the_container_invocation(self):
        assert (
            "docker compose exec backend python -m app.domains.geo.etl.load_canales_consorcio"
            in (loader.__doc__ or "")
        )


class TestDriftGuard:
    """JD-A-011: each packaged copy and its frontend artifact are one file."""

    @pytest.mark.parametrize("name", ["relevados.geojson", "propuestas.geojson"])
    def test_packaged_copy_is_byte_identical_to_the_frontend_artifact(self, name: str):
        packaged = Path(loader.__file__).resolve().parent / "data" / name
        frontend = FRONTEND_DIR / name
        assert packaged.is_file(), f"falta la copia empaquetada: {packaged}"
        assert frontend.is_file(), f"no está el original del frontend: {frontend}"
        assert _sha256(packaged) == _sha256(frontend), (
            f"la copia empaquetada de {name} derivó del artefacto del frontend: "
            f"volver a copiar {frontend} sobre {packaged}"
        )


class TestSourceValidation:
    """Parse-time guards fail loud rather than silently skipping a feature."""

    def test_estado_mismatch_against_file_family_aborts(self):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "properties": {"id": "x", "nombre": "X", "estado": "propuesto"},
                    "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                }
            ],
        }
        with pytest.raises(loader.EtlAssertionError, match="familia 'relevado'"):
            loader.parse_features(payload, "relevado")

    def test_non_linestring_geometry_aborts(self):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "properties": {"id": "x", "nombre": "X", "estado": "relevado"},
                    "geometry": {"type": "Point", "coordinates": [0, 0]},
                }
            ],
        }
        with pytest.raises(loader.EtlAssertionError, match="no es LineString"):
            loader.parse_features(payload, "relevado")

    def test_missing_id_aborts(self):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "properties": {"nombre": "X", "estado": "relevado"},
                    "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                }
            ],
        }
        with pytest.raises(loader.EtlAssertionError, match="sin id de canal"):
            loader.parse_features(payload, "relevado")


# ── load (real PostgreSQL) ───────────────────────────────────────────────────


@pytest.fixture
def canales_db(test_engine) -> Session:
    connection = test_engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    # canal_consorcio (+ canal_catchment) are migration-only; build them from
    # 0020's real DDL. geo_layers already exists (ORM model) as an FK target.
    for statement in _MIGRATION.UPGRADE_STATEMENTS:
        session.execute(text(statement))
    session.commit()  # release the DDL savepoint

    yield session

    session.close()
    trans.rollback()
    connection.close()


def _count_by_estado(db: Session, estado: str) -> int:
    return int(
        db.execute(
            text("SELECT count(*) FROM canal_consorcio WHERE estado = :e"), {"e": estado}
        ).scalar_one()
    )


class TestLoad:
    def test_loads_60_curated_canals(self, canales_db: Session):
        code = loader.run_load(canales_db)
        assert code == loader.EXIT_OK

        total = int(canales_db.execute(text("SELECT count(*) FROM canal_consorcio")).scalar_one())
        assert total == TOTAL_COUNT
        assert _count_by_estado(canales_db, "relevado") == RELEVADO_COUNT
        assert _count_by_estado(canales_db, "propuesto") == PROPUESTO_COUNT

    def test_stored_ids_estados_and_geometry_are_correct(self, canales_db: Session):
        loader.run_load(canales_db)

        # A known relevado (prioridad NULL) and a known propuesto (prioridad set).
        rel = canales_db.execute(
            text(
                "SELECT estado, prioridad, ST_SRID(geom) AS srid, "
                "GeometryType(geom) AS gtype, ST_IsValid(geom) AS valid "
                "FROM canal_consorcio WHERE id = 'canal-ne-sin-intervencion'"
            )
        ).one()
        assert rel.estado == "relevado"
        assert rel.prioridad is None
        assert rel.srid == 4326
        assert rel.gtype == "LINESTRING"
        assert rel.valid is True

        prop = canales_db.execute(
            text(
                "SELECT estado, prioridad, longitud_m "
                "FROM canal_consorcio WHERE id = 'n3-tramo-faltante-de-interconexion'"
            )
        ).one()
        assert prop.estado == "propuesto"
        assert prop.prioridad == "Alta"
        assert prop.longitud_m == pytest.approx(685.5)

        # Every stored geometry is a valid 4326 LineString.
        bad = canales_db.execute(
            text(
                "SELECT count(*) FROM canal_consorcio "
                "WHERE NOT ST_IsValid(geom) OR ST_SRID(geom) <> 4326 "
                "OR GeometryType(geom) <> 'LINESTRING'"
            )
        ).scalar_one()
        assert bad == 0

    def test_reload_is_idempotent(self, canales_db: Session):
        loader.run_load(canales_db)
        first = int(canales_db.execute(text("SELECT count(*) FROM canal_consorcio")).scalar_one())

        # Second run must UPSERT onto the same ids, not grow the table.
        code = loader.run_load(canales_db)
        assert code == loader.EXIT_OK
        second = int(canales_db.execute(text("SELECT count(*) FROM canal_consorcio")).scalar_one())
        assert first == second == TOTAL_COUNT

    def test_dry_run_writes_nothing(self, canales_db: Session):
        code = loader.run_load(canales_db, dry_run=True)
        assert code == loader.EXIT_OK
        total = int(canales_db.execute(text("SELECT count(*) FROM canal_consorcio")).scalar_one())
        assert total == 0  # rolled back
