from __future__ import annotations

import traceback
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def process_dem_pipeline_impl(
    *,
    area_id: str,
    dem_path: str,
    bbox: list[float] | None,
    job_id: str | None,
    create_geo_job,
    update_job,
    run_step,
    get_processing,
    register_raster_layer,
    register_layer,
    tipo_geo_job,
    tipo_geo_layer,
    estado_geo_job,
    formato_geo_layer,
) -> dict:
    if job_id is None:
        job_id = create_geo_job(
            tipo=tipo_geo_job.DEM_PIPELINE,
            parametros={"area_id": area_id, "dem_path": dem_path, "bbox": bbox},
        )

    update_job(job_id, estado=estado_geo_job.RUNNING, progreso=0)
    output_dir = Path(dem_path).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, str] = {}
    step = 0
    total_steps = 12
    processing = get_processing()

    def _progress():
        nonlocal step
        step += 1
        update_job(job_id, progreso=int((step / total_steps) * 100))

    try:
        if bbox:
            clipped = str(output_dir / "dem_clipped.tif")
            run_step(
                job_id,
                "clip_dem",
                processing.clip_dem,
                (dem_path, tuple(bbox), clipped),
            )
            working_dem = clipped
            outputs["clipped_dem"] = clipped
        else:
            working_dem = dem_path
        _progress()

        filled = str(output_dir / "dem_filled.tif")
        run_step(job_id, "fill_sinks", processing.fill_sinks, (working_dem, filled))
        outputs["filled_dem"] = filled
        _progress()

        slope = str(output_dir / "slope.tif")
        run_step(job_id, "compute_slope", processing.compute_slope, (filled, slope))
        outputs["slope"] = slope
        register_raster_layer(
            nombre=f"slope_{area_id}",
            tipo=tipo_geo_layer.SLOPE,
            archivo_path=slope,
            area_id=area_id,
        )
        _progress()

        aspect = str(output_dir / "aspect.tif")
        run_step(job_id, "compute_aspect", processing.compute_aspect, (filled, aspect))
        outputs["aspect"] = aspect
        register_raster_layer(
            nombre=f"aspect_{area_id}",
            tipo=tipo_geo_layer.ASPECT,
            archivo_path=aspect,
            area_id=area_id,
        )
        _progress()

        flow_dir = str(output_dir / "flow_dir.tif")
        run_step(
            job_id,
            "compute_flow_direction",
            processing.compute_flow_direction,
            (filled, flow_dir),
        )
        outputs["flow_dir"] = flow_dir
        register_raster_layer(
            nombre=f"flow_dir_{area_id}",
            tipo=tipo_geo_layer.FLOW_DIR,
            archivo_path=flow_dir,
            area_id=area_id,
        )
        _progress()

        flow_acc = str(output_dir / "flow_acc.tif")
        run_step(
            job_id,
            "compute_flow_accumulation",
            processing.compute_flow_accumulation,
            (filled, flow_acc),
        )
        outputs["flow_acc"] = flow_acc
        register_raster_layer(
            nombre=f"flow_acc_{area_id}",
            tipo=tipo_geo_layer.FLOW_ACC,
            archivo_path=flow_acc,
            area_id=area_id,
        )
        _progress()

        twi = str(output_dir / "twi.tif")
        run_step(job_id, "compute_twi", processing.compute_twi, (slope, flow_acc, twi))
        outputs["twi"] = twi
        register_raster_layer(
            nombre=f"twi_{area_id}",
            tipo=tipo_geo_layer.TWI,
            archivo_path=twi,
            area_id=area_id,
        )
        _progress()

        hand = str(output_dir / "hand.tif")
        run_step(
            job_id,
            "compute_hand",
            processing.compute_hand,
            (filled, flow_dir, flow_acc, hand),
        )
        outputs["hand"] = hand
        register_raster_layer(
            nombre=f"hand_{area_id}",
            tipo=tipo_geo_layer.HAND,
            archivo_path=hand,
            area_id=area_id,
        )
        _progress()

        drainage = str(output_dir / "drainage.geojson")
        run_step(
            job_id,
            "extract_drainage_network",
            processing.extract_drainage_network,
            (flow_acc, 1000, drainage),
        )
        outputs["drainage"] = drainage
        register_layer(
            nombre=f"drainage_{area_id}",
            tipo=tipo_geo_layer.DRAINAGE,
            archivo_path=drainage,
            area_id=area_id,
            formato=formato_geo_layer.GEOJSON,
        )
        _progress()

        profile_curvature = run_step(
            job_id,
            "compute_profile_curvature",
            processing.compute_profile_curvature,
            (filled, str(output_dir)),
        )
        outputs["profile_curvature"] = profile_curvature
        register_raster_layer(
            nombre=f"profile_curvature_{area_id}",
            tipo=tipo_geo_layer.PROFILE_CURVATURE,
            archivo_path=profile_curvature,
            area_id=area_id,
        )
        _progress()

        tpi = run_step(
            job_id, "compute_tpi", processing.compute_tpi, (filled, str(output_dir))
        )
        outputs["tpi"] = tpi
        register_raster_layer(
            nombre=f"tpi_{area_id}",
            tipo=tipo_geo_layer.TPI,
            archivo_path=tpi,
            area_id=area_id,
        )
        _progress()

        terrain_class = run_step(
            job_id,
            "classify_terrain",
            processing.classify_terrain,
            (filled, str(output_dir)),
            {
                "hand_path": hand,
                "tpi_path": tpi,
                "curvature_path": profile_curvature,
                "flow_acc_path": flow_acc,
                "twi_path": twi,
            },
        )
        outputs["terrain_class"] = terrain_class
        register_raster_layer(
            nombre=f"terrain_class_{area_id}",
            tipo=tipo_geo_layer.TERRAIN_CLASS,
            archivo_path=terrain_class,
            area_id=area_id,
        )
        _progress()

        update_job(
            job_id, estado=estado_geo_job.COMPLETED, progreso=100, resultado=outputs
        )
        logger.info("dem_pipeline.done", area_id=area_id, job_id=job_id)
        return {"job_id": job_id, "status": "completed", "outputs": outputs}
    except Exception:
        update_job(job_id, estado=estado_geo_job.FAILED, error=traceback.format_exc())
        logger.error(
            "dem_pipeline.failed", area_id=area_id, job_id=job_id, exc_info=True
        )
        raise


