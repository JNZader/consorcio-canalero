"""Celery tasks for Rainfall v2 ingest, revisit and backfill."""

import time
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
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

# design.md D2 / Ops.3: seconds paced between each backfilled year in
# backfill_baseline_range, so a real 1991-2020 run does not hammer the GEE
# quota. 5s is a guess pending the Ops.1 1991-only dry run; Ops.3 settles it
# from the observed real pace and adjusts this default if it proves wrong.
RAINFALL_BACKFILL_PACE_SECONDS = 5

# R4-204 (review-ledger.md "Pre-PR review — PR3"): celery_app.py's default
# `task_time_limit=600` applies here (this task is not in
# `RECOVERABLE_TASK_ANNOTATIONS`); a handful of slow rows (adapter-level
# timeout + retries, tasks.py `ResilientAdapter(..., timeout_seconds=60,
# max_retries=2)`) can approach it well before MAX_OUTBOX_BATCH rows are
# drained, and a hard SIGKILL there loses the chance to record a clean
# `batch_truncated` event or return a partial result. Decision 2c's
# per-row commit already makes a graceful early exit trivial -- nothing is
# lost by stopping BETWEEN rows: every prior row in this batch is already
# committed, and the remaining candidates are simply picked up by next
# minute's scheduled run (celery_app.py "rainfall-process-outbox"). Margin
# below the 600s hard limit is one worst-case row's own time budget.
PROCESS_OUTBOX_WALL_CLOCK_BUDGET_SECONDS = 420

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
    from app.domains.geo.rainfall import temporal
    from app.domains.geo.rainfall.adapters.gee_client import UnknownProviderScope, asset_name_for
    from app.domains.geo.rainfall.compute import (
        BASELINE_EVIDENCE_INVALID,
        BASELINE_SCOPE_UNMAPPED,
        baseline_cutoff_for,
        build_snapshot,
        data_revision_for,
        fingerprint_lock_key,
        revision_family,
        revision_write_decision,
        served_state,
    )
    from app.domains.geo.rainfall.models import RainfallAnalysisRevision
    from app.domains.geo.rainfall.policy import (
        RAINFALL_METRIC_POLICY,
        RAINFALL_METRIC_POLICY_REVISION,
    )
    from app.domains.geo.rainfall.repository import (
        BASELINE_SPAN_END,
        BASELINE_SPAN_START,
        DuplicateBaselineSlotError,
        RainfallRepository,
        acquire_fingerprint_lock,
        baseline_cumulatives,
        baseline_daily_values,
        intervals_in_window,
        persist_revision,
    )
    from app.domains.geo.rainfall.scope import AnalysisScope
    from app.domains.geo.rainfall.service import RAINFALL_HISTORICAL_SOURCE, fallback_used_for

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
    # design.md D6: widened from [year_start, year_end) so
    # antecedents.d90 (compute.py) can read up to 90 days into the PRIOR
    # year when comparison_end falls early in the analysis year --
    # year_start - 90d is the worst case across the whole year
    # (comparison_end == Jan 1), so it covers every d7/d30/d90 window for
    # any comparison_end within [Jan 1, Dec 31]. build_snapshot's own
    # in_window filter keeps annual.selected scoped to
    # [year_start, comparison_end) unchanged. Widening the read changes
    # data_revision_for's input, which is fine and expected: one new
    # revision per key on the next build.
    persisted = intervals_in_window(
        db,
        source_id=row.source_id,
        scope_kind=row.scope_kind,
        scope_id=row.scope_id,
        scope_version=row.scope_version,
        start=year_start - timedelta(days=90),
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

    # design.md D1: resolve the scope's historical baseline BEFORE building
    # the snapshot (comparison_end_date is computed independently here,
    # ahead of build_snapshot's own identical internal computation, purely
    # so this resolution can happen first — reused below instead of
    # re-derived from the returned envelope). A scope with no known
    # provider asset (the pre-existing basin gap, gee_client.py:42-45) must
    # not become a build crash: UnknownProviderScope is caught and
    # build_snapshot receives baseline=None (full suppression wiring
    # completes in slice 2a's annual.normal/percentile builder).
    #
    # design.md D5 amendment (slice 2b, LI2A-101): the baseline windows are
    # cut at the EFFECTIVE end this build reaches (compute.baseline_cutoff_for
    # over the same intervals build_snapshot is about to read), never at the
    # calendar comparison_end -- otherwise a lagging provider would rank a
    # selected year short by the lag against baselines totalled through
    # today. With no lag the two dates are identical.
    comparison_end_date = temporal.comparison_end(row.year, temporal.buenos_aires_date(now))
    baseline_unavailable_reason = BASELINE_SCOPE_UNMAPPED
    window_baseline_unavailable_reason = BASELINE_SCOPE_UNMAPPED
    try:
        baseline_asset = asset_name_for(scope.kind, scope.id)
    except UnknownProviderScope:
        baseline = None
        window_baseline = None
    else:
        try:
            baseline = baseline_cumulatives(
                db,
                source_id=RAINFALL_HISTORICAL_SOURCE,
                asset=baseline_asset,
                dates=temporal.baseline_dates(
                    baseline_cutoff_for(year=row.year, now=now, intervals=resolved)
                ),
            )
        except DuplicateBaselineSlotError as exc:
            # LI2B-004: a duplicated slot in ONE baseline year used to abort
            # the whole build -- annual, antecedents and intensity with it --
            # and no retry could fix it, because a retry cannot un-duplicate
            # persisted data. That made the key PERMANENTLY unbuildable and
            # made it the sharpest feeder of LI2B-001's re-enqueue loop.
            # Degrade instead: only the two metrics that actually read the
            # baseline lose their evidence, and they suppress with their own
            # honest reason while the rest of the snapshot still builds and
            # lands. The event is the loud part -- suppression alone would
            # look like an ordinary thin baseline to an operator.
            baseline = None
            baseline_unavailable_reason = BASELINE_EVIDENCE_INVALID
            record_event(
                "rainfall.baseline.duplicate_slots",
                source_id=exc.source_id,
                asset=exc.asset,
                baseline_year=exc.year,
                matched_rows=exc.matched,
                distinct_slots=exc.distinct_slots,
                scope_kind=row.scope_kind,
                scope_id=row.scope_id,
                scope_version=row.scope_version,
                year=row.year,
            )

        # design.md D2 (lluvia-antecedente-referencia): the WINDOW reference
        # reads the SAME provider-asset key as a raw daily series, bounded to
        # [1991-01-01, 2021-01-01). Its consumer
        # (`compute._antecedent_reference_metrics`) lands in the next slice;
        # the read is wired HERE, with its containment, because the
        # containment is the part that must never arrive late.
        #
        # A `try` OF ITS OWN, deliberately not the one above widened to cover
        # both reads. The wider scan sees duplicates `baseline_cumulatives`
        # STRUCTURALLY cannot -- its windows stop at each baseline year's
        # cutoff, so a duplicate later in a year is invisible there and
        # visible here -- so the two reads can disagree about baseline
        # validity within one build. That divergence is intended: same
        # evidence, two honest answers, because the two surfaces make
        # different claims. One shared handler would collapse them, and the
        # annual pair would suppress as `baseline_evidence_invalid` on a
        # duplicate its own read never met: a metric degraded by another
        # metric's evidence, with nothing on any surface to say so.
        #
        # And it must exist AT ALL for LI2B-004's reason: an escaping
        # exception makes the key permanently unbuildable (no retry can
        # un-duplicate persisted data) and feeds LI2B-001's re-enqueue loop.
        try:
            window_baseline = baseline_daily_values(
                db, source_id=RAINFALL_HISTORICAL_SOURCE, asset=baseline_asset
            )
        except DuplicateBaselineSlotError as exc:
            window_baseline = None
            window_baseline_unavailable_reason = BASELINE_EVIDENCE_INVALID
            # The loud part. Suppression alone reads to an operator as an
            # ordinary thin baseline; the numbers name the broken invariant.
            record_event(
                "rainfall.window_baseline.duplicate_slots",
                source_id=exc.source_id,
                asset=exc.asset,
                baseline_year=exc.year,
                matched_rows=exc.matched,
                distinct_slots=exc.distinct_slots,
                scope_kind=row.scope_kind,
                scope_id=row.scope_id,
                scope_version=row.scope_version,
                year=row.year,
            )

    snapshot = build_snapshot(
        scope=scope,
        year=row.year,
        role=row.role,
        source_id=row.source_id,
        intervals=resolved,
        batch=batch,
        now=now,
        # Task 4.1: documents every role/source divergence from spec.md's
        # named spec-primary candidate, not just the daily flip -- see
        # service.RAINFALL_SPEC_PRIMARY_SOURCE_BY_ROLE.
        fallback_used=fallback_used_for(row.role, row.source_id),
        baseline=baseline,
        baseline_unavailable_reason=baseline_unavailable_reason,
        # S2a task 3.0: the six window reference metrics consume THIS value --
        # the span-bounded read above, degraded by the handler above -- and
        # `compute.py` performs no read of its own. A second read there would
        # carry neither the [1991-01-01, 2021-01-01) bound nor the duplicate
        # containment, and every test of this read would have stayed green
        # while the served metrics ranked against a wider distribution. The
        # span travels WITH the values because it is the only thing that
        # separates a never-persisted day from a hole in the record.
        window_baseline=window_baseline,
        window_baseline_unavailable_reason=window_baseline_unavailable_reason,
        window_baseline_span=(
            temporal.utc_day(BASELINE_SPAN_START),
            temporal.utc_day(BASELINE_SPAN_END),
        ),
    )

    family = revision_family(batch["provider_revision"])
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
        # R2-002: read the incumbent's provenance through served_state()
        # itself, the single reader compute.py documents, instead of a raw
        # dict subscript that duplicated its logic and could KeyError on a
        # shape served_state already treats as merely "unknown". Guaranteed
        # non-None here: revision_write_decision only returns "latched"
        # when its own served_state(incumbent) call already succeeded.
        incumbent_state = (
            served_state(incumbent_snapshot) if incumbent_snapshot is not None else None
        )
        incumbent_source_id = incumbent_state[0] if incumbent_state is not None else None
        record_event(
            "rainfall.build.latched",
            data_revision=data_revision,
            source_id=row.source_id,
            incumbent_source_id=incumbent_source_id,
        )
        return {"revision_id": None, "data_revision": data_revision, "decision": decision}
    elif decision == "gate_refused":
        # design.md "No backoff in v1": every refusal is instrumented so a
        # future backoff constant has real provider-lag evidence to use.
        # R2-008: flat scope_kind/scope_id/scope_version/year fields, the
        # same shape rainfall.finalization.skipped uses (tasks.py
        # _revisit_stage2) -- was a nested `scope` dict, the only event in
        # this module that shaped its scope that way.
        metric = snapshot["annual"]["selected"]
        record_event(
            "rainfall.finalization.gate_refused",
            scope_kind=row.scope_kind,
            scope_id=row.scope_id,
            scope_version=row.scope_version,
            year=row.year,
            coverage=metric["coverage"],
            completeness=metric["completeness"],
            quality_score=metric["quality"]["score"],
        )
        return {"revision_id": None, "data_revision": data_revision, "decision": decision}
    elif decision != "write":
        # R2-005: revision_write_decision's return type is
        # Literal["write", "latched", "gate_refused"] (compute.py); this is
        # the explicit fail-loud branch for anything else, replacing what
        # was previously a silent fall-through into the write path below.
        raise ValueError(f"revision_write_decision returned unrecognized decision: {decision!r}")

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


def _revisit_stage1(db: Session, *, current_year: int) -> dict[str, int]:
    """Current-Year Revisit Cycle: append a fresh ``pending`` row per
    current-year ``done`` key so a materialized snapshot never freezes for
    the rest of the year (design.md "Current-Year Revisit Cycle"). The
    candidate set is rotated (C2 -- see
    ``repository.current_year_done_keys``), so a key sorted past the batch
    cursor still gets reached within a bounded number of sweeps rather than
    starving forever."""
    from sqlalchemy.exc import IntegrityError

    from app.domains.geo.rainfall.repository import current_year_done_keys, pending_row_for_key
    from app.domains.geo.rainfall.service import carryover_labels

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
        if pending_row_for_key(db, **key) is not None:
            record_event("rainfall.revisit.skipped", reason="pending_in_flight", **key)
            skipped += 1
            continue

        db.add(
            RainfallOutbox(
                **key,
                # LI2B-003: `outcome:` markers describe ONE build's decision,
                # not the work -- a fresh attempt must not inherit the
                # previous one's refusal, or the read path would back off on
                # a key that has since been rebuilt.
                work_labels=carryover_labels(row.work_labels),
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


def _revisit_stage2(db: Session, *, now: datetime) -> dict[str, int]:
    """Year-Rollover Finalization: transition a completed-year key off its
    provisional satellite source once CHIRPS v3 Final is adequate
    (design.md "Year-Rollover Finalization"). Selection is on the SERVED
    snapshot's own provenance -- never on outbox history, which
    self-extinguishes on the first gated refusal.

    R2-007: derives ``current_year`` from ``now.year`` internally instead
    of taking it as a separate parameter -- the caller (``_revisit_stale``)
    always computed it as ``now.year`` in the first place (design.md
    "Current-Year Revisit Cycle" step 1: both stages share the same clock),
    so carrying both was a redundant, driftable pair.
    """
    from sqlalchemy.exc import IntegrityError

    from app.domains.geo.rainfall.compute import served_state
    from app.domains.geo.rainfall.repository import (
        RainfallRepository,
        completed_year_daily_done_keys,
        pending_row_for_key,
    )
    from app.domains.geo.rainfall.service import (
        RAINFALL_HISTORICAL_SOURCE,
        carryover_labels,
        resolve_missing_work_source,
    )

    current_year = now.year
    scanned = 0
    enqueued = 0
    skipped = 0
    terminated = 0
    for row in completed_year_daily_done_keys(db, before_year=current_year, limit=MAX_OUTBOX_BATCH):
        scanned += 1
        # R2-008: flat scope_kind/scope_id/scope_version/year fields, the
        # same shape rainfall.finalization.gate_refused now uses
        # (tasks._persist_analysis_revision) -- was missing scope_version.
        scope = {
            "scope_kind": row.scope_kind,
            "scope_id": row.scope_id,
            "scope_version": row.scope_version,
            "year": row.year,
        }

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
            # C1 (review-ledger.md "Pre-PR review — PR3"): selection now
            # genuinely stops for this key via
            # repository.completed_year_daily_done_keys's own SQL
            # exclusion (a lateral read of the same served-state pair,
            # relying on the latch's guarantee that a provisional revision
            # is never written over a final incumbent) -- a terminated key
            # should no longer even reach this loop. This branch stays as
            # defense-in-depth for the race the SQL check's docstring
            # documents (a final revision landing between the SQL scan and
            # this read) and now counts into the accounting (R2-004)
            # instead of silently `continue`-ing, so
            # scanned == enqueued + skipped + terminated closes.
            terminated += 1
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

        if pending_row_for_key(db, **key) is not None:
            record_event("rainfall.finalization.skipped", reason="pending_in_flight", **scope)
            skipped += 1
            continue

        db.add(
            RainfallOutbox(
                **key,
                # LI2B-003: `outcome:` markers are stripped here for the same
                # reason as in stage 1 -- a finalization retry is a NEW
                # attempt, not an inheritance of the refusal that made this
                # key a candidate in the first place.
                work_labels=list(
                    {*carryover_labels(row.work_labels), f"role:{work['role']}", "finalization"}
                ),
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

    return {
        "scanned": scanned,
        "enqueued": enqueued,
        "skipped": skipped,
        "terminated": terminated,
    }


def _revisit_stale(db: Session, now: datetime | None, retry: Any = None) -> dict[str, int]:
    """R2-006: unlike its siblings (``ingest_source_scope``/``build_analysis``,
    decision 2 -- given a ``db``, write through it and NEVER commit), stage
    1 and stage 2 both COMMIT PER ROW through the given session, not just
    when they opened their own. This is a deliberate exception, not an
    oversight: the sweep's own per-key work has no caller-owned transaction
    to defer to (there is no "batch" transaction the way
    ``_process_outbox_batch`` re-claims rows into), so each row commits the
    moment its own INSERT lands, exactly like decision 2c's per-row commit
    in the outbox consumer.

    Stage 1 runs inside its own try/except (R4-203 -- review-ledger.md
    "Pre-PR review — PR3"): an unexpected exception there is recorded via
    ``rainfall.revisit.failed`` instead of aborting the whole sweep, and
    stage 2 still runs this cycle -- a completed year's provisional-to-final
    transition must not go a day late just because stage 1 hit a transient
    error. When *retry* is supplied (the bound Celery task's ``self.retry``,
    restored on ``revisit_stale`` below after the two-stage rewrite dropped
    ``bind=True``/``max_retries`` without an equivalent), the task retries
    once BOTH stages have already run and their events are recorded, giving
    stage 1 a near-term second attempt instead of waiting for tomorrow's
    Beat cycle.
    """
    sweep_now = now or datetime.now(UTC)
    current_year = sweep_now.year

    stage1_exc: Exception | None = None
    try:
        stage1 = _revisit_stage1(db, current_year=current_year)
    except Exception as exc:  # noqa: BLE001 -- stage 1 must not block stage 2
        db.rollback()
        stage1_exc = exc
        stage1 = {"scanned": 0, "enqueued": 0, "skipped": 0}
        record_event(
            "rainfall.revisit.failed",
            error_type=type(exc).__name__,
            error_message=str(exc)[:200],
        )
    else:
        record_event(
            "rainfall.revisit.completed",
            revisit_scanned=stage1["scanned"],
            revisit_enqueued=stage1["enqueued"],
            revisit_skipped=stage1["skipped"],
            truncated=stage1["scanned"] == MAX_OUTBOX_BATCH,
        )

    stage2 = _revisit_stage2(db, now=sweep_now)
    record_event(
        "rainfall.finalization.completed",
        finalization_scanned=stage2["scanned"],
        finalization_enqueued=stage2["enqueued"],
        finalization_skipped=stage2["skipped"],
        finalization_terminated=stage2["terminated"],
        truncated=stage2["scanned"] == MAX_OUTBOX_BATCH,
    )

    result = {
        "scanned": stage1["scanned"],
        "enqueued": stage1["enqueued"],
        "skipped": stage1["skipped"],
        "finalization_scanned": stage2["scanned"],
        "finalization_enqueued": stage2["enqueued"],
        "finalization_skipped": stage2["skipped"],
        "finalization_terminated": stage2["terminated"],
    }

    if stage1_exc is not None and retry is not None:
        # Both stages already ran and their events are already recorded
        # above; retry() raises (Celery's own Retry when running through a
        # worker, or the original exception when called directly, as in
        # tests) to get stage 1 a near-term second attempt.
        raise retry(exc=stage1_exc, countdown=300) from stage1_exc

    return result


@celery_app.task(name="rainfall.revisit_stale", bind=True, max_retries=2)
def revisit_stale(self, db: Session | None = None, now: datetime | None = None) -> dict[str, int]:
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

    ``bind=True``/``max_retries=2`` restored (R4-203 -- review-ledger.md
    "Pre-PR review — PR3"): the archived per-key version of this task
    carried both; PR3's two-stage rewrite dropped them without an
    equivalent, silencing a stage-1 failure until tomorrow's Beat cycle
    instead of retrying it. ``self.retry`` is threaded into
    ``_revisit_stale`` and used only AFTER stage 2 has already run this
    cycle -- see that function's docstring.
    """
    if db is not None:
        return _revisit_stale(db, now, retry=self.retry)
    with SessionLocal() as local_db:
        return _revisit_stale(local_db, now, retry=self.retry)


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
    from app.domains.geo.rainfall.service import NON_WRITE_DECISIONS, outcome_label

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

    built = build_analysis(outbox_id=str(row.id), batch=batch, db=db, now=now)

    # LI2B-003: `revision_write_decision` can refuse to write ("latched" or
    # "gate_refused", both instrumented as events inside
    # _persist_analysis_revision) while this row still finishes cleanly --
    # the work RAN, it just produced no new revision. Marking the row `done`
    # with nothing else to show for it left the served snapshot stale AND
    # indistinguishable from a productive `done`, so the request path had no
    # way to back its re-enqueue off (service._requeue_cooldown) and the key
    # stayed permanently stale and permanently hot. `work_labels` is the only
    # schema-compatible place to stamp this (RainfallOutbox has no
    # result/note column); the list is REBOUND, never mutated in place, so
    # the JSON column is actually marked dirty.
    decision = (built or {}).get("decision")
    if decision in NON_WRITE_DECISIONS:
        marker = outcome_label(decision)
        if marker not in row.work_labels:
            row.work_labels = [*row.work_labels, marker]

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

    R4-204 (review-ledger.md "Pre-PR review — PR3"): the loop also bails
    out cleanly once ``PROCESS_OUTBOX_WALL_CLOCK_BUDGET_SECONDS`` has
    elapsed, checked BETWEEN rows (never mid-row) -- every row already
    processed this cycle is already committed (decision 2c), so stopping
    here loses nothing; it only trades a possible hard SIGKILL at
    celery_app.py's ``task_time_limit=600`` for a clean early return and an
    observable ``rainfall.outbox.batch_truncated`` event.
    """
    build_now = now or datetime.now(UTC)
    batch_started = time.monotonic()
    candidate_ids = (
        db.execute(
            select(RainfallOutbox.id)
            .where(RainfallOutbox.status == "pending")
            .where(RainfallOutbox.next_attempt_at <= datetime.now(UTC))
            # BL-ORDER-BY-CREATED-AT-SWEEP: `created_at` is a
            # `server_default=func.now()`, i.e. the TRANSACTION timestamp, so every
            # row enqueued by one request ties exactly. With a LIMIT on top, the tie
            # decides which rows enter the batch AT ALL -- heap order, re-evaluated
            # each cycle, which is how one row gets skipped repeatedly. `id` breaks
            # it deterministically; FIFO across transactions is unchanged.
            .order_by(RainfallOutbox.created_at, RainfallOutbox.id)
            .limit(MAX_OUTBOX_BATCH)
        )
        .scalars()
        .all()
    )

    succeeded = 0
    failed = 0
    delayed = 0
    skipped = 0
    for index, outbox_id in enumerate(candidate_ids):
        if time.monotonic() - batch_started > PROCESS_OUTBOX_WALL_CLOCK_BUDGET_SECONDS:
            record_event(
                "rainfall.outbox.batch_truncated",
                processed=index,
                remaining=len(candidate_ids) - index,
            )
            break

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


def backfill_baseline_range(
    asset: str,
    *,
    years: Iterable[int] = range(1991, 2021),
    source_id: str = "chirps-v3-final",
    role: str = "historical",
) -> dict[str, Any]:
    """One-shot 1991-2020 historical baseline backfill orchestrator
    (design.md D2).

    Reuses :func:`backfill_missing` verbatim per ``(source_id, role,
    "provider_asset", asset, BASELINE_ASSET_VERSION, year)`` key -- the key
    IS the asset (D1), so N zone scopes sharing one asset cost 30
    reductions total, never 30N: a caller resolves the shared asset once
    and calls this function once per asset, not once per zone scope.
    Idempotent by :func:`backfill_missing`'s own per-key checkpoint
    short-circuit: an interrupted run resumes at the first year without
    ``completed_at`` and re-fetches nothing already completed.

    Stops **labelled** -- never a bare traceback -- on
    ``(AdapterError, CircuitOpen)``, both explicitly (Judgment Day round 1,
    LIA-004): ``CircuitOpen`` is raised by
    ``ResilientAdapterState.can_attempt()`` (resilience.py) OUTSIDE the
    retry loop that turns provider failures into ``AdapterError``, so it
    bypasses ``ingest_source_scope``'s own ``except AdapterError`` and
    would otherwise escape here raw on exactly the realistic rerun. Bare
    ``RuntimeError`` is deliberately not caught -- it would relabel a
    genuine bug (from the session, ``_run_with_timeout``, or Celery itself)
    as a clean quota stop. The circuit is Redis-backed per role and
    persists ~300s ACROSS PROCESSES (resilience.py), so a rerun inside that
    window is expected to stop again immediately with the same labelled
    event -- see ``backfill_cli.py``'s runbook note.
    """
    from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION
    from app.domains.geo.rainfall.adapters.resilience import AdapterError, CircuitOpen

    years_list = list(years)
    completed: list[int] = []
    for index, year in enumerate(years_list):
        try:
            result = backfill_missing(
                source_id=source_id,
                role=role,
                scope_kind="provider_asset",
                scope_id=asset,
                scope_version=BASELINE_ASSET_VERSION,
                year=year,
            )
        except (AdapterError, CircuitOpen) as exc:
            reason = "circuit_open" if isinstance(exc, CircuitOpen) else "adapter_error"
            record_event("rainfall.backfill.stopped", asset=asset, year=year, reason=reason)
            return {
                "stopped": True,
                "reason": reason,
                "year": year,
                "completed_years": completed,
            }

        completed.append(year)
        record_event("rainfall.backfill.year", asset=asset, year=year, status=result["status"])
        if index < len(years_list) - 1:
            time.sleep(RAINFALL_BACKFILL_PACE_SECONDS)

    return {"stopped": False, "completed_years": completed}
