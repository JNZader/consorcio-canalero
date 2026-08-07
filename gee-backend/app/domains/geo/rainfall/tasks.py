"""Celery tasks for Rainfall v2 ingest, revisit and backfill."""

from datetime import UTC, datetime
from typing import Any

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.domains.geo.rainfall.models import RainfallBackfillCheckpoint


@celery_app.task(name="rainfall.ingest_source_scope", bind=True, max_retries=3)
def ingest_source_scope(
    self,
    *,
    source_id: str,
    role: str,
    scope_kind: str,
    scope_id: str,
    scope_version: str,
    year: int,
) -> dict[str, Any]:
    from app.domains.geo.rainfall.adapters.resilience import AdapterError, ResilientAdapter
    from app.domains.geo.rainfall.feature_flags import RAINFALL_SOURCE_ROLES

    if role not in RAINFALL_SOURCE_ROLES:
        raise ValueError(f"unsupported rainfall role: {role}")

    adapter = ResilientAdapter(
        lambda **_kwargs: (_ for _ in ()).throw(NotImplementedError("provider adapter not wired")),
        timeout_seconds=60,
        max_retries=2,
    )
    start = datetime(year, 1, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC)
    try:
        batch = adapter.fetch(
            source_id=source_id,
            role=role,
            scope_kind=scope_kind,
            scope_id=scope_id,
            scope_version=scope_version,
            start=start,
            end=end,
        )
    except AdapterError as exc:
        raise self.retry(exc=exc, countdown=300) from exc
    return {
        "source_id": batch.source_id,
        "scope_kind": batch.scope_kind,
        "scope_id": batch.scope_id,
        "year": year,
        "intervals": len(batch.intervals),
    }


@celery_app.task(name="rainfall.revisit_stale", bind=True, max_retries=2)
def revisit_stale(
    self,
    *,
    source_id: str,
    role: str,
    scope_kind: str,
    scope_id: str,
    scope_version: str,
    year: int,
) -> dict[str, Any]:
    return ingest_source_scope(
        source_id=source_id,
        role=role,
        scope_kind=scope_kind,
        scope_id=scope_id,
        scope_version=scope_version,
        year=year,
    )


@celery_app.task(name="rainfall.backfill_missing")
def backfill_missing(
    *, source_id: str, role: str, scope_kind: str, scope_id: str, scope_version: str, year: int
) -> dict[str, Any]:
    with SessionLocal() as db:
        filters = {
            "source_id": source_id,
            "scope_kind": scope_kind,
            "scope_id": scope_id,
            "scope_version": scope_version,
            "year": year,
        }
        checkpoint = db.query(RainfallBackfillCheckpoint).filter_by(**filters).first()
        if checkpoint is None:
            checkpoint = RainfallBackfillCheckpoint(**filters)
            db.add(checkpoint)
        if checkpoint.completed_at is not None:
            return {"status": "already_complete", "intervals": 0}
        result = ingest_source_scope(**filters)
        checkpoint.completed_at = datetime.now(UTC)
        db.commit()
        return {"status": "completed", **result}
