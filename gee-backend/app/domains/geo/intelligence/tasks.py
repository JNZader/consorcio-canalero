"""
Celery tasks for long-running intelligence calculations.

All tasks run on the "geo" queue.
"""

from __future__ import annotations

import traceback
import uuid

import structlog

from app.core.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _get_deps():
    """Lazy import to avoid loading geopandas at Celery startup."""
    from app.db.session import SessionLocal
    from app.domains.geo.intelligence.repository import IntelligenceRepository
    from app.domains.geo.intelligence import service as intel_service
    from app.domains.geo.models import EstadoGeoJob, TipoGeoLayer
    from app.domains.geo.repository import GeoRepository

    return {
        "SessionLocal": SessionLocal,
        "intel_repo": IntelligenceRepository(),
        "intel_service": intel_service,
        "EstadoGeoJob": EstadoGeoJob,
        "TipoGeoLayer": TipoGeoLayer,
        "geo_repo": GeoRepository(),
    }


def _get_db():
    """Create a short-lived DB session for task work."""
    deps = _get_deps()
    return deps["SessionLocal"]()


# ---------------------------------------------------------------------------
# Batch HCI Calculation
# ---------------------------------------------------------------------------


@celery_app.task(queue="geo", name="geo.intelligence.calculate_hci_all")
def task_calculate_hci_all_zones(
    pendiente_media: float = 0.5,
    acumulacion_media: float = 0.5,
    twi_medio: float = 0.5,
    proximidad_canal_m: float = 500.0,
    historial_inundacion: float = 0.3,
) -> dict:
    deps = _get_deps()
    db = _get_db()
    try:
        zonas, total = deps["intel_repo"].get_zonas(db, page=1, limit=1000)
        results = []
        for zona in zonas:
            try:
                result = deps["intel_service"].calculate_hci_for_zone(
                    db, zona.id,
                    pendiente_media=pendiente_media,
                    acumulacion_media=acumulacion_media,
                    twi_medio=twi_medio,
                    proximidad_canal_m=proximidad_canal_m,
                    historial_inundacion=historial_inundacion,
                )
                results.append(result)
            except Exception:
                logger.error("hci.zone_failed", zona_id=str(zona.id), exc_info=True)
        logger.info("hci.batch_done", total=len(results))
        return {"status": "completed", "zonas_calculadas": len(results)}
    except Exception:
        logger.error("hci.batch_failed", exc_info=True)
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Full Conflict Detection
# ---------------------------------------------------------------------------


@celery_app.task(queue="geo", name="geo.intelligence.detect_all_conflicts")
def task_detect_all_conflicts(buffer_m: float = 50.0) -> dict:
    """Detect infrastructure conflict points between canals, roads, and drainage.

    Loads canal geometries from GEE assets (candil, ml, noroeste, norte),
    road geometries from GEE assets (red_vial/caminos), and drainage from
    the DRAINAGE GeoLayer on disk. Then calls detect_conflicts() to find
    intersection points filtered by flow accumulation and slope.
    """
    import geopandas as gpd

    deps = _get_deps()
    db = _get_db()
    try:
        # 1. Get raster layers (flow_acc + slope) — required
        flow_acc_layers, _ = deps["geo_repo"].get_layers(
            db, tipo_filter=deps["TipoGeoLayer"].FLOW_ACC, page=1, limit=1
        )
        slope_layers, _ = deps["geo_repo"].get_layers(
            db, tipo_filter=deps["TipoGeoLayer"].SLOPE, page=1, limit=1
        )
        if not flow_acc_layers or not slope_layers:
            return {"status": "skipped", "reason": "No flow_acc or slope layers available"}

        flow_acc_path = flow_acc_layers[0].archivo_path
        slope_path = slope_layers[0].archivo_path

        # 2. Load canal geometries from GEE assets
        canales_gdf = _load_canales_from_gee()
        if canales_gdf.empty:
            logger.warning("conflicts.no_canales", msg="No canal data available")

        # 3. Load road geometries from GEE assets
        caminos_gdf = _load_caminos_from_gee()
        if caminos_gdf.empty:
            logger.warning("conflicts.no_caminos", msg="No road data available")

        # 4. Load drainage from GeoLayer (GeoJSON file on disk)
        drenajes_gdf = _load_drainage_from_layers(db, deps)
        if drenajes_gdf.empty:
            logger.warning("conflicts.no_drenajes", msg="No drainage data available")

        # Need at least 2 non-empty datasets to detect intersections
        non_empty = sum(
            1 for gdf in [canales_gdf, caminos_gdf, drenajes_gdf] if not gdf.empty
        )
        if non_empty < 2:
            return {
                "status": "skipped",
                "reason": "Need at least 2 infrastructure datasets (canals, roads, drainage)",
            }

        result = deps["intel_service"].detect_conflicts(
            db,
            canales_gdf=canales_gdf,
            caminos_gdf=caminos_gdf,
            drenajes_gdf=drenajes_gdf,
            flow_acc_path=flow_acc_path,
            slope_path=slope_path,
            buffer_m=buffer_m,
        )
        logger.info("conflicts.detected", count=result["conflictos_detectados"])
        return {"status": "completed", **result}
    except Exception:
        logger.error("conflicts.task_failed", exc_info=True)
        raise
    finally:
        db.close()


