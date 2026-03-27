"""
Celery tasks for the DEM terrain analysis pipeline.

All tasks run on the "geo" queue and are executed by the
GDAL-based geo-worker container.

Each task:
  1. Updates GeoJob status to "running"
  2. Calls the pure processing function
  3. Registers the result as a GeoLayer
  4. Updates GeoJob status to "completed" (or "failed" on error)
  5. Returns the output path
"""

from __future__ import annotations

import traceback
import uuid
from pathlib import Path

import structlog

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
import app.auth.models  # noqa: F401 — register User table for FK resolution
from app.domains.geo.models import (
    EstadoGeoJob,
    FormatoGeoLayer,
    FuenteGeoLayer,
    TipoGeoJob,
    TipoGeoLayer,
)
from app.domains.geo.repository import GeoRepository


def _get_processing():
    """Lazy import of processing module — only available in geo-worker container."""
    from app.domains.geo import processing

    return processing

logger = structlog.get_logger(__name__)

repo = GeoRepository()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_db():
    """Create a short-lived DB session for task work."""
    return SessionLocal()


def _update_job(job_id: str, **kwargs):
    """Update a GeoJob inside its own session+commit cycle."""
    db = _get_db()
    try:
        repo.update_job_status(db, uuid.UUID(job_id), **kwargs)
        db.commit()
    finally:
        db.close()


def _register_layer(
    *,
    nombre: str,
    tipo: str,
    archivo_path: str,
    area_id: str | None = None,
    formato: str = FormatoGeoLayer.GEOTIFF,
) -> str:
    """Register a GeoLayer record and return its id as string."""
    db = _get_db()
    try:
        layer = repo.create_layer(
            db,
            nombre=nombre,
            tipo=tipo,
            fuente=FuenteGeoLayer.DEM_PIPELINE,
            archivo_path=archivo_path,
            formato=formato,
            area_id=area_id,
        )
        db.commit()
        return str(layer.id)
    finally:
        db.close()


def _run_step(
    job_id: str,
    step_name: str,
    fn,
    args: tuple,
    kwargs: dict | None = None,
) -> str:
    """Run a processing function, handling status and errors.

    Returns:
        The output path returned by *fn*.
    """
    kwargs = kwargs or {}
    logger.info(f"{step_name}.start", job_id=job_id)
    try:
        result = fn(*args, **kwargs)
        logger.info(f"{step_name}.done", job_id=job_id, output=result)
        return result
    except Exception:
        logger.error(f"{step_name}.failed", job_id=job_id, exc_info=True)
        raise


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


