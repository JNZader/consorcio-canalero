"""Celery tasks for Rainfall v2 ingest, revisit and backfill."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.domains.geo.rainfall.metrics import record_event
from app.domains.geo.rainfall.models import RainfallBackfillCheckpoint, RainfallOutbox
from app.domains.geo.rainfall.repository import claim_outbox_row, persist_intervals

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


SQPE_NOT_AVAILABLE_MSG = (
    "sqpe-obs provider not available in GEE (SMN NetCDF); spec permits CHIRPS v3 daily fallback"
)


def _concrete_fetch(source_id: str) -> Any:
    """Return the wired provider fetch for *source_id*.

    Only evidence-validated providers are wired here (CHIRPS v3 RNN/SAT and
    IMERG V07; GEE spike PASS, 2026-08-07). Every other candidate keeps
    raising ``NotImplementedError`` until its own validation evidence passes,
    and SQPE-OBS stays explicitly unwired because GEE does not host it.
    """
    from app.domains.geo.rainfall.adapters.chirps import ChirpsV3Adapter
    from app.domains.geo.rainfall.adapters.imerg import ImergV07Adapter

    if source_id == "sqpe-obs":
        # TODO(smn-path): fetch SQPE-OBS from SMN's NetCDF product once an SMN
        # adapter exists (no SQPE product in the GEE catalog — SMN NetCDF
        # distribution). The daily role falls back to validated CHIRPS v3.
        raise NotImplementedError(SQPE_NOT_AVAILABLE_MSG)
    if source_id in {"chirps-v3-final", "chirps-v3-sat"}:
        return ChirpsV3Adapter().fetch
    if source_id == "imerg-v07":
        return ImergV07Adapter().fetch
    raise NotImplementedError(
        f"no wired provider adapter for {source_id!r} (evidence-gated candidate)"
    )


def _batch_result(batch: Any, *, year: int, persisted: dict[str, int]) -> dict[str, Any]:
    """Build the JSON-safe evidence dict PR2's ``build_analysis`` will read
    alongside the persisted rows (design.md Interfaces: ``ingest_source_scope``)."""
    return {
        "source_id": batch.source_id,
        "scope_kind": batch.scope_kind,
        "scope_id": batch.scope_id,
        "year": year,
        "intervals": len(batch.intervals),
        "persisted": persisted["inserted"],
        "superseded": persisted["superseded"],
        "provider_revision": batch.quality.get("provider_revision"),
        "unit": batch.intervals[0].unit if batch.intervals else None,
        "cadence_seconds": batch.cadence.total_seconds(),
        "coverage": batch.coverage,
        "completeness": batch.completeness,
        "quality": batch.quality,
        "discrepancies": list(batch.discrepancies),
        "checksum": batch.checksum,
    }


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
    db: Session | None = None,
) -> dict[str, Any]:
    """Fetch and persist one source/scope/year.

    Session boundary (decision 2): given a ``db``, write through it and
    never commit — the caller (the outbox consumer, decision 2c) owns the
    per-row transaction. Given ``None``, open and commit an isolated
    ``SessionLocal()`` — this keeps the direct-call contract
    (``test_provider_adapters.py:436-456``) working unmodified and is what
    ``backfill_missing`` relies on for a scope it does not itself open.
    """
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
        _concrete_fetch(source_id),
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

    if db is not None:
        persisted = persist_intervals(
            db,
            source_id=source_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
            scope_version=scope_version,
            rows=batch.intervals,
        )
        return _batch_result(batch, year=year, persisted=persisted)

    with SessionLocal() as local_db:
        persisted = persist_intervals(
            local_db,
            source_id=source_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
            scope_version=scope_version,
            rows=batch.intervals,
        )
        local_db.commit()
        return _batch_result(batch, year=year, persisted=persisted)


def _persist_analysis_revision(
    db: Session, *, outbox_id: str, batch: dict[str, Any], now: datetime
) -> dict[str, Any]:
    from app.domains.geo.rainfall.compute import (
        build_snapshot,
        data_revision_for,
        fingerprint_lock_key,
        revision_family,
        revision_write_decision,
    )
    from app.domains.geo.rainfall.models import RainfallAnalysisRevision
    from app.domains.geo.rainfall.policy import (
        RAINFALL_METRIC_POLICY,
        RAINFALL_METRIC_POLICY_REVISION,
    )
    from app.domains.geo.rainfall.repository import (
        RainfallRepository,
        acquire_fingerprint_lock,
        intervals_in_window,
        persist_revision,
    )
    from app.domains.geo.rainfall.scope import AnalysisScope

    row = db.get(RainfallOutbox, outbox_id)
    if row is None:
        raise ValueError(f"rainfall_outbox row {outbox_id!r} not found for build_analysis")
    if row.request_fingerprint is None:
        # decision 4b: deriving or skipping a null-fingerprint row is
        # _process_outbox_row's job (task 2.11), not build_analysis's — a
        # direct call with none set is a caller bug and must be loud.
        raise ValueError(
            f"rainfall_outbox row {outbox_id!r} has no request_fingerprint; the caller "
            "must derive or skip it before calling build_analysis (decision 4b)"
        )

    # design.md "Serializing siblings — the per-fingerprint advisory lock":
    # build_analysis's FIRST database statement, inside the per-row
    # transaction of decision 2c and BEFORE the incumbent get_snapshot read
    # below. Makes read -> decide -> INSERT atomic per fingerprint across
    # two sibling builds sharing this fingerprint (task 3.3).
    acquire_fingerprint_lock(db, lock_key=fingerprint_lock_key(row.request_fingerprint))

    incumbent = RainfallRepository().get_snapshot(db, row.request_fingerprint)
    incumbent_snapshot = incumbent.snapshot if incumbent is not None else None

    year_start = datetime(row.year, 1, 1, tzinfo=UTC)
    year_end = datetime(row.year + 1, 1, 1, tzinfo=UTC)
    persisted = intervals_in_window(
        db,
        source_id=row.source_id,
        scope_kind=row.scope_kind,
        scope_id=row.scope_id,
        scope_version=row.scope_version,
        start=year_start,
        end=year_end,
    )
    resolved = [
        (interval.interval_start, interval.interval_end, interval.value) for interval in persisted
    ]

    # `regional_estimate` is a property of the ORIGINAL public request (was
    # this scope reached via a parcel search?), not of the outbox key or the
    # computation itself: it is not part of the fingerprint's hashed input
    # (router.py builds the fingerprint dict from scope/year/event_window
    # only) and never feeds temporal/compute logic — disclosure metadata
    # only. The outbox row carries no such flag, so it defaults to False.
    scope = AnalysisScope(
        kind=row.scope_kind, id=row.scope_id, version=row.scope_version, regional_estimate=False
    )

    snapshot = build_snapshot(
        scope=scope,
        year=row.year,
        role=row.role,
        source_id=row.source_id,
        intervals=resolved,
        batch=batch,
        now=now,
    )

    family = revision_family(batch["provider_revision"])
    comparison_end_date = date.fromisoformat(snapshot["comparison_end"])
    data_revision = data_revision_for(
        row.source_id,
        family,
        scope,
        row.year,
        comparison_end_date,
        [(interval_start, value) for interval_start, _end, value in resolved],
    )

    # decision 9b's write gate, applied on the candidate, before any INSERT,
    # already serialized against a sibling build by the advisory lock above
    # (task 3.6).
    decision = revision_write_decision(incumbent_snapshot, snapshot, RAINFALL_METRIC_POLICY)

    if decision == "latched":
        # design.md "The latch": a provisional candidate over a final
        # incumbent is never written -- the daily-role sibling that would
        # otherwise shadow a finalized year via created_at DESC ordering.
        record_event(
            "rainfall.build.latched",
            data_revision=data_revision,
            source_id=row.source_id,
            incumbent_source_id=incumbent_snapshot["annual"]["selected"]["provenance"]["source_id"],
        )
        return {"revision_id": None, "data_revision": data_revision, "decision": decision}

    if decision == "gate_refused":
        # design.md "No backoff in v1": every refusal is instrumented so a
        # future backoff constant has real provider-lag evidence to use.
        metric = snapshot["annual"]["selected"]
        record_event(
            "rainfall.finalization.gate_refused",
            scope={"kind": row.scope_kind, "id": row.scope_id, "version": row.scope_version},
            year=row.year,
            coverage=metric["coverage"],
            completeness=metric["completeness"],
            quality_score=metric["quality"]["score"],
        )
        return {"revision_id": None, "data_revision": data_revision, "decision": decision}

    # decision == "write"
    # R4-003: read BEFORE the write to tell a genuinely new revision apart
    # from persist_revision's idempotent no-op (its own ON CONFLICT DO
    # NOTHING branch doesn't surface that distinction to the caller) —
    # observability only, not the compute decision itself.
    already_existed = (
        db.scalar(
            select(RainfallAnalysisRevision.id).where(
                RainfallAnalysisRevision.request_fingerprint == row.request_fingerprint,
                RainfallAnalysisRevision.policy_revision == RAINFALL_METRIC_POLICY_REVISION,
                RainfallAnalysisRevision.data_revision == data_revision,
            )
        )
        is not None
    )

    revision_id = persist_revision(
        db,
        request_fingerprint=row.request_fingerprint,
        policy_revision=RAINFALL_METRIC_POLICY_REVISION,
        data_revision=data_revision,
        snapshot=snapshot,
    )

    # R4-101: this event fires pre-commit, inside the row's savepoint -- a
    # commit failure after this point yields an event for rolled-back work.
    # Bounded: rainfall.outbox.done (post-commit) is the durable signal; see
    # docs/lluvia-v2-observability-workbook.md.
    record_event(
        "rainfall.build.revision_written",
        data_revision=data_revision,
        created=not already_existed,
    )

    return {"revision_id": str(revision_id), "data_revision": data_revision, "decision": decision}


@celery_app.task(name="rainfall.build_analysis")
def build_analysis(
    *,
    outbox_id: str,
    batch: dict[str, Any],
    db: Session | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute and persist the analysis revision for one outbox row's key,
    from the intervals ``persist_intervals`` just wrote (decision 1:
    chained in-process, same cycle as ingest, before ``status="done"``).

    Session boundary matches ``ingest_source_scope`` (decision 2): given a
    ``db``, write through it and never commit; given ``None``, open and
    commit an isolated ``SessionLocal()``.

    ``now`` is the disclosure-date seam (design.md Interfaces): defaults to
    ``datetime.now(UTC)`` and feeds ``temporal.comparison_end`` /
    ``buenos_aires_date`` inside ``build_snapshot`` and nothing else.
    """
    build_now = now or datetime.now(UTC)
    if db is not None:
        return _persist_analysis_revision(db, outbox_id=outbox_id, batch=batch, now=build_now)

    with SessionLocal() as local_db:
        result = _persist_analysis_revision(
            local_db, outbox_id=outbox_id, batch=batch, now=build_now
        )
        local_db.commit()
        return result


