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
from typing import Any

from celery.utils.log import get_task_logger

from app.core.celery_app import celery_app
from app.domains.geo.gee_tasks_support import (
    build_classification_result,
    build_flood_analysis_result,
    build_sar_temporal_result,
    detect_vv_anomalies_impl,
    update_status_if_needed,
)

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

    if analisis_id:
        update_status_if_needed(
            analisis_id=analisis_id,
            repo=repo,
            db=db,
            uuid_module=uuid,
            estado=Estado.RUNNING,
        )
        db.commit()

    try:
        from datetime import date

        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)

        gee = _get_gee()
        explorer = gee["explorer"]

        resultado = build_flood_analysis_result(
            explorer=explorer,
            start_date=start_date,
            end_date=end_date,
            method=method,
        )
        resultado["method"] = method
        resultado["start_date"] = start_date_str
        resultado["end_date"] = end_date_str
        resultado["status"] = "completed"

        if analisis_id:
            update_status_if_needed(
                analisis_id=analisis_id,
                repo=repo,
                db=db,
                uuid_module=uuid,
                estado=Estado.COMPLETED,
                resultado=resultado,
            )
            db.commit()

        logger.info(
            "analyze_flood_task.completed analisis_id=%s method=%s",
            analisis_id,
            method,
        )
        return resultado

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logger.error("analyze_flood_task.failed: %s", exc)

        if analisis_id:
            try:
                update_status_if_needed(
                    analisis_id=analisis_id,
                    repo=repo,
                    db=db,
                    uuid_module=uuid,
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

    if analisis_id:
        update_status_if_needed(
            analisis_id=analisis_id,
            repo=repo,
            db=db,
            uuid_module=uuid,
            estado=Estado.RUNNING,
        )
        db.commit()

    try:
        from datetime import date

        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)

        gee = _get_gee()
        explorer = gee["explorer"]

        import datetime as _datetime
        import ee

        resultado = build_classification_result(
            explorer=explorer,
            start_date=start_date,
            end_date=end_date,
            logger=logger,
            ee_module=ee,
            datetime_module=_datetime,
        )
        resultado["start_date"] = start_date_str
        resultado["end_date"] = end_date_str
        resultado["status"] = "completed"

        if analisis_id:
            update_status_if_needed(
                analisis_id=analisis_id,
                repo=repo,
                db=db,
                uuid_module=uuid,
                estado=Estado.COMPLETED,
                resultado=resultado,
            )
            db.commit()

        logger.info(
            "supervised_classification_task.completed analisis_id=%s",
            analisis_id,
        )
        return resultado

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logger.error("supervised_classification_task.failed: %s", exc)

        if analisis_id:
            try:
                update_status_if_needed(
                    analisis_id=analisis_id,
                    repo=repo,
                    db=db,
                    uuid_module=uuid,
                    estado=Estado.FAILED,
                    error=error_msg[:2000],
                )
                db.commit()
            except Exception:
                db.rollback()

        raise
    finally:
        db.close()


# ── Pure function: anomaly detection ──────────────────────


def detect_vv_anomalies(
    dates: list[str],
    vv_values: list[float],
    sigma: float = 2.0,
) -> dict[str, Any]:
    """Detect anomalies in a VV backscatter time series."""
    return detect_vv_anomalies_impl(dates=dates, vv_values=vv_values, sigma=sigma)


# ── Celery task: SAR temporal analysis ───────────────────


@celery_app.task(name="gee.sar_temporal", bind=True)
def sar_temporal_task(
    self,
    start_date_str: str,
    end_date_str: str,
    scale: int = 100,
    analisis_id: str | None = None,
):
    """
    SAR temporal analysis: VV backscatter time series + anomaly detection.

    Computes mean VV per Sentinel-1 image over the zona geometry,
    then flags dates where VV drops below baseline - 2*std.

    Args:
        start_date_str: Analysis start date (ISO format).
        end_date_str: Analysis end date (ISO format).
        scale: Pixel scale in meters for reduceRegion (default 100).
        analisis_id: Optional AnalisisGeo record ID for status tracking.
    """
    deps = _get_deps()
    db = deps["SessionLocal"]()
    repo = deps["repo"]
    Estado = deps["EstadoGeoJob"]

    if analisis_id:
        update_status_if_needed(
            analisis_id=analisis_id,
            repo=repo,
            db=db,
            uuid_module=uuid,
            estado=Estado.RUNNING,
        )
        db.commit()

    try:
        from datetime import date

        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)

        gee = _get_gee()
        explorer = gee["explorer"]

        resultado = build_sar_temporal_result(
            explorer=explorer,
            start_date=start_date,
            end_date=end_date,
            scale=scale,
            detect_fn=detect_vv_anomalies_impl,
        )

        if analisis_id:
            update_status_if_needed(
                analisis_id=analisis_id,
                repo=repo,
                db=db,
                uuid_module=uuid,
                estado=Estado.COMPLETED,
                resultado=resultado,
            )
            db.commit()

        logger.info(
            "sar_temporal_task.completed analisis_id=%s image_count=%s",
            analisis_id,
            resultado["image_count"],
        )
        return resultado

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logger.error("sar_temporal_task.failed: %s", exc)

        if analisis_id:
            try:
                update_status_if_needed(
                    analisis_id=analisis_id,
                    repo=repo,
                    db=db,
                    uuid_module=uuid,
                    estado=Estado.FAILED,
                    error=error_msg[:2000],
                )
                db.commit()
            except Exception:
                db.rollback()

        raise
    finally:
        db.close()