@celery_app.task(queue="geo", name="geo.process_dem_pipeline")
def process_dem_pipeline(
    area_id: str,
    dem_path: str,
    bbox: list[float] | None = None,
    job_id: str | None = None,
) -> dict:
    """Orchestrate the full DEM analysis pipeline for a given area.

    Steps (10 % each):
      1. clip_dem (if bbox provided)
      2. fill_sinks
      3. compute_slope
      4. compute_aspect
      5. compute_flow_direction
      6. compute_flow_accumulation
      7. compute_twi
      8. compute_hand
      9. extract_drainage_network
     10. classify_terrain

    Args:
        area_id: Identifier for the processing area.
        dem_path: Path to the input DEM GeoTIFF.
        bbox: Optional [minx, miny, maxx, maxy] to clip the DEM.
        job_id: Optional pre-created GeoJob id.

    Returns:
        dict with output paths and summary statistics.
    """
    # -- Create / reuse job ------------------------------------------------
    if job_id is None:
        db = _get_db()
        try:
            job = repo.create_job(
                db,
                tipo=TipoGeoJob.DEM_PIPELINE,
                parametros={"area_id": area_id, "dem_path": dem_path, "bbox": bbox},
            )
            db.commit()
            job_id = str(job.id)
        finally:
            db.close()

    _update_job(job_id, estado=EstadoGeoJob.RUNNING, progreso=0)

    output_dir = Path(dem_path).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, str] = {}
    step = 0
    total_steps = 10

    def _progress():
        nonlocal step
        step += 1
        pct = int((step / total_steps) * 100)
        _update_job(job_id, progreso=pct)

    try:
        # 1. Clip ----------------------------------------------------------
        if bbox:
            clipped = str(output_dir / "dem_clipped.tif")
            _run_step(job_id, "clip_dem", _get_processing().clip_dem, (dem_path, tuple(bbox), clipped))
            working_dem = clipped
            outputs["clipped_dem"] = clipped
        else:
            working_dem = dem_path
        _progress()

        # 2. Fill sinks ----------------------------------------------------
        filled = str(output_dir / "dem_filled.tif")
        _run_step(job_id, "fill_sinks", _get_processing().fill_sinks, (working_dem, filled))
        outputs["filled_dem"] = filled
        _progress()

        # 3. Slope ---------------------------------------------------------
        slope = str(output_dir / "slope.tif")
        _run_step(job_id, "compute_slope", _get_processing().compute_slope, (filled, slope))
        outputs["slope"] = slope
        _register_layer(
            nombre=f"slope_{area_id}",
            tipo=TipoGeoLayer.SLOPE,
            archivo_path=slope,
            area_id=area_id,
        )
        _progress()

        # 4. Aspect --------------------------------------------------------
        aspect = str(output_dir / "aspect.tif")
        _run_step(job_id, "compute_aspect", _get_processing().compute_aspect, (filled, aspect))
        outputs["aspect"] = aspect
        _register_layer(
            nombre=f"aspect_{area_id}",
            tipo=TipoGeoLayer.ASPECT,
            archivo_path=aspect,
            area_id=area_id,
        )
        _progress()

        # 5. Flow direction ------------------------------------------------
        flow_dir = str(output_dir / "flow_dir.tif")
        _run_step(
            job_id, "compute_flow_direction", _get_processing().compute_flow_direction, (filled, flow_dir)
        )
        outputs["flow_dir"] = flow_dir
        _register_layer(
            nombre=f"flow_dir_{area_id}",
            tipo=TipoGeoLayer.FLOW_DIR,
            archivo_path=flow_dir,
            area_id=area_id,
        )
        _progress()

        # 6. Flow accumulation ---------------------------------------------
        flow_acc = str(output_dir / "flow_acc.tif")
        _run_step(
            job_id,
            "compute_flow_accumulation",
            _get_processing().compute_flow_accumulation,
            (flow_dir, flow_acc),
        )
        outputs["flow_acc"] = flow_acc
        _register_layer(
            nombre=f"flow_acc_{area_id}",
            tipo=TipoGeoLayer.FLOW_ACC,
            archivo_path=flow_acc,
            area_id=area_id,
        )
        _progress()

        # 7. TWI -----------------------------------------------------------
        twi = str(output_dir / "twi.tif")
        _run_step(job_id, "compute_twi", _get_processing().compute_twi, (slope, flow_acc, twi))
        outputs["twi"] = twi
        _register_layer(
            nombre=f"twi_{area_id}",
            tipo=TipoGeoLayer.TWI,
            archivo_path=twi,
            area_id=area_id,
        )
        _progress()

        # 8. HAND ----------------------------------------------------------
        hand = str(output_dir / "hand.tif")
        _run_step(
            job_id, "compute_hand", _get_processing().compute_hand, (filled, flow_dir, flow_acc, hand)
        )
        outputs["hand"] = hand
        _register_layer(
            nombre=f"hand_{area_id}",
            tipo=TipoGeoLayer.HAND,
            archivo_path=hand,
            area_id=area_id,
        )
        _progress()

        # 9. Drainage network (vector) ------------------------------------
        drainage = str(output_dir / "drainage.geojson")
        _run_step(
            job_id,
            "extract_drainage_network",
            _get_processing().extract_drainage_network,
            (flow_acc, 1000, drainage),
        )
        outputs["drainage"] = drainage
        _register_layer(
            nombre=f"drainage_{area_id}",
            tipo=TipoGeoLayer.DRAINAGE,
            archivo_path=drainage,
            area_id=area_id,
            formato=FormatoGeoLayer.GEOJSON,
        )
        _progress()

        # 10. Terrain classification ---------------------------------------
        terrain_class = str(output_dir / "terrain_class.tif")
        _run_step(
            job_id,
            "classify_terrain",
            _get_processing().classify_terrain,
            (slope, twi, flow_acc, terrain_class),
        )
        outputs["terrain_class"] = terrain_class
        _register_layer(
            nombre=f"terrain_class_{area_id}",
            tipo=TipoGeoLayer.TERRAIN_CLASS,
            archivo_path=terrain_class,
            area_id=area_id,
        )
        _progress()

        # -- Done ----------------------------------------------------------
        _update_job(
            job_id,
            estado=EstadoGeoJob.COMPLETED,
            progreso=100,
            resultado=outputs,
        )
        logger.info("dem_pipeline.done", area_id=area_id, job_id=job_id)
        return {"job_id": job_id, "status": "completed", "outputs": outputs}

    except Exception as exc:
        _update_job(
            job_id,
            estado=EstadoGeoJob.FAILED,
            error=traceback.format_exc(),
        )
        logger.error("dem_pipeline.failed", area_id=area_id, job_id=job_id, exc_info=True)
        raise


