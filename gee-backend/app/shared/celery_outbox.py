"""Transactional outbox for durable, allowlisted Celery publication.

Domain producers enqueue an outbox row in the same transaction as their
tracking row.  Publication happens after commit and is retried by Celery Beat
with the original task UUID, so a broker acknowledgement failure can only
cause a duplicate delivery of the same logical task.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Literal, Protocol

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    and_,
    delete,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.exceptions import sanitize_error_message
from app.db.base import Base, TimestampMixin, UUIDMixin


logger = logging.getLogger(__name__)

DEFAULT_LEASE = timedelta(minutes=5)
DEFAULT_RETENTION = timedelta(days=30)
DEFAULT_PUBLISH_BATCH_SIZE = 25
DEFAULT_CLEANUP_BATCH_SIZE = 500
MAX_PUBLISH_BATCH_SIZE = 100
MAX_CLEANUP_BATCH_SIZE = 1000
MAX_BACKOFF_SECONDS = 15 * 60
INITIAL_BACKOFF_SECONDS = 5
MAX_ERROR_LENGTH = 255


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CeleryTaskKey(str, Enum):
    """Only task objects explicitly named here may be published."""

    PROCESS_DEM_PIPELINE = "geo.process_dem_pipeline"
    COMPUTE_SLOPE = "geo.compute_slope"
    COMPUTE_ASPECT = "geo.compute_aspect"
    COMPUTE_FLOW_DIRECTION = "geo.compute_flow_direction"
    COMPUTE_FLOW_ACCUMULATION = "geo.compute_flow_accumulation"
    COMPUTE_TWI = "geo.compute_twi"
    COMPUTE_HAND = "geo.compute_hand"
    EXTRACT_DRAINAGE_NETWORK = "geo.extract_drainage_network"
    CLASSIFY_TERRAIN = "geo.classify_terrain"
    ANALYZE_FLOOD = "gee.analyze_flood"
    SUPERVISED_CLASSIFICATION = "gee.supervised_classification"
    RUN_FULL_DEM_PIPELINE = "geo.run_full_dem_pipeline"
    DELINEATE_BASINS = "geo.delineate_basins"
    COMPOSITE_ANALYSIS = "geo.composite_analysis"
    SAR_TEMPORAL = "gee.sar_temporal"
    COMPUTE_ROAD_FLOW_CROSSINGS = "geo.intelligence.compute_road_flow_crossings"


class CeleryTask(Protocol):
    """Narrow interface needed from a concrete Celery task object."""

    name: str

    def apply_async(
        self,
        args: list[Any],
        kwargs: dict[str, Any],
        task_id: str,
        retry: bool,
    ) -> Any: ...


TaskRegistry = Mapping[CeleryTaskKey, CeleryTask]
SessionFactory = Callable[[], Session]


class CeleryTaskOutbox(UUIDMixin, TimestampMixin, Base):
    """One durable publication intent for one preallocated Celery task ID."""

    __tablename__ = "celery_task_outbox"
    __table_args__ = (
        UniqueConstraint(
            "celery_task_id",
            name="uq_celery_task_outbox_celery_task_id",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_celery_task_outbox_attempts_nonnegative",
        ),
        CheckConstraint(
            "((lease_id IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_id IS NOT NULL AND lease_expires_at IS NOT NULL))",
            name="ck_celery_task_outbox_lease_pair",
        ),
        CheckConstraint(
            "published_at IS NULL OR (lease_id IS NULL AND lease_expires_at IS NULL)",
            name="ck_celery_task_outbox_published_unleased",
        ),
        Index(
            "ix_celery_task_outbox_due",
            "next_attempt_at",
            "lease_expires_at",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
        Index(
            "ix_celery_task_outbox_published_at",
            "published_at",
            postgresql_where=text("published_at IS NOT NULL"),
        ),
    )

    celery_task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_key: Mapped[str] = mapped_column(String(128), nullable=False)
    task_args: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    task_kwargs: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    lease_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(String(MAX_ERROR_LENGTH), nullable=True)


@dataclass(frozen=True)
class ClaimedCeleryTask:
    """Immutable publication data copied before the claiming session closes."""

    outbox_id: uuid.UUID
    celery_task_id: str
    task_key: str
    task_args: list[Any]
    task_kwargs: dict[str, Any]
    attempts: int
    lease_id: uuid.UUID


class UnknownCeleryTaskKeyError(RuntimeError):
    """Raised when a persisted key is absent from the fixed registry."""


class InvalidCeleryTaskRegistryError(RuntimeError):
    """Raised when a registry entry does not match its declared task name."""


@lru_cache(maxsize=1)
def get_celery_task_registry() -> TaskRegistry:
    """Return concrete task objects; persisted rows never select arbitrary names."""
    from app.domains.geo.gee_tasks import (
        analyze_flood_task,
        sar_temporal_task,
        supervised_classification_task,
    )
    from app.domains.geo.intelligence.tasks import compute_road_flow_crossings
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

    registry: dict[CeleryTaskKey, CeleryTask] = {
        CeleryTaskKey.PROCESS_DEM_PIPELINE: process_dem_pipeline,
        CeleryTaskKey.COMPUTE_SLOPE: compute_slope,
        CeleryTaskKey.COMPUTE_ASPECT: compute_aspect,
        CeleryTaskKey.COMPUTE_FLOW_DIRECTION: compute_flow_direction,
        CeleryTaskKey.COMPUTE_FLOW_ACCUMULATION: compute_flow_accumulation,
        CeleryTaskKey.COMPUTE_TWI: compute_twi,
        CeleryTaskKey.COMPUTE_HAND: compute_hand,
        CeleryTaskKey.EXTRACT_DRAINAGE_NETWORK: extract_drainage_network,
        CeleryTaskKey.CLASSIFY_TERRAIN: classify_terrain,
        CeleryTaskKey.ANALYZE_FLOOD: analyze_flood_task,
        CeleryTaskKey.SUPERVISED_CLASSIFICATION: supervised_classification_task,
        CeleryTaskKey.RUN_FULL_DEM_PIPELINE: run_full_dem_pipeline,
        CeleryTaskKey.DELINEATE_BASINS: delineate_basins_task,
        CeleryTaskKey.COMPOSITE_ANALYSIS: composite_analysis_task,
        CeleryTaskKey.SAR_TEMPORAL: sar_temporal_task,
        CeleryTaskKey.COMPUTE_ROAD_FLOW_CROSSINGS: compute_road_flow_crossings,
    }
    for task_key, task in registry.items():
        if task.name != task_key.value:
            raise InvalidCeleryTaskRegistryError(
                "Allowlisted Celery task object has an unexpected registered name"
            )
    return MappingProxyType(registry)


def _copy_json_payload(
    task_args: list[Any] | None,
    task_kwargs: dict[str, Any] | None,
) -> tuple[list[Any], dict[str, Any]]:
    if task_args is not None and not isinstance(task_args, list):
        raise TypeError("task_args must be a list")
    if task_kwargs is not None and not isinstance(task_kwargs, dict):
        raise TypeError("task_kwargs must be a dict")

    try:
        encoded = json.dumps(
            [task_args or [], task_kwargs or {}],
            allow_nan=False,
            separators=(",", ":"),
        )
        copied_args, copied_kwargs = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError("Celery outbox payload must be JSON serializable") from exc
    return copied_args, copied_kwargs


def enqueue_celery_task(
    db: Session,
    *,
    celery_task_id: uuid.UUID,
    task_key: CeleryTaskKey,
    task_args: list[Any] | None = None,
    task_kwargs: dict[str, Any] | None = None,
) -> CeleryTaskOutbox:
    """Add an allowlisted publication intent; the caller owns the transaction."""
    if not isinstance(celery_task_id, uuid.UUID):
        raise TypeError("celery_task_id must be a UUID")
    if not isinstance(task_key, CeleryTaskKey):
        raise TypeError("task_key must be a CeleryTaskKey")

    copied_args, copied_kwargs = _copy_json_payload(task_args, task_kwargs)
    row = CeleryTaskOutbox(
        id=uuid.uuid4(),
        celery_task_id=str(celery_task_id),
        task_key=task_key.value,
        task_args=copied_args,
        task_kwargs=copied_kwargs,
        attempts=0,
        next_attempt_at=_utc_now(),
    )
    db.add(row)
    return row


def celery_outbox_backoff(attempts: int) -> timedelta:
    """Return 5s exponential retry delay capped at 15 minutes."""
    safe_attempts = max(1, attempts)
    exponent = min(safe_attempts - 1, 8)
    seconds = min(INITIAL_BACKOFF_SECONDS * (2**exponent), MAX_BACKOFF_SECONDS)
    return timedelta(seconds=seconds)


def _safe_publication_error(error: Exception) -> str:
    safe_message = sanitize_error_message(error, "Celery publication failed")
    return f"{type(error).__name__}: {safe_message}"[:MAX_ERROR_LENGTH]


def _new_session() -> Session:
    from app.db.session import SessionLocal

    return SessionLocal()


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception as error:
        logger.error(
            "celery_outbox.rollback_failed error_type=%s",
            type(error).__name__,
        )


def _close_quietly(db: Session) -> None:
    try:
        db.close()
    except Exception as error:
        logger.error(
            "celery_outbox.session_close_failed error_type=%s",
            type(error).__name__,
        )


def _claim_due_celery_task(
    db: Session,
    *,
    now: datetime,
    lease_for: timedelta,
    outbox_id: uuid.UUID | None = None,
) -> ClaimedCeleryTask | None:
    """Claim one due row under ``FOR UPDATE SKIP LOCKED``."""
    if lease_for <= timedelta(0):
        raise ValueError("lease_for must be positive")

    available_lease = or_(
        and_(
            CeleryTaskOutbox.lease_id.is_(None),
            CeleryTaskOutbox.lease_expires_at.is_(None),
        ),
        CeleryTaskOutbox.lease_expires_at <= now,
    )
    statement = (
        select(CeleryTaskOutbox)
        .where(
            CeleryTaskOutbox.published_at.is_(None),
            CeleryTaskOutbox.next_attempt_at <= now,
            available_lease,
        )
        .order_by(
            CeleryTaskOutbox.next_attempt_at,
            CeleryTaskOutbox.created_at,
            CeleryTaskOutbox.id,
        )
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if outbox_id is not None:
        statement = statement.where(CeleryTaskOutbox.id == outbox_id)

    row = db.execute(statement).scalar_one_or_none()
    if row is None:
        return None

    lease_id = uuid.uuid4()
    row.attempts += 1
    row.last_attempt_at = now
    row.lease_id = lease_id
    row.lease_expires_at = now + lease_for
    row.updated_at = now
    return ClaimedCeleryTask(
        outbox_id=row.id,
        celery_task_id=row.celery_task_id,
        task_key=row.task_key,
        task_args=list(row.task_args),
        task_kwargs=dict(row.task_kwargs),
        attempts=row.attempts,
        lease_id=lease_id,
    )


def _claim_committed(
    *,
    session_factory: SessionFactory,
    now: datetime,
    lease_for: timedelta,
    outbox_id: uuid.UUID | None = None,
) -> ClaimedCeleryTask | None:
    db = session_factory()
    try:
        claim = _claim_due_celery_task(
            db,
            now=now,
            lease_for=lease_for,
            outbox_id=outbox_id,
        )
        db.commit()
        return claim
    except Exception:
        _rollback_quietly(db)
        raise
    finally:
        _close_quietly(db)


def _resolve_task(claim: ClaimedCeleryTask, task_registry: TaskRegistry) -> CeleryTask:
    try:
        task_key = CeleryTaskKey(claim.task_key)
    except ValueError as exc:
        raise UnknownCeleryTaskKeyError("Persisted Celery task key is not allowlisted") from exc

    task = task_registry.get(task_key)
    if task is None:
        raise UnknownCeleryTaskKeyError("Celery task key has no concrete registry entry")
    if task.name != task_key.value:
        raise InvalidCeleryTaskRegistryError(
            "Allowlisted Celery task object has an unexpected registered name"
        )
    return task


def _publish_claimed(
    claim: ClaimedCeleryTask,
    *,
    task_registry: TaskRegistry | None = None,
) -> None:
    registry = task_registry if task_registry is not None else get_celery_task_registry()
    task = _resolve_task(claim, registry)
    task.apply_async(
        args=claim.task_args,
        kwargs=claim.task_kwargs,
        task_id=claim.celery_task_id,
        retry=False,
    )


def _finalize_published(
    db: Session,
    *,
    claim: ClaimedCeleryTask,
    now: datetime,
) -> bool:
    result = db.execute(
        update(CeleryTaskOutbox)
        .where(
            CeleryTaskOutbox.id == claim.outbox_id,
            CeleryTaskOutbox.lease_id == claim.lease_id,
            CeleryTaskOutbox.published_at.is_(None),
        )
        .values(
            published_at=now,
            lease_id=None,
            lease_expires_at=None,
            last_error=None,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return int(getattr(result, "rowcount", 0)) == 1


def _record_publish_failure(
    db: Session,
    *,
    claim: ClaimedCeleryTask,
    error: Exception,
    now: datetime,
) -> bool:
    result = db.execute(
        update(CeleryTaskOutbox)
        .where(
            CeleryTaskOutbox.id == claim.outbox_id,
            CeleryTaskOutbox.lease_id == claim.lease_id,
            CeleryTaskOutbox.published_at.is_(None),
        )
        .values(
            lease_id=None,
            lease_expires_at=None,
            next_attempt_at=now + celery_outbox_backoff(claim.attempts),
            last_error=_safe_publication_error(error),
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return int(getattr(result, "rowcount", 0)) == 1


def _commit_claim_update(
    operation: Callable[[Session], bool],
    *,
    session_factory: SessionFactory,
) -> bool:
    db = session_factory()
    try:
        updated = operation(db)
        db.commit()
        return updated
    except Exception:
        _rollback_quietly(db)
        raise
    finally:
        _close_quietly(db)


PublishOutcome = Literal["published", "failed", "finalize_lost"]


def _process_claimed(
    claim: ClaimedCeleryTask,
    *,
    session_factory: SessionFactory,
    now: datetime,
    task_registry: TaskRegistry | None = None,
) -> PublishOutcome:
    try:
        _publish_claimed(claim, task_registry=task_registry)
    except Exception as publication_error:
        error_to_record = publication_error
        try:
            recorded = _commit_claim_update(
                lambda db: _record_publish_failure(
                    db,
                    claim=claim,
                    error=error_to_record,
                    now=now,
                ),
                session_factory=session_factory,
            )
        except Exception as storage_error:
            logger.error(
                "celery_outbox.failure_record_failed outbox_id=%s attempt=%s error_type=%s",
                claim.outbox_id,
                claim.attempts,
                type(storage_error).__name__,
            )
            return "finalize_lost"

        logger.warning(
            "celery_outbox.publish_failed outbox_id=%s attempt=%s error_type=%s",
            claim.outbox_id,
            claim.attempts,
            type(publication_error).__name__,
        )
        return "failed" if recorded else "finalize_lost"

    try:
        finalized = _commit_claim_update(
            lambda db: _finalize_published(db, claim=claim, now=now),
            session_factory=session_factory,
        )
    except Exception as storage_error:
        logger.error(
            "celery_outbox.success_finalize_failed outbox_id=%s attempt=%s error_type=%s",
            claim.outbox_id,
            claim.attempts,
            type(storage_error).__name__,
        )
        return "finalize_lost"

    if not finalized:
        logger.warning(
            "celery_outbox.lease_lost outbox_id=%s attempt=%s",
            claim.outbox_id,
            claim.attempts,
        )
        return "finalize_lost"
    return "published"


def try_publish_celery_task(
    outbox_id: uuid.UUID,
    *,
    session_factory: SessionFactory | None = None,
    now: datetime | None = None,
    lease_for: timedelta = DEFAULT_LEASE,
    task_registry: TaskRegistry | None = None,
) -> bool:
    """Best-effort immediate publish; all durable retries remain in the database."""
    if not isinstance(outbox_id, uuid.UUID):
        return False

    factory = session_factory or _new_session
    attempted_at = now or _utc_now()
    try:
        claim = _claim_committed(
            session_factory=factory,
            now=attempted_at,
            lease_for=lease_for,
            outbox_id=outbox_id,
        )
    except Exception as claim_error:
        logger.error(
            "celery_outbox.immediate_claim_failed outbox_id=%s error_type=%s",
            outbox_id,
            type(claim_error).__name__,
        )
        return False

    if claim is None:
        return False
    try:
        outcome = _process_claimed(
            claim,
            session_factory=factory,
            now=attempted_at,
            task_registry=task_registry,
        )
    except Exception as process_error:
        logger.error(
            "celery_outbox.immediate_process_failed outbox_id=%s error_type=%s",
            outbox_id,
            type(process_error).__name__,
        )
        return False
    return outcome == "published"


def _cleanup_published(
    db: Session,
    *,
    cutoff: datetime,
    batch_size: int,
) -> int:
    if batch_size <= 0:
        return 0

    ids_to_delete = (
        select(CeleryTaskOutbox.id)
        .where(
            CeleryTaskOutbox.published_at.is_not(None),
            CeleryTaskOutbox.published_at < cutoff,
        )
        .order_by(CeleryTaskOutbox.published_at, CeleryTaskOutbox.id)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
        .cte("celery_outbox_retention_batch")
    )
    result = db.execute(
        delete(CeleryTaskOutbox)
        .where(CeleryTaskOutbox.id.in_(select(ids_to_delete.c.id)))
        .execution_options(synchronize_session=False)
    )
    return int(getattr(result, "rowcount", 0))


def _cleanup_committed(
    *,
    session_factory: SessionFactory,
    cutoff: datetime,
    batch_size: int,
) -> int:
    db = session_factory()
    try:
        deleted = _cleanup_published(db, cutoff=cutoff, batch_size=batch_size)
        db.commit()
        return deleted
    except Exception:
        _rollback_quietly(db)
        raise
    finally:
        _close_quietly(db)


def publish_due_celery_tasks(
    *,
    batch_size: int = DEFAULT_PUBLISH_BATCH_SIZE,
    lease_for: timedelta = DEFAULT_LEASE,
    retention: timedelta = DEFAULT_RETENTION,
    cleanup_batch_size: int = DEFAULT_CLEANUP_BATCH_SIZE,
    session_factory: SessionFactory | None = None,
    now: datetime | None = None,
    task_registry: TaskRegistry | None = None,
) -> dict[str, int]:
    """Publish a bounded due batch, isolating every row and retention pass."""
    if lease_for <= timedelta(0):
        raise ValueError("lease_for must be positive")
    if retention < timedelta(0):
        raise ValueError("retention must not be negative")

    publish_limit = min(max(batch_size, 0), MAX_PUBLISH_BATCH_SIZE)
    cleanup_limit = min(max(cleanup_batch_size, 0), MAX_CLEANUP_BATCH_SIZE)
    factory = session_factory or _new_session
    stats = {
        "claimed": 0,
        "published": 0,
        "failed": 0,
        "finalize_lost": 0,
        "claim_errors": 0,
        "cleaned": 0,
    }

    for _ in range(publish_limit):
        attempted_at = now or _utc_now()
        try:
            claim = _claim_committed(
                session_factory=factory,
                now=attempted_at,
                lease_for=lease_for,
            )
        except Exception as claim_error:
            stats["claim_errors"] += 1
            logger.error(
                "celery_outbox.batch_claim_failed error_type=%s",
                type(claim_error).__name__,
            )
            break

        if claim is None:
            break

        stats["claimed"] += 1
        try:
            outcome = _process_claimed(
                claim,
                session_factory=factory,
                now=attempted_at,
                task_registry=task_registry,
            )
        except Exception as process_error:
            stats["finalize_lost"] += 1
            logger.error(
                "celery_outbox.batch_process_failed outbox_id=%s attempt=%s error_type=%s",
                claim.outbox_id,
                claim.attempts,
                type(process_error).__name__,
            )
            continue
        stats[outcome] += 1

    cleanup_now = now or _utc_now()
    try:
        stats["cleaned"] = _cleanup_committed(
            session_factory=factory,
            cutoff=cleanup_now - retention,
            batch_size=cleanup_limit,
        )
    except Exception as cleanup_error:
        logger.error(
            "celery_outbox.retention_failed error_type=%s",
            type(cleanup_error).__name__,
        )

    return stats
