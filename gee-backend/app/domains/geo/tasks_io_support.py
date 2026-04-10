from __future__ import annotations

import traceback
from pathlib import Path


def download_dem_from_gee_task_impl(*, area_id: str, job_id: str | None, update_job, get_gee_service, run_step, get_processing, register_layer, tipo_geo_layer, estado_geo_job, logger) -> dict:
    if job_id:
        update_job(job_id, estado=estado_geo_job.RUNNING, progreso=5)
    try:
        gee_svc = get_gee_service()
        zona_geojson = gee_svc.zona.geometry().getInfo()
        output_dir = Path(f"/data/geo/{area_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        dem_path = str(output_dir / "dem_raw.tif")
        run_step(job_id or "no-job", "download_dem_from_gee", get_processing().download_dem_from_gee, (zona_geojson, dem_path))
        register_layer(nombre=f"dem_raw_{area_id}", tipo=tipo_geo_layer.DEM_RAW, archivo_path=dem_path, area_id=area_id)
        if job_id:
            update_job(job_id, progreso=15)
        logger.info("download_dem_from_gee.done", area_id=area_id, dem_path=dem_path)
        return {"dem_path": dem_path, "area_id": area_id}
    except Exception:
        if job_id:
            update_job(job_id, estado=estado_geo_job.FAILED, error=traceback.format_exc())
        raise


def delineate_basins_task_impl(*, area_id: str, flow_dir_path: str, min_area_ha: float, job_id: str | None, store_zonas: bool, update_job, run_step, get_processing, register_layer, tipo_geo_layer, formato_geo_layer, estado_geo_job, get_db, logger) -> dict:
    if job_id:
        update_job(job_id, estado=estado_geo_job.RUNNING)
    try:
        output_dir = Path(flow_dir_path).parent
        basins_raster = str(output_dir / "basins.tif")
        basins_geojson = str(output_dir / "basins.geojson")
        run_step(job_id or "no-job", "delineate_basins", get_processing().delineate_basins, (flow_dir_path, basins_raster, basins_geojson), {"min_area_ha": min_area_ha})
        register_layer(nombre=f"basins_{area_id}", tipo=tipo_geo_layer.BASINS, archivo_path=basins_geojson, area_id=area_id, formato=formato_geo_layer.GEOJSON)
        zonas_created = 0
        if store_zonas:
            import json as _json
            from app.domains.geo.intelligence.repository import IntelligenceRepository

            intel_repo = IntelligenceRepository()
            with open(basins_geojson) as f:
                basins_data = _json.load(f)
            db = get_db()
            try:
                for feature in basins_data.get("features", []):
                    props = feature.get("properties", {})
                    intel_repo.create_zona(
                        db,
                        nombre=f"basin_{area_id}_{props.get('basin_id', 0)}",
                        geometria=f"SRID=4326;{_json.dumps(feature['geometry'])}",
                        cuenca="auto_delineated",
                        superficie_ha=props.get("area_ha", 0.0),
                    )
                    zonas_created += 1
                db.commit()
            finally:
                db.close()
        if job_id:
            update_job(job_id, estado=estado_geo_job.COMPLETED, progreso=100)
        logger.info("delineate_basins.done", area_id=area_id, basins_geojson=basins_geojson, zonas_created=zonas_created)
        return {"basins_geojson": basins_geojson, "basins_raster": basins_raster, "zonas_created": zonas_created}
    except Exception:
        if job_id:
            update_job(job_id, estado=estado_geo_job.FAILED, error=traceback.format_exc())
        raise