# ── Individual analysis tasks ────────────────────
# These wrap the pure processing functions for one-off execution via Celery.


@celery_app.task(queue="geo", name="geo.compute_slope")
def compute_slope(dem_path: str, output_path: str, job_id: str | None = None) -> dict:
    """Compute slope (in degrees) from a DEM raster."""
    if job_id:
        _update_job(job_id, estado=EstadoGeoJob.RUNNING)
    try:
        result = _get_processing().compute_slope(dem_path, output_path)
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.COMPLETED, progreso=100)
        return {"output_path": result}
    except Exception:
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.FAILED, error=traceback.format_exc())
        raise


@celery_app.task(queue="geo", name="geo.compute_aspect")
def compute_aspect(dem_path: str, output_path: str, job_id: str | None = None) -> dict:
    """Compute aspect (orientation in degrees, 0-360) from a DEM raster."""
    if job_id:
        _update_job(job_id, estado=EstadoGeoJob.RUNNING)
    try:
        result = _get_processing().compute_aspect(dem_path, output_path)
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.COMPLETED, progreso=100)
        return {"output_path": result}
    except Exception:
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.FAILED, error=traceback.format_exc())
        raise


@celery_app.task(queue="geo", name="geo.compute_flow_direction")
def compute_flow_direction(
    dem_path: str, output_path: str, job_id: str | None = None
) -> dict:
    """Compute flow direction (D8 algorithm) from a DEM raster."""
    if job_id:
        _update_job(job_id, estado=EstadoGeoJob.RUNNING)
    try:
        result = _get_processing().compute_flow_direction(dem_path, output_path)
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.COMPLETED, progreso=100)
        return {"output_path": result}
    except Exception:
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.FAILED, error=traceback.format_exc())
        raise


@celery_app.task(queue="geo", name="geo.compute_flow_accumulation")
def compute_flow_accumulation(
    dem_path: str, output_path: str, job_id: str | None = None
) -> dict:
    """Compute flow accumulation from a DEM raster."""
    if job_id:
        _update_job(job_id, estado=EstadoGeoJob.RUNNING)
    try:
        result = _get_processing().compute_flow_accumulation(dem_path, output_path)
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.COMPLETED, progreso=100)
        return {"output_path": result}
    except Exception:
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.FAILED, error=traceback.format_exc())
        raise


