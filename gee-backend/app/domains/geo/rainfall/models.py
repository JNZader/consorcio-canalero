"""Append-only Rainfall evidence and immutable interval facts."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, Session, mapped_column, validates

from app.db.base import Base, TimestampMixin, UUIDMixin


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
            "role",
            "scope_kind",
            "scope_id",
            "scope_version",
            "year",
            name="uq_rainfall_backfill_source_scope_version_year",
        ),
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False, server_default="historical")
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_version: Mapped[str] = mapped_column(String(128), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    cursor: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RainfallOutbox(UUIDMixin, TimestampMixin, Base):
    """Durable, labelled missing-work queue for Rainfall v2 analysis requests."""

    __tablename__ = "rainfall_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'done', 'failed')",
            name="ck_rainfall_outbox_status",
        ),
        CheckConstraint(
            "retry_count >= 0",
            name="ck_rainfall_outbox_retry_count",
        ),
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_version: Mapped[str] = mapped_column(String(128), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    work_labels: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    interval_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    request_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)

    @validates("status")
    def _validate_status(self, _key: str, value: str) -> str:
        if value not in {"pending", "done", "failed"}:
            raise ValueError(f"invalid rainfall outbox status: {value}")
        return value


Index(
    "ix_rainfall_outbox_pending_unique",
    RainfallOutbox.source_id,
    RainfallOutbox.role,
    RainfallOutbox.scope_kind,
    RainfallOutbox.scope_id,
    RainfallOutbox.scope_version,
    RainfallOutbox.year,
    unique=True,
    postgresql_where=(RainfallOutbox.status == "pending"),
)

# Non-unique done-lookup index (decision 6, migration lluvia_v2_005): the
# pending-unique index above cannot serve a "most recent done row for this
# key" seek. Serves `recent_done` (PR3) and gives the current-year revisit
# sweep its `DISTINCT ON (key) ... ORDER BY key, completed_at DESC` for free.
Index(
    "ix_rainfall_outbox_done_lookup",
    RainfallOutbox.source_id,
    RainfallOutbox.role,
    RainfallOutbox.scope_kind,
    RainfallOutbox.scope_id,
    RainfallOutbox.scope_version,
    RainfallOutbox.year,
    RainfallOutbox.completed_at,
)


class RainfallExtremeEvent(UUIDMixin, Base):
    """One extreme-rainfall event span, detected or curated (design.md D2/D8).

    Append-only, like every other table in this module (D13, ``_IMMUTABLE_TYPES``
    below): a catalog row is a permanent public statement about the weather, so
    the detector never edits one -- a changed telling is a NEW generation under
    a new ``detector_revision``, with the old rows retained and still readable
    under their OWN sealed parameters.

    **Two provenances with genuinely different obligations.** A ``detected`` row
    was ranked and must carry the whole evidence set; a ``curated`` row is
    institutional memory that was NEVER ranked. Declaring the statistics NOT
    NULL would leave only two ways to seed the three legacy anchors: fabricate
    numbers for an unranked event -- which spec R6 (No Invented Events) forbids
    outright -- or fail the migration. So the rule lives in the
    provenance-conditional CHECK pair (``ck_detected_complete`` /
    ``ck_curated_unranked``), which says the true thing instead.

    ``clipped_at_span_end`` is DERIVED, never a column: whether an event was cut
    by the frozen span's last day is a function of ``end_date`` and the span
    sealed on the row, and a stored copy would go stale the moment a later
    generation widened the span.

    **Every JSON column here is ``none_as_null=True``, and that is load-bearing,
    not style.** SQLAlchemy's default renders a Python ``None`` into a JSON
    ``null`` VALUE, which is emphatically not SQL ``NULL``: without the flag a
    detected row written with ``fired_windows=None`` satisfies ``fired_windows
    IS NOT NULL`` and sails straight through ``ck_detected_complete``. Measured,
    not reasoned about -- three cases of this suite passed a row the CHECK was
    written to refuse until the flag was set. The CHECK pair is the whole reason
    the statistics can be nullable at all, so a JSON default that quietly
    satisfies it defeats the schema's only real invariant.
    """

    __tablename__ = "rainfall_extreme_event"
    __table_args__ = (
        # The path lookup the imagery bridge resolves an id through. FULL, not
        # partial: `event_key` is NOT NULL on both provenances (curated rows
        # carry the legacy slugs), so there is no NULL here to make rows
        # spuriously distinct -- which is exactly the reason the OTHER unique
        # index, over a nullable `tier`, has to be partial.
        UniqueConstraint(
            "source_id",
            "scope_kind",
            "scope_id",
            "scope_version",
            "detector_revision",
            "event_key",
            name="uq_rainfall_extreme_event_key",
        ),
        CheckConstraint(
            "provenance <> 'detected' OR ("
            "tier IS NOT NULL AND max_percentile IS NOT NULL AND "
            "fired_windows IS NOT NULL AND sealed_detection_params IS NOT NULL AND "
            "peak_date IS NOT NULL AND climatology_span_start IS NOT NULL AND "
            "climatology_span_end IS NOT NULL AND curated_payload IS NULL)",
            name="ck_detected_complete",
        ),
        CheckConstraint(
            "provenance <> 'curated' OR ("
            "tier IS NULL AND max_percentile IS NULL AND "
            "fired_windows IS NULL AND sealed_detection_params IS NULL AND "
            "peak_date IS NULL AND climatology_span_start IS NULL AND "
            "climatology_span_end IS NULL AND curated_payload IS NOT NULL)",
            name="ck_curated_unranked",
        ),
        # Enforced in BOTH directions on purpose. The forward half is what makes
        # CRITICAL-4 ("curated rows vanish on a revision bump") structurally
        # impossible rather than policy-dependent; the reverse half stops a
        # detected row from wearing the sentinel and being swept up by every
        # curated read for free. A NULL revision would have served the same
        # exemption while quietly defeating the `event_key` unique above.
        CheckConstraint(
            "(provenance = 'curated') = (detector_revision = 'curated')",
            name="ck_curated_revision_sentinel",
        ),
        CheckConstraint("tier IS NULL OR tier IN ('extrema', 'alta')", name="ck_tier_domain"),
        CheckConstraint("provenance IN ('detected', 'curated')", name="ck_provenance_domain"),
        CheckConstraint(
            "end_date >= start_date AND "
            "(peak_date IS NULL OR (peak_date >= start_date AND peak_date <= end_date))",
            name="ck_dates_ordered",
        ),
    )

    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_version: Mapped[str] = mapped_column(String(128), nullable=False)
    detector_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The SERVED id -- `ext_YYYYMMDD` / `alt_YYYYMMDD` for detected rows, the
    #: legacy slugs (`mar_2015`, ...) for curated ones. The UUID primary key is
    #: a database key and never leaves the database.
    event_key: Mapped[str] = mapped_column(String(64), nullable=False)
    tier: Mapped[str | None] = mapped_column(String(16))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    peak_date: Mapped[date | None] = mapped_column(Date)
    max_percentile: Mapped[float | None] = mapped_column(Float)
    fired_windows: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    #: The full frozen constants block (D5) plus its digest, sealed PER ROW so
    #: the row is self-describing without reading the code that wrote it.
    sealed_detection_params: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    climatology_span_start: Mapped[date | None] = mapped_column(Date)
    climatology_span_end: Mapped[date | None] = mapped_column(Date)  # exclusive
    curated_payload: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# The identity of a DETECTED row. PARTIAL, and the partiality is the whole
# point: `tier` is NULL on every curated row, and in Postgres NULL != NULL, so
# a plain unique over these columns would treat every curated row as distinct
# from every other -- the constraint would keep existing while it stopped
# constraining, with no error anywhere to notice. Restricting it to detected
# rows makes it say exactly what it means. `tier` is IN the key because both
# tiers are persisted (spec R1 S2) and an `alta` span is a superset of the
# `extrema` spans inside it, so one `start_date` routinely hosts one row of
# each: a key without `tier` collides on the ratified behaviour.
Index(
    "uq_rainfall_extreme_event_identity",
    RainfallExtremeEvent.source_id,
    RainfallExtremeEvent.scope_kind,
    RainfallExtremeEvent.scope_id,
    RainfallExtremeEvent.scope_version,
    RainfallExtremeEvent.detector_revision,
    RainfallExtremeEvent.tier,
    RainfallExtremeEvent.start_date,
    unique=True,
    postgresql_where=(RainfallExtremeEvent.provenance == "detected"),
)

# The serving read (D12): one generation, optionally one tier, newest first.
Index(
    "ix_rainfall_extreme_event_serving",
    RainfallExtremeEvent.detector_revision,
    RainfallExtremeEvent.tier,
    text("start_date DESC"),
)


_IMMUTABLE_TYPES = (
    RainfallSourceEligibility,
    RainfallIntervalValue,
    RainfallIntervalLifecycle,
    RainfallAnalysisRevision,
    RainfallExtremeEvent,
)


@event.listens_for(Session, "before_flush")
def _prevent_rainfall_audit_mutation(
    session: Session, _flush_context: object, _instances: object
) -> None:
    """Reject normal updates/deletes; expiry purge is a database-only controlled path.

    **The scope is the ORM FLUSH, and the limits are load-bearing.** This hook
    inspects `session.dirty` / `session.deleted`, i.e. instances the unit of work
    is tracking, so a bulk `update()` / `delete()` routed through
    `session.execute` and any raw SQL bypass it entirely — neither goes through a
    flush, so neither presents anything for this to inspect. Nothing in-tree
    takes either path against these tables today (grep-verified at B1b review),
    which makes this guard sufficient NOW rather than sufficient by
    construction; a future bulk path would need its own refusal.

    In-place mutation of a JSON payload is likewise invisible here, and the
    reason is worth stating plainly rather than leaving as a gap: these are
    plain `JSON` columns, not `MutableDict`, so mutating a loaded payload's
    contents does not mark the attribute dirty. Such a change is therefore both
    undetected by this hook AND never persisted — it is discarded with the
    session rather than written behind the guard's back.
    """
    changed = set(session.dirty).union(session.deleted)
    for instance in changed:
        if isinstance(instance, _IMMUTABLE_TYPES):
            raise ValueError(f"{type(instance).__name__} rows are append-only")
