"""Snapshot serialization keeps JSON and CSV state/provenance semantics identical."""

import csv
import hashlib
import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from math import isfinite
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.domains.geo.rainfall.metrics import record_event
from app.domains.geo.rainfall.models import RainfallOutbox
from app.domains.geo.rainfall.policy import MetricThresholdPolicy, apply_metric_policy
from app.domains.geo.rainfall.schemas import MetricResult

METRIC_GROUPS = ("annual", "antecedents", "intensity")

RAINFALL_HISTORICAL_SOURCE = "chirps-v3-final"
# TODO(smn): SQPE-OBS has no GEE catalog entry (SMN NetCDF distribution,
# tasks._concrete_fetch) and no per-role eligibility outcome has been
# recorded for the daily role under "Source Eligibility Validation Gate".
# Task 4.1 (rainfall-materialization PR 4, design.md decision 7): interim
# default under the daily role's MAY-fallback clause (delta spec
# "Evidence-Gated Source Roles" MODIFIED requirement) -- a deliberate,
# tracked deviation, not a completed validation. Swap back to "sqpe-obs"
# once an SMN adapter exists.
RAINFALL_DAILY_SOURCE = "chirps-v3-sat"
RAINFALL_INTENSITY_SOURCE = "sinarame-rqpe"
# Task 3.18: matches adapters/manifests.py's validation-role candidate
# (`smn-gauge`, singular) -- was `smn-gauges`, a typo that never matched.
RAINFALL_VALIDATION_SOURCE = "smn-gauge"

# Task 4.1: spec.md's NAMED spec-primary candidate per role -- distinct
# from the constants above, which are what the system actually resolves to
# right now. For every role except "daily" the two agree today. "daily"
# is the one deliberate divergence (RAINFALL_DAILY_SOURCE's TODO(smn)
# above): spec.md:206 names SQPE-OBS as the daily candidate, but the
# system serves chirps-v3-sat under the daily MAY-fallback clause until an
# SMN adapter exists. `fallback_used_for` is the single place this table
# is read, so a future eligibility change updates exactly one dict entry.
RAINFALL_SPEC_PRIMARY_SOURCE_BY_ROLE: dict[str, str] = {
    "historical": RAINFALL_HISTORICAL_SOURCE,
    "daily": "sqpe-obs",
    "intensity": RAINFALL_INTENSITY_SOURCE,
    "validation": RAINFALL_VALIDATION_SOURCE,
}


def fallback_used_for(role: str, source_id: str) -> bool:
    """True when *source_id* -- the source actually resolved and used for
    *role* -- diverges from spec.md's named spec-primary candidate for
    that role (delta spec "Evidence-Gated Source Roles" MODIFIED
    requirement). Feeds `provenance.fallback_used` on every persisted
    snapshot: `compute.build_snapshot`'s `fallback_used` parameter, threaded
    in from `tasks._persist_analysis_revision`. An unmapped role reports no
    divergence rather than raising -- `resolve_missing_work_source` is the
    sole source of truth for which roles exist; this function only compares,
    it never routes.
    """
    primary = RAINFALL_SPEC_PRIMARY_SOURCE_BY_ROLE.get(role)
    return primary is not None and primary != source_id


# decision 6: skip request-path re-enqueue when a `done` row for the same
# key completed within this window, regardless of whether a revision
# exists -- see queue_missing_analysis. Engineering guess tuned to the 5s
# frontend poll; confirm against real GEE quota headroom (Open Questions).
RAINFALL_RECOMPUTE_COOLDOWN = timedelta(minutes=10)

# LI2B-001 (review-ledger.md "Slice 2b -- resilience lens + general
# refuter"): a key whose newest terminal row is `failed` matched NEITHER the
# recent-`done` cooldown above NOR the pending pre-check below, so every poll
# started a fresh MAX_RETRIES cycle. For a TRANSIENT failure that is merely
# wasteful; for a DETERMINISTIC compute-time failure (ingest succeeds, so the
# adapter's circuit breaker never trips and each attempt is a real full-year
# GEE fetch) it never terminates on its own -- neither sweep resurrects a
# `failed` key, so the request path is the only thing that can, and the only
# thing that must be bounded.
#
# 6 hours is chosen against BOTH failure shapes: a transient failure heals on
# the first read after the cooldown lapses (well inside one working day), and
# a deterministic one is capped at <= 4 retry cycles per day instead of one
# per poll. Shorter would not meaningfully speed up the transient case --
# nothing that fails deterministically becomes fixable in minutes -- while
# multiplying the deterministic burn.
RAINFALL_FAILED_REQUEUE_COOLDOWN = timedelta(hours=6)