def _pending_row_for_key(
    db: Session,
    *,
    source_id: str,
    role: str,
    scope_kind: str,
    scope_id: str,
    scope_version: str,
    year: int,
) -> RainfallOutbox | None:
    """Pre-check mirroring ``ix_rainfall_outbox_pending_unique`` (decision 8's
    discipline, same shape as ``queue_missing_analysis``'s own check)."""
    return (
        db.query(RainfallOutbox)
        .filter_by(
            source_id=source_id,
            role=role,
            scope_kind=scope_kind,
            scope_id=scope_id,
            scope_version=scope_version,
            year=year,
            status="pending",
        )
        .first()
    )


def _revisit_stage1(db: Session, *, current_year: int) -> dict[str, int]:
    """Current-Year Revisit Cycle: append a fresh ``pending`` row per
    current-year ``done`` key so a materialized snapshot never freezes for
    the rest of the year (design.md "Current-Year Revisit Cycle")."""
    from sqlalchemy.exc import IntegrityError

    from app.domains.geo.rainfall.repository import current_year_done_keys

    scanned = 0
    enqueued = 0
    skipped = 0
    for row in current_year_done_keys(db, year=current_year, limit=MAX_OUTBOX_BATCH):
        scanned += 1
        key = {
            "source_id": row.source_id,
            "role": row.role,
            "scope_kind": row.scope_kind,
            "scope_id": row.scope_id,
            "scope_version": row.scope_version,
            "year": row.year,
        }
        if row.request_fingerprint is None:
            record_event("rainfall.revisit.skipped", reason="fingerprint_unavailable", **key)
            skipped += 1
            continue
        if _pending_row_for_key(db, **key) is not None:
            record_event("rainfall.revisit.skipped", reason="pending_in_flight", **key)
            skipped += 1
            continue

        db.add(
            RainfallOutbox(
                **key,
                work_labels=list(row.work_labels),
                interval_start=row.interval_start,
                interval_end=row.interval_end,
                status="pending",
                request_fingerprint=row.request_fingerprint,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            record_event("rainfall.revisit.skipped", reason="pending_in_flight", **key)
            skipped += 1
            continue
        enqueued += 1

    return {"scanned": scanned, "enqueued": enqueued, "skipped": skipped}


def _revisit_stage2(db: Session, *, current_year: int, now: datetime) -> dict[str, int]:
    """Year-Rollover Finalization: transition a completed-year key off its
    provisional satellite source once CHIRPS v3 Final is adequate
    (design.md "Year-Rollover Finalization"). Selection is on the SERVED
    snapshot's own provenance -- never on outbox history, which
    self-extinguishes on the first gated refusal."""
    from sqlalchemy.exc import IntegrityError

    from app.domains.geo.rainfall.compute import served_state
    from app.domains.geo.rainfall.repository import (
        RainfallRepository,
        completed_year_daily_done_keys,
    )
    from app.domains.geo.rainfall.service import (
        RAINFALL_HISTORICAL_SOURCE,
        resolve_missing_work_source,
    )

    scanned = 0
    enqueued = 0
    skipped = 0
    for row in completed_year_daily_done_keys(db, before_year=current_year, limit=MAX_OUTBOX_BATCH):
        scanned += 1
        scope = {"scope_kind": row.scope_kind, "scope_id": row.scope_id, "year": row.year}

        incumbent = RainfallRepository().get_snapshot(db, row.request_fingerprint)
        if incumbent is None:
            # A `done` row with no revision is the JDA-002 healing case, not
            # a finalization case -- nothing for this sweep to transition.
            record_event("rainfall.finalization.skipped", reason="revision_missing", **scope)
            skipped += 1
            continue

        state = served_state(incumbent.snapshot)
        if state is None:
            record_event("rainfall.finalization.skipped", reason="provenance_unavailable", **scope)
            skipped += 1
            continue

        served_source_id, served_temporal_state = state
        if (served_source_id, served_temporal_state) == (RAINFALL_HISTORICAL_SOURCE, "final"):
            # Terminated: an adequate final revision is already served --
            # stop selecting this key, today and forever (design.md
            # "Termination, stated as a proof obligation").
            continue

        year_start = datetime(row.year, 1, 1, tzinfo=UTC)
        year_end = datetime(row.year + 1, 1, 1, tzinfo=UTC)
        if row.interval_start != year_start or row.interval_end != year_end:
            # Structurally unreachable (resolve_missing_work_source routes
            # any event_window request to the intensity role before the
            # year test, so a role='daily' row cannot carry event-window
            # bounds) -- kept as a loud assertion, not a silent mismatch.
            record_event("rainfall.finalization.skipped", reason="event_window_key", **scope)
            skipped += 1
            continue

        # The source and role are the WORK and must be re-resolved -- the
        # `done` row's own source_id is exactly the stale provisional value
        # this stage exists to leave. The fingerprint is the IDENTITY and
        # is copied verbatim below.
        work = resolve_missing_work_source(None, row.year, now=now)
        key = {
            "source_id": work["source_id"],
            "role": work["role"],
            "scope_kind": row.scope_kind,
            "scope_id": row.scope_id,
            "scope_version": row.scope_version,
            "year": row.year,
        }

        if _pending_row_for_key(db, **key) is not None:
            record_event("rainfall.finalization.skipped", reason="pending_in_flight", **scope)
            skipped += 1
            continue

        db.add(
            RainfallOutbox(
                **key,
                work_labels=list({*row.work_labels, f"role:{work['role']}", "finalization"}),
                interval_start=work["interval_start"],
                interval_end=work["interval_end"],
                status="pending",
                request_fingerprint=row.request_fingerprint,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            record_event("rainfall.finalization.skipped", reason="pending_in_flight", **scope)
            skipped += 1
            continue
        enqueued += 1

    return {"scanned": scanned, "enqueued": enqueued, "skipped": skipped}


def _revisit_stale(db: Session, now: datetime | None) -> dict[str, int]:
    sweep_now = now or datetime.now(UTC)
    current_year = sweep_now.year

    stage1 = _revisit_stage1(db, current_year=current_year)
    stage2 = _revisit_stage2(db, current_year=current_year, now=sweep_now)

    return {
        "scanned": stage1["scanned"],
        "enqueued": stage1["enqueued"],
        "skipped": stage1["skipped"],
        "finalization_scanned": stage2["scanned"],
        "finalization_enqueued": stage2["enqueued"],
        "finalization_skipped": stage2["skipped"],
    }


@celery_app.task(name="rainfall.revisit_stale")
def revisit_stale(db: Session | None = None, now: datetime | None = None) -> dict[str, int]:
    """Daily two-stage sweep (design.md "Current-Year Revisit Cycle" +
    "Year-Rollover Finalization"). Stage 1 refreshes every already-
    materialized current-year key; stage 2 transitions a completed year
    off its provisional satellite source once CHIRPS v3 Final is adequate.

    ``now`` is the sweep's own clock seam (design.md Interfaces): supplies
    ``current_year`` for BOTH stages and is threaded into stage 2's
    ``resolve_missing_work_source(None, year, now=now)`` re-resolution so
    the selection and the re-resolution agree on the same calendar --
    without that last hop the seam dead-ends at ``current_year`` and stage
    2 would re-resolve against the real clock, routing a completed year
    back to ``daily``/``chirps-v3-sat`` and inverting its own fix.
    """
    if db is not None:
        return _revisit_stale(db, now)
    with SessionLocal() as local_db:
        return _revisit_stale(local_db, now)


def _backoff_seconds(retry_count: int) -> int:
    """Exponential backoff capped at roughly one hour."""
    return min(2**retry_count * 60, 3600)


def _derive_full_year_fingerprint(row: RainfallOutbox) -> str | None:
    """Derive the full-year request fingerprint for a legacy null-fingerprint
    row (decision 4b), but ONLY when it is safe: recomputation is exact only
    while the row's interval bounds are exactly the year bounds (no
    ``event_window``, which the outbox key does not otherwise disclose).
    Returns ``None`` when the bounds do not match — the caller must then
    skip compute rather than guess.
    """
    from app.domains.geo.rainfall.service import analysis_request_fingerprint

    year_start = datetime(row.year, 1, 1, tzinfo=UTC)
    year_end = datetime(row.year + 1, 1, 1, tzinfo=UTC)
    if row.interval_start != year_start or row.interval_end != year_end:
        return None
    return analysis_request_fingerprint(
        {
            "scope": {"kind": row.scope_kind, "id": row.scope_id, "version": row.scope_version},
            "year": row.year,
        }
    )


def _process_outbox_row(row: RainfallOutbox, db: Session, now: datetime) -> str:
    """Process one outbox row's ingest + compute chain (decision 1: chained
    in-process, same cycle, before ``status="done"``). Returns ``"done"``.

    Raises on ANY failure — ingest or compute — instead of catching
    internally. The savepoint boundary (decision 2b) and the retry/backoff
    bookkeeping live in the caller (``_process_outbox_batch``), because that
    bookkeeping must be written AFTER the savepoint has rolled a poisoned
    transaction back to a writable state; catching here and writing the
    bookkeeping from inside the very transaction a DB-level failure may
    have aborted is exactly what the savepoint exists to avoid.

    ``now`` is the disclosure-date seam (design.md Interfaces), passed
    through to ``build_analysis`` and nothing else here.
    """
    batch = ingest_source_scope(
        source_id=row.source_id,
        role=row.role,
        scope_kind=row.scope_kind,
        scope_id=row.scope_id,
        scope_version=row.scope_version,
        year=row.year,
        db=db,
    )

    if row.request_fingerprint is None:
        derived = _derive_full_year_fingerprint(row)
        if derived is None:
            record_event(
                "rainfall.compute.skipped",
                reason="fingerprint_unavailable",
                source_id=row.source_id,
                role=row.role,
                scope_kind=row.scope_kind,
                scope_id=row.scope_id,
                year=row.year,
            )
            row.status = "done"
            row.completed_at = datetime.now(UTC)
            row.last_error = None
            return "done"
        row.request_fingerprint = derived

    build_analysis(outbox_id=str(row.id), batch=batch, db=db, now=now)

    row.status = "done"
    row.completed_at = datetime.now(UTC)
    row.last_error = None
    return "done"


def _process_outbox_batch(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Drain a bounded batch of pending rainfall outbox rows, committing
    each row's work individually (decision 2c).

    A plain, unlocked read selects candidate ids first; each row is then
    re-claimed with its own ``FOR UPDATE SKIP LOCKED``
    (``repository.claim_outbox_row``) immediately before its work — this is
    what restores mutual exclusion across the every-minute overlapping runs
    (``celery_app.py``) that a naive per-row commit would otherwise break by
    releasing the old batch-wide lock on rows this worker has not started
    yet. Each row's work is isolated in a ``SAVEPOINT`` (decision 2b), so a
    DB-level failure mid-row still leaves the outer transaction writable for
    the retry/backoff bookkeeping, committed as soon as the row finishes.

    Rows whose metric-role is gated off by the feature flag are SKIPPED —
    not counted as processed or failed, never retried — because a rollback
    must keep the audit trail of queued work intact until the role is
    re-enabled.
    """
    build_now = now or datetime.now(UTC)
    candidate_ids = (
        db.execute(
            select(RainfallOutbox.id)
            .where(RainfallOutbox.status == "pending")
            .where(RainfallOutbox.next_attempt_at <= datetime.now(UTC))
            .order_by(RainfallOutbox.created_at)
            .limit(MAX_OUTBOX_BATCH)
        )
        .scalars()
        .all()
    )

    succeeded = 0
    failed = 0
    delayed = 0
    skipped = 0
    for outbox_id in candidate_ids:
        row = claim_outbox_row(db, outbox_id=outbox_id, now=datetime.now(UTC))
        if row is None:
            # Another worker already claimed or finished it since the
            # unlocked candidate read above; nothing to do this cycle.
            continue

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
            db.commit()  # release the claim's row lock
            continue

        # R4-003: captured INSIDE the except block — `except ... as exc`
        # implicitly unbinds `exc` once the block exits, so these need to
        # survive into the failed/delayed record_event calls below.
        error_type: str | None = None
        error_message: str | None = None
        try:
            with db.begin_nested():
                _process_outbox_row(row, db, build_now)
        except Exception as exc:  # noqa: BLE001 — deliberate broad catch for durable retry
            error_type = type(exc).__name__
            error_message = str(exc)[:200]
            row.retry_count += 1
            row.last_error = str(exc)[:4000]
            row.status = "failed" if row.retry_count >= MAX_RETRIES else "pending"
            row.next_attempt_at = datetime.now(UTC) + timedelta(
                seconds=_backoff_seconds(row.retry_count)
            )
        db.commit()

        if row.status == "done":
            record_event(
                "rainfall.outbox.done",
                source_id=row.source_id,
                role=row.role,
                scope_kind=row.scope_kind,
                scope_id=row.scope_id,
                year=row.year,
            )
            succeeded += 1
        elif row.status == "failed":
            record_event(
                "rainfall.outbox.failed",
                source_id=row.source_id,
                role=row.role,
                scope_kind=row.scope_kind,
                scope_id=row.scope_id,
                year=row.year,
                retry_count=row.retry_count,
                error_type=error_type,
                error_message=error_message,
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
                error_type=error_type,
                error_message=error_message,
            )
            delayed += 1

    return {
        "processed": succeeded + failed + delayed,
        "succeeded": succeeded,
        "failed": failed,
        "delayed": delayed,
        "skipped": skipped,
    }


@celery_app.task(name="rainfall.process_outbox")
def process_outbox(db: Session | None = None, now: datetime | None = None) -> dict[str, int]:
    """Drain a bounded batch of pending rainfall outbox rows.

    ``now`` is the disclosure-date seam (design.md Interfaces): resolved
    once per batch in ``_process_outbox_batch`` so every row in one batch
    shares one instant, then threaded down to ``build_analysis`` through
    ``_process_outbox_row``. Deliberately NOT threaded: ``completed_at``,
    ``next_attempt_at`` and the backoff arithmetic, plus the
    ``next_attempt_at <= now`` claim predicate in ``claim_outbox_row`` —
    those stay on the real wall clock so a test clock can move the
    disclosure date without manufacturing a due retry or a fake completion
    timestamp.
    """
    if db is not None:
        return _process_outbox_batch(db, now)
    with SessionLocal() as db:
        return _process_outbox_batch(db, now)


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
        # Pass this session down (decision 2) so the checkpoint write and the
        # interval persistence share one transaction: a failure inside ingest
        # leaves the whole `with` block uncommitted, not a partially-written
        # checkpoint next to intervals that never actually landed.
        result = ingest_source_scope(**filters, db=db)
        checkpoint.completed_at = datetime.now(UTC)
        db.commit()
        return {"status": "completed", **result}
