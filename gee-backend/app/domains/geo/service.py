"""
Service layer for the geo domain.

Bridges the FastAPI world (request/response) with Celery tasks and the repository.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.domains.geo.models import (
    EstadoGeoJob,
    GeoJob,
    GeoLayer,
    TipoGeoJob,
)
from app.domains.geo.repository import GeoRepository

repo = GeoRepository()


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
    """Create a GeoJob, dispatch the Celery pipeline task, and return the job.

    Args:
        db: Active database session.
        dem_path: Path to the input DEM GeoTIFF.
        bbox: Optional bounding box [minx, miny, maxx, maxy].
        area_id: Identifier for the processing area.
        user_id: User who submitted the job.

    Returns:
        The newly created GeoJob (estado=PENDING, celery_task_id set).
    """
    from app.domains.geo.tasks import process_dem_pipeline

    area_id = area_id or str(uuid.uuid4())[:8]

    job = repo.create_job(
        db,
        tipo=TipoGeoJob.DEM_PIPELINE,
        parametros={"dem_path": dem_path, "bbox": bbox, "area_id": area_id},
        usuario_id=user_id,
    )
    db.flush()

    result = process_dem_pipeline.delay(
        area_id=area_id,
        dem_path=dem_path,
        bbox=bbox,
        job_id=str(job.id),
    )

    repo.update_job_status(
        db,
        job.id,
        celery_task_id=result.id,
    )
    db.commit()

    return job


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