def run_full_dem_pipeline_impl(
    *,
    area_id: str,
    min_basin_area_ha: float,
    job_id: str | None,
    create_geo_job,
    update_job,
    cleanup_full_dem_state,
    prepare_full_pipeline_dem,
    process_dem_pipeline,
    generate_auto_basins,
    tipo_geo_job,
    estado_geo_job,
) -> dict:
    if job_id is None:
        job_id = create_geo_job(
            tipo=tipo_geo_job.DEM_FULL_PIPELINE,
            parametros={"area_id": area_id, "min_basin_area_ha": min_basin_area_ha},
        )

    update_job(job_id, estado=estado_geo_job.RUNNING, progreso=0)
    cleanup_full_dem_state(area_id)

    try:
        logger.info("full_dem_pipeline.stage1_download", area_id=area_id)
        update_job(job_id, progreso=5)
        output_dir = Path(f"/data/geo/{area_id}")
        dem_path, prepared_dem_path = prepare_full_pipeline_dem(area_id)
        update_job(job_id, progreso=15)

        logger.info("full_dem_pipeline.stage1b_prepare", area_id=area_id)
        update_job(job_id, progreso=20)

        logger.info("full_dem_pipeline.stage2_terrain", area_id=area_id)
        pipeline_result = process_dem_pipeline(
            area_id=area_id, dem_path=prepared_dem_path, bbox=None, job_id=None
        )
        update_job(job_id, progreso=85)

        logger.info("full_dem_pipeline.stage3_basins", area_id=area_id)
        zonas_created, basins_raster, basins_geojson = generate_auto_basins(
            area_id=area_id,
            pipeline_result=pipeline_result,
            output_dir=output_dir,
            min_basin_area_ha=min_basin_area_ha,
        )
        all_outputs = {
            "dem_raw": dem_path,
            "basins_raster": basins_raster,
            "basins_geojson": basins_geojson,
            "zonas_created": zonas_created,
            **pipeline_result.get("outputs", {}),
        }
        update_job(
            job_id, estado=estado_geo_job.COMPLETED, progreso=100, resultado=all_outputs
        )
        logger.info(
            "full_dem_pipeline.done",
            area_id=area_id,
            job_id=job_id,
            zonas_created=zonas_created,
        )
        return {"job_id": job_id, "status": "completed", "outputs": all_outputs}
    except Exception:
        update_job(job_id, estado=estado_geo_job.FAILED, error=traceback.format_exc())
        logger.error("full_dem_pipeline.failed", area_id=area_id, exc_info=True)
        raise


