"""Celery tasks for Rainfall v2 ingest, revisit and backfill."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.domains.geo.rainfall.metrics import record_event
from app.domains.geo.rainfall.models import RainfallBackfillCheckpoint, RainfallOutbox

MAX_OUTBOX_BATCH = 50
MAX_RETRIES = 5

RAINFALL_FEATURE_FLAGS_SETTING = "analisis/rainfall_feature_flags"


class RainfallRoleDisabled(ValueError):
    """The metric-role's source-role activation flag (feature flag) is OFF.

    Raised by ``ingest_source_scope`` before any provider contact and used by
    the outbox consumer to skip (never delete) rows whose role is gated.
    """


def _role_enabled(role: str, db: Session | None = None) -> bool:
    """A role is ingestable only when the deployment's feature flag says so.

    An absent setting (never configured) is treated as OPEN so a stack that
    ran before the rollout gate exists keeps working; an explicit
    ``false``/omitted role under ``analisis/rainfall_feature_flags`` is the
    rollback signal that gates the role off.
    """
    from app.domains.settings.service import SettingsService
    from app.domains.geo.rainfall.feature_flags import get_rainfall_feature_flags

    if db is None:
        with SessionLocal() as local:
            raw = SettingsService().get_setting(local, RAINFALL_FEATURE_FLAGS_SETTING, default=None)
    else:
        raw = SettingsService().get_setting(db, RAINFALL_FEATURE_FLAGS_SETTING, default=None)
    if raw is None or not isinstance(raw, dict):
        # Unconfigured deployment: no explicit gate was ever set.
        return True
    return get_rainfall_feature_flags({"rainfall_feature_flags": raw}).is_enabled(role)


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

    if not _role_enabled(role):
        raise RainfallRoleDisabled(f"rainfall role {role!r} is disabled by feature flag")

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
    """Drain a bounded batch of pending rainfall outbox rows.

    Rows whose metric-role is gated off by the feature flag are SKIPPED — not
    counted as processed or failed, never retried — because a rollback must
    keep the audit trail of queued work intact until the role is re-enabled.
    """
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
    skipped = 0
    for row in rows:
        if not _role_enabled(row.role, db):
            record_event(
                "rainfall.outbox.gated",
                source_id=row.source_id,
                role=row.role,
                scope_kind=row.scope_kind,
                scope_id=row.scope_id,
                year=row.year,
            )
            skipped += 1
            continue
        status = _process_outbox_row(row, db)
        if status == "done":
            record_event(
                "rainfall.outbox.done",
                source_id=row.source_id,
                role=row.role,
                scope_kind=row.scope_kind,
                scope_id=row.scope_id,
                year=row.year,
            )
            succeeded += 1
        elif status == "failed":
            record_event(
                "rainfall.outbox.failed",
                source_id=row.source_id,
                role=row.role,
                scope_kind=row.scope_kind,
                scope_id=row.scope_id,
                year=row.year,
                retry_count=row.retry_count,
            )
            failed += 1
        else:
            record_event(
                "rainfall.outbox.delayed",
                source_id=row.source_id,
                role=row.role,
                scope_kind=row.scope_kind,
                scope_id=row.scope_id,
                year=row.year,
                retry_count=row.retry_count,
            )
            delayed += 1
    db.commit()

    return {
        "processed": succeeded + failed + delayed,
        "succeeded": succeeded,
        "failed": failed,
        "delayed": delayed,
        "skipped": skipped,
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
