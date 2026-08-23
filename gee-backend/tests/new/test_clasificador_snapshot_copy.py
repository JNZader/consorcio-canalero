"""Real-PG: the properties ``run_classification_task`` exists for.

The classifier reads ``dem_filled.tif`` — a file the DEM pipeline **owns,
archives, rewrites in place and deletes after committing**. So it takes exactly
the protocol Fase A takes, and this file asserts the same properties against the
classifier rather than trusting that "same shape as the crossing run" stayed
true: a copied protocol with one step quietly missing looks identical in review
and fails identically in production.

The classifier-specific one is the last class. A crossing run reading a torn
raster mostly fails to parse; a classifier reading a **truncated** one samples
fewer cells and returns a median — a number that reads exactly like a
measurement. Corroboration is what turns that into a named refusal.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.crs import CRS
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.geo.relevamiento import clasificador_service

AREA = "zona_clasif_snapshot"
TRAMO = "clasif-snap-1"
CELL = 30.0
UTM = CRS.from_epsg(32720)

#: A footprint that really contains the seeded road, so the spatial pre-filter
#: admits it. Around -62.8 / -33.0 in UTM 20S — the same corner Fase A's
#: snapshot suite uses, for the same reason.
ORIGIN_X = 331_000.0
ORIGIN_Y = 6_348_000.0
TRANSFORM = Affine(CELL, 0.0, ORIGIN_X, 0.0, -CELL, ORIGIN_Y)

#: The road row sits 2.5 m above everything else, and the flank offset (60 m =
#: two cells) lands on rows 8 and 12. ``median(road) - median(flank) = 2.5``,
#: comfortably past the 1.0 m threshold, so the expected verdict is not a
#: coin-flip against the seeded parameters.
BASE_M = 100.0
ALTURA_CAMINO_M = 102.5


def _write_dem(path: Path) -> str:
    shape = (21, 21)
    data = np.full(shape, BASE_M)
    data[10, :] = ALTURA_CAMINO_M
    with rasterio.open(
        str(path),
        "w",
        driver="GTiff",
        height=shape[0],
        width=shape[1],
        count=1,
        dtype="float64",
        crs=UTM,
        transform=TRANSFORM,
        nodata=-9999.0,
    ) as dst:
        dst.write(data.astype("float64"), 1)
    return str(path)


def _road_wkt() -> str:
    """A due-east road along the raised row, in 4326."""
    import geopandas as gpd
    from shapely.geometry import LineString

    def centre(row, col):
        return TRANSFORM * (col + 0.5, row + 0.5)

    line = LineString([centre(10, 1), centre(10, 19)])
    gdf = gpd.GeoDataFrame({"geometry": [line]}, geometry="geometry", crs=UTM).to_crs(4326)
    return gdf.iloc[0].geometry.wkt


@pytest.fixture
def dem_filled(tmp_path) -> str:
    """The REAL filled DEM, under the only name the classifier accepts."""
    return _write_dem(tmp_path / "dem_filled.tif")


@pytest.fixture
def session_factory(test_engine):
    """Real committing sessions — commit visibility is the whole subject.

    The rolled-back ``db`` fixture cannot express "another process inserted a DEM
    job between two of my transactions".
    """
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=test_engine)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def seeded(db, dem_filled):
    """One road inside the DEM, and the DEM run whose ``resultado`` names it.

    The DEM job is COMPLETED and inserted **before** any run starts, so its
    ``updated_at`` is older than every pre-check mark: it is the record of a
    finished pipeline, not an intervention.
    """
    db.execute(
        text(
            "INSERT INTO red_vial (id, source_id, geom, geom_hash) "
            "VALUES (:id, :id, ST_GeomFromText(:wkt, 4326), 'h')"
        ),
        {"id": TRAMO, "wkt": _road_wkt()},
    )
    db.execute(
        text(
            "INSERT INTO geo_jobs (id, tipo, estado, progreso, parametros, resultado, "
            " created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'dem_pipeline', 'completed', 100, "
            " CAST(:params AS json), CAST(:resultado AS json), now(), now())"
        ),
        {
            "params": f'{{"area_id": "{AREA}"}}',
            "resultado": f'{{"filled_dem": "{dem_filled}"}}',
        },
    )
    db.commit()
    yield
    db.execute(text("DELETE FROM tramo_clasificacion_candidata WHERE tramo_ref = :t"), {"t": TRAMO})
    db.execute(text("DELETE FROM geo_jobs"))
    db.execute(text("DELETE FROM red_vial WHERE id = :t"), {"t": TRAMO})
    db.commit()


def _insert_dem_job(db, estado: str, *, area_id: str = AREA) -> uuid.UUID:
    job_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO geo_jobs (id, tipo, estado, progreso, parametros, "
            " created_at, updated_at) "
            "VALUES (:id, 'dem_pipeline', :estado, 0, CAST(:params AS json), now(), now())"
        ),
        {"id": str(job_id), "estado": estado, "params": f'{{"area_id": "{area_id}"}}'},
    )
    db.commit()
    return job_id


def _classification_job(db) -> str:
    job_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO geo_jobs (id, tipo, estado, progreso, parametros, "
            " created_at, updated_at) "
            "VALUES (:id, 'tramo_classification', 'pending', 0, "
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


def _candidata_count(db: Session) -> int:
    return int(
        db.execute(
            text("SELECT count(*) FROM tramo_clasificacion_candidata WHERE tramo_ref = :t"),
            {"t": TRAMO},
        ).scalar_one()
    )


def _scratch_root(tmp_path, nombre: str) -> str:
    root = tmp_path / nombre
    root.mkdir()
    return str(root)


class TestPreCheckRefusesEarly:
    """A DEM job PENDING **or** RUNNING makes the run refuse before it claims.

    ``pending`` matters: the API creates the row as PENDING and the worker claims
    it after broker latency, so a PENDING DEM row means destruction is imminent.
    """

    @pytest.mark.parametrize("estado", ["pending", "running"])
    def test_refuses_leaving_the_job_failed_and_nothing_written(
        self, db, seeded, session_factory, tmp_path, estado: str
    ):
        _insert_dem_job(db, estado)
        job_id = _classification_job(db)

        result = clasificador_service.run_classification_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            scratch_root=_scratch_root(tmp_path, "scratch"),
        )

        assert result["status"] == "skipped"
        assert result["motivo"] == "dem_job_running_pre_check"

        estado_final, error = _job_estado(db, job_id)
        assert estado_final == "failed", (
            "there is no SKIPPED estado: a refusal has to land on a real one, and "
            "PENDING → FAILED is the transition that keeps the row honest"
        )
        assert "dem_job_running_pre_check" in error
        assert _candidata_count(db) == 0, "a refused run writes NOTHING"

    def test_a_dem_job_for_another_area_does_not_block(self, db, seeded, session_factory, tmp_path):
        _insert_dem_job(db, "running", area_id="otra_zona")
        job_id = _classification_job(db)

        result = clasificador_service.run_classification_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            scratch_root=_scratch_root(tmp_path, "scratch"),
        )

        assert result["status"] == "completed"
        assert result["candidatas"] == 1
        assert _candidata_count(db) == 1
        clasificacion = db.execute(
            text(
                "SELECT clasificacion_candidata::text FROM tramo_clasificacion_candidata "
                "WHERE tramo_ref = :t"
            ),
            {"t": TRAMO},
        ).scalar_one()
        assert clasificacion == "terraplen", (
            "a road 2.5 m above its flanks is an embankment; anything else means "
            "the sampling ran somewhere other than the raster's own CRS"
        )


class TestPostCopyRecheck:
    """The case the pre-check ALONE cannot catch.

    A pipeline can reach RUNNING one microsecond after the pre-check returns
    empty. The re-check is keyed on ``updated_at >= pre_check_at``, and the mark
    comes from ``SELECT now()`` on the DATABASE because the column it compares
    against is stamped by the database server.
    """

    def test_a_dem_job_appearing_during_the_copy_aborts_the_run(
        self, db, seeded, session_factory, tmp_path, monkeypatch
    ):
        job_id = _classification_job(db)
        inserted: list[uuid.UUID] = []
        original = clasificador_service._copiar_a_scratch

        def racing_copy(dem_path, *, scratch_root):
            result = original(dem_path, scratch_root=scratch_root)
            racer = session_factory()
            try:
                inserted.append(_insert_dem_job(racer, "running"))
            finally:
                racer.close()
            return result

        monkeypatch.setattr(clasificador_service, "_copiar_a_scratch", racing_copy)

        result = clasificador_service.run_classification_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            scratch_root=_scratch_root(tmp_path, "scratch"),
        )

        assert inserted, "the racing DEM job must actually have been inserted"
        assert result["status"] == "skipped"
        assert result["motivo"] == "dem_job_started_during_copy"

        estado_final, error = _job_estado(db, job_id)
        assert estado_final == "failed"
        assert "dem_job_started_during_copy" in error
        assert _candidata_count(db) == 0

    def test_the_mark_is_the_database_clock_not_the_workers(
        self, db, seeded, session_factory, tmp_path, monkeypatch
    ):
        """A worker clock hours ahead must not blind the re-check.

        ``now`` is injectable and is used for ``calculada_en``; if the pre-check
        mark were ever taken from it, a skewed worker would produce a mark in the
        future and every racing DEM job would slip under it. The mark comes from
        ``SELECT now()``, so this run still aborts.
        """
        from datetime import datetime, timedelta, timezone

        job_id = _classification_job(db)
        original = clasificador_service._copiar_a_scratch

        def racing_copy(dem_path, *, scratch_root):
            result = original(dem_path, scratch_root=scratch_root)
            racer = session_factory()
            try:
                _insert_dem_job(racer, "running")
            finally:
                racer.close()
            return result

        monkeypatch.setattr(clasificador_service, "_copiar_a_scratch", racing_copy)

        result = clasificador_service.run_classification_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            now=lambda: datetime.now(timezone.utc) + timedelta(hours=6),
            scratch_root=_scratch_root(tmp_path, "scratch"),
        )

        assert result["motivo"] == "dem_job_started_during_copy", (
            "taken from the worker's clock, a six-hour skew would have hidden the "
            "racing job and the run would have classified against torn rasters"
        )


class TestTheRealFilledDemOrNothing:
    """Law 2: no surface substitutes for ``dem_filled.tif``."""

    def test_an_unresolvable_dem_fails_the_job_and_writes_nothing(
        self, db, seeded, session_factory, tmp_path
    ):
        db.execute(text("UPDATE geo_jobs SET resultado = NULL WHERE tipo::text = 'dem_pipeline'"))
        db.commit()
        job_id = _classification_job(db)

        result = clasificador_service.run_classification_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            scratch_root=_scratch_root(tmp_path, "scratch"),
        )

        assert result["status"] == "failed"
        assert result["motivo"].startswith("dem_filled_no_disponible")

        estado_final, error = _job_estado(db, job_id)
        assert estado_final == "failed", "a named refusal is not a row left RUNNING"
        assert "dem_filled_no_disponible" in error
        assert _candidata_count(db) == 0, (
            "no candidate is better than a candidate computed against a surface nobody chose"
        )


class TestScratchIsAlwaysRemoved:
    def test_the_scratch_directory_is_gone_after_a_successful_run(
        self, db, seeded, session_factory, tmp_path
    ):
        root = Path(_scratch_root(tmp_path, "scratch-ok"))
        job_id = _classification_job(db)

        result = clasificador_service.run_classification_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            scratch_root=str(root),
        )

        assert result["status"] == "completed"
        assert list(root.iterdir()) == [], "the scratch dir must be removed in a finally"

    def test_the_scratch_directory_is_gone_after_an_abort(
        self, db, seeded, session_factory, tmp_path, monkeypatch
    ):
        root = Path(_scratch_root(tmp_path, "scratch-abort"))
        job_id = _classification_job(db)
        original = clasificador_service._copiar_a_scratch

        def racing_copy(dem_path, *, scratch_root):
            result = original(dem_path, scratch_root=scratch_root)
            racer = session_factory()
            try:
                _insert_dem_job(racer, "running")
            finally:
                racer.close()
            return result

        monkeypatch.setattr(clasificador_service, "_copiar_a_scratch", racing_copy)

        clasificador_service.run_classification_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            scratch_root=str(root),
        )

        assert list(root.iterdir()) == [], (
            "even an aborted run leaks at most one area's worth of temporary rasters"
        )


class TestScratchIsNotLeakedOnCopyFailure:
    """A failure INSIDE the copy helper removes its own directory.

    The caller only learns the scratch path from the helper's RETURN value, so an
    exception between ``mkdtemp`` and ``return`` leaks the directory forever with
    no owner — nothing in the run knows it exists, and the ``finally`` that would
    have cleaned it up is holding ``scratch = None``. The DEM pipeline deleting
    the source file mid-copy is exactly how this happens in production.
    """

    def test_a_failed_copy_leaves_no_directory_behind(self, tmp_path):
        root = Path(_scratch_root(tmp_path, "scratch-root"))

        with pytest.raises(FileNotFoundError):
            clasificador_service._copiar_a_scratch(
                str(tmp_path / "se_borro_dem_filled.tif"), scratch_root=str(root)
            )

        assert list(root.iterdir()) == [], (
            "an orphaned scratch directory is never collected: nothing else knows its name"
        )


class TestNoZombieRunning:
    """``EstadoGeoJob`` has PENDING/RUNNING/COMPLETED/FAILED and nothing else.

    Every refusal path is therefore a compare-and-set to FAILED, and no exception
    may strand a claimed row in RUNNING.
    """

    @pytest.mark.parametrize("racing_estado", ["pending", "running"])
    def test_no_job_is_left_running_on_any_refusal_path(
        self, db, seeded, session_factory, tmp_path, racing_estado: str
    ):
        _insert_dem_job(db, racing_estado)
        job_id = _classification_job(db)

        clasificador_service.run_classification_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            scratch_root=_scratch_root(tmp_path, "scratch"),
        )

        stranded = db.execute(
            text(
                "SELECT count(*) FROM geo_jobs "
                "WHERE tipo::text = 'tramo_classification' AND estado::text = 'running'"
            )
        ).scalar_one()
        assert stranded == 0

    def test_an_unexpected_failure_after_the_claim_is_not_a_zombie(
        self, db, seeded, session_factory, tmp_path, monkeypatch
    ):
        """The generic handler, exercised rather than asserted in a comment.

        Post-claim and pre-compute is the window a bare ``finally: db.close()``
        would leave stranded in RUNNING for ever.
        """
        job_id = _classification_job(db)

        def boom(_db):
            raise RuntimeError("settings unreachable")

        monkeypatch.setattr(clasificador_service, "leer_parametros", boom)

        with pytest.raises(RuntimeError):
            clasificador_service.run_classification_task(
                area_id=AREA,
                job_id=job_id,
                session_factory=session_factory,
                scratch_root=_scratch_root(tmp_path, "scratch"),
            )

        estado_final, error = _job_estado(db, job_id)
        assert estado_final == "failed", "no post-claim exception may strand the row in RUNNING"
        assert "error_inesperado" in error
        assert _candidata_count(db) == 0


class TestACorruptCopyIsNamedNotAveraged:
    """The failure mode a median hides — and why corroboration is not optional.

    A truncated copy does not necessarily raise: it samples fewer cells and
    returns a perfectly well-formed ``confianza_m``. That number would be stored
    as a candidate, labelled with the parameters that "produced" it, and nothing
    downstream could tell it apart from a real one. The refusal names what was
    OBSERVED — an empty, size-unstable or zero-dimension copy — and never claims
    a cause it did not check.
    """

    def test_a_truncated_copy_refuses_instead_of_storing_a_median(
        self, db, seeded, session_factory, tmp_path, monkeypatch
    ):
        job_id = _classification_job(db)
        original = clasificador_service._copiar_a_scratch

        def truncating_copy(dem_path, *, scratch_root):
            scratch, destino = original(dem_path, scratch_root=scratch_root)
            # Exactly what a pipeline rewriting the file in place looks like if
            # the copy catches it between truncate and write.
            Path(destino).write_bytes(b"")
            return scratch, destino

        monkeypatch.setattr(clasificador_service, "_copiar_a_scratch", truncating_copy)

        result = clasificador_service.run_classification_task(
            area_id=AREA,
            job_id=job_id,
            session_factory=session_factory,
            scratch_root=_scratch_root(tmp_path, "scratch"),
        )

        assert result["status"] == "skipped"
        assert result["motivo"] == "copia_corrupta_post_check"

        estado_final, error = _job_estado(db, job_id)
        assert estado_final == "failed"
        assert "copia_corrupta_post_check" in error
        assert "DEM job" not in (error or ""), (
            "the observation is an unreadable copy; blaming a DEM job would be a "
            "cause this check never looked for"
        )
        assert _candidata_count(db) == 0, (
            "the whole point: no median from a truncated raster reaches the table"
        )