def cleanup_full_dem_state_impl(
    *, area_id: str, get_db, geo_repo, intelligence_repo_cls
) -> None:
    logger.info("full_dem_pipeline.cleanup_start", area_id=area_id)
    db = get_db()
    try:
        intel_repo = intelligence_repo_cls()
        layers_deleted = geo_repo.delete_layers_by_area_id(db, area_id)
        zonas_deleted = intel_repo.delete_zonas_by_cuenca(db, "auto_delineated")
        db.commit()
        logger.info(
            "full_dem_pipeline.cleanup_done",
            area_id=area_id,
            layers_deleted=layers_deleted,
            zonas_deleted=zonas_deleted,
        )
    finally:
        db.close()

    output_dir = Path(f"/data/geo/{area_id}/output")
    if not output_dir.exists():
        return

    import shutil

    for child in output_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    logger.info("full_dem_pipeline.output_dir_cleaned", path=str(output_dir))


def prepare_full_pipeline_dem_impl(
    *,
    area_id: str,
    get_gee_service,
    get_processing,
    register_raster_layer,
    tipo_geo_layer,
    geometry_override: dict | None = None,
) -> tuple[str, str]:
    gee_svc = get_gee_service()
    if geometry_override is not None:
        zona_geojson = geometry_override
    else:
        zona_geojson = gee_svc.zona.geometry().getInfo()

    output_dir = Path(f"/data/geo/{area_id}")
    output_dir.mkdir(parents=True, exist_ok=True)

    dem_raw = str(output_dir / "dem_raw.tif")
    dem_nodata = str(output_dir / "dem_nodata.tif")
    dem_utm = str(output_dir / "dem_utm.tif")
    dem_clipped = str(output_dir / "dem_clipped.tif")
    dem_filtered = str(output_dir / "dem_filtered.tif")

    processing = get_processing()
    processing.download_dem_from_gee(zona_geojson, dem_raw)
    processing.ensure_nodata(dem_raw, dem_nodata)
    processing.reproject_to_utm(dem_nodata, dem_utm)
    processing.clip_to_geometry(dem_utm, zona_geojson, dem_clipped)
    processing.remove_off_terrain_objects(dem_clipped, dem_filtered)

    register_raster_layer(
        nombre=f"dem_raw_{area_id}",
        tipo=tipo_geo_layer.DEM_RAW,
        archivo_path=dem_filtered,
        area_id=area_id,
    )
    return dem_raw, dem_filtered


def count_manual_basins_impl(*, get_db) -> int:
    db = get_db()
    try:
        from sqlalchemy import text

        return db.execute(
            text(
                "SELECT COUNT(*) FROM zonas_operativas WHERE cuenca != 'auto_delineated'"
            )
        ).scalar()
    finally:
        db.close()


def store_auto_delineated_basins_impl(
    *, area_id: str, basins_geojson: str, get_db, intelligence_repo_cls
) -> int:
    import json as _json
    from shapely.geometry import shape as _shape

    intel_repo = intelligence_repo_cls()
    with open(basins_geojson) as f:
        basins_data = _json.load(f)

    zonas_created = 0
    db = get_db()
    try:
        for feature in basins_data.get("features", []):
            props = feature.get("properties", {})
            basin_id = props.get("basin_id", 0)
            area_ha = props.get("area_ha", 0.0)
            geom_wkt = _shape(feature["geometry"]).wkt
            intel_repo.create_zona(
                db,
                nombre=f"basin_{area_id}_{basin_id}",
                geometria=f"SRID=4326;{geom_wkt}",
                cuenca="auto_delineated",
                superficie_ha=area_ha,
            )
            zonas_created += 1
        db.commit()
        return zonas_created
    finally:
        db.close()


def generate_auto_basins_impl(
    *,
    area_id: str,
    pipeline_result: dict,
    output_dir: Path,
    min_basin_area_ha: float,
    count_manual_basins,
    get_processing,
    register_layer,
    store_auto_delineated_basins,
    tipo_geo_layer,
    formato_geo_layer,
) -> tuple[int, str, str]:
    manual_count = count_manual_basins()
    if manual_count > 0:
        logger.info(
            "full_dem_pipeline.skip_auto_basins",
            area_id=area_id,
            manual_basins=manual_count,
        )
        return 0, "", ""

    flow_dir_path = pipeline_result["outputs"].get("flow_dir")
    if not flow_dir_path:
        raise RuntimeError("Terrain pipeline did not produce flow_dir output")

    basins_raster = str(output_dir / "output" / area_id / "basins.tif")
    basins_geojson = str(output_dir / "output" / area_id / "basins.geojson")

    get_processing().delineate_basins(
        flow_dir_path, basins_raster, basins_geojson, min_area_ha=min_basin_area_ha
    )
    register_layer(
        nombre=f"basins_{area_id}",
        tipo=tipo_geo_layer.BASINS,
        archivo_path=basins_geojson,
        area_id=area_id,
        formato=formato_geo_layer.GEOJSON,
    )

    zonas_created = store_auto_delineated_basins(
        area_id=area_id, basins_geojson=basins_geojson
    )
    return zonas_created, basins_raster, basins_geojson
