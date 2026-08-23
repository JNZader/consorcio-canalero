"""Real-PG: a regression guard on code this change does NOT touch.

With the dedicated table this is a **regression guard on untouched code**, not a
predicate under test — and that inversion is the point. Round 1 planned to
overload ``puntos_conflicto``, which has four unfiltered aggregate readers: the
public ``vt_`` view, the dashboard matview's ``SELECT COUNT(*)``,
``conflictos_activos`` and ``get_conflictos`` with no ``tipo_filter``. Each would
have needed a synchronized exclusion predicate, and the matview would have needed
re-creating along with the UNIQUE index that makes
``REFRESH MATERIALIZED VIEW CONCURRENTLY`` legal.

The dedicated table means **nothing was written where any of them read**, which
is a stronger guarantee than four predicates kept in sync. This asserts it rather
than claiming it, because a guard on untouched code is cheap and is the standing
evidence that it stayed untouched.

The three untouched-file proofs at the end are the same argument at the level of
the diff.
"""

from __future__ import annotations

import importlib
import subprocess
import uuid
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.crs import CRS
from sqlalchemy import text

from app.domains.geo.intelligence import cruces_camino_service
from app.domains.geo.intelligence.repository import IntelligenceRepository

AREA = "zona_regresion"
CELL = 30.0
UTM = CRS.from_epsg(32720)
TRANSFORM = Affine(CELL, 0.0, 331_000.0, 0.0, -CELL, 6_348_000.0)

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_REF = "origin/feat/flujo-caminos-s1-red-vial"


def _write_raster(path: Path, data: np.ndarray) -> str:
    with rasterio.open(
        str(path),
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="float64",
        crs=UTM,
        transform=TRANSFORM,
        nodata=-9999.0,
    ) as dst:
        dst.write(data.astype("float64"), 1)
    return str(path)


@pytest.fixture
def session_factory(test_engine):
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=test_engine)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def seeded(db, tmp_path):
    """A runnable area, plus one PRE-EXISTING ``puntos_conflicto`` row.

    The pre-existing row matters: the counters must be non-zero before the run,
    or "unchanged" would be indistinguishable from "both zero".
    """
    canal_migration = importlib.import_module("app.db.migrations.versions.0020_add_canal_consorcio")
    db.execute(text(canal_migration.CREATE_CANAL_CONSORCIO))

    import geopandas as gpd
    from shapely.geometry import LineString

    def centre(row, col):
        return TRANSFORM * (col + 0.5, row + 0.5)

    line = LineString([centre(10, 1), centre(10, 19)])
    wkt = gpd.GeoDataFrame({"geometry": [line]}, geometry="geometry", crs=UTM).to_crs(4326)
    db.execute(
        text(
            "INSERT INTO red_vial (id, source_id, geom, geom_hash) "
            "VALUES ('reg-1', 'reg-1', ST_GeomFromText(:w, 4326), 'h')"
        ),
        {"w": wkt.iloc[0].geometry.wkt},
    )

    shape = (21, 21)
    acc = np.full(shape, 100.0)
    acc[10, 10] = 8000.0
    paths = {
        f"natural_flow_dir_{AREA}": (
            "flow_dir",
            _write_raster(tmp_path / "fd.tif", np.full(shape, 4.0)),
        ),
        f"natural_flow_acc_{AREA}": ("flow_acc", _write_raster(tmp_path / "fa.tif", acc)),
    }
    for nombre, (tipo, path) in paths.items():
        db.execute(
            text(
                "INSERT INTO geo_layers (id, nombre, tipo, fuente, archivo_path, formato, "
                " srid, area_id, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :n, :t, 'dem_pipeline', :p, 'geotiff', 4326, "
                " :a, now(), now())"
            ),
            {"n": nombre, "t": tipo, "p": path, "a": AREA},
        )

    # A pre-existing legacy conflict — including a ``canal_camino`` one, the
    # tipo the legacy detector still emits and which this change deliberately
    # leaves alone.
    db.execute(
        text(
            "INSERT INTO puntos_conflicto (id, tipo, geometria, descripcion, severidad, "
            " acumulacion_valor, pendiente_valor, created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'canal_camino', "
            " ST_SetSRID(ST_MakePoint(-62.8, -33.0), 4326), 'legacy', 'alta', 6000, 0.2, "
            " now(), now())"
        )
    )
    db.commit()

    yield
    db.execute(text("DELETE FROM cruce_camino WHERE area_id = :a"), {"a": AREA})
    db.execute(text("DELETE FROM geo_layers WHERE area_id = :a"), {"a": AREA})
    db.execute(text("DELETE FROM geo_jobs"))
    db.execute(text("DELETE FROM red_vial WHERE id = 'reg-1'"))
    db.execute(text("DELETE FROM puntos_conflicto"))
    db.execute(text("DROP TABLE IF EXISTS canal_consorcio CASCADE"))
    db.commit()


