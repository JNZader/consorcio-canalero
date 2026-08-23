"""
Service layer for the geo domain.

Bridges the FastAPI world (request/response) with Celery tasks and the repository.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.geo.models import (
    GeoJob,
    GeoLayer,
    TipoGeoJob,
)
from app.domains.geo.repository import GeoRepository
from app.shared.celery_outbox import (
    CeleryTaskKey,
    enqueue_celery_task,
    try_publish_celery_task,
)

logger = get_logger(__name__)

repo = GeoRepository()


# ---------------------------------------------------------------------------
# Task-key mapping
# ---------------------------------------------------------------------------


def _get_task_key_map() -> Mapping[TipoGeoJob, CeleryTaskKey]:
    """Map every accepted GeoJob type to a fixed outbox allowlist key."""
    return {
        TipoGeoJob.DEM_PIPELINE: CeleryTaskKey.PROCESS_DEM_PIPELINE,
        TipoGeoJob.SLOPE: CeleryTaskKey.COMPUTE_SLOPE,
        TipoGeoJob.ASPECT: CeleryTaskKey.COMPUTE_ASPECT,
        TipoGeoJob.FLOW_DIR: CeleryTaskKey.COMPUTE_FLOW_DIRECTION,
        TipoGeoJob.FLOW_ACC: CeleryTaskKey.COMPUTE_FLOW_ACCUMULATION,
        TipoGeoJob.TWI: CeleryTaskKey.COMPUTE_TWI,
        TipoGeoJob.HAND: CeleryTaskKey.COMPUTE_HAND,
        TipoGeoJob.DRAINAGE: CeleryTaskKey.EXTRACT_DRAINAGE_NETWORK,
        TipoGeoJob.TERRAIN_CLASS: CeleryTaskKey.CLASSIFY_TERRAIN,
        TipoGeoJob.GEE_FLOOD: CeleryTaskKey.ANALYZE_FLOOD,
        TipoGeoJob.GEE_CLASSIFICATION: CeleryTaskKey.SUPERVISED_CLASSIFICATION,
        TipoGeoJob.DEM_FULL_PIPELINE: CeleryTaskKey.RUN_FULL_DEM_PIPELINE,
        TipoGeoJob.BASIN_DELINEATION: CeleryTaskKey.DELINEATE_BASINS,
        TipoGeoJob.COMPOSITE_ANALYSIS: CeleryTaskKey.COMPOSITE_ANALYSIS,
        TipoGeoJob.ROAD_FLOW_CROSSINGS: CeleryTaskKey.COMPUTE_ROAD_FLOW_CROSSINGS,
        TipoGeoJob.TRAMO_CLASSIFICATION: CeleryTaskKey.CLASSIFY_ROAD_SEGMENTS,
    }


def _resolve_task_key(tipo: str | TipoGeoJob) -> tuple[TipoGeoJob, CeleryTaskKey]:
    """Resolve and validate a task key before any database row is created."""
    try:
        normalized_tipo = TipoGeoJob(tipo)
    except (TypeError, ValueError) as exc:
        raise ValueError("Unsupported GeoJob type") from exc

    task_key = _get_task_key_map().get(normalized_tipo)
    if task_key is None:
        raise ValueError("Unsupported GeoJob type")
    return normalized_tipo, task_key


def _rollback_dispatch_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception as rollback_error:
        logger.error(
            "geo_job.dispatch_rollback_failed",
            error_type=type(rollback_error).__name__,
        )


# ---------------------------------------------------------------------------
# Generic job dispatch
# ---------------------------------------------------------------------------


def dispatch_job(
    db: Session,
    *,
    tipo: str | TipoGeoJob,
    parametros: dict | None = None,
    usuario_id: uuid.UUID | None = None,
) -> GeoJob:
    """Atomically persist a GeoJob and its durable Celery publication intent."""
    normalized_tipo, task_key = _resolve_task_key(tipo)
    stored_parameters = parametros or {}
    celery_task_id = uuid.uuid4()

    try:
        job = repo.create_job(
            db,
            tipo=normalized_tipo,
            parametros=stored_parameters,
            usuario_id=usuario_id,
            celery_task_id=str(celery_task_id),
        )
        outbox = enqueue_celery_task(
            db,
            celery_task_id=celery_task_id,
            task_key=task_key,
            task_kwargs={**stored_parameters, "job_id": str(job.id)},
        )
        db.commit()
    except Exception:
        _rollback_dispatch_quietly(db)
        raise

    db.refresh(job)
    try:
        published = try_publish_celery_task(outbox.id)
    except Exception as publication_error:
        published = False
        logger.error(
            "geo_job.outbox_immediate_publish_failed",
            job_id=str(job.id),
            outbox_id=str(outbox.id),
            error_type=type(publication_error).__name__,
        )

    if not published:
        logger.warning(
            "geo_job.outbox_publication_deferred",
            job_id=str(job.id),
            outbox_id=str(outbox.id),
            task_key=task_key.value,
        )
    return job


# ---------------------------------------------------------------------------
# Pipeline submission
# ---------------------------------------------------------------------------


def submit_pipeline_job(
    db: Session,
    *,
    dem_path: str,
    bbox: list[float] | None = None,
    area_id: str | None = None,
    user_id: uuid.UUID | None = None,
) -> GeoJob:
    """Submit the standard DEM pipeline through the generic durable producer."""
    resolved_area_id = area_id or str(uuid.uuid4())[:8]
    return dispatch_job(
        db,
        tipo=TipoGeoJob.DEM_PIPELINE,
        parametros={
            "dem_path": dem_path,
            "bbox": bbox,
            "area_id": resolved_area_id,
        },
        usuario_id=user_id,
    )


# ---------------------------------------------------------------------------
# Job queries
# ---------------------------------------------------------------------------


def get_job_status(db: Session, job_id: uuid.UUID) -> Optional[GeoJob]:
    """Return a GeoJob by id, or None if not found."""
    return repo.get_job_by_id(db, job_id)


def list_jobs(
    db: Session,
    *,
    page: int = 1,
    limit: int = 20,
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
) -> tuple[list[GeoJob], int]:
    """Paginated list of geo jobs."""
    return repo.get_jobs(db, page=page, limit=limit, estado_filter=estado, tipo_filter=tipo)


# ---------------------------------------------------------------------------
# Layer queries
# ---------------------------------------------------------------------------


def get_layers(
    db: Session,
    *,
    area_id: Optional[str] = None,
    tipo: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[GeoLayer], int]:
    """List geo layers, optionally filtered by area and type."""
    return repo.get_layers(
        db,
        page=page,
        limit=limit,
        tipo_filter=tipo,
        area_id_filter=area_id,
    )


def get_layer_by_id(db: Session, layer_id: uuid.UUID) -> Optional[GeoLayer]:
    """Return a single GeoLayer or None."""
    return repo.get_layer_by_id(db, layer_id)
