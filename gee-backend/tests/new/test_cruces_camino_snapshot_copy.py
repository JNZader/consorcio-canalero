"""Real-PG: the five properties the snapshot-copy protocol exists for.

The advisory lock this replaced did not work, for four independent reasons that
are all still true of the code: ``cleanup_full_dem_state_impl`` COMMITs — and so
releases any transaction-scoped lock — *before* it deletes the output files, so a
blocked reader would be woken up precisely in time to read files being deleted;
the plain pipeline's ``archive_previous_output`` was never covered by any
proposed lock at all and renames the directory out from under the reader;
``hashtext`` shares its single-key ``int4`` space with the auth domain's
refresh-token family locks; and the stage-2 in-place raster rewrites are outside
the one place a lock was proposed.

So the reader is made independent of the writer's TIMING instead. Property (3)
below is the one the whole protocol exists for; properties (1), (2), (4) and (5)
are what keep it from trading one failure mode for another.

``tasks_dem_support.py`` is asserted unmodified: there is no producer half to
keep in sync, which is why there is no "the guard is worthless if only one side
takes it" failure mode to test for.
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
from sqlalchemy.orm import Session

from app.domains.geo.intelligence import cruces_camino_service

AREA = "zona_snapshot"
CELL = 30.0
UTM = CRS.from_epsg(32720)

#: A footprint that really contains the seeded road, so the spatial pre-filter
#: admits it. Around -62.8 / -33.0 in UTM 20S.
ORIGIN_X = 331_000.0
ORIGIN_Y = 6_348_000.0
TRANSFORM = Affine(CELL, 0.0, ORIGIN_X, 0.0, -CELL, ORIGIN_Y)


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


def _road_wkt() -> str:
    """A due-east road across the raster, in 4326."""
    import geopandas as gpd
    from shapely.geometry import LineString

    def centre(row, col):
        return TRANSFORM * (col + 0.5, row + 0.5)

    line = LineString([centre(10, 1), centre(10, 19)])
    gdf = gpd.GeoDataFrame({"geometry": [line]}, geometry="geometry", crs=UTM).to_crs(4326)
    return gdf.iloc[0].geometry.wkt


@pytest.fixture
def rasters(tmp_path):
    """A pointer raster (due north) and an accumulation raster with one ridge."""
    shape = (21, 21)
    acc = np.full(shape, 100.0)
    acc[10, 10] = 8000.0
    return (
        _write_raster(tmp_path / "natural_flow_dir.tif", np.full(shape, 4.0)),
        _write_raster(tmp_path / "natural_flow_acc.tif", acc),
    )


@pytest.fixture
def seeded(db, rasters):
    """One road, the canal table, and the two layer rows the resolver looks up.

    ``canal_consorcio`` is **migration-only** — it has no ORM model, so
    ``Base.metadata.create_all`` does not build it and this fixture runs
    ``0020``'s real DDL, as ``test_load_canales_consorcio`` does. It is dropped
    again on teardown: this fixture commits, and leaving the table behind would
    break that other suite, which creates it inside a rolled-back transaction.
    The canal derivation is UNCONDITIONAL, so the table has to be there even
    though this area has no canals in it.
    """
    canal_migration = importlib.import_module("app.db.migrations.versions.0020_add_canal_consorcio")
    db.execute(text(canal_migration.CREATE_CANAL_CONSORCIO))
    db.commit()

    flow_dir_path, flow_acc_path = rasters
    db.execute(
        text(
            "INSERT INTO red_vial (id, source_id, geom, geom_hash) "
            "VALUES ('snap-1', 'snap-1', ST_GeomFromText(:wkt, 4326), 'h')"
        ),
        {"wkt": _road_wkt()},
    )
    for nombre, tipo, path in (
        (f"natural_flow_dir_{AREA}", "flow_dir", flow_dir_path),
        (f"natural_flow_acc_{AREA}", "flow_acc", flow_acc_path),
    ):
        db.execute(
            text(
                "INSERT INTO geo_layers "
                "(id, nombre, tipo, fuente, archivo_path, formato, srid, area_id, "
                " created_at, updated_at) "
                "VALUES (gen_random_uuid(), :n, :t, 'dem_pipeline', :p, 'geotiff', 4326, "
                ":a, now(), now())"
            ),
            {"n": nombre, "t": tipo, "p": path, "a": AREA},
        )
    db.commit()
    yield
    db.execute(text("DELETE FROM cruce_camino WHERE area_id = :a"), {"a": AREA})
    db.execute(text("DELETE FROM geo_layers WHERE area_id = :a"), {"a": AREA})
    db.execute(text("DELETE FROM geo_jobs"))
    db.execute(text("DELETE FROM red_vial WHERE id = 'snap-1'"))
    db.execute(text("DROP TABLE IF EXISTS canal_consorcio CASCADE"))
    db.commit()


@pytest.fixture
def session_factory(test_engine):
    """Real committing sessions — the protocol's whole subject is commit visibility.

    The rolled-back ``db`` fixture cannot express "another process inserted a DEM
    job between two of my transactions", which is exactly property (2).
    """
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=test_engine)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


def _insert_dem_job(db, estado: str, *, area_id: str = AREA) -> uuid.UUID:
    job_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO geo_jobs (id, tipo, estado, progreso, parametros, "
            " created_at, updated_at) "
            "VALUES (:id, 'dem_pipeline', :estado, 0, "
            " CAST(:params AS json), now(), now())"
        ),
        {
            "id": str(job_id),
            "estado": estado,
            "params": f'{{"area_id": "{area_id}"}}',
        },
    )
    db.commit()
    return job_id


def _crossing_job(db) -> str:
    job_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO geo_jobs (id, tipo, estado, progreso, parametros, "
            " created_at, updated_at) "
            "VALUES (:id, 'road_flow_crossings', 'pending', 0, "
            " CAST(:params AS json), now(), now())"
        ),
        {"id": str(job_id), "params": f'{{"area_id": "{AREA}"}}'},
    )
    db.commit()
    return str(job_id)


def _job_estado(db: Session, job_id: str) -> tuple[str, str | None]:
    return db.execute(
        text("SELECT estado::text, error FROM geo_jobs WHERE id = :id"), {"id": job_id}
    ).one()


def _crossing_count(db: Session) -> int:
    return int(
        db.execute(
            text("SELECT count(*) FROM cruce_camino WHERE area_id = :a"), {"a": AREA}
        ).scalar_one()
    )


class TestProperty1PreCheckRefusesEarly:
    """A DEM job PENDING **or** RUNNING makes the run refuse before it claims.

    ``pending`` matters: on the real dispatch path the API creates the row as
    PENDING and the worker claims it after broker latency, so a PENDING DEM row
    means destruction is imminent. Refusing early beats racing it.
    """

    @pytest.mark.parametrize("estado", ["pending", "running"])
    def test_refuses_leaving_the_job_failed_and_nothing_written(
        self, db, seeded, session_factory, tmp_path, estado: str
    ):
        _insert_dem_job(db, estado)
        job_id = _crossing_job(db)

        result = cruces_camino_service.run_crossing_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            scratch_root=str(tmp_path / "scratch"),
        )

        assert result["status"] == "skipped"
        assert result["motivo"] == "dem_job_running_pre_check"

        estado_final, error = _job_estado(db, job_id)
        assert estado_final == "failed"
        assert "dem_job_running_pre_check" in error
        assert AREA in error, "the motivo must name the area"
        assert _crossing_count(db) == 0, "a refused run writes NOTHING"

    def test_a_dem_job_for_another_area_does_not_block(self, db, seeded, session_factory, tmp_path):
        _insert_dem_job(db, "running", area_id="otra_zona")
        job_id = _crossing_job(db)

        result = cruces_camino_service.run_crossing_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            scratch_root=str(tmp_path / "scratch"),
        )

        assert result["status"] == "completed"


class TestProperty2PostCopyRecheck:
    """The case the pre-check ALONE cannot catch.

    A pipeline can reach RUNNING one microsecond after the pre-check returns
    empty. The re-check is keyed on ``updated_at >= pre_check_at`` and not on
    ``created_at`` precisely so that the ``PENDING → RUNNING`` claim of a job
    *created before* the pre-check still trips it.
    """

    def test_a_dem_job_appearing_during_the_copy_aborts_the_run(
        self, db, seeded, session_factory, tmp_path, monkeypatch
    ):
        job_id = _crossing_job(db)
        inserted: list[uuid.UUID] = []
        original = cruces_camino_service.copiar_rasters_a_scratch

        def racing_copy(variante, *, scratch_root):
            result = original(variante, scratch_root=scratch_root)
            # The race, made deterministic: a DEM job reaches RUNNING after the
            # pre-check and while the copy is in flight.
            racer = session_factory()
            try:
                inserted.append(_insert_dem_job(racer, "running"))
            finally:
                racer.close()
            return result

        monkeypatch.setattr(cruces_camino_service, "copiar_rasters_a_scratch", racing_copy)

        result = cruces_camino_service.run_crossing_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            scratch_root=str(tmp_path / "scratch"),
        )

        assert inserted, "the racing DEM job must actually have been inserted"
        assert result["status"] == "skipped"
        assert result["motivo"] == "dem_job_started_during_copy"

        estado_final, error = _job_estado(db, job_id)
        assert estado_final == "failed"
        assert "dem_job_started_during_copy" in error
        assert _crossing_count(db) == 0

    def test_a_job_created_before_the_precheck_but_claimed_after_still_trips_it(
        self, db, seeded, session_factory, tmp_path, monkeypatch
    ):
        """Why the key is ``updated_at`` and not ``created_at``.

        The DEM row is inserted as PENDING *after* the crossing run's pre-check
        (so the pre-check cannot see it), then claimed. ``created_at`` would be
        newer than the mark here too — so this is arranged so the row's
        ``created_at`` is deliberately pushed BACK before the mark, leaving only
        the claim's ``updated_at`` bump to catch it.
        """
        job_id = _crossing_job(db)
        original = cruces_camino_service.copiar_rasters_a_scratch

        def racing_copy(variante, *, scratch_root):
            result = original(variante, scratch_root=scratch_root)
            racer = session_factory()
            try:
                dem_id = _insert_dem_job(racer, "pending")
                # Backdate created_at well before the pre-check, then claim:
                # only the updated_at bump remains as evidence.
                racer.execute(
                    text(
                        "UPDATE geo_jobs SET created_at = now() - interval '2 days' WHERE id = :id"
                    ),
                    {"id": str(dem_id)},
                )
                racer.execute(
                    text(
                        "UPDATE geo_jobs SET estado = 'running', updated_at = now() WHERE id = :id"
                    ),
                    {"id": str(dem_id)},
                )
                racer.commit()
            finally:
                racer.close()
            return result

        monkeypatch.setattr(cruces_camino_service, "copiar_rasters_a_scratch", racing_copy)

        result = cruces_camino_service.run_crossing_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            scratch_root=str(tmp_path / "scratch"),
        )

        assert result["motivo"] == "dem_job_started_during_copy", (
            "keyed on created_at this job would have looked two days old and slipped through"
        )


class TestProperty3TheWholePoint:
    """After the copy, destroying the originals changes NOTHING."""

    def test_deleting_and_rewriting_the_sources_mid_run_has_no_effect(
        self, db, seeded, session_factory, tmp_path, rasters, monkeypatch
    ):
        flow_dir_path, flow_acc_path = rasters

        # Baseline: an undisturbed run.
        baseline_job = _crossing_job(db)
        baseline = cruces_camino_service.run_crossing_task(
            area_id=AREA,
            job_id=baseline_job,
            session_factory=session_factory,
            scratch_root=str(tmp_path / "scratch-baseline"),
        )
        assert baseline["status"] == "completed"
        expected = db.execute(
            text(
                "SELECT tramo_ref, tipo, ST_AsText(geometria), area_aporte_ha, "
                "orden_ranking, confianza FROM cruce_camino WHERE area_id = :a "
                "ORDER BY tipo, orden_ranking NULLS LAST"
            ),
            {"a": AREA},
        ).all()
        assert expected, "the baseline run must actually produce crossings"

        # Now sabotage the SOURCES after the copy, exactly as an archiving or
        # wiping pipeline would.
        original = cruces_camino_service.copiar_rasters_a_scratch

        def sabotaging_copy(variante, *, scratch_root):
            result = original(variante, scratch_root=scratch_root)
            Path(flow_dir_path).unlink()
            shape = (21, 21)
            _write_raster(Path(flow_acc_path), np.full(shape, 999_999.0))
            return result

        monkeypatch.setattr(cruces_camino_service, "copiar_rasters_a_scratch", sabotaging_copy)

        sabotaged_job = _crossing_job(db)
        result = cruces_camino_service.run_crossing_task(
            area_id=AREA,
            job_id=sabotaged_job,
            session_factory=session_factory,
            scratch_root=str(tmp_path / "scratch-sabotaged"),
        )

        assert result["status"] == "completed", (
            "the run reads its private copies, so a deleted source cannot stop it"
        )
        actual = db.execute(
            text(
                "SELECT tramo_ref, tipo, ST_AsText(geometria), area_aporte_ha, "
                "orden_ranking, confianza FROM cruce_camino WHERE area_id = :a "
                "ORDER BY tipo, orden_ranking NULLS LAST"
            ),
            {"a": AREA},
        ).all()
        assert actual == expected, (
            "rewriting the sources after the copy must change NOTHING about the "
            "produced crossings — this is the property the protocol exists for"
        )


class TestProperty4ScratchIsAlwaysRemoved:
    def test_the_scratch_directory_is_gone_after_a_successful_run(
        self, db, seeded, session_factory, tmp_path
    ):
        root = tmp_path / "scratch-ok"
        root.mkdir()
        job_id = _crossing_job(db)

        cruces_camino_service.run_crossing_task(
            area_id=AREA, job_id=job_id, session_factory=session_factory, scratch_root=str(root)
        )

        assert list(root.iterdir()) == [], "the scratch dir must be removed in a finally"

    def test_the_scratch_directory_is_gone_after_an_abort(
        self, db, seeded, session_factory, tmp_path, monkeypatch
    ):
        root = tmp_path / "scratch-abort"
        root.mkdir()
        job_id = _crossing_job(db)
        original = cruces_camino_service.copiar_rasters_a_scratch

        def racing_copy(variante, *, scratch_root):
            result = original(variante, scratch_root=scratch_root)
            racer = session_factory()
            try:
                _insert_dem_job(racer, "running")
            finally:
                racer.close()
            return result

        monkeypatch.setattr(cruces_camino_service, "copiar_rasters_a_scratch", racing_copy)

        cruces_camino_service.run_crossing_task(
            area_id=AREA, job_id=job_id, session_factory=session_factory, scratch_root=str(root)
        )

        assert list(root.iterdir()) == [], (
            "even a crashed run leaks at most one area's worth of temporary rasters"
        )


class TestProperty5NoZombieRunning:
    """``EstadoGeoJob`` has exactly PENDING/RUNNING/COMPLETED/FAILED.

    There is no ``SKIPPED`` value and this change adds none, so a refusal has to
    land somewhere real. Both refusal paths are compare-and-set transitions to
    FAILED: the pre-check refuses *before* the claim (PENDING → FAILED) and the
    post-copy abort is an explicit RUNNING → FAILED. There is no path where a
    wait, a timeout or an abort strands a row in RUNNING — which is exactly what
    a blocking lock wait killed by ``lock_timeout`` inside an already-claimed job
    could have done.
    """

    @pytest.mark.parametrize("racing_estado", ["pending", "running"])
    def test_no_job_is_left_running_on_any_refusal_path(
        self, db, seeded, session_factory, tmp_path, racing_estado: str
    ):
        _insert_dem_job(db, racing_estado)
        job_id = _crossing_job(db)

        cruces_camino_service.run_crossing_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            scratch_root=str(tmp_path / "scratch"),
        )

        stranded = db.execute(
            text(
                "SELECT count(*) FROM geo_jobs "
                "WHERE tipo::text = 'road_flow_crossings' AND estado::text = 'running'"
            )
        ).scalar_one()
        assert stranded == 0

    def test_the_estado_enum_gained_no_skipped_value(self, db):
        labels = (
            db.execute(
                text(
                    "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'estado_geo_job'"
                )
            )
            .scalars()
            .all()
        )
        assert set(labels) == {"pending", "running", "completed", "failed"}


class TestTheProducerHalfDoesNotExist:
    def test_tasks_dem_support_is_unmodified(self):
        """Law 8, and the reason the protocol beats the lock it replaced.

        The snapshot-copy protocol needs no cooperation from the writer, so there
        is no producer-side edit and therefore no "the guard is worthless if only
        one side takes it" failure mode.
        """
        diff = subprocess.run(
            [
                "git",
                "diff",
                "--stat",
                "origin/feat/flujo-caminos-s1-red-vial...HEAD",
                "--",
                "gee-backend/app/domains/geo/tasks_dem_support.py",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[3],
        )
        assert diff.returncode == 0, diff.stderr
        assert diff.stdout.strip() == "", (
            f"tasks_dem_support.py must be untouched by this change:\n{diff.stdout}"
        )