@celery_app.task(queue="geo", name="geo.compute_twi")
def compute_twi(
    slope_path: str,
    flow_acc_path: str,
    output_path: str,
    job_id: str | None = None,
) -> dict:
    """Compute Topographic Wetness Index (TWI)."""
    if job_id:
        _update_job(job_id, estado=EstadoGeoJob.RUNNING)
    try:
        result = _get_processing().compute_twi(slope_path, flow_acc_path, output_path)
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.COMPLETED, progreso=100)
        return {"output_path": result}
    except Exception:
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.FAILED, error=traceback.format_exc())
        raise


@celery_app.task(queue="geo", name="geo.compute_hand")
def compute_hand(
    dem_path: str,
    flow_dir_path: str,
    flow_acc_path: str,
    output_path: str,
    job_id: str | None = None,
) -> dict:
    """Compute Height Above Nearest Drainage (HAND)."""
    if job_id:
        _update_job(job_id, estado=EstadoGeoJob.RUNNING)
    try:
        result = _get_processing().compute_hand(dem_path, flow_dir_path, flow_acc_path, output_path)
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.COMPLETED, progreso=100)
        return {"output_path": result}
    except Exception:
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.FAILED, error=traceback.format_exc())
        raise


@celery_app.task(queue="geo", name="geo.extract_drainage_network")
def extract_drainage_network(
    flow_acc_path: str,
    threshold: int,
    output_path: str,
    job_id: str | None = None,
) -> dict:
    """Extract a drainage network from flow accumulation using a threshold."""
    if job_id:
        _update_job(job_id, estado=EstadoGeoJob.RUNNING)
    try:
        result = _get_processing().extract_drainage_network(flow_acc_path, threshold, output_path)
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.COMPLETED, progreso=100)
        return {"output_path": result}
    except Exception:
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.FAILED, error=traceback.format_exc())
        raise


@celery_app.task(queue="geo", name="geo.classify_terrain")
def classify_terrain(
    slope_path: str,
    twi_path: str,
    flow_acc_path: str,
    output_path: str,
    job_id: str | None = None,
) -> dict:
    """Classify terrain into categories based on slope, TWI, and flow accumulation."""
    if job_id:
        _update_job(job_id, estado=EstadoGeoJob.RUNNING)
    try:
        result = _get_processing().classify_terrain(slope_path, twi_path, flow_acc_path, output_path)
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.COMPLETED, progreso=100)
        return {"output_path": result}
    except Exception:
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.FAILED, error=traceback.format_exc())
        raise


# ── DEM Full Pipeline Tasks ────────────────────


def _get_gee_service():
    """Lazy import of gee_service — only available when GEE is configured."""
    from app.domains.geo.gee_service import GEEService, _ensure_initialized

    _ensure_initialized()
    return GEEService()


