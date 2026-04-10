from __future__ import annotations

import traceback
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def composite_analysis_task_impl(
    *,
    area_id: str,
    weights_flood: dict[str, float] | None,
    weights_drainage: dict[str, float] | None,
    job_id: str | None,
    create_geo_job,
    update_job,
    resolve_composite_area_dir,
    validate_composite_prerequisites,
    run_step,
    get_composites,
    register_layer,
    convert_to_cog_safe,
    merge_drainage_networks_if_available,
    store_composite_zonal_stats,
    intel_repo,
    tipo_geo_job,
    tipo_geo_layer,
    estado_geo_job,
) -> dict:
    composites = get_composites()
    if job_id is None:
        job_id = create_geo_job(
            tipo=tipo_geo_job.COMPOSITE_ANALYSIS,
            parametros={
                "area_id": area_id,
                "weights_flood": weights_flood,
                "weights_drainage": weights_drainage,
            },
        )

    update_job(job_id, estado=estado_geo_job.RUNNING, progreso=0)

    try:
        area_dir = resolve_composite_area_dir(area_id)
        validate_composite_prerequisites(area_dir)
        update_job(job_id, progreso=10)
        outputs: dict[str, str] = {}

        flood_output = str(Path(area_dir) / "flood_risk.tif")
        run_step(job_id, "compute_flood_risk", composites.compute_flood_risk, (area_dir, flood_output), {"weights": weights_flood})
        flood_cog = convert_to_cog_safe(flood_output)
        flood_weights = weights_flood or composites.DEFAULT_FLOOD_WEIGHTS
        register_layer(
            nombre=f"flood_risk_{area_id}",
            tipo=tipo_geo_layer.FLOOD_RISK,
            archivo_path=flood_output,
            area_id=area_id,
            metadata_extra={"weights": flood_weights, "cog_path": flood_cog}
            if flood_cog
            else {"weights": flood_weights, "cog_error": "conversion failed"},
        )
        outputs["flood_risk"] = flood_output
        update_job(job_id, progreso=30)

        merge_drainage_networks_if_available(
            job_id=job_id, area_id=area_id, area_dir=area_dir, composites=composites, outputs=outputs
        )
        update_job(job_id, progreso=40)

        drainage_output = str(Path(area_dir) / "drainage_need.tif")
        run_step(
            job_id,
            "compute_drainage_need",
            composites.compute_drainage_need,
            (area_dir, drainage_output),
            {"weights": weights_drainage},
        )
        drainage_cog = convert_to_cog_safe(drainage_output)
        drainage_weights = weights_drainage or composites.DEFAULT_DRAINAGE_WEIGHTS
        register_layer(
            nombre=f"drainage_need_{area_id}",
            tipo=tipo_geo_layer.DRAINAGE_NEED,
            archivo_path=drainage_output,
            area_id=area_id,
            metadata_extra={"weights": drainage_weights, "cog_path": drainage_cog}
            if drainage_cog
            else {"weights": drainage_weights, "cog_error": "conversion failed"},
        )
        outputs["drainage_need"] = drainage_output
        update_job(job_id, progreso=60)

        zonal_stats_count = store_composite_zonal_stats(
            area_id=area_id,
            flood_output=flood_output,
            drainage_output=drainage_output,
            composites=composites,
            intel_repo=intel_repo,
            flood_weights=flood_weights,
            drainage_weights=drainage_weights,
        )
        outputs["zonal_stats_count"] = str(zonal_stats_count)
        update_job(job_id, progreso=90)
        update_job(job_id, estado=estado_geo_job.COMPLETED, progreso=100, resultado=outputs)
        logger.info("composite_analysis.done", area_id=area_id, job_id=job_id)
        return {"job_id": job_id, "status": "completed", "outputs": outputs}
    except Exception:
        update_job(job_id, estado=estado_geo_job.FAILED, error=traceback.format_exc())
        logger.error("composite_analysis.failed", area_id=area_id, job_id=job_id, exc_info=True)
        raise


def resolve_composite_area_dir_impl(*, area_id: str, get_db, geo_repo, tipo_geo_layer) -> str:
    db = get_db()
    try:
        layers, _ = geo_repo.get_layers(db, area_id_filter=area_id, tipo_filter=tipo_geo_layer.HAND, limit=1)
        if not layers:
            raise RuntimeError(f"No HAND layer found for area '{area_id}'. Run the DEM pipeline first.")
        return str(Path(layers[0].archivo_path).parent)
    finally:
        db.close()