# LI2B-003: a `done` row whose build returned a NON-WRITE decision
# ("latched"/"gate_refused", compute.revision_write_decision) served nothing
# new and cannot be healed by retrying sooner -- only by upstream data
# improving. Its re-enqueue therefore backs off to the cadence of the write
# gate's own daily sweep (celery_app.py's `rainfall.revisit_stale` beat)
# rather than the 10-minute recompute cooldown that governs a PRODUCTIVE
# `done`. Without this, a post-rollover key sat permanently stale AND
# permanently hot: one full-year ingest every ten minutes, forever, with no
# progress possible until the provider published adequate Final data.
RAINFALL_REFUSED_REQUEUE_COOLDOWN = timedelta(days=1)

# LI2B-003: the outbox row's own record of a build that refused to write.
# `work_labels` is the only schema-compatible place to stamp it (RainfallOutbox
# has no result/note column, models.py), so outcome markers live in their own
# `outcome:` namespace and are STRIPPED whenever the sweeps copy a row's labels
# forward (tasks._carryover_labels) -- a marker describes ONE build's outcome,
# never the work itself, and a healed key must not inherit it.
OUTCOME_LABEL_PREFIX = "outcome:"
NON_WRITE_DECISIONS = ("latched", "gate_refused")


def outcome_label(decision: str) -> str:
    """The `work_labels` marker for a build *decision* (LI2B-003)."""
    return f"{OUTCOME_LABEL_PREFIX}{decision}"


def carryover_labels(labels: Any) -> list[str]:
    """*labels* minus every `outcome:` marker -- what a NEW outbox row may
    inherit from an older row for the same key."""
    return [label for label in labels if not str(label).startswith(OUTCOME_LABEL_PREFIX)]


def non_write_outcome(row: RainfallOutbox) -> str | None:
    """The non-write decision *row*'s build recorded, or ``None`` when it
    recorded none (a productive `done`, or a row written before LI2B-003)."""
    labels = set(row.work_labels or ())
    for decision in NON_WRITE_DECISIONS:
        if outcome_label(decision) in labels:
            return decision
    return None


def _parse_event_window(event_window: dict[str, Any] | None) -> tuple[datetime, datetime] | None:
    if event_window is None:
        return None
    start = event_window.get("start")
    end = event_window.get("end")
    if not isinstance(start, str) or not isinstance(end, str):
        return None
    try:
        parsed_start = datetime.fromisoformat(start.replace("Z", "+00:00"))
        parsed_end = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    if (
        parsed_start.utcoffset() is None
        or parsed_end.utcoffset() is None
        or parsed_end <= parsed_start
    ):
        return None
    return parsed_start, parsed_end


