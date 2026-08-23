"""The candidate-classification run: fencing, a private copy, and one write.

Same shape as the crossing run (Fase A), for the same reasons:

1. **Pre-check before claiming.** If a DEM pipeline owns this area, refuse while
   the job is still PENDING, so no task ever owns a RUNNING row it is about to
   abandon.
2. **Claim by compare-and-set**, the shared fencing primitive, so two workers
   cannot both own one job.
3. **Copy the raster, then revalidate.** The pipeline archives directories,
   rewrites rasters in place and deletes files after committing, so a reader that
   depends on the writer's timing is a reader that will eventually read a
   half-deleted file. Working from a private copy removes the dependency instead
   of trying to interleave with it. The re-check mark comes from ``SELECT now()``
   on the DATABASE, because the predicate compares against ``geo_jobs.updated_at``
   — a column the database server stamps — and taking it from the worker's clock
   would make the window depend on cross-host clock skew.
4. **Compute from the copy**, and
5. **write in ONE transaction**, keyed ``(tramo_ref, geo_job_id)`` so a re-run
   adds a new generation of candidates instead of overwriting the previous one.

Nothing here is a measurement: every row it writes is labelled a candidate, in
its own table, and the parameters that produced it travel with the run.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import structlog
from sqlalchemy import text

from app.domains.geo.intelligence.cruces_camino_support import (
    DemJobEnCurso,
    dem_job_ocupado,
    verificar_dem_libre,
)
from app.domains.geo.relevamiento.clasificador import (
    DemFilledNoDisponible,
    clasificar_tramo,
    leer_parametros,
    resolver_dem_filled,
)
from app.domains.geo.relevamiento.repository import RelevamientoRepository

logger = structlog.get_logger(__name__)

SCRATCH_ROOT = os.environ.get("CRUCES_SCRATCH_ROOT", tempfile.gettempdir())


def _raster_bbox_4326(path: str) -> tuple[float, float, float, float]:
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(path) as src:
        return transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)


def _raster_crs(path: str):
    import rasterio

    with rasterio.open(path) as src:
        return src.crs


def _copiar_a_scratch(dem_path: str, *, scratch_root: str) -> tuple[str, str]:
    """A private copy, so a pipeline mid-run cannot change what we are reading."""
    scratch = tempfile.mkdtemp(prefix="clasif_tramo_", dir=scratch_root)
    destino = os.path.join(scratch, os.path.basename(dem_path))
    shutil.copy2(dem_path, destino)
    return scratch, destino


def _fail(db, jobs, job_id: str, *, expected: str, motivo: str, area_id: str) -> None:
    from app.domains.geo.models import EstadoGeoJob

    jobs.update_job_status_if_current(
        db,
        uuid.UUID(job_id),
        expected_estado=expected,
        estado=EstadoGeoJob.FAILED.value,
        error=motivo,
    )
    db.commit()
    logger.warning("clasificador_tramo.rechazado", area_id=area_id, motivo=motivo)


def run_classification_task(
    *,
    area_id: str,
    job_id: Optional[str],
    session_factory: Callable[[], Any],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    scratch_root: Optional[str] = None,
) -> dict[str, Any]:
    """Classify this area's active segments against the real filled DEM."""
    import geopandas as gpd
    from shapely import wkt as shapely_wkt

    from app.domains.geo.intelligence.repository import IntelligenceRepository
    from app.domains.geo.models import EstadoGeoJob, TipoGeoJob
    from app.domains.geo.repository import GeoRepository

    intel = IntelligenceRepository()
    jobs = GeoRepository()
    repo = RelevamientoRepository()
    scratch_root = scratch_root or SCRATCH_ROOT

    db = session_factory()
    try:
        # From the DB clock: the guard predicate compares against a column the
        # database stamps, so the mark must come from the same clock.
        pre_check_at = db.execute(text("SELECT now()")).scalar_one()
        if job_id is None:
            job = jobs.create_job(
                db,
                tipo=TipoGeoJob.TRAMO_CLASSIFICATION.value,
                parametros={"area_id": area_id},
            )
            db.commit()
            job_id = str(job.id)

        if dem_job_ocupado(db, area_id):
            _fail(
                db,
                jobs,
                job_id,
                expected=EstadoGeoJob.PENDING.value,
                motivo="dem_job_running_pre_check",
                area_id=area_id,
            )
            return {"job_id": job_id, "status": "skipped", "motivo": "dem_job_running_pre_check"}

        claimed = jobs.update_job_status_if_current(
            db,
            uuid.UUID(job_id),
            expected_estado=EstadoGeoJob.PENDING.value,
            estado=EstadoGeoJob.RUNNING.value,
            progreso=0,
        )
        db.commit()
        if not claimed:
            logger.info("clasificador_tramo.not_claimed", area_id=area_id, job_id=job_id)
            return {"job_id": job_id, "status": "skipped", "motivo": "fence_lost"}
    finally:
        db.close()

    scratch = None
    try:
        db = session_factory()
        try:
            parametros = leer_parametros(db)
            dem_path = resolver_dem_filled(intel.get_dem_resultados(db, area_id))
        finally:
            db.close()

        scratch, dem_copia = _copiar_a_scratch(dem_path, scratch_root=scratch_root)

        db = session_factory()
        try:
            verificar_dem_libre(db, area_id, desde=pre_check_at)
        finally:
            db.close()

        minx, miny, maxx, maxy = _raster_bbox_4326(dem_copia)
        db = session_factory()
        try:
            filas = intel.get_red_vial_en_bbox(db, minx=minx, miny=miny, maxx=maxx, maxy=maxy)
        finally:
            db.close()

        candidatas: list[dict[str, Any]] = []
        sin_cobertura: list[str] = []
        if filas:
            # Everything metric happens in the RASTER's CRS: a 15 m step and a
            # 60 m offset applied to degrees would be off by five orders of
            # magnitude, which is the ``crs=4326`` trap this repo already has a
            # scar from.
            gdf = gpd.GeoDataFrame(
                {
                    "id": [f["id"] for f in filas],
                    "geometry": [shapely_wkt.loads(f["wkt"]) for f in filas],
                },
                geometry="geometry",
                crs=4326,
            ).to_crs(_raster_crs(dem_copia))

            for tramo_ref, geometria in zip(gdf["id"], gdf.geometry):
                resultado = clasificar_tramo(geometria, dem_copia, **parametros)
                if resultado is None:
                    sin_cobertura.append(str(tramo_ref))
                    continue
                candidatas.append({"tramo_ref": str(tramo_ref), **resultado})

        calculada_en = now()
        db = session_factory()
        try:
            repo.insertar_candidatas(
                db,
                filas=candidatas,
                geo_job_id=uuid.UUID(job_id),
                calculada_en=calculada_en,
            )
            resultado_job = {
                "area_id": area_id,
                "candidatas": len(candidatas),
                "sin_cobertura": sin_cobertura,
                "parametros": {**parametros, "dem": os.path.basename(dem_path)},
            }
            completed = jobs.update_job_status_if_current(
                db,
                uuid.UUID(job_id),
                expected_estado=EstadoGeoJob.RUNNING.value,
                estado=EstadoGeoJob.COMPLETED.value,
                progreso=100,
                resultado=resultado_job,
            )
            if not completed:
                db.rollback()
                logger.warning("clasificador_tramo.fence_lost_at_write", area_id=area_id)
                return {"job_id": job_id, "status": "skipped", "motivo": "fence_lost"}
            db.commit()
        finally:
            db.close()

        logger.info("clasificador_tramo.done", area_id=area_id, candidatas=len(candidatas))
        return {"job_id": job_id, "status": "completed", **resultado_job}

    except DemFilledNoDisponible as exc:
        motivo = f"dem_filled_no_disponible ({exc.detalle})"
        db = session_factory()
        try:
            _fail(
                db,
                jobs,
                job_id,
                expected=EstadoGeoJob.RUNNING.value,
                motivo=motivo,
                area_id=area_id,
            )
        finally:
            db.close()
        return {"job_id": job_id, "status": "failed", "motivo": motivo}
    except DemJobEnCurso as exc:
        db = session_factory()
        try:
            _fail(
                db,
                jobs,
                job_id,
                expected=EstadoGeoJob.RUNNING.value,
                motivo=exc.motivo,
                area_id=area_id,
            )
        finally:
            db.close()
        return {"job_id": job_id, "status": "skipped", "motivo": exc.motivo}
    except Exception as exc:  # pragma: no cover — the no-zombie guarantee
        db = session_factory()
        try:
            _fail(
                db,
                jobs,
                job_id,
                expected=EstadoGeoJob.RUNNING.value,
                motivo=f"error_inesperado: {exc}",
                area_id=area_id,
            )
        finally:
            db.close()
        raise
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)


__all__ = ["run_classification_task"]
