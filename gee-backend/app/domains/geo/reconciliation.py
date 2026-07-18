"""Recovery for geo jobs orphaned by broker/worker/process failures."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.domains.geo.models import AnalisisGeo, EstadoGeoJob, GeoJob

_STALE_ERROR = "Job marked failed by stale-job reconciliation after worker/broker loss"


def reconcile_stale_geo_jobs(
    db: Session,
    *,
    stale_after: timedelta,
    now: datetime | None = None,
) -> dict[str, int]:
    """Atomically fail active jobs whose last update predates ``stale_after``.

    The predicate is idempotent: completed/failed rows and rows already handled
    by an earlier reconciliation pass are never changed again.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - stale_after
    active = (EstadoGeoJob.PENDING, EstadoGeoJob.RUNNING)

    job_result = db.execute(
        update(GeoJob)
        .where(GeoJob.estado.in_(active), GeoJob.updated_at < cutoff)
        .values(estado=EstadoGeoJob.FAILED, error=_STALE_ERROR, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    analysis_result = db.execute(
        update(AnalisisGeo)
        .where(AnalisisGeo.estado.in_(active), AnalisisGeo.updated_at < cutoff)
        .values(estado=EstadoGeoJob.FAILED, error=_STALE_ERROR, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    return {
        "geo_jobs": int(job_result.rowcount or 0),
        "gee_analyses": int(analysis_result.rowcount or 0),
    }
