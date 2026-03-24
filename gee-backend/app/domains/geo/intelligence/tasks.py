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
    deps = _get_deps()
    db = _get_db()
    try:
        flow_acc_layers, _ = deps["geo_repo"].get_layers(
            db, tipo_filter=deps["TipoGeoLayer"].FLOW_ACC, page=1, limit=1
        )
        slope_layers, _ = deps["geo_repo"].get_layers(
            db, tipo_filter=deps["TipoGeoLayer"].SLOPE, page=1, limit=1
        )
        if not flow_acc_layers or not slope_layers:
            return {"status": "skipped", "reason": "No flow_acc or slope layers available"}
        logger.info("conflicts.task_placeholder")
        return {"status": "completed", "message": "Conflict detection requires canal/road/drainage data"}
    except Exception:
        logger.error("conflicts.task_failed", exc_info=True)
        raise
    finally:
        db.close()


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