def resolve_missing_work_source(
    event_window: dict[str, Any] | None,
    year: int,
    *,
    requested_role: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Map a public analysis request to the configured source, role and
    interval bounds.

    ``now`` is the sweep-stage-2 re-resolution seam (design.md Interfaces):
    it feeds EXACTLY the ``year == now.year`` routing test below and nothing
    else -- ``requested_role``/``event_window`` are tested first and the
    interval bounds derive from ``year`` alone. Threaded IN from
    ``revisit_stale``'s stage 2 (Year-Rollover Finalization step 6);
    deliberately NOT threaded from the request path -- ``read_analysis`` ->
    ``queue_missing_analysis`` leaves it unset, so a live request always
    routes on the real clock. Defaults to ``datetime.now(UTC)``.
    """
    if requested_role == "validation":
        source_id = RAINFALL_VALIDATION_SOURCE
        role = "validation"
    elif event_window is not None:
        source_id = RAINFALL_INTENSITY_SOURCE
        role = "intensity"
    elif year == (now or datetime.now(UTC)).year:
        source_id = RAINFALL_DAILY_SOURCE
        role = "daily"
    else:
        source_id = RAINFALL_HISTORICAL_SOURCE
        role = "historical"

    window = _parse_event_window(event_window)
    if window is not None:
        interval_start, interval_end = window
    else:
        interval_start = datetime(year, 1, 1, tzinfo=UTC)
        interval_end = datetime(year + 1, 1, 1, tzinfo=UTC)

    return {
        "source_id": source_id,
        "role": role,
        "interval_start": interval_start,
        "interval_end": interval_end,
    }


SNAPSHOT_ROOT_KEYS = {
    "analysis_revision_id",
    # design.md D3 (slice 3a): the revision's own content address, injected at
    # disclosure time from the served row exactly as `analysis_revision_id` is
    # -- `build_snapshot` cannot set it, since it is computed AFTER the
    # snapshot exists (`tasks._persist_analysis_revision`). Disclosing it is
    # what makes the client half of the series consistency check possible: the
    # /series echo compared against the snapshot the tab is holding.
    "data_revision",
    "scope",
    "regional_estimate",
    "year",
    "comparison_end",
    "baseline",
    "annual",
    "antecedents",
    "intensity",
    "summary",
    "source_health",
    "metric_policy",
}


class SnapshotContractError(ValueError):
    """Persisted snapshot does not match the canonical disclosure envelope."""


def analysis_request_fingerprint(request: Any) -> str:
    """Build the server-owned immutable lookup key from the public request."""
    if hasattr(request, "model_dump"):
        request = request.model_dump(mode="json", exclude_none=True)
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _default_request_fingerprint(
    *, scope: Any, year: int, event_window: dict[str, Any] | None
) -> str:
    """Fallback fingerprint for a caller that does not pass one explicitly
    (decision 4). Mirrors router.py's own request-dict construction exactly,
    including OMITTING ``event_window`` entirely when it is ``None`` rather
    than setting it — ``analysis_request_fingerprint``'s JSON canonicalization
    does not treat a present-but-null key the same as an absent one, so a
    careless recompute here would silently diverge from the router's own
    fingerprint for the identical request."""
    request: dict[str, Any] = {
        "scope": {"kind": scope.kind, "id": scope.id, "version": scope.version},
        "year": year,
    }
    if event_window is not None:
        request["event_window"] = event_window
    return analysis_request_fingerprint(request)


def _reused_outbox_response(
    row: RainfallOutbox, *, source: dict[str, Any], scope: Any, year: int
) -> dict[str, Any]:
    """R2-003 (review-ledger.md "Pre-PR review — PR3"): the two "found an
    existing pending row for this key" branches in ``queue_missing_analysis``
    below -- the upfront pre-check hit, and the post-``IntegrityError``
    re-read after losing a real race -- emitted and returned the identical
    shape; this is their one implementation.
    """
    record_event(
        "rainfall.outbox.reused",
        source_id=source["source_id"],
        role=source["role"],
        scope_kind=scope.kind,
        scope_id=scope.id,
        scope_version=scope.version,
        year=year,
        labels=row.work_labels,
    )
    return {
        "status": "queued",
        "outbox_id": str(row.id),
        "scope": {"kind": scope.kind, "id": scope.id, "version": scope.version},
        "year": year,
        "labels": row.work_labels,
    }


def _requeue_cooldown(
    db: Any, *, key: dict[str, Any], now: datetime
) -> tuple[RainfallOutbox, str, timedelta] | None:
    """The request path's re-enqueue cooldowns, in precedence order, or
    ``None`` when this key may be enqueued.

    Three windows, one per terminal shape a key's history can be in:

    1. ``recent_done`` within ``RAINFALL_RECOMPUTE_COOLDOWN`` (10 min,
       decision 6) -- the hot path, unchanged, evaluated first because it is
       the cheapest and by far the most common.
    2. the key's newest terminal row is ``failed`` and went terminal within
       ``RAINFALL_FAILED_REQUEUE_COOLDOWN`` (6 h, LI2B-001).
    3. the key's newest terminal row is a ``done`` whose build REFUSED to
       write, within ``RAINFALL_REFUSED_REQUEUE_COOLDOWN`` (24 h, LI2B-003).

    2 and 3 read the NEWEST terminal row rather than "any row in the window"
    (``repository.latest_terminal_attempt``), so a key that failed or was
    refused and has since been healed reports its healthy ``done`` row and is
    not suppressed by its own history.
    """
    from app.domains.geo.rainfall.repository import latest_terminal_attempt, recent_done

    # decision 6: a recent `done` row for this key skips re-enqueue
    # REGARDLESS of whether a revision exists -- a time-bounded skip stops
    # the per-poll GEE burn while letting a done-without-revision heal
    # itself once the cooldown lapses.
    recent = recent_done(db, **key, since=now - RAINFALL_RECOMPUTE_COOLDOWN)
    if recent is not None:
        return recent, "recent_done", RAINFALL_RECOMPUTE_COOLDOWN

    terminal = latest_terminal_attempt(db, **key)
    if terminal is None:
        return None
    # `done` rows are dated by completed_at, `failed` rows only by updated_at
    # -- see latest_terminal_attempt's docstring for why not next_attempt_at.
    attempted_at = terminal.completed_at or terminal.updated_at

    if terminal.status == "failed":
        if attempted_at >= now - RAINFALL_FAILED_REQUEUE_COOLDOWN:
            return terminal, "terminal_failed", RAINFALL_FAILED_REQUEUE_COOLDOWN
        return None

    decision = non_write_outcome(terminal)
    if decision is not None and attempted_at >= now - RAINFALL_REFUSED_REQUEUE_COOLDOWN:
        return terminal, f"non_write_{decision}", RAINFALL_REFUSED_REQUEUE_COOLDOWN
    return None


def queue_missing_analysis(
    db: Any,
    *,
    scope: Any,
    year: int,
    labels: tuple[str, ...] = ("analysis_missing",),
    event_window: dict[str, Any] | None = None,
    requested_role: str | None = None,
    request_fingerprint: str | None = None,
) -> dict[str, Any]:
    from app.domains.geo.rainfall.repository import pending_row_for_key

    fingerprint = request_fingerprint or _default_request_fingerprint(
        scope=scope, year=year, event_window=event_window
    )
    source = resolve_missing_work_source(event_window, year, requested_role=requested_role)
    key = {
        "source_id": source["source_id"],
        "role": source["role"],
        "scope_kind": scope.kind,
        "scope_id": scope.id,
        "scope_version": scope.version,
        "year": year,
    }

    cooldown = _requeue_cooldown(db, key=key, now=datetime.now(UTC))
    if cooldown is not None:
        row, reason, window = cooldown
        record_event(
            "rainfall.outbox.cooldown",
            **key,
            outbox_id=str(row.id),
            reason=reason,
            cooldown_seconds=int(window.total_seconds()),
        )
        return {
            "status": "queued",
            "outbox_id": str(row.id),
            "scope": {"kind": scope.kind, "id": scope.id, "version": scope.version},
            "year": year,
            "labels": row.work_labels,
        }

    existing = pending_row_for_key(db, **key)
    if existing is not None:
        return _reused_outbox_response(existing, source=source, scope=scope, year=year)

    labels_with_role = tuple({*labels, f"role:{source['role']}"})
    outbox = RainfallOutbox(
        source_id=source["source_id"],
        role=source["role"],
        scope_kind=scope.kind,
        scope_id=scope.id,
        scope_version=scope.version,
        year=year,
        work_labels=list(labels_with_role),
        interval_start=source["interval_start"],
        interval_end=source["interval_end"],
        request_fingerprint=fingerprint,
    )
    db.add(outbox)
    try:
        db.flush()
        db.commit()
    except IntegrityError:
        # decision 8's discipline (task 3.18): two identical requests can
        # both pass the `existing` pre-check above before either commits --
        # the race window the check alone cannot close. The loser's own
        # INSERT collides with the winner's now-committed row on
        # ix_rainfall_outbox_pending_unique; rolling back and re-reading
        # that row is a reuse, not a failure, so both callers still get a
        # 202 with the SAME outbox_id.
        db.rollback()
        reused = pending_row_for_key(db, **key)
        if reused is None:
            # The constraint guarantees a matching row exists; a lost race
            # that skipped it would mean the constraint itself is wrong.
            raise RuntimeError(
                "queue_missing_analysis hit IntegrityError but found no matching "
                f"pending row (source_id={source['source_id']!r}, role={source['role']!r}, "
                f"scope={scope.kind}/{scope.id}/{scope.version}, year={year})"
            ) from None
        return _reused_outbox_response(reused, source=source, scope=scope, year=year)

    record_event(
        "rainfall.outbox.queued",
        source_id=source["source_id"],
        role=source["role"],
        scope_kind=scope.kind,
        scope_id=scope.id,
        scope_version=scope.version,
        year=year,
        labels=list(labels_with_role),
    )
    return {
        "status": "queued",
        "outbox_id": str(outbox.id),
        "scope": {"kind": scope.kind, "id": scope.id, "version": scope.version},
        "year": year,
        "labels": list(labels_with_role),
    }


def _metric_policy(
    snapshot: dict[str, Any], expected_revision: str
) -> MetricThresholdPolicy | None:
    raw = snapshot.get("metric_policy")
    if not isinstance(raw, dict) or raw.get("revision") != expected_revision:
        return None
    coverage = raw.get("minimum_coverage_by_metric")
    quality = raw.get("minimum_quality_by_metric")
    duration = raw.get("duration_threshold")
    if not isinstance(coverage, dict) or not isinstance(quality, dict):
        return None
    if duration is not None and (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not isfinite(duration)
    ):
        return None
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or not 0 <= value <= 1
        for values in (coverage, quality)
        for value in values.values()
    ):
        return None
    if duration is not None and duration < 0:
        return None
    return MetricThresholdPolicy(expected_revision, coverage, quality, duration)


def _unavailable(metric: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "metric": metric.get("metric", "unknown"),
        "value": None,
        "state": "unavailable",
        "reason": reason,
    }


def _is_finite_metric_value(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)


def _normalize_metric(
    raw: dict[str, Any], policy: MetricThresholdPolicy | None, expected_revision: str
) -> dict[str, Any]:
    raw_value = raw.get("value")
    if raw_value is not None and not _is_finite_metric_value(raw_value):
        return _unavailable(raw, "metric_contract_invalid")
    if any(not _is_finite_metric_value(raw.get(field)) for field in ("coverage", "completeness")):
        return _unavailable(raw, "metric_contract_invalid")
    try:
        metric = MetricResult.model_validate(raw)
    except (TypeError, ValidationError):
        return _unavailable(raw, "metric_contract_invalid")
    if metric.revision != expected_revision:
        return _unavailable(raw, "policy_revision_mismatch")
    if metric.state in {"suppressed", "unavailable"}:
        return {**raw, "value": None}
    if policy is None:
        return _unavailable(raw, "policy_unavailable")
    score = metric.quality.get("score")
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not isfinite(score)
        or not 0 <= score <= 1
    ):
        return _unavailable(raw, "metric_quality_invalid")
    applied = apply_metric_policy(
        policy,
        metric.metric,
        value=metric.value,
        coverage=metric.coverage,
        quality_score=score,
        completeness=metric.completeness,
    )
    state = (
        metric.state
        if metric.state == "partial" and applied.state == "available"
        else applied.state
    )
    return {**raw, "value": applied.value, "state": state, "reason": applied.reason}


# ---------------------------------------------------------------------------
# The disclosure-time summary (design.md D4, lluvia-insights slice 2b)
# ---------------------------------------------------------------------------

# Same vocabulary the panel prints beside the narrative
# (consorcio-web/.../rainfall/rainfallFormat.ts): the coherence invariant is
# about what a reader sees, so the summary must name a metric the way its own
# badge does. An unknown key falls back to the key itself, exactly as
# `metricLabel` does on the client.
SUMMARY_METRIC_LABELS: dict[str, str] = {
    "selected": "Acumulado del año",
    "normal": "Normal 1991–2020",
    "percentile": "Percentil histórico",
    "d7": "Antecedente 7 días",
    "d30": "Antecedente 30 días",
    "d90": "Antecedente 90 días",
    "p30": "P30",
    "p60": "P60",
    "p3h": "P3h",
    "p24h": "P24h",
    "i30": "I30",
    "i60": "I60",
    "peak": "Pico del evento",
    "duration": "Duración del evento",
}

SUMMARY_STATE_LABELS: dict[str, str] = {
    "available": "disponible",
    "partial": "parcial",
    "suppressed": "suprimida",
    "unavailable": "no disponible",
}

SUMMARY_AVAILABLE_PREFIX = "Disponibles:"
SUMMARY_PARTIAL_PREFIX = "Parciales:"
SUMMARY_MISSING_PREFIX = "Sin dato:"
SUMMARY_EMPTY = "Este análisis no divulga métricas."


def _summary_entry(name: str, metric: dict[str, Any]) -> str:
    """One metric's phrase. Reads ``state``/``reason``/``value`` -- the three
    fields the policy owns -- plus ``unit``, which policy never rewrites and
    without which "204.0" and "50.0" would be indistinguishable millimetres
    and percentiles in the same sentence."""
    label = SUMMARY_METRIC_LABELS.get(name, name)
    state = metric.get("state")
    if state in {"available", "partial"} and _is_finite_metric_value(metric.get("value")):
        unit = metric.get("unit")
        measured = f"{metric['value']:.1f}"
        return (
            f"{label} {measured} {unit}"
            if isinstance(unit, str) and unit
            else f"{label} {measured}"
        )
    state_label = SUMMARY_STATE_LABELS.get(state, "estado desconocido")
    reason = metric.get("reason")
    if isinstance(reason, str) and reason:
        return f"{label} ({state_label}: {reason})"
    return f"{label} ({state_label})"


def rainfall_summary(groups: dict[str, Any]) -> str:
    """The served narrative, derived from ALREADY-NORMALIZED metric groups
    (design.md D4).

    Pure and total: it reads only what ``_normalize_metric`` decided --
    ``state``, ``reason``, ``value`` (and the untouched ``unit``) -- never
    build-time ``completeness``/``quality``, which survive normalization
    unchanged and would describe states that were never served. Membership
    is structural rather than narrated: a metric appears under
    ``Disponibles`` if and only if its DISCLOSED state is ``available``, so
    the summary cannot call available something the policy suppressed.

    Metric order follows the envelope's own group/metric order, which
    ``build_snapshot`` fixes and the JSON round-trip preserves, so the same
    stored revision always narrates identically.
    """
    buckets: dict[str, list[str]] = {"available": [], "partial": [], "missing": []}
    for group_name in METRIC_GROUPS:
        group = groups.get(group_name)
        if not isinstance(group, dict):
            continue
        for name, metric in group.items():
            if not isinstance(metric, dict):
                continue
            state = metric.get("state")
            bucket = state if state in {"available", "partial"} else "missing"
            buckets[bucket].append(_summary_entry(name, metric))

    sentences = [
        f"{prefix} {'; '.join(entries)}."
        for prefix, entries in (
            (SUMMARY_AVAILABLE_PREFIX, buckets["available"]),
            (SUMMARY_PARTIAL_PREFIX, buckets["partial"]),
            (SUMMARY_MISSING_PREFIX, buckets["missing"]),
        )
        if entries
    ]
    return " ".join(sentences) if sentences else SUMMARY_EMPTY


def normalize_snapshot(snapshot: object, *, expected_policy_revision: str) -> dict[str, Any]:
    """Validate and apply one approved policy before JSON or CSV disclosure."""
    if not isinstance(snapshot, dict) or not set(snapshot) <= SNAPSHOT_ROOT_KEYS:
        raise SnapshotContractError("snapshot envelope is invalid")
    policy = _metric_policy(snapshot, expected_policy_revision)
    normalized = dict(snapshot)
    for group_name in METRIC_GROUPS:
        group = snapshot.get(group_name)
        if group is None:
            continue
        if not isinstance(group, dict) or any(
            not isinstance(metric, dict) or not ({"metric", "value"} & set(metric))
            for metric in group.values()
        ):
            raise SnapshotContractError("snapshot envelope is invalid")
        normalized[group_name] = {
            name: _normalize_metric(metric, policy, expected_policy_revision)
            for name, metric in group.items()
        }
    # design.md D4: the narrative is assembled HERE, after the loop above
    # decided every served state, and it OVERWRITES anything the stored
    # envelope carried -- `build_snapshot` emits no summary, and a legacy
    # build-time one would describe states this policy revision may never
    # serve. Safe for the same reason the router injects
    # `analysis_revision_id` post-normalize: the root-key set is validated on
    # INPUT, and `summary` is already allow-listed.
    normalized["summary"] = rainfall_summary(normalized)
    return normalized


def metric_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten nested metric groups without coercing a missing value to zero."""
    return [
        dict(metric)
        for group_name in METRIC_GROUPS
        if isinstance((group := snapshot.get(group_name)), dict)
        for metric in group.values()
        if isinstance(metric, dict) and "metric" in metric
    ]


# The characters a spreadsheet reads as "this cell is an expression" on
# import. `=` is the obvious one; `+`/`-`/`@` open the same door in Excel and
# LibreOffice, and a leading tab or CR slips a trigger past a naive
# `startswith("=")` check because the reader strips the whitespace first.
SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Prefixing with an apostrophe is the neutralization both readers honour: the
# cell renders as text and is never evaluated. Deliberately NOT stripping or
# rewriting the value -- an export is evidence, and silently mutating what the
# provider sent would be a worse defect than the one being closed.
SPREADSHEET_TEXT_MARKER = "'"


def neutralize_spreadsheet_formula(text: str) -> str:
    """Make one cell's TEXT inert for a spreadsheet reader.

    ONE definition of "text a spreadsheet would execute", shared by both export
    formats (the `temporal.utc_day` precedent), so the audit CSV and the xlsx
    workbook can never disagree about the same value.

    The two formats need it for different reasons and lose it in different
    ways. The xlsx has a structural lever -- ``cell.data_type = "s"``
    (`export._append`) types the cell as a string in the file itself, and Excel
    never evaluates a string cell. A CSV has no types at all: the READER decides
    what each cell is, which is why the audit CSV is the MORE exposed of the two
    exports (LI3B-001) even though it is the one nobody thought of as a
    document. Applying this at value level in both keeps the structural guard as
    a second layer rather than a single point of failure, and keeps the same
    hostile value rendering identically in both files.

    Only ``str`` is ever passed here by either caller: a negative FLOAT is a
    number, not executable text, and quoting it would break every consumer that
    parses the column.
    """
    return (
        f"{SPREADSHEET_TEXT_MARKER}{text}"
        if text.startswith(SPREADSHEET_FORMULA_PREFIXES)
        else text
    )


def _csv_cell(value: Any) -> Any:
    """Nested evidence stays JSON; the formula guard runs on plain text cells.

    The JSON envelope is itself the containment for nested evidence: a dict, a
    list or a tuple encodes to a cell that ALWAYS starts with ``{`` or ``[``,
    and neither is in ``SPREADSHEET_FORMULA_PREFIXES``, so a hostile string
    nested inside can never begin the cell. Running the guard over the encoded
    text was therefore a no-op for every possible input (LI4-002) -- and it
    documented a defence that does not exist, which is the more expensive half:
    the next reader trusts it instead of checking that the envelope holds.

    ``json.dumps`` is NOT decorative here and must stay. Handing the csv writer
    a bare list makes it write Python's ``repr`` (``['=1+1']``, single quotes),
    which no consumer can parse back as JSON.

    A plain ``str`` cell has no envelope -- it is the caller's raw text -- so it
    is the one shape that still needs the guard (`unit`, `reason`, ... are
    provider-fed).
    """
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return neutralize_spreadsheet_formula(value) if isinstance(value, str) else value


def metric_rows_csv(rows: list[dict[str, Any]]) -> str:
    """Serialize every displayed field; null stays blank and nested evidence stays JSON."""
    fields = tuple(sorted({key for row in rows for key in row}))
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_cell(value) for key, value in row.items()})
    return output.getvalue()
