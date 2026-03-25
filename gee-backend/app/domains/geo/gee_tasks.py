"""
Celery tasks for Google Earth Engine analysis.

Handles long-running GEE operations in the background.
These tasks run on the DEFAULT queue (not geo queue) because GEE
is cloud-based, not GDAL-based — no heavy local computation needed.

Each task:
  1. Creates/updates an AnalisisGeo record (estado → running)
  2. Initializes GEE and uses ImageExplorer / GEEService
  3. Runs analysis (flood comparison, NDVI classification, etc.)
  4. Persists resultado JSON to AnalisisGeo record
  5. Updates estado to completed (or failed on error)
"""

from __future__ import annotations

import traceback
import uuid

from celery.utils.log import get_task_logger

from app.core.celery_app import celery_app

logger = get_task_logger(__name__)


def _get_deps():
    """Lazy imports to avoid pulling in heavy modules at Celery startup."""
    from app.db.session import SessionLocal
    from app.domains.geo.models import EstadoGeoJob
    from app.domains.geo.repository import GeoRepository

    return {
        "SessionLocal": SessionLocal,
        "EstadoGeoJob": EstadoGeoJob,
        "repo": GeoRepository(),
    }


def _get_gee():
    """Lazy import and init of GEE service components."""
    from app.domains.geo.gee_service import (
        _ensure_initialized,
        get_image_explorer,
    )

    _ensure_initialized()
    return {
        "explorer": get_image_explorer(),
    }


@celery_app.task(name="gee.analyze_flood", bind=True)
def analyze_flood_task(
    self,
    start_date_str: str,
    end_date_str: str,
    method: str = "fusion",
    analisis_id: str | None = None,
    job_id: str | None = None,
):
    """
    Analyze floods using SAR and Optical imagery via GEE.

    Uses ImageExplorer to fetch Sentinel-1 (SAR) and Sentinel-2 (optical)
    imagery, then runs flood comparison and NDWI-based water detection.

    Args:
        start_date_str: Analysis start date (ISO format).
        end_date_str: Analysis end date (ISO format).
        method: Analysis method — "fusion" (SAR+optical), "sar_only", "optical_only".
        analisis_id: Optional AnalisisGeo record ID for status tracking.
        job_id: Optional GeoJob ID (from dispatch_job).
    """
    deps = _get_deps()
    db = deps["SessionLocal"]()
    repo = deps["repo"]
    Estado = deps["EstadoGeoJob"]

    # Mark as running
    if analisis_id:
        repo.update_analisis_status(
            db, uuid.UUID(analisis_id), estado=Estado.RUNNING
        )
        db.commit()

    try:
        from datetime import date

        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)

        gee = _get_gee()
        explorer = gee["explorer"]

        resultado = {}

        # Optical-based flood detection (NDWI water mask)
        if method in ("fusion", "optical_only"):
            optical_result = explorer.get_sentinel2_image(
                target_date=start_date,
                days_buffer=(end_date - start_date).days or 10,
                max_cloud=60,
                visualization="inundacion",
            )
            resultado["optical"] = {
                k: v for k, v in optical_result.items() if k != "error"
            }
            if "error" in optical_result:
                resultado["optical"]["warning"] = optical_result["error"]

            # Also get NDWI for stats
            ndwi_result = explorer.get_sentinel2_image(
                target_date=start_date,
                days_buffer=(end_date - start_date).days or 10,
                max_cloud=60,
                visualization="ndwi",
            )
            resultado["ndwi"] = {
                k: v for k, v in ndwi_result.items() if k != "error"
            }

        # SAR-based water detection
        if method in ("fusion", "sar_only"):
            sar_result = explorer.get_sentinel1_image(
                target_date=start_date,
                days_buffer=(end_date - start_date).days or 10,
                visualization="vv_flood",
            )
            resultado["sar"] = {
                k: v for k, v in sar_result.items() if k != "error"
            }
            if "error" in sar_result:
                resultado["sar"]["warning"] = sar_result["error"]

        # Flood comparison if we have both dates
        if method == "fusion" and (end_date - start_date).days > 5:
            try:
                comparison = explorer.get_flood_comparison(
                    flood_date=start_date,
                    normal_date=end_date,
                    days_buffer=15,
                    max_cloud=60,
                )
                resultado["comparison"] = comparison
            except Exception as comp_err:
                resultado["comparison_error"] = str(comp_err)

        resultado["method"] = method
        resultado["start_date"] = start_date_str
        resultado["end_date"] = end_date_str
        resultado["status"] = "completed"

        # Persist results
        if analisis_id:
            repo.update_analisis_status(
                db,
                uuid.UUID(analisis_id),
                estado=Estado.COMPLETED,
                resultado=resultado,
            )
            db.commit()

        logger.info(
            "analyze_flood_task.completed",
            analisis_id=analisis_id,
            method=method,
        )
        return resultado

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logger.error("analyze_flood_task.failed", error=str(exc))

        if analisis_id:
            try:
                repo.update_analisis_status(
                    db,
                    uuid.UUID(analisis_id),
                    estado=Estado.FAILED,
                    error=error_msg[:2000],
                )
                db.commit()
            except Exception:
                db.rollback()

        raise
    finally:
        db.close()


