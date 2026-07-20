"""Recovery for geo jobs orphaned by broker/worker/process failures."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.orm import Session

from app.domains.geo.models import AnalisisGeo, EstadoGeoJob, GeoJob
from app.shared.celery_outbox import CeleryTaskOutbox

_STALE_ERROR = "Job marked failed by stale-job reconciliation after worker/broker loss"


def reconcile_stale_geo_jobs(
    db: Session,
    *,
    stale_after: timedelta,
    now: datetime | None = None,
) -> dict[str, int]:
    """Fail stale trackers without racing durable GeoJob publication.

    Stale RUNNING GeoJobs are terminalized so worker loss cannot orphan them;
    late or redelivered workers are fenced by their expected-state updates. Old
    PENDING GeoJobs remain retryable while an unpublished outbox intent exists,
    and receive a full ``stale_after`` grace period from publication. Legacy
    PENDING jobs without an intent, or jobs whose publication grace expired,
    fail in the same set-based update. AnalisisGeo keeps its pre-outbox
    reconciliation behavior until its dedicated producer is migrated.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - stale_after

    protected_intent = exists(
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

    job_result = db.execute(
        update(GeoJob)
        .where(
            GeoJob.updated_at < cutoff,
            or_(
                GeoJob.estado == EstadoGeoJob.RUNNING,
                and_(
                    GeoJob.estado == EstadoGeoJob.PENDING,
                    ~protected_intent,
                ),
            ),
        )
        .values(estado=EstadoGeoJob.FAILED, error=_STALE_ERROR, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    analysis_result = db.execute(
        update(AnalisisGeo)
        .where(
            AnalisisGeo.estado.in_((EstadoGeoJob.PENDING, EstadoGeoJob.RUNNING)),
            AnalisisGeo.updated_at < cutoff,
        )
        .values(estado=EstadoGeoJob.FAILED, error=_STALE_ERROR, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    return {
        "geo_jobs": int(getattr(job_result, "rowcount", 0) or 0),
        "gee_analyses": int(getattr(analysis_result, "rowcount", 0) or 0),
    }
