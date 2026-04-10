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
from app.domains.geo.tasks_support import (
    cleanup_full_dem_state_impl,
    composite_analysis_task_impl,
    count_manual_basins_impl,
    generate_auto_basins_impl,
    merge_drainage_networks_if_available_impl,
    process_dem_pipeline_impl,
    prepare_full_pipeline_dem_impl,
    resolve_composite_area_dir_impl,
    run_full_dem_pipeline_impl,
    store_auto_delineated_basins_impl,
    store_composite_zonal_stats_impl,
    validate_composite_prerequisites_impl,
)
from app.domains.geo.tasks_io_support import (
    delineate_basins_task_impl,
    download_dem_from_gee_task_impl,
)


def _get_processing():
    from app.domains.geo import processing

    return processing


logger = structlog.get_logger(__name__)
repo = GeoRepository()


def _get_db():
    return SessionLocal()


def _update_job(job_id: str, **kwargs):
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
    metadata_extra: dict | None = None,
) -> str:
    db = _get_db()
    try:
        layer = repo.upsert_layer(
            db,
            nombre=nombre,
            tipo=tipo,
            fuente=FuenteGeoLayer.DEM_PIPELINE,
            archivo_path=archivo_path,
            formato=formato,
            area_id=area_id,
            metadata_extra=metadata_extra,
        )
        db.commit()
        return str(layer.id)
    finally:
        db.close()


def _convert_to_cog_safe(input_path: str) -> str | None:
    try:
        cog_path = _get_processing().convert_to_cog(input_path)
        logger.info("cog_conversion.done", input=input_path, output=cog_path)
        return cog_path
    except Exception:
        logger.warning("cog_conversion.failed", input=input_path, exc_info=True)
        return None


def _run_step(
    job_id: str,
    step_name: str,
    fn,
    args: tuple,
    kwargs: dict | None = None,
) -> str:
    kwargs = kwargs or {}
    logger.info(f"{step_name}.start", job_id=job_id)
    try:
        result = fn(*args, **kwargs)
        logger.info(f"{step_name}.done", job_id=job_id, output=result)
        return result
    except Exception:
        logger.error(f"{step_name}.failed", job_id=job_id, exc_info=True)
        raise


def _build_cog_metadata(cog_path: str | None, extra: dict | None = None) -> dict:
    metadata = dict(extra or {})
    if cog_path:
        metadata["cog_path"] = cog_path
    else:
        metadata["cog_error"] = "conversion failed"
    return metadata


def _register_raster_layer(
    *,
    nombre: str,
    tipo: str,
    archivo_path: str,
    area_id: str,
    metadata_extra: dict | None = None,
) -> str:
    return _register_layer(
        nombre=nombre,
        tipo=tipo,
        archivo_path=archivo_path,
        area_id=area_id,
        metadata_extra=_build_cog_metadata(
            _convert_to_cog_safe(archivo_path), metadata_extra
        ),
    )


def _create_geo_job(*, tipo: str, parametros: dict) -> str:
    db = _get_db()
    try:
        job = repo.create_job(db, tipo=tipo, parametros=parametros)
        db.commit()
        return str(job.id)
    finally:
        db.close()


@celery_app.task(queue="geo", name="geo.process_dem_pipeline")
def process_dem_pipeline(
    area_id: str,
    dem_path: str,
    bbox: list[float] | None = None,
    job_id: str | None = None,
) -> dict:
    return process_dem_pipeline_impl(
        area_id=area_id,
        dem_path=dem_path,
        bbox=bbox,
        job_id=job_id,
        create_geo_job=_create_geo_job,
        update_job=_update_job,
        run_step=_run_step,
        get_processing=_get_processing,
        register_raster_layer=_register_raster_layer,
        register_layer=_register_layer,
        tipo_geo_job=TipoGeoJob,
        tipo_geo_layer=TipoGeoLayer,
        estado_geo_job=EstadoGeoJob,
        formato_geo_layer=FormatoGeoLayer,
    )


def _run_simple_processing_task(
    processing_method: str,
    *args,
    job_id: str | None = None,
    **kwargs,
) -> dict:
    if job_id:
        _update_job(job_id, estado=EstadoGeoJob.RUNNING)
    try:
        result = getattr(_get_processing(), processing_method)(*args, **kwargs)
        if job_id:
            _update_job(job_id, estado=EstadoGeoJob.COMPLETED, progreso=100)
        return {"output_path": result}
    except Exception:
        if job_id:
            _update_job(
                job_id, estado=EstadoGeoJob.FAILED, error=traceback.format_exc()
            )
        raise


@celery_app.task(queue="geo", name="geo.compute_slope")
def compute_slope(dem_path: str, output_path: str, job_id: str | None = None) -> dict:
    return _run_simple_processing_task(
        "compute_slope",
        dem_path,
        output_path,
        job_id=job_id,
    )


@celery_app.task(queue="geo", name="geo.compute_aspect")
def compute_aspect(dem_path: str, output_path: str, job_id: str | None = None) -> dict:
    return _run_simple_processing_task(
        "compute_aspect",
        dem_path,
        output_path,
        job_id=job_id,
    )