def _snapshot(db) -> dict[str, int]:
    """The three aggregates plus the raw row count, read exactly as they are today.

    * ``conflictos_activos`` — ``get_dashboard_inteligente``'s unfiltered
      ``COUNT(*) FROM puntos_conflicto`` (``repository_metrics.py:192``).
    * the default ``GET /conflictos`` total — ``get_conflictos`` with **no**
      ``tipo_filter`` (``repository_metrics.py:71-87``, exposed by
      ``router.py:162-173``).
    * the raw row count, which is what the dashboard matview's
      ``total_conflictos`` sub-select reads.

    Each is called through the real repository rather than re-typed as SQL, so a
    change to any of them shows up here instead of being shadowed by a copy.
    """
    repo = IntelligenceRepository()
    total_rows = int(db.execute(text("SELECT count(*) FROM puntos_conflicto")).scalar_one())
    dashboard = repo.get_dashboard_inteligente(db)
    conflictos, total_default = repo.get_conflictos(db, page=1, limit=1000)
    return {
        "puntos_conflicto_rows": total_rows,
        "conflictos_activos": dashboard["conflictos_activos"],
        "get_conflictos_total": total_default,
        "get_conflictos_len": len(conflictos),
    }


class TestNothingExistingMoved:
    def test_a_full_crossing_run_changes_no_conflict_aggregate(
        self, db, seeded, session_factory, tmp_path
    ):
        before = _snapshot(db)
        assert before["puntos_conflicto_rows"] > 0, (
            "the guard is vacuous if the counters start at zero"
        )

        job_id = uuid.uuid4()
        db.execute(
            text(
                "INSERT INTO geo_jobs (id, tipo, estado, progreso, parametros, "
                " created_at, updated_at) VALUES "
                "(:id, 'road_flow_crossings', 'pending', 0, CAST(:p AS json), now(), now())"
            ),
            {"id": str(job_id), "p": f'{{"area_id": "{AREA}"}}'},
        )
        db.commit()

        result = cruces_camino_service.run_crossing_task(
            area_id=AREA,
            job_id=str(job_id),
            session_factory=session_factory,
            scratch_root=str(tmp_path / "scratch"),
        )
        assert result["status"] == "completed"
        assert result["cruces"] > 0, "the run must actually have written crossings"

        after = _snapshot(db)
        assert after == before, (
            "the crossing run wrote nowhere any conflict aggregate reads — "
            f"before={before} after={after}"
        )

    def test_puntos_conflicto_gained_exactly_zero_rows(self, db, seeded, session_factory, tmp_path):
        before = int(db.execute(text("SELECT count(*) FROM puntos_conflicto")).scalar_one())

        job_id = uuid.uuid4()
        db.execute(
            text(
                "INSERT INTO geo_jobs (id, tipo, estado, progreso, parametros, "
                " created_at, updated_at) VALUES "
                "(:id, 'road_flow_crossings', 'pending', 0, CAST(:p AS json), now(), now())"
            ),
            {"id": str(job_id), "p": f'{{"area_id": "{AREA}"}}'},
        )
        db.commit()

        cruces_camino_service.run_crossing_task(
            area_id=AREA,
            job_id=str(job_id),
            session_factory=session_factory,
            scratch_root=str(tmp_path / "scratch"),
        )

        after = int(db.execute(text("SELECT count(*) FROM puntos_conflicto")).scalar_one())
        assert after == before

    def test_the_legacy_canal_camino_tipo_is_untouched(self, db, seeded):
        """The two live in different tables and do not interfere.

        ``detectar_puntos_conflicto_impl`` keeps emitting ``canal_camino`` into
        ``puntos_conflicto`` exactly as today; retiring that tipo remains a
        plausible follow-up and is still out of scope.
        """
        legacy = int(
            db.execute(
                text("SELECT count(*) FROM puntos_conflicto WHERE tipo = 'canal_camino'")
            ).scalar_one()
        )
        assert legacy == 1


