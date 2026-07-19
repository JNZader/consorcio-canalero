"""
Celery tasks for Google Earth Engine analysis.

Handles long-running GEE operations in the background.
These tasks run on the DEFAULT queue (not geo queue) because GEE
is cloud-based, not GDAL-based — no heavy local computation needed.

Each tracked task:
  1. Atomically claims its AnalisisGeo or GeoJob row (pending → running)
  2. Initializes GEE and uses ImageExplorer / GEEService
  3. Runs analysis (flood comparison, NDVI classification, etc.)
  4. Persists the result only while the tracker remains running
  5. Fences completed/failed writes against reconciliation and duplicate delivery
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


def _update_tracking(
    *,
    analisis_id: str | None,
    job_id: str | None,
    expected_estado: str,
    estado: str | None = None,
    progreso: int | None = None,
    resultado: dict[str, Any] | None = None,
    error: str | None = None,
) -> bool:
    """Atomically update exactly one durable tracker and close its transaction."""
    if analisis_id and job_id:
        raise ValueError("analisis_id and job_id are mutually exclusive")

    tracking_id = analisis_id or job_id
    if not tracking_id:
        return True

    tracking_uuid = uuid.UUID(tracking_id)
    deps = _get_deps()
    db = deps["SessionLocal"]()
    repo = deps["repo"]

    try:
        if analisis_id:
            updated = repo.update_analisis_status_if_current(
                db,
                tracking_uuid,
                expected_estado=expected_estado,
                estado=estado,
                resultado=resultado,
                error=error,
            )
        else:
            updated = repo.update_job_status_if_current(
                db,
                tracking_uuid,
                expected_estado=expected_estado,
                estado=estado,
                progreso=progreso,
                resultado=resultado,
                error=error,
            )
        db.commit()
        return updated
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _skipped_result(*, analisis_id: str | None, job_id: str | None) -> dict[str, str]:
    result = {"status": "skipped"}
    if analisis_id:
        result["analisis_id"] = analisis_id
    if job_id:
        result["job_id"] = job_id
    return result


@celery_app.task(name="gee.analyze_flood", bind=True)
def analyze_flood_task(
    self,
    start_date_str: str,
    end_date_str: str,
    method: str = "fusion",
    analisis_id: str | None = None,
    job_id: str | None = None,
):
    """Analyze floods using SAR and optical imagery via GEE."""
    Estado = _get_deps()["EstadoGeoJob"]
    tracked = bool(analisis_id or job_id)

    if tracked and not _update_tracking(
        analisis_id=analisis_id,
        job_id=job_id,
        expected_estado=Estado.PENDING,
        estado=Estado.RUNNING,
    ):
        return _skipped_result(analisis_id=analisis_id, job_id=job_id)

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

        if tracked and not _update_tracking(
            analisis_id=analisis_id,
            job_id=job_id,
            expected_estado=Estado.RUNNING,
            estado=Estado.COMPLETED,
            progreso=100,
            resultado=resultado,
        ):
            return _skipped_result(analisis_id=analisis_id, job_id=job_id)

        logger.info(
            "analyze_flood_task.completed analisis_id=%s job_id=%s method=%s",
            analisis_id,
            job_id,
            method,
        )
        return resultado

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logger.error("analyze_flood_task.failed: %s", exc)

        if tracked:
            try:
                _update_tracking(
                    analisis_id=analisis_id,
                    job_id=job_id,
                    expected_estado=Estado.RUNNING,
                    estado=Estado.FAILED,
                    error=error_msg[:2000],
                )
            except Exception:
                logger.exception(
                    "analyze_flood_task.status_update_failed analisis_id=%s job_id=%s",
                    analisis_id,
                    job_id,
                )

        raise


@celery_app.task(name="gee.supervised_classification", bind=True)
def supervised_classification_task(
    self,
    start_date_str: str,
    end_date_str: str,
    analisis_id: str | None = None,
    job_id: str | None = None,
):
    """Classify land use from Sentinel-2 NDVI/NDWI imagery."""
    Estado = _get_deps()["EstadoGeoJob"]
    tracked = bool(analisis_id or job_id)

    if tracked and not _update_tracking(
        analisis_id=analisis_id,
        job_id=job_id,
        expected_estado=Estado.PENDING,
        estado=Estado.RUNNING,
    ):
        return _skipped_result(analisis_id=analisis_id, job_id=job_id)

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

        if tracked and not _update_tracking(
            analisis_id=analisis_id,
            job_id=job_id,
            expected_estado=Estado.RUNNING,
            estado=Estado.COMPLETED,
            progreso=100,
            resultado=resultado,
        ):
            return _skipped_result(analisis_id=analisis_id, job_id=job_id)

        logger.info(
            "supervised_classification_task.completed analisis_id=%s job_id=%s",
            analisis_id,
            job_id,
        )
        return resultado

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logger.error("supervised_classification_task.failed: %s", exc)

        if tracked:
            try:
                _update_tracking(
                    analisis_id=analisis_id,
                    job_id=job_id,
                    expected_estado=Estado.RUNNING,
                    estado=Estado.FAILED,
                    error=error_msg[:2000],
                )
            except Exception:
                logger.exception(
                    "supervised_classification_task.status_update_failed analisis_id=%s job_id=%s",
                    analisis_id,
                    job_id,
                )

        raise


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
    """Compute a Sentinel-1 VV time series and anomaly detection."""
    Estado = _get_deps()["EstadoGeoJob"]
    tracked = bool(analisis_id)

    if tracked and not _update_tracking(
        analisis_id=analisis_id,
        job_id=None,
        expected_estado=Estado.PENDING,
        estado=Estado.RUNNING,
    ):
        return _skipped_result(analisis_id=analisis_id, job_id=None)

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

        if tracked and not _update_tracking(
            analisis_id=analisis_id,
            job_id=None,
            expected_estado=Estado.RUNNING,
            estado=Estado.COMPLETED,
            resultado=resultado,
        ):
            return _skipped_result(analisis_id=analisis_id, job_id=None)

        logger.info(
            "sar_temporal_task.completed analisis_id=%s image_count=%s",
            analisis_id,
            resultado["image_count"],
        )
        return resultado

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        logger.error("sar_temporal_task.failed: %s", exc)

        if tracked:
            try:
                _update_tracking(
                    analisis_id=analisis_id,
                    job_id=None,
                    expected_estado=Estado.RUNNING,
                    estado=Estado.FAILED,
                    error=error_msg[:2000],
                )
            except Exception:
                logger.exception(
                    "sar_temporal_task.status_update_failed analisis_id=%s",
                    analisis_id,
                )

        raise