def validate_composite_prerequisites_impl(area_dir: str) -> None:
    required_files = ["hand.tif", "twi.tif", "flow_acc.tif", "profile_curvature.tif", "tpi.tif"]
    missing = [f for f in required_files if not (Path(area_dir) / f).exists()]
    has_drainage = (
        (Path(area_dir) / "drainage.tif").exists()
        or (Path(area_dir) / "drainage_combined.geojson").exists()
        or (Path(area_dir) / "drainage.geojson").exists()
    )
    if not has_drainage:
        missing.append("drainage.tif or drainage.geojson")
    if missing:
        raise FileNotFoundError(
            f"Missing prerequisite layers in {area_dir}: {', '.join(missing)}. Run the full DEM pipeline first."
        )


def merge_drainage_networks_if_available_impl(
    *, job_id: str, area_id: str, area_dir: str, composites, outputs: dict[str, str], run_step
) -> None:
    auto_drainage = str(Path(area_dir) / "drainage.geojson")
    combined_drainage = str(Path(area_dir) / "drainage_combined.geojson")
    if not Path(auto_drainage).exists():
        return
    try:
        run_step(
            job_id,
            "merge_drainage_networks",
            composites.merge_drainage_networks,
            (auto_drainage,),
            {"output_path": combined_drainage},
        )
        outputs["drainage_combined"] = combined_drainage
        stale_tif = Path(area_dir) / "drainage.tif"
        if stale_tif.exists():
            stale_tif.unlink()
    except Exception:
        logger.warning("composite_analysis.merge_drainage_failed", area_id=area_id, exc_info=True)


def store_composite_zonal_stats_impl(
    *,
    area_id: str,
    flood_output: str,
    drainage_output: str,
    composites,
    intel_repo,
    flood_weights: dict[str, float],
    drainage_weights: dict[str, float],
    get_db,
    composite_zonal_stats_model,
) -> int:
    from datetime import date as date_mod

    from geoalchemy2.shape import to_shape
    from shapely.geometry import mapping as shapely_mapping
    from sqlalchemy import delete

    db = get_db()
    try:
        zonas, _ = intel_repo.get_zonas(db, page=1, limit=10000)
        if not zonas:
            logger.warning(
                "composite_analysis.no_zonas",
                area_id=area_id,
                msg="No ZonaOperativa records found — skipping zonal stats",
            )
            return 0

        zona_dicts = []
        for zona in zonas:
            try:
                geom_shapely = to_shape(zona.geometria)
                zona_dicts.append({"id": zona.id, "nombre": zona.nombre, "geometry": shapely_mapping(geom_shapely)})
            except Exception:
                logger.warning("composite_analysis.zona_geom_error", zona_id=str(zona.id), exc_info=True)

        today = date_mod.today()
        flood_stats = composites.extract_composite_zonal_stats(flood_output, zona_dicts, "flood_risk")
        for stat in flood_stats:
            stat["weights_used"] = flood_weights
            stat["fecha_calculo"] = today

        drainage_stats = composites.extract_composite_zonal_stats(drainage_output, zona_dicts, "drainage_need")
        for stat in drainage_stats:
            stat["weights_used"] = drainage_weights
            stat["fecha_calculo"] = today

        all_stats = flood_stats + drainage_stats
        if all_stats:
            zona_ids = list({stat["zona_id"] for stat in all_stats if stat.get("zona_id")})
            tipos = list({stat["tipo"] for stat in all_stats if stat.get("tipo")})
            if zona_ids and tipos:
                db.execute(
                    delete(composite_zonal_stats_model).where(
                        composite_zonal_stats_model.zona_id.in_(zona_ids),
                        composite_zonal_stats_model.tipo.in_(tipos),
                    )
                )
                db.flush()
            db.add_all([composite_zonal_stats_model(**stat) for stat in all_stats])
            db.commit()
            logger.info("composite_analysis.zonal_stats_inserted", count=len(all_stats), area_id=area_id)

        return len(all_stats)
    finally:
        db.close()