def _diff_stat(*paths: str) -> str:
    # These proofs are CHAIN-SCOPED: they only mean anything in a checkout
    # where the S1 base ref exists (single-branch/shallow fetches, source
    # archives, and any clone after the branch is merged and deleted do not
    # have it). There the honest outcome is an explicit skip, not a red that
    # blames the code for the shape of the local VCS state.
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{BASE_REF}^{{commit}}"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if probe.returncode != 0:
        pytest.skip(f"base ref {BASE_REF} unavailable in this checkout; chain-scoped proof")
    result = subprocess.run(
        ["git", "diff", "--stat", f"{BASE_REF}...HEAD", "--", *paths],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


class TestUntouchedFileProofs:
    """Three claims about the diff, each executable rather than asserted in prose."""

    def test_tasks_dem_support_is_untouched(self):
        """Law 8: the snapshot-copy protocol replaced the producer-side edit."""
        assert _diff_stat("gee-backend/app/domains/geo/tasks_dem_support.py") == ""

    def test_martin_and_the_reader_grants_are_untouched(self):
        """Law 4: nothing is published, so the public surface cannot have moved.

        The containment is CONFIGURATION — ``auto_publish: false`` plus the
        explicit ``tables:`` list — not a narrow database grant: Martin connects
        as the application role and could read any table if discovery were on. So
        an empty diff here is the actual security argument, not a formality.
        """
        assert (
            _diff_stat(
                "martin/",
                "scripts/provision_martin_reader.sql",
                "gee-backend/tests/new/test_martin_reader_grants.py",
            )
            == ""
        )

    def test_repository_metrics_is_untouched(self):
        """No exclusion predicate was needed, because nothing was written there."""
        assert _diff_stat("gee-backend/app/domains/geo/intelligence/repository_metrics.py") == ""

    # A fourth proof used to re-run ``test_martin_reader_grants.py`` as a nested
    # pytest subprocess "to prove it still passes unedited". Removed 2026-08-23:
    # the diff proof above already pins the file byte-for-byte, the file runs in
    # the normal suite with its own fixtures anyway, and the nested run executed
    # against the SHARED CI database — its teardown ``DROP TABLE users`` failed
    # whenever the outer suite had already created the FK-dependent tables, so
    # the proof was red or green depending on pytest-randomly's ordering, not on
    # anything about the code.


class TestNoPublishedObjectWasCreated:
    def test_cruce_camino_has_no_view_and_no_martin_entry(self, db, seeded):
        views = (
            db.execute(
                text(
                    "SELECT viewname FROM pg_views WHERE schemaname = 'public' "
                    "AND definition ILIKE '%cruce_camino%'"
                )
            )
            .scalars()
            .all()
        )
        assert views == [], f"cruce_camino must have no view at all — found {views}"

        matviews = (
            db.execute(
                text(
                    "SELECT matviewname FROM pg_matviews WHERE schemaname = 'public' "
                    "AND definition ILIKE '%cruce_camino%'"
                )
            )
            .scalars()
            .all()
        )
        assert matviews == []

    def test_the_martin_config_names_no_crossing_source(self):
        config = (REPO_ROOT / "martin" / "config.yaml").read_text()
        assert "cruce_camino" not in config
        assert "road_flow" not in config