@celery_app.task(name="gee.supervised_classification", bind=True)
def supervised_classification_task(
    self,
    start_date_str: str,
    end_date_str: str,
    analisis_id: str | None = None,
    job_id: str | None = None,
):
    """
    Land-use classification using NDVI from Sentinel-2.

    Uses ImageExplorer to fetch NDVI imagery, then runs
    clasificar_terreno_dinamico() for pixel-level classification
    (water, dense vegetation, sparse vegetation, bare soil).

    Args:
        start_date_str: Analysis start date (ISO format).
        end_date_str: Analysis end date (ISO format).
        analisis_id: Optional AnalisisGeo record ID for status tracking.
        job_id: Optional GeoJob ID (from dispatch_job).
    """
    deps = _get_deps()
    db = deps["SessionLocal"]()
    repo = deps["repo"]
    Estado = deps["EstadoGeoJob"]

    # Mark as running
    if analisis_id:
        repo.update_analisis_status(
            db, uuid.UUID(analisis_id), estado=Estado.RUNNING
        )
        db.commit()

    try:
        from datetime import date

        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)

        gee = _get_gee()
        explorer = gee["explorer"]

        resultado = {}

        # Get NDVI visualization tiles
        ndvi_result = explorer.get_sentinel2_image(
            target_date=start_date,
            days_buffer=(end_date - start_date).days or 10,
            max_cloud=60,
            visualization="ndvi",
        )
        resultado["ndvi"] = {
            k: v for k, v in ndvi_result.items() if k != "error"
        }
        if "error" in ndvi_result:
            resultado["ndvi"]["warning"] = ndvi_result["error"]

        # Get RGB reference tiles
        rgb_result = explorer.get_sentinel2_image(
            target_date=start_date,
            days_buffer=(end_date - start_date).days or 10,
            max_cloud=60,
            visualization="rgb",
        )
        resultado["rgb"] = {
            k: v for k, v in rgb_result.items() if k != "error"
        }

        # Get agriculture visualization
        agri_result = explorer.get_sentinel2_image(
            target_date=start_date,
            days_buffer=(end_date - start_date).days or 10,
            max_cloud=60,
            visualization="agricultura",
        )
        resultado["agricultura"] = {
            k: v for k, v in agri_result.items() if k != "error"
        }

        # Get false color for vegetation analysis
        fc_result = explorer.get_sentinel2_image(
            target_date=start_date,
            days_buffer=(end_date - start_date).days or 10,
            max_cloud=60,
            visualization="falso_color",
        )
        resultado["falso_color"] = {
            k: v for k, v in fc_result.items() if k != "error"
        }

        resultado["start_date"] = start_date_str
        resultado["end_date"] = end_date_str
        resultado["status"] = "completed"
        resultado["classification_type"] = "ndvi_based"

        # Persist results
        if analisis_id:
            repo.update_analisis_status(
                db,
                uuid.UUID(analisis_id),
                estado=Estado.COMPLETED,
                resultado=resultado,
            )
            db.commit()

        logger.info(
            "supervised_classification_task.completed",
            analisis_id=analisis_id,
        )
        return resultado

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logger.error("supervised_classification_task.failed", error=str(exc))

        if analisis_id:
            try:
                repo.update_analisis_status(
                    db,
                    uuid.UUID(analisis_id),
                    estado=Estado.FAILED,
                    error=error_msg[:2000],
                )
                db.commit()
            except Exception:
                db.rollback()

        raise
    finally:
        db.close()
