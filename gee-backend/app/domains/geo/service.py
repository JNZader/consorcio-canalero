"""
Service layer for the geo domain.

Bridges the FastAPI world (request/response) with Celery tasks and the repository.
"""

from __future__ import annotations

import uuid
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.geo.models import (
    GeoJob,
    GeoLayer,
    TipoGeoJob,
)
from app.domains.geo.repository import GeoRepository

logger = get_logger(__name__)

repo = GeoRepository()


# ---------------------------------------------------------------------------
# Task dispatch map (lazy imports to avoid circular deps at module level)
# ---------------------------------------------------------------------------


def _get_task_dispatch_map() -> dict[str, Callable]:
    """Return a mapping from TipoGeoJob value to a callable that dispatches
    the corresponding Celery task via ``.delay()``.

    Imports are deferred so the module can be imported without pulling in
    Celery task registrations at startup.
    """
    from app.domains.geo.gee_tasks import (
        analyze_flood_task,
        supervised_classification_task,
    )
    from app.domains.geo.tasks import (
        classify_terrain,
        composite_analysis_task,
        compute_aspect,
        compute_flow_accumulation,
        compute_flow_direction,
        compute_hand,
        compute_slope,
        compute_twi,
        delineate_basins_task,
        extract_drainage_network,
        process_dem_pipeline,
        run_full_dem_pipeline,
    )

    return {
        TipoGeoJob.DEM_PIPELINE: lambda p: process_dem_pipeline.delay(**p),
        TipoGeoJob.SLOPE: lambda p: compute_slope.delay(**p),
        TipoGeoJob.ASPECT: lambda p: compute_aspect.delay(**p),
        TipoGeoJob.FLOW_DIR: lambda p: compute_flow_direction.delay(**p),
        TipoGeoJob.FLOW_ACC: lambda p: compute_flow_accumulation.delay(**p),
        TipoGeoJob.TWI: lambda p: compute_twi.delay(**p),
        TipoGeoJob.HAND: lambda p: compute_hand.delay(**p),
        TipoGeoJob.DRAINAGE: lambda p: extract_drainage_network.delay(**p),
        TipoGeoJob.TERRAIN_CLASS: lambda p: classify_terrain.delay(**p),
        TipoGeoJob.GEE_FLOOD: lambda p: analyze_flood_task.delay(**p),
        TipoGeoJob.GEE_CLASSIFICATION: lambda p: supervised_classification_task.delay(**p),
        TipoGeoJob.DEM_FULL_PIPELINE: lambda p: run_full_dem_pipeline.delay(**p),
        TipoGeoJob.BASIN_DELINEATION: lambda p: delineate_basins_task.delay(**p),
        TipoGeoJob.COMPOSITE_ANALYSIS: lambda p: composite_analysis_task.delay(**p),
    }


# ---------------------------------------------------------------------------
# Generic job dispatch
# ---------------------------------------------------------------------------


def dispatch_job(
    db: Session,
    *,
    tipo: str,
    parametros: dict | None = None,
    usuario_id: uuid.UUID | None = None,
) -> GeoJob:
    """Create a GeoJob, dispatch the matching Celery task, and return the job.

    Args:
        db: Active database session.
        tipo: A ``TipoGeoJob`` value indicating which task to dispatch.
        parametros: JSON-serialisable dict of task parameters.
        usuario_id: Optional user who submitted the job.

    Returns:
        The newly created GeoJob with ``celery_task_id`` set (when a
        matching task exists in the dispatch map).
    """
    parametros = parametros or {}

    job = repo.create_job(
        db,
        tipo=tipo,
        parametros=parametros,
        usuario_id=usuario_id,
    )
    db.flush()

    dispatch_map = _get_task_dispatch_map()
    task_launcher = dispatch_map.get(tipo)

    if task_launcher is not None:
        result = task_launcher({**parametros, "job_id": str(job.id)})
        repo.update_job_status(db, job.id, celery_task_id=result.id)
    else:
        logger.warning("dispatch_job.no_task_mapping", tipo=tipo, job_id=str(job.id))

    db.commit()
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