@celery_app.task(queue="geo", name="geo.compute_flow_direction")
def compute_flow_direction(
    dem_path: str, output_path: str, job_id: str | None = None
) -> dict:
    return _run_simple_processing_task(
        "compute_flow_direction",
        dem_path,
        output_path,
        job_id=job_id,
    )


@celery_app.task(queue="geo", name="geo.compute_flow_accumulation")
def compute_flow_accumulation(
    dem_path: str, output_path: str, job_id: str | None = None
) -> dict:
    return _run_simple_processing_task(
        "compute_flow_accumulation",
        dem_path,
        output_path,
        job_id=job_id,
    )


@celery_app.task(queue="geo", name="geo.compute_twi")
def compute_twi(
    slope_path: str,
    flow_acc_path: str,
    output_path: str,
    job_id: str | None = None,
) -> dict:
    return _run_simple_processing_task(
        "compute_twi",
        slope_path,
        flow_acc_path,
        output_path,
        job_id=job_id,
    )


@celery_app.task(queue="geo", name="geo.compute_hand")
def compute_hand(
    dem_path: str,
    flow_dir_path: str,
    flow_acc_path: str,
    output_path: str,
    job_id: str | None = None,
) -> dict:
    return _run_simple_processing_task(
        "compute_hand",
        dem_path,
        flow_dir_path,
        flow_acc_path,
        output_path,
        job_id=job_id,
    )


@celery_app.task(queue="geo", name="geo.extract_drainage_network")
def extract_drainage_network(
    flow_acc_path: str,
    threshold: int,
    output_path: str,
    job_id: str | None = None,
) -> dict:
    return _run_simple_processing_task(
        "extract_drainage_network",
        flow_acc_path,
        threshold,
        output_path,
        job_id=job_id,
    )


@celery_app.task(queue="geo", name="geo.classify_terrain")
def classify_terrain(
    filled_dem_path: str,
    output_dir: str,
    hand_path: str | None = None,
    tpi_path: str | None = None,
    curvature_path: str | None = None,
    flow_acc_path: str | None = None,
    twi_path: str | None = None,
    job_id: str | None = None,
) -> dict:
    return _run_simple_processing_task(
        "classify_terrain",
        filled_dem_path,
        output_dir,
        hand_path=hand_path,
        tpi_path=tpi_path,
        curvature_path=curvature_path,
        flow_acc_path=flow_acc_path,
        twi_path=twi_path,
        job_id=job_id,
    )


def _get_gee_service():
    from app.domains.geo.gee_service import GEEService, _ensure_initialized

    _ensure_initialized()
    return GEEService()


@celery_app.task(queue="geo", name="geo.download_dem_from_gee")
def download_dem_from_gee_task(
    area_id: str,
    job_id: str | None = None,
) -> dict:
    return download_dem_from_gee_task_impl(
        area_id=area_id,
        job_id=job_id,
        update_job=_update_job,
        get_gee_service=_get_gee_service,
        run_step=_run_step,
        get_processing=_get_processing,
        register_layer=_register_layer,
        tipo_geo_layer=TipoGeoLayer,
        estado_geo_job=EstadoGeoJob,
        logger=logger,
    )


@celery_app.task(queue="geo", name="geo.delineate_basins")
def delineate_basins_task(
    area_id: str,
    flow_dir_path: str,
    min_area_ha: float = 5000.0,
    job_id: str | None = None,
    store_zonas: bool = True,
) -> dict:
    return delineate_basins_task_impl(
        area_id=area_id,
        flow_dir_path=flow_dir_path,
        min_area_ha=min_area_ha,
        job_id=job_id,
        store_zonas=store_zonas,
        update_job=_update_job,
        run_step=_run_step,
        get_processing=_get_processing,
        register_layer=_register_layer,
        tipo_geo_layer=TipoGeoLayer,
        formato_geo_layer=FormatoGeoLayer,
        estado_geo_job=EstadoGeoJob,
        get_db=_get_db,
        logger=logger,
    )


def _cleanup_full_dem_state(area_id: str) -> None:
    from app.domains.geo.intelligence.repository import IntelligenceRepository

    cleanup_full_dem_state_impl(
        area_id=area_id,
        get_db=_get_db,
        geo_repo=repo,
        intelligence_repo_cls=IntelligenceRepository,
    )


def _prepare_full_pipeline_dem(area_id: str) -> tuple[str, str]:
    return prepare_full_pipeline_dem_impl(
        area_id=area_id,
        get_gee_service=_get_gee_service,
        get_processing=_get_processing,
        register_raster_layer=_register_raster_layer,
        tipo_geo_layer=TipoGeoLayer,
    )


def _count_manual_basins() -> int:
    return count_manual_basins_impl(get_db=_get_db)


