"""Append-only Rainfall evidence and immutable interval facts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base, UUIDMixin


class RainfallSourceEligibility(UUIDMixin, Base):
    __tablename__ = "rainfall_source_eligibility"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "role", "evidence_revision", name="uq_rainfall_eligibility_evidence"
        ),
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    criteria: Mapped[dict] = mapped_column(JSON, nullable=False)
    failed_criteria: Mapped[list] = mapped_column(JSON, nullable=False)
    manifest_version: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RainfallIntervalValue(UUIDMixin, Base):
    __tablename__ = "rainfall_interval_value"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "scope_kind",
            "scope_id",
            "scope_version",
            "interval_start",
            "interval_end",
            "provider_revision",
            name="uq_rainfall_interval_revision",
        ),
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_version: Mapped[str] = mapped_column(String(128), nullable=False)
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)


class RainfallIntervalLifecycle(UUIDMixin, Base):
    """Append-only supersession/expiry evidence for an immutable interval fact."""

    __tablename__ = "rainfall_interval_lifecycle"
    interval_value_id: Mapped[UUID] = mapped_column("interval_value_id", nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    superseded_by_id: Mapped[UUID | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RainfallAnalysisRevision(UUIDMixin, Base):
    __tablename__ = "rainfall_analysis_revision"
    __table_args__ = (
        UniqueConstraint(
            "request_fingerprint",
            "policy_revision",
            "data_revision",
            name="uq_rainfall_analysis_snapshot",
        ),
    )
    request_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    data_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RainfallBackfillCheckpoint(UUIDMixin, Base):
    __tablename__ = "rainfall_backfill_checkpoint"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "scope_kind",
            "scope_id",
            "scope_version",
            "year",
            name="uq_rainfall_backfill_source_scope_version_year",
        ),
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_version: Mapped[str] = mapped_column(String(128), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    cursor: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


_IMMUTABLE_TYPES = (
    RainfallSourceEligibility,
    RainfallIntervalValue,
    RainfallIntervalLifecycle,
    RainfallAnalysisRevision,
)


@event.listens_for(Session, "before_flush")
def _prevent_rainfall_audit_mutation(
    session: Session, _flush_context: object, _instances: object
) -> None:
    """Reject normal updates/deletes; expiry purge is a database-only controlled path."""
    changed = set(session.dirty).union(session.deleted)
    for instance in changed:
        if isinstance(instance, _IMMUTABLE_TYPES):
            raise ValueError(f"{type(instance).__name__} rows are append-only")