@celery_app.task(queue="geo", name="geo.download_dem_from_gee")
def download_dem_from_gee_task(
    area_id: str,
    job_id: str | None = None,
) -> dict:
    """Download Copernicus GLO-30 DEM from GEE for the zona geometry.

    Registers the result as a GeoLayer with tipo=DEM_RAW.
    Returns the DEM file path for chaining.
    """
    if job_id:
        _update_job(job_id, estado=EstadoGeoJob.RUNNING, progreso=5)

    try:
        # Get zona geometry from GEE assets
        gee_svc = _get_gee_service()
        zona_geojson = gee_svc.zona.geometry().getInfo()

        output_dir = Path(f"/data/geo/{area_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        dem_path = str(output_dir / "dem_raw.tif")

        _run_step(
            job_id or "no-job",
            "download_dem_from_gee",
            _get_processing().download_dem_from_gee,
            (zona_geojson, dem_path),
        )

        # Register as GeoLayer
        _register_layer(
            nombre=f"dem_raw_{area_id}",
            tipo=TipoGeoLayer.DEM_RAW,
            archivo_path=dem_path,
            area_id=area_id,
        )

        if job_id:
            _update_job(job_id, progreso=15)

        logger.info("download_dem_from_gee.done", area_id=area_id, dem_path=dem_path)
        return {"dem_path": dem_path, "area_id": area_id}

    except Exception:
        if job_id:
            _update_job(
                job_id,
                estado=EstadoGeoJob.FAILED,
                error=traceback.format_exc(),
            )
        raise


@celery_app.task(queue="geo", name="geo.delineate_basins")
def delineate_basins_task(
    area_id: str,
    flow_dir_path: str,
    min_area_ha: float = 10.0,
    job_id: str | None = None,
    store_zonas: bool = True,
) -> dict:
    """Delineate watershed basins from flow direction raster.

    Vectorizes basins, filters micro-basins, registers GeoLayer(BASINS),
    and optionally creates ZonaOperativa records.
    """
    if job_id:
        _update_job(job_id, estado=EstadoGeoJob.RUNNING)

    try:
        output_dir = Path(flow_dir_path).parent
        basins_raster = str(output_dir / "basins.tif")
        basins_geojson = str(output_dir / "basins.geojson")

        result_path = _run_step(
            job_id or "no-job",
            "delineate_basins",
            _get_processing().delineate_basins,
            (flow_dir_path, basins_raster, basins_geojson),
            {"min_area_ha": min_area_ha},
        )

        # Register as GeoLayer
        _register_layer(
            nombre=f"basins_{area_id}",
            tipo=TipoGeoLayer.BASINS,
            archivo_path=basins_geojson,
            area_id=area_id,
            formato=FormatoGeoLayer.GEOJSON,
        )

        # Optionally create ZonaOperativa records
        zonas_created = 0
        if store_zonas:
            import json as _json

            from app.domains.geo.intelligence.repository import IntelligenceRepository

            intel_repo = IntelligenceRepository()

            with open(basins_geojson) as f:
                basins_data = _json.load(f)

            db = _get_db()
            try:
                for feature in basins_data.get("features", []):
                    props = feature.get("properties", {})
                    basin_id = props.get("basin_id", 0)
                    area_ha = props.get("area_ha", 0.0)
                    geom_json = _json.dumps(feature["geometry"])

                    intel_repo.create_zona(
                        db,
                        nombre=f"basin_{area_id}_{basin_id}",
                        geometria=f"SRID=4326;{geom_json}",
                        cuenca="auto_delineated",
                        superficie_ha=area_ha,
                    )
                    zonas_created += 1

                db.commit()
            finally:
                db.close()

        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.COMPLETED, progreso=100)

        logger.info(
            "delineate_basins.done",
            area_id=area_id,
            basins_geojson=basins_geojson,
            zonas_created=zonas_created,
        )
        return {
            "basins_geojson": basins_geojson,
            "basins_raster": basins_raster,
            "zonas_created": zonas_created,
        }

    except Exception:
        if job_id:
            _update_job(
                job_id,
                estado=EstadoGeoJob.FAILED,
                error=traceback.format_exc(),
            )
        raise


