"""Recovery for geo jobs orphaned by broker/worker/process failures."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.orm import Session

from app.domains.geo.models import AnalisisGeo, EstadoGeoJob, GeoJob, TipoGeoJob
from app.shared.celery_outbox import CeleryTaskOutbox

_STALE_ERROR = "Job marked failed by stale-job reconciliation after worker/broker loss"
WORKER_LOST_ERROR = "worker_lost"

# Types whose workers CAS or heartbeat during compute. GEE flood/class stay on
# the long ``stale_after`` floor until they grow a mid-run heartbeat: Celery
# may run them for hours with ``updated_at`` frozen at claim.
_GEE_GEOJOB_TIPOS = (TipoGeoJob.GEE_FLOOD, TipoGeoJob.GEE_CLASSIFICATION)


def reconcile_stale_geo_jobs(
    db: Session,
    *,
    stale_after: timedelta,
    now: datetime | None = None,
    heartbeat_stale_after: timedelta | None = None,
) -> dict[str, int]:
    """Fail stale trackers without racing durable GeoJob publication.

    Stale RUNNING trackers are terminalized so worker loss cannot orphan them;
    late or redelivered workers are fenced by their expected-state updates. Old
    PENDING trackers remain retryable while an unpublished outbox intent exists,
    and receive a full ``stale_after`` grace period from publication. Legacy
    PENDING trackers without an intent, or trackers whose publication grace
    expired, fail in one set-based update per tracker table.

    RUNNING rows of heartbeat-backed tipos use ``heartbeat_stale_after`` (idle
    since last CAS), so an orphan DEM no longer blocks crossings for the full
    broker-visibility window. GEE GeoJob tipos and AnalisisGeo keep ``stale_after``.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - stale_after
    heartbeat_stale_after = heartbeat_stale_after or min(stale_after, timedelta(minutes=45))
    if heartbeat_stale_after > stale_after:
        heartbeat_stale_after = stale_after
    heartbeat_cutoff = now - heartbeat_stale_after

    protected_job_intent = exists(
        select(1)
        .select_from(CeleryTaskOutbox)
        .where(
            CeleryTaskOutbox.celery_task_id == GeoJob.celery_task_id,
            or_(
                CeleryTaskOutbox.published_at.is_(None),
                CeleryTaskOutbox.published_at >= cutoff,
            ),
        )
    ).correlate(GeoJob)

    protected_analysis_intent = exists(
        select(1)
        .select_from(CeleryTaskOutbox)
        .where(
            CeleryTaskOutbox.celery_task_id == AnalisisGeo.celery_task_id,
            or_(
                CeleryTaskOutbox.published_at.is_(None),
                CeleryTaskOutbox.published_at >= cutoff,
            ),
        )
    ).correlate(AnalisisGeo)

    geo_running = db.execute(
        update(GeoJob)
        .where(
            GeoJob.estado == EstadoGeoJob.RUNNING,
            or_(
                and_(
                    GeoJob.tipo.in_(_GEE_GEOJOB_TIPOS),
                    GeoJob.updated_at < cutoff,
                ),
                and_(
                    GeoJob.tipo.notin_(_GEE_GEOJOB_TIPOS),
                    GeoJob.updated_at < heartbeat_cutoff,
                ),
            ),
        )
        .values(estado=EstadoGeoJob.FAILED, error=WORKER_LOST_ERROR, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    geo_pending = db.execute(
        update(GeoJob)
        .where(
            GeoJob.updated_at < cutoff,
            GeoJob.estado == EstadoGeoJob.PENDING,
            ~protected_job_intent,
        )
        .values(estado=EstadoGeoJob.FAILED, error=_STALE_ERROR, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    analysis_running = db.execute(
        update(AnalisisGeo)
        .where(
            AnalisisGeo.updated_at < cutoff,
            AnalisisGeo.estado == EstadoGeoJob.RUNNING,
        )
        .values(estado=EstadoGeoJob.FAILED, error=WORKER_LOST_ERROR, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    analysis_pending = db.execute(
        update(AnalisisGeo)
        .where(
            AnalisisGeo.updated_at < cutoff,
            AnalisisGeo.estado == EstadoGeoJob.PENDING,
            ~protected_analysis_intent,
        )
        .values(estado=EstadoGeoJob.FAILED, error=_STALE_ERROR, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    return {
        "geo_jobs": int(getattr(geo_running, "rowcount", 0) or 0)
        + int(getattr(geo_pending, "rowcount", 0) or 0),
        "gee_analyses": int(getattr(analysis_running, "rowcount", 0) or 0)
        + int(getattr(analysis_pending, "rowcount", 0) or 0),
    }
