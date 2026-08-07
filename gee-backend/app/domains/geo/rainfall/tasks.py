"""Celery tasks for Rainfall v2 ingest, revisit and backfill."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.domains.geo.rainfall.models import RainfallBackfillCheckpoint, RainfallOutbox

MAX_OUTBOX_BATCH = 50
MAX_RETRIES = 5


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
    from app.config import settings
    from app.domains.geo.rainfall.adapters.resilience import (
        AdapterError,
        RedisCircuitStore,
        ResilientAdapter,
    )
    from app.domains.geo.rainfall.feature_flags import RAINFALL_SOURCE_ROLES

    if role not in RAINFALL_SOURCE_ROLES:
        raise ValueError(f"unsupported rainfall role: {role}")

    adapter = ResilientAdapter(
        lambda **_kwargs: (_ for _ in ()).throw(NotImplementedError("provider adapter not wired")),
        store=RedisCircuitStore(settings.redis_url),
        timeout_seconds=60,
        max_retries=2,
        failure_threshold=3,
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


def _backoff_seconds(retry_count: int) -> int:
    """Exponential backoff capped at roughly one hour."""
    return min(2**retry_count * 60, 3600)


def _process_outbox_row(row: RainfallOutbox, db: Session) -> str:
    """Process one outbox row; return its new status."""
    try:
        ingest_source_scope(
            source_id=row.source_id,
            role=row.role,
            scope_kind=row.scope_kind,
            scope_id=row.scope_id,
            scope_version=row.scope_version,
            year=row.year,
        )
    except Exception as exc:  # noqa: BLE001 — deliberate broad catch for durable retry
        row.retry_count += 1
        row.last_error = str(exc)[:4000]
        if row.retry_count >= MAX_RETRIES:
            row.status = "failed"
        else:
            row.status = "pending"
        row.next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=_backoff_seconds(row.retry_count)
        )
        return row.status

    row.status = "done"
    row.completed_at = datetime.now(UTC)
    row.last_error = None
    return "done"


def _process_outbox_batch(db: Session) -> dict[str, int]:
    """Drain a bounded batch of pending rainfall outbox rows."""
    rows = (
        db.execute(
            select(RainfallOutbox)
            .where(RainfallOutbox.status == "pending")
            .where(RainfallOutbox.next_attempt_at <= datetime.now(UTC))
            .order_by(RainfallOutbox.created_at)
            .limit(MAX_OUTBOX_BATCH)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )

    succeeded = 0
    failed = 0
    delayed = 0
    for row in rows:
        status = _process_outbox_row(row, db)
        if status == "done":
            succeeded += 1
        elif status == "failed":
            failed += 1
        else:
            delayed += 1
    db.commit()

    return {
        "processed": succeeded + failed + delayed,
        "succeeded": succeeded,
        "failed": failed,
        "delayed": delayed,
    }


@celery_app.task(name="rainfall.process_outbox")
def process_outbox(db: Session | None = None) -> dict[str, int]:
    """Drain a bounded batch of pending rainfall outbox rows."""
    if db is not None:
        return _process_outbox_batch(db)
    with SessionLocal() as db:
        return _process_outbox_batch(db)


@celery_app.task(name="rainfall.backfill_missing")
def backfill_missing(
    *, source_id: str, role: str, scope_kind: str, scope_id: str, scope_version: str, year: int
) -> dict[str, Any]:
    with SessionLocal() as db:
        filters = {
            "source_id": source_id,
            "role": role,
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