@celery_app.task(queue="geo", name="geo.run_full_dem_pipeline")
def run_full_dem_pipeline(
    area_id: str,
    min_basin_area_ha: float = 10.0,
    job_id: str | None = None,
) -> dict:
    """Full DEM pipeline: download from GEE → terrain analysis → basin delineation.

    Orchestrates three stages sequentially:
        1. Download DEM from GEE (Copernicus GLO-30)
        2. Run existing 10-step terrain pipeline (fill, slope, aspect, etc.)
        3. Delineate watershed basins and store as ZonaOperativa

    Args:
        area_id: Identifier for the processing area.
        min_basin_area_ha: Minimum basin area for filtering.
        job_id: Pre-created GeoJob id.

    Returns:
        dict with all output paths and summary.
    """
    # Create job if not provided
    if job_id is None:
        db = _get_db()
        try:
            job = repo.create_job(
                db,
                tipo=TipoGeoJob.DEM_FULL_PIPELINE,
                parametros={
                    "area_id": area_id,
                    "min_basin_area_ha": min_basin_area_ha,
                },
            )
            db.commit()
            job_id = str(job.id)
        finally:
            db.close()

    _update_job(job_id, estado=EstadoGeoJob.RUNNING, progreso=0)

    try:
        # ── Stage 1: Download DEM from GEE ──
        logger.info("full_dem_pipeline.stage1_download", area_id=area_id)
        _update_job(job_id, progreso=5)

        gee_svc = _get_gee_service()
        zona_geojson = gee_svc.zona.geometry().getInfo()

        output_dir = Path(f"/data/geo/{area_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        dem_path = str(output_dir / "dem_raw.tif")

        _get_processing().download_dem_from_gee(zona_geojson, dem_path)

        _register_layer(
            nombre=f"dem_raw_{area_id}",
            tipo=TipoGeoLayer.DEM_RAW,
            archivo_path=dem_path,
            area_id=area_id,
        )
        _update_job(job_id, progreso=15)

        # ── Stage 2: Run existing terrain pipeline ──
        logger.info("full_dem_pipeline.stage2_terrain", area_id=area_id)

        # Call the pipeline function directly (not via Celery .delay)
        pipeline_result = process_dem_pipeline(
            area_id=area_id,
            dem_path=dem_path,
            bbox=None,
            job_id=None,  # Don't create a sub-job; we manage status ourselves
        )

        _update_job(job_id, progreso=85)

        # ── Stage 3: Basin delineation ──
        logger.info("full_dem_pipeline.stage3_basins", area_id=area_id)

        flow_dir_path = pipeline_result["outputs"].get("flow_dir")
        if not flow_dir_path:
            raise RuntimeError("Terrain pipeline did not produce flow_dir output")

        basins_raster = str(output_dir / "output" / area_id / "basins.tif")
        basins_geojson = str(output_dir / "output" / area_id / "basins.geojson")

        _get_processing().delineate_basins(
            flow_dir_path,
            basins_raster,
            basins_geojson,
            min_area_ha=min_basin_area_ha,
        )

        _register_layer(
            nombre=f"basins_{area_id}",
            tipo=TipoGeoLayer.BASINS,
            archivo_path=basins_geojson,
            area_id=area_id,
            formato=FormatoGeoLayer.GEOJSON,
        )

        # Store basins as ZonaOperativa records
        import json as _json

        from app.domains.geo.intelligence.repository import IntelligenceRepository

        intel_repo = IntelligenceRepository()
        zonas_created = 0

        with open(basins_geojson) as f:
            basins_data = _json.load(f)

        db = _get_db()
        try:
            for feature in basins_data.get("features", []):
                props = feature.get("properties", {})
                basin_id = props.get("basin_id", 0)
                area_ha = props.get("area_ha", 0.0)
                geom_json = _json.dumps(feature["geometry"])

                intel_repo.create_zona(
                    db,
                    nombre=f"basin_{area_id}_{basin_id}",
                    geometria=f"SRID=4326;{geom_json}",
                    cuenca="auto_delineated",
                    superficie_ha=area_ha,
                )
                zonas_created += 1
            db.commit()
        finally:
            db.close()

        # ── Done ──
        all_outputs = {
            "dem_raw": dem_path,
            "basins_raster": basins_raster,
            "basins_geojson": basins_geojson,
            "zonas_created": zonas_created,
            **pipeline_result.get("outputs", {}),
        }

        _update_job(
            job_id,
            estado=EstadoGeoJob.COMPLETED,
            progreso=100,
            resultado=all_outputs,
        )

        logger.info(
            "full_dem_pipeline.done",
            area_id=area_id,
            job_id=job_id,
            zonas_created=zonas_created,
        )
        return {"job_id": job_id, "status": "completed", "outputs": all_outputs}

    except Exception:
        _update_job(
            job_id,
            estado=EstadoGeoJob.FAILED,
            error=traceback.format_exc(),
        )
        logger.error("full_dem_pipeline.failed", area_id=area_id, exc_info=True)
        raise