def _load_canales_from_gee() -> "gpd.GeoDataFrame":
    """Load canal geometries from GEE assets (candil, ml, noroeste, norte)."""
    import geopandas as gpd

    try:
        from app.domains.geo.gee_service import get_layer_geojson

        canal_layers = ["candil", "ml", "noroeste", "norte"]
        all_gdfs = []
        for layer_name in canal_layers:
            try:
                geojson = get_layer_geojson(layer_name)
                if geojson and geojson.get("features"):
                    gdf = gpd.GeoDataFrame.from_features(
                        geojson["features"], crs="EPSG:4326"
                    )
                    if not gdf.empty:
                        all_gdfs.append(gdf)
            except Exception:
                logger.warning(
                    "conflicts.canal_load_failed", layer=layer_name, exc_info=True
                )
                continue

        if all_gdfs:
            import pandas as pd

            return gpd.GeoDataFrame(pd.concat(all_gdfs, ignore_index=True))
    except ImportError:
        logger.warning("conflicts.gee_not_available")
    except Exception:
        logger.warning("conflicts.canales_load_failed", exc_info=True)

    return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry")


def _load_caminos_from_gee() -> "gpd.GeoDataFrame":
    """Load road geometries from GEE assets (red_vial/caminos)."""
    import geopandas as gpd

    try:
        from app.domains.geo.gee_service import get_layer_geojson

        geojson = get_layer_geojson("caminos")
        if geojson and geojson.get("features"):
            return gpd.GeoDataFrame.from_features(
                geojson["features"], crs="EPSG:4326"
            )
    except ImportError:
        logger.warning("conflicts.gee_not_available")
    except Exception:
        logger.warning("conflicts.caminos_load_failed", exc_info=True)

    return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry")


def _load_drainage_from_layers(db, deps) -> "gpd.GeoDataFrame":
    """Load drainage network from the DRAINAGE GeoLayer (GeoJSON on disk)."""
    import geopandas as gpd

    try:
        drainage_layers, _ = deps["geo_repo"].get_layers(
            db, tipo_filter=deps["TipoGeoLayer"].DRAINAGE, page=1, limit=1
        )
        if drainage_layers and drainage_layers[0].archivo_path:
            return gpd.read_file(drainage_layers[0].archivo_path)
    except Exception:
        logger.warning("conflicts.drainage_load_failed", exc_info=True)

    return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry")


# ---------------------------------------------------------------------------
# Watershed Zonification
# ---------------------------------------------------------------------------


@celery_app.task(queue="geo", name="geo.intelligence.generate_zonification")
def task_generate_zonification(dem_layer_id: str, threshold: int = 2000) -> dict:
    deps = _get_deps()
    db = _get_db()
    try:
        layer = deps["geo_repo"].get_layer_by_id(db, uuid.UUID(dem_layer_id))
        if layer is None:
            return {"status": "failed", "error": f"DEM layer {dem_layer_id} not found"}
        flow_acc_layers, _ = deps["geo_repo"].get_layers(
            db, tipo_filter=deps["TipoGeoLayer"].FLOW_ACC,
            area_id_filter=layer.area_id, page=1, limit=1,
        )
        if not flow_acc_layers:
            return {"status": "failed", "error": "No flow_acc layer available for this area"}
        result = deps["intel_service"].generate_zones(
            db, dem_path=layer.archivo_path,
            flow_acc_path=flow_acc_layers[0].archivo_path,
            cuenca=layer.area_id or "default", threshold=threshold,
        )
        logger.info("zonification.done", zonas=result["zonas_creadas"])
        return {"status": "completed", **result}
    except Exception:
        logger.error("zonification.failed", exc_info=True)
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Alert Evaluation
# ---------------------------------------------------------------------------


@celery_app.task(queue="geo", name="geo.intelligence.evaluate_alerts")
def task_evaluate_alerts() -> dict:
    deps = _get_deps()
    db = _get_db()
    try:
        result = deps["intel_service"].check_alerts(db)
        logger.info("alerts.evaluated", **result)
        return {"status": "completed", **result}
    except Exception:
        logger.error("alerts.evaluation_failed", exc_info=True)
        raise
    finally:
        db.close()