def _store_auto_delineated_basins(
    *,
    area_id: str,
    basins_geojson: str,
) -> int:
    from app.domains.geo.intelligence.repository import IntelligenceRepository

    return store_auto_delineated_basins_impl(
        area_id=area_id,
        basins_geojson=basins_geojson,
        get_db=_get_db,
        intelligence_repo_cls=IntelligenceRepository,
    )


def _generate_auto_basins(
    *,
    area_id: str,
    pipeline_result: dict,
    output_dir: Path,
    min_basin_area_ha: float,
) -> tuple[int, str, str]:
    return generate_auto_basins_impl(
        area_id=area_id,
        pipeline_result=pipeline_result,
        output_dir=output_dir,
        min_basin_area_ha=min_basin_area_ha,
        count_manual_basins=_count_manual_basins,
        get_processing=_get_processing,
        register_layer=_register_layer,
        store_auto_delineated_basins=_store_auto_delineated_basins,
        tipo_geo_layer=TipoGeoLayer,
        formato_geo_layer=FormatoGeoLayer,
    )


@celery_app.task(queue="geo", name="geo.run_full_dem_pipeline")
def run_full_dem_pipeline(
    area_id: str,
    min_basin_area_ha: float = 5000.0,
    job_id: str | None = None,
) -> dict:
    return run_full_dem_pipeline_impl(
        area_id=area_id,
        min_basin_area_ha=min_basin_area_ha,
        job_id=job_id,
        create_geo_job=_create_geo_job,
        update_job=_update_job,
        cleanup_full_dem_state=_cleanup_full_dem_state,
        prepare_full_pipeline_dem=_prepare_full_pipeline_dem,
        process_dem_pipeline=process_dem_pipeline,
        generate_auto_basins=_generate_auto_basins,
        tipo_geo_job=TipoGeoJob,
        estado_geo_job=EstadoGeoJob,
    )


def _get_composites():
    from app.domains.geo import composites

    return composites


def _resolve_composite_area_dir(area_id: str) -> str:
    return resolve_composite_area_dir_impl(
        area_id=area_id,
        get_db=_get_db,
        geo_repo=repo,
        tipo_geo_layer=TipoGeoLayer,
    )


def _validate_composite_prerequisites(area_dir: str) -> None:
    validate_composite_prerequisites_impl(area_dir)


def _merge_drainage_networks_if_available(
    job_id: str,
    area_id: str,
    area_dir: str,
    composites,
    outputs: dict[str, str],
) -> None:
    merge_drainage_networks_if_available_impl(
        job_id=job_id,
        area_id=area_id,
        area_dir=area_dir,
        composites=composites,
        outputs=outputs,
        run_step=_run_step,
    )


def _store_composite_zonal_stats(
    *,
    area_id: str,
    flood_output: str,
    drainage_output: str,
    composites,
    intel_repo,
    flood_weights: dict[str, float],
    drainage_weights: dict[str, float],
) -> int:
    from app.domains.geo.intelligence.models import CompositeZonalStats

    return store_composite_zonal_stats_impl(
        area_id=area_id,
        flood_output=flood_output,
        drainage_output=drainage_output,
        composites=composites,
        intel_repo=intel_repo,
        flood_weights=flood_weights,
        drainage_weights=drainage_weights,
        get_db=_get_db,
        composite_zonal_stats_model=CompositeZonalStats,
    )


@celery_app.task(queue="geo", name="geo.composite_analysis")
def composite_analysis_task(
    area_id: str,
    weights_flood: dict[str, float] | None = None,
    weights_drainage: dict[str, float] | None = None,
    job_id: str | None = None,
) -> dict:
    from app.domains.geo.intelligence.repository import IntelligenceRepository

    intel_repo = IntelligenceRepository()
    return composite_analysis_task_impl(
        area_id=area_id,
        weights_flood=weights_flood,
        weights_drainage=weights_drainage,
        job_id=job_id,
        create_geo_job=_create_geo_job,
        update_job=_update_job,
        resolve_composite_area_dir=_resolve_composite_area_dir,
        validate_composite_prerequisites=_validate_composite_prerequisites,
        run_step=_run_step,
        get_composites=_get_composites,
        register_layer=_register_layer,
        convert_to_cog_safe=_convert_to_cog_safe,
        merge_drainage_networks_if_available=_merge_drainage_networks_if_available,
        store_composite_zonal_stats=_store_composite_zonal_stats,
        intel_repo=intel_repo,
        tipo_geo_job=TipoGeoJob,
        tipo_geo_layer=TipoGeoLayer,
        estado_geo_job=EstadoGeoJob,
    )


@celery_app.task(queue="geo", name="geo.rainfall_daily_sync")
def rainfall_daily_sync() -> dict:
    from datetime import date as date_type, timedelta as td

    from app.domains.geo.rainfall_service import backfill_rainfall

    db = _get_db()
    try:
        yesterday = date_type.today() - td(days=1)
        result = backfill_rainfall(db, start_date=yesterday, end_date=yesterday)
        logger.info(
            "rainfall_daily_sync.done",
            date=yesterday.isoformat(),
            records=result["total_records"],
        )
        return result
    finally:
        db.close()
