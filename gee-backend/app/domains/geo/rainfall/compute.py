"""Pure Rainfall v2 materialization logic: no Session, no network.

Boundary rule (design.md "Technical Approach"): adapters own providers,
``compute.py`` is pure, ``repository.py`` owns SQL, ``tasks.py`` only
orchestrates and owns the Session. Every function in this module is a plain
transformation over its inputs and is safe to unit-test without a database.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from app.domains.geo.rainfall import temporal
from app.domains.geo.rainfall.adapters.manifests import CANDIDATE_MANIFESTS
from app.domains.geo.rainfall.policy import (
    RAINFALL_METRIC_POLICY,
    RAINFALL_METRIC_POLICY_REVISION,
    MetricThresholdPolicy,
    apply_metric_policy,
)
from app.domains.geo.rainfall.scope import AnalysisScope

_CORRECTION_SEPARATOR = "+r"


def revision_family(provider_revision: str) -> str:
    """Strip a correction suffix, returning the provider-revision family.

    ``"v3-nrt+r2"`` -> ``"v3-nrt"``; a bare family revision (no adapter has
    ever emitted a correction for it) maps to itself. ``"+r"`` is reserved as
    the correction separator (design.md "NRT Correction Supersession");
    adapters MUST NOT emit ``+`` in a ``provider_revision``.
    """
    return provider_revision.split(_CORRECTION_SEPARATOR, 1)[0]


def correction_revision(family: str, ordinal: int) -> str:
    """Build the n-th correction's ``provider_revision`` string for *family*.

    ``("v3-nrt", 2)`` -> ``"v3-nrt+r2"``. The ordinal is 1 for a slot's first
    correction, chained off the current row's own ordinal for later ones
    (design.md "NRT Correction Supersession" step 2, "changed" branch).
    """
    if ordinal < 1:
        raise ValueError(f"correction ordinal must be >= 1, got {ordinal}")
    return f"{family}{_CORRECTION_SEPARATOR}{ordinal}"


# ---------------------------------------------------------------------------
# Snapshot materialization (design.md decisions 5/5b/5c and Interfaces)
# ---------------------------------------------------------------------------

_SOURCE_CLASS_BY_ID: dict[str, str] = {
    manifest.source_id: manifest.source_class for manifest in CANDIDATE_MANIFESTS
}


def _source_class_for(source_id: str) -> str:
    try:
        return _SOURCE_CLASS_BY_ID[source_id]
    except KeyError as exc:
        raise ValueError(
            f"no candidate manifest registers a source_class for source_id={source_id!r}"
        ) from exc


# ---------------------------------------------------------------------------
# annual.normal / annual.percentile (design.md D4/D5, slice 2a)
# ---------------------------------------------------------------------------

# design.md D5: eligible baseline years must clear this SAMPLE-SIZE floor
# before normal/percentile are disclosed at all -- a floor, not a
# policy.RAINFALL_METRIC_POLICY threshold entry, since apply_metric_policy
# only speaks fractions (coverage/quality) and cannot see absolute n.
# February 29 has only 8 leap years in 1991-2020
# (temporal.baseline_years_for), well below this floor -- so a Feb 29
# comparison suppresses structurally, with no special-case code below.
MIN_BASELINE_YEARS = 20

# design.md D5: a baseline year's OWN day-completeness must clear this
# floor to count toward MIN_BASELINE_YEARS -- a year with a data gap must
# not silently participate as if it were whole.
_BASELINE_YEAR_COMPLETENESS_THRESHOLD = 0.95

# design.md D5: normal/percentile always carry the HISTORICAL baseline's
# own source_id, regardless of what sourced the selected year (role
# assignment, not blending) -- a bare literal (not service.py's
# RAINFALL_HISTORICAL_SOURCE) to keep compute.py's import graph pointed
# only at policy.py/scope.py/temporal.py/adapters.manifests, never at the
# orchestration layer above it.
_BASELINE_SOURCE_ID = "chirps-v3-final"


def weibull_percentile(baseline_values: Sequence[float], selected_value: float) -> float:
    """Empirical Weibull plotting-position rank (design.md D5) -- pure, no
    suppression logic; the caller applies the two-layer floor (per-year
    completeness, then :data:`MIN_BASELINE_YEARS`) before ever calling this.

    Sample = *baseline_values* plus *selected_value* (``N = n + 1``);
    returns ``p = 100 * i / (N + 1)`` where ``i`` is the 1-based ascending
    rank of *selected_value* within the combined sample, ties taking the
    MEAN of their tied positions. Including the selected year in its own
    sample avoids a degenerate 0/100 rank and keeps the range 3.1-96.9 at
    n=30 baseline years (the lowest/highest possible ranks, i=1 and i=N).
    """
    combined = sorted([*baseline_values, selected_value])
    n = len(combined)
    tied_positions = [
        position + 1 for position, value in enumerate(combined) if value == selected_value
    ]
    mean_rank = sum(tied_positions) / len(tied_positions)
    return 100 * mean_rank / (n + 1)


def _normal_and_percentile_metrics(
    *,
    baseline: dict[int, tuple[float, int, int]] | None,
    comparison_end_date: date,
    selected_value: float | None,
    selected_temporal_state: str,
    nominal_resolution: str,
    scope: AnalysisScope,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """``annual.normal``/``annual.percentile`` (design.md D4/D5): ALWAYS
    present in the envelope -- an unmapped or thin baseline suppresses
    these two metrics rather than dropping them, so a served analysis has
    a stable metric shape regardless of baseline coverage.

    Both are built from the historical baseline alone
    (``repository.baseline_cumulatives``, D1), never from an adapter
    ``batch`` -- there is no adapter batch behind a SQL aggregate to
    inherit ``quality``/``discrepancies`` from (task 2a.8, LIB-102 fold).
    ``Provenance`` and ``MetricResult`` both set ``extra="forbid"``
    (schemas.py:11,25), so every field below is built explicitly from
    scratch rather than assumed from a partial source.
    """
    possible_years = temporal.baseline_years_for(comparison_end_date)
    eligible_years = sorted(
        year
        for year, (_total, matched, expected) in (baseline or {}).items()
        if year in possible_years
        and expected > 0
        and (matched / expected) >= _BASELINE_YEAR_COMPLETENESS_THRESHOLD
    )
    completeness = (len(eligible_years) / len(possible_years)) if possible_years else 0.0
    coverage = (
        min((baseline[year][1] / baseline[year][2]) for year in eligible_years)
        if eligible_years
        else 0.0
    )

    last_baseline_year = max(possible_years)
    envelope_start = datetime(1991, 1, 1, tzinfo=UTC)
    envelope_end = datetime(
        last_baseline_year, comparison_end_date.month, comparison_end_date.day, tzinfo=UTC
    ) + timedelta(days=1)

    if baseline is None:
        normal_state, normal_reason = "suppressed", "baseline_scope_unmapped"
        percentile_state, percentile_reason = "suppressed", "baseline_scope_unmapped"
        normal_value = percentile_value = None
    elif len(eligible_years) < MIN_BASELINE_YEARS:
        # design.md D5: the per-year completeness floor already trimmed
        # `eligible_years` above; Feb 29 (only 8 leap years in 1991-2020)
        # suppresses HERE, unconditionally -- 8 < MIN_BASELINE_YEARS.
        normal_state, normal_reason = "suppressed", "baseline_years_below_minimum"
        percentile_state, percentile_reason = "suppressed", "baseline_years_below_minimum"
        normal_value = percentile_value = None
    else:
        normal_value = sum(baseline[year][0] for year in eligible_years) / len(eligible_years)
        normal_state, normal_reason = "available", None
        if selected_value is None:
            # The rank needs a selected-year total to rank AGAINST; the
            # normal (a pure baseline average) does not.
            percentile_value = None
            percentile_state, percentile_reason = (
                "suppressed",
                "annual_selected_value_unavailable",
            )
        else:
            eligible_totals = [baseline[year][0] for year in eligible_years]
            percentile_value = weibull_percentile(eligible_totals, selected_value)
            percentile_state, percentile_reason = "available", None

    quality = {
        "score": completeness,
        "eligible_years": eligible_years,
        "baseline_years_possible": len(possible_years),
    }

    def _provenance(method: str) -> dict[str, Any]:
        return {
            "source_id": _BASELINE_SOURCE_ID,
            "source_class": _source_class_for(_BASELINE_SOURCE_ID),
            "method": method,
            "nominal_resolution": nominal_resolution,
            "aggregation": "daily",
            "spatial_scope": scope.kind,
            "freshness": now.isoformat(),
            "available_through": envelope_end.isoformat(),
        }

    normal_metric = {
        "metric": "annual_normal",
        "value": normal_value,
        "unit": "mm",
        "state": normal_state,
        "reason": normal_reason,
        "interval_start": envelope_start.isoformat(),
        "interval_end": envelope_end.isoformat(),
        "coverage": coverage,
        "completeness": completeness,
        "quality": quality,
        "discrepancies": [],
        "temporal_state": "final",
        "revision": RAINFALL_METRIC_POLICY_REVISION,
        "provenance": _provenance("mean"),
        "fallback_used": False,
    }
    percentile_metric = {
        "metric": "annual_percentile",
        "value": percentile_value,
        "unit": "percentil",
        "state": percentile_state,
        "reason": percentile_reason,
        "interval_start": envelope_start.isoformat(),
        "interval_end": envelope_end.isoformat(),
        "coverage": coverage,
        "completeness": completeness,
        "quality": dict(quality),
        "discrepancies": [],
        "temporal_state": "provisional" if selected_temporal_state == "provisional" else "final",
        "revision": RAINFALL_METRIC_POLICY_REVISION,
        "provenance": _provenance("weibull_rank"),
        "fallback_used": False,
    }
    return normal_metric, percentile_metric


# ---------------------------------------------------------------------------
# antecedents.{d7,d30,d90} (design.md D6, slice 2a)
# ---------------------------------------------------------------------------

_ANTECEDENT_WINDOWS: tuple[tuple[str, int], ...] = (("d7", 7), ("d30", 30), ("d90", 90))


def _antecedent_metric(
    *,
    name: str,
    days: int,
    intervals: Sequence[tuple[datetime, datetime, float]],
    end: datetime,
    cadence: timedelta,
    source_id: str,
    scope: AnalysisScope,
    now: datetime,
    aggregation: str,
    nominal_resolution: str,
    batch: dict[str, Any],
    temporal_state: str,
    fallback_used: bool,
) -> dict[str, Any]:
    """One ``antecedents.{d7,d30,d90}`` entry (design.md D6): a
    cadence-exact rolling total ending at *end*, never at the calendar-year
    boundary, read from *intervals* -- the D6-widened
    ``[year_start - 90d, year_end)`` set the caller
    (``tasks._persist_analysis_revision``) reads, so a window that dips
    into the prior year still finds its rows here. Same *source_id* as
    ``annual.selected`` -- never mixing revision families (design.md D6).

    *end* is the CLIPPED disclosure end
    ``min(comparison_end_exclusive, last_interval_end)`` that
    ``annual.selected`` already uses (design.md D6 amendment), NOT the raw
    calendar ``comparison_end``: provider lag is the documented steady
    state, so anchoring the window at a slot nobody has published yet
    would fail the exact-slot-set check below and suppress all three
    antecedents on every current-year build. ``provenance.available_through``
    therefore discloses that same clipped end -- the honest value -- exactly
    as ``annual.selected`` reports its own clipped ``window_end``.

    ``temporal.rolling_total`` requires an EXACT cadence-aligned match
    (design.md: "never a short sum"), so *intervals* is filtered down to
    precisely ``[end - days, end)`` before the call; a gap anywhere in
    that window raises ``EventSuppressed``, suppressed here with its own
    reason rather than a partial sum.
    """
    window = timedelta(days=days)
    window_start = end - window
    window_pairs = tuple(
        (interval_start, value)
        for interval_start, _interval_end, value in intervals
        if window_start <= interval_start < end
    )
    expected_slots = int(window / cadence) if cadence > timedelta() else 0
    matched_slots = len(window_pairs)
    completeness = (matched_slots / expected_slots) if expected_slots > 0 else 0.0

    try:
        total = temporal.rolling_total(
            end=end, window=window, cadence=cadence, intervals=window_pairs
        )
    except temporal.EventSuppressed:
        value, state, reason = None, "suppressed", "antecedent_window_incomplete"
    else:
        value, state, reason = total, "available", None

    quality = {**batch["quality"], "score": completeness, "checksum": batch["checksum"]}
    provenance = {
        "source_id": source_id,
        "source_class": _source_class_for(source_id),
        "method": "sum",
        "nominal_resolution": nominal_resolution,
        "aggregation": aggregation,
        "spatial_scope": scope.kind,
        "freshness": now.isoformat(),
        "available_through": end.isoformat(),
    }
    return {
        "metric": name,
        "value": value,
        "unit": "mm",
        "state": state,
        "reason": reason,
        "interval_start": window_start.isoformat(),
        "interval_end": end.isoformat(),
        "coverage": completeness,
        "completeness": completeness,
        "quality": quality,
        "discrepancies": list(batch["discrepancies"]),
        "temporal_state": temporal_state,
        "revision": RAINFALL_METRIC_POLICY_REVISION,
        "provenance": provenance,
        "fallback_used": fallback_used,
    }


def build_snapshot(
    *,
    scope: AnalysisScope,
    year: int,
    role: str,
    source_id: str,
    intervals: Sequence[tuple[datetime, datetime, float]],
    batch: dict[str, Any],
    now: datetime,
    fallback_used: bool = False,
    baseline: dict[int, tuple[float, int, int]] | None = None,
) -> dict[str, Any]:
    """Build the snapshot envelope: root keys are a subset of
    ``SNAPSHOT_ROOT_KEYS``. v1 shipped only ``annual.selected`` (decision
    5); slice 2a (design.md D3/D4/D5/D6) grows it with
    ``annual.{normal,percentile}`` and ``antecedents.{d7,d30,d90}`` --
    ALWAYS present, suppressed (never omitted) when their evidence is
    insufficient, so a served analysis has a stable metric shape
    regardless of baseline coverage.

    ``baseline`` is the caller's resolved historical baseline
    (``repository.baseline_cumulatives``, design.md D1): ``{year: (total_mm,
    matched_days, expected_days)}``, or ``None`` when the scope has no known
    provider asset -- in which case ``annual.normal``/``annual.percentile``
    both suppress with reason ``"baseline_scope_unmapped"`` (design.md D5).

    Coverage/completeness/quality are recomputed here, at build time, over
    ``[year_start, min(comparison_end, last_interval_end))`` — the
    *disclosure* window — rather than reused from the fetch-time batch
    (decision 5c): the adapter measures coverage over the whole requested
    year, which would report a current year in progress as near-zero
    forever. ``quality``/``discrepancies``/``checksum`` evidence is carried
    from the batch as-is; only ``score`` (decision 5b) is added, set to the
    measured completeness — there is no independent QC signal for a
    satellite zonal mean.

    ``intervals`` is a plain, ORM-free sequence of
    ``(interval_start, interval_end, value)`` — the resolved, non-superseded
    rows for the whole requested year (repository.intervals_in_window's
    result, stripped of its ORM identity by the caller).
    """
    starts = [interval_start for interval_start, _interval_end, _value in intervals]
    if len(starts) != len(set(starts)):
        # intervals_in_window's anti-join is supposed to guarantee at most
        # one non-superseded row per slot; a duplicate here is a broken
        # invariant that must be loud, not a quietly inflated total.
        raise ValueError("build_snapshot received a duplicated interval_start slot")

    year_start = datetime(year, 1, 1, tzinfo=UTC)
    comparison_end_date = temporal.comparison_end(year, temporal.buenos_aires_date(now))
    comparison_end_exclusive = datetime(
        comparison_end_date.year, comparison_end_date.month, comparison_end_date.day, tzinfo=UTC
    ) + timedelta(days=1)

    in_window = [
        (interval_start, interval_end, value)
        for interval_start, interval_end, value in intervals
        if year_start <= interval_start < comparison_end_exclusive
    ]

    if in_window:
        last_interval_end = max(interval_end for _s, interval_end, _v in in_window)
        window_end = min(comparison_end_exclusive, last_interval_end)
        total_value: float | None = sum(value for _s, _e, value in in_window)
    else:
        window_end = comparison_end_exclusive
        total_value = None

    cadence_seconds = batch["cadence_seconds"]
    expected_slots = (
        int((window_end - year_start) / timedelta(seconds=cadence_seconds))
        if cadence_seconds > 0
        else 0
    )
    matched_slots = len(in_window)
    completeness = (matched_slots / expected_slots) if expected_slots > 0 else 0.0
    coverage = completeness

    quality = {**batch["quality"], "score": completeness, "checksum": batch["checksum"]}

    if total_value is None:
        metric_state, metric_reason = "unavailable", "no_data_in_disclosure_window"
    else:
        metric_state, metric_reason = "available", None

    aggregation = "daily" if cadence_seconds == 86400 else f"{int(cadence_seconds)}s"
    scale_m = batch["quality"].get("scale_m", "unknown")
    nominal_resolution = f"{scale_m}m"

    provenance = {
        "source_id": source_id,
        "source_class": _source_class_for(source_id),
        "method": "sum",
        "nominal_resolution": nominal_resolution,
        "aggregation": aggregation,
        "spatial_scope": scope.kind,
        "freshness": now.isoformat(),
        "available_through": window_end.isoformat(),
    }

    annual_metric = {
        "metric": "annual",
        "value": total_value,
        "unit": batch.get("unit") or "mm",
        "state": metric_state,
        "reason": metric_reason,
        "interval_start": year_start.isoformat(),
        "interval_end": window_end.isoformat(),
        "coverage": coverage,
        "completeness": completeness,
        "quality": quality,
        "discrepancies": list(batch["discrepancies"]),
        "temporal_state": "final" if role == "historical" else "provisional",
        "revision": RAINFALL_METRIC_POLICY_REVISION,
        "provenance": provenance,
        "fallback_used": fallback_used,
    }

    # design.md D4/D5 (slice 2a): built from the SAME comparison_end_date
    # annual.selected just used, so both metrics are cut off at exactly
    # that date -- never a different, independently-derived cutoff.
    normal_metric, percentile_metric = _normal_and_percentile_metrics(
        baseline=baseline,
        comparison_end_date=comparison_end_date,
        selected_value=total_value,
        selected_temporal_state=annual_metric["temporal_state"],
        nominal_resolution=nominal_resolution,
        scope=scope,
        now=now,
    )

    # design.md D6 (slice 2a): *intervals* is the D6-widened
    # [year_start - 90d, year_end) set the caller now reads -- a window
    # that dips into the prior year still finds its rows here, while
    # annual.selected above stayed scoped to the unwidened `in_window`.
    #
    # The windows END at `window_end` -- the SAME
    # min(comparison_end_exclusive, last_interval_end) clip annual.selected
    # applies above -- not at the calendar comparison_end (design.md D6
    # amendment). Provider lag is the documented steady state, and
    # temporal.rolling_total demands an exact slot set, so a rigid calendar
    # anchor would demand a slot for TODAY and suppress all three
    # antecedents on every current-year build. With no in-window intervals
    # at all, `window_end` falls back to comparison_end_exclusive and the
    # windows suppress anyway: their last expected slot (end - cadence) is
    # never earlier than year_start, so it would have been in `in_window`
    # had it existed.
    cadence = timedelta(seconds=cadence_seconds) if cadence_seconds > 0 else timedelta()
    antecedents = {
        name: _antecedent_metric(
            name=name,
            days=days,
            intervals=intervals,
            end=window_end,
            cadence=cadence,
            source_id=source_id,
            scope=scope,
            now=now,
            aggregation=aggregation,
            nominal_resolution=nominal_resolution,
            batch=batch,
            temporal_state=annual_metric["temporal_state"],
            fallback_used=fallback_used,
        )
        for name, days in _ANTECEDENT_WINDOWS
    }

    return {
        "scope": {"kind": scope.kind, "id": scope.id, "version": scope.version},
        "regional_estimate": scope.regional_estimate,
        "year": year,
        "comparison_end": comparison_end_date.isoformat(),
        "baseline": "1991-2020",
        "metric_policy": {
            "revision": RAINFALL_METRIC_POLICY_REVISION,
            "minimum_coverage_by_metric": dict(RAINFALL_METRIC_POLICY.minimum_coverage_by_metric),
            "minimum_quality_by_metric": dict(RAINFALL_METRIC_POLICY.minimum_quality_by_metric),
            "duration_threshold": RAINFALL_METRIC_POLICY.duration_threshold,
        },
        "annual": {
            "selected": annual_metric,
            "normal": normal_metric,
            "percentile": percentile_metric,
        },
        "antecedents": antecedents,
    }


def data_revision_for(
    source_id: str,
    provider_revision_family: str,
    scope: AnalysisScope,
    year: int,
    comparison_end: date,
    intervals: Sequence[tuple[datetime, float]],
) -> str:
    """Content address (decision 3b): stable when neither the resolved
    interval values nor the disclosed ``comparison_end`` move; changes when
    either does. ``comparison_end`` MUST be in the hash — while the provider
    lags, the interval set is byte-identical day over day, and a
    content-only address would collide on ``uq_rainfall_analysis_snapshot``
    and freeze the served comparison end on the day of first compute.
    """
    canonical_intervals = sorted(
        ((interval_start.isoformat(), round(value, 6)) for interval_start, value in intervals),
        key=lambda item: item[0],
    )
    canonical = json.dumps(
        [
            source_id,
            provider_revision_family,
            [scope.kind, scope.id, scope.version],
            year,
            comparison_end.isoformat(),
            canonical_intervals,
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Year-rollover finalization: served_state, revision_write_decision, the
# per-fingerprint advisory lock key (design.md "Year-Rollover Finalization",
# "Serializing siblings — the per-fingerprint advisory lock")
# ---------------------------------------------------------------------------


def fingerprint_lock_key(request_fingerprint: str) -> int:
    """Deterministic signed 64-bit advisory-lock key derived from a request
    fingerprint (a lowercase sha256 hex digest, service.py:102-107). No new
    column: take the first 16 hex chars (the first 8 bytes) as an unsigned
    big-endian integer and reinterpret that as PostgreSQL's signed
    ``bigint`` -- process-stable (no ``hash()`` randomization). A collision
    between two unrelated fingerprints costs one shared queue slot, never a
    wrong answer.
    """
    unsigned = int(request_fingerprint[:16], 16)
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


def served_state(snapshot: dict[str, Any]) -> tuple[str, str] | None:
    """``(annual.selected.provenance.source_id, annual.selected.temporal_state)``
    from a complete envelope, or ``None`` when either is missing (a corrupt
    or pre-contract row) -- treated as *unknown*, never as *finalized*. The
    single Python function that reads it (R2-002 -- review-ledger.md
    "Pre-PR review — PR3"): called from stage 2's own defense-in-depth
    check (``tasks._revisit_stage2``), :func:`revision_write_decision`, and
    the latch branch's own event payload (``tasks._persist_analysis_revision``)
    -- so there is one place to be wrong, not three raw dict subscripts
    that could each drift from it independently.
    ``repository.completed_year_daily_done_keys`` mirrors these same two
    JSON fields in raw SQL for its own exclusion filter (a SUPERSET, not
    the authority -- see that function's docstring); it cannot call this
    function, since it runs inside the database, so it is a deliberate,
    documented second implementation, not a fourth Python reader.
    """
    annual = snapshot.get("annual")
    if not isinstance(annual, dict):
        return None
    selected = annual.get("selected")
    if not isinstance(selected, dict):
        return None
    provenance = selected.get("provenance")
    if not isinstance(provenance, dict):
        return None
    source_id = provenance.get("source_id")
    temporal_state = selected.get("temporal_state")
    if not isinstance(source_id, str) or not isinstance(temporal_state, str):
        return None
    return source_id, temporal_state


def revision_write_decision(
    incumbent: dict[str, Any] | None,
    candidate: dict[str, Any],
    policy: MetricThresholdPolicy,
) -> Literal["write", "latched", "gate_refused"]:
    """``"write"`` | ``"latched"`` | ``"gate_refused"`` (design.md
    "Write gate — no-regression semantics"). R2-005: typed as a
    ``Literal`` rather than a bare ``str`` so the consumer
    (``tasks._persist_analysis_revision``) can branch on it exhaustively
    with an explicit fail-loud ``else`` instead of a silent fall-through.

    - No incumbent, or the incumbent's ``served_state`` is ``None`` (an
      envelope the router would 503 on anyway), or incumbent and candidate
      name the same ``source_id`` -> ``"write"``. Stage 1's daily rebuild
      and the first-materialization case; decision 3b's content address
      already makes a no-information rebuild a silent no-op.
    - Cross-source, candidate ``provisional``, incumbent ``final`` ->
      ``"latched"``. Never write -- see "The latch" in design.md.
    - Cross-source otherwise (the finalization case) -> ``"write"`` iff
      ``apply_metric_policy`` -- the SAME function the disclosure path
      already runs -- reports ``state == "available"``; otherwise
      ``"gate_refused"``.
    """
    incumbent_state = served_state(incumbent) if incumbent is not None else None
    if incumbent_state is None:
        return "write"

    incumbent_source_id, incumbent_temporal_state = incumbent_state
    candidate_state = served_state(candidate)
    if candidate_state is None:
        # A candidate this module built itself is always well-formed; an
        # unreadable candidate would be a compute bug, not a policy branch.
        raise ValueError("revision_write_decision received a candidate with no served_state")
    candidate_source_id, candidate_temporal_state = candidate_state

    if incumbent_source_id == candidate_source_id:
        return "write"

    if candidate_temporal_state == "provisional" and incumbent_temporal_state == "final":
        return "latched"

    metric = candidate["annual"]["selected"]
    applied = apply_metric_policy(
        policy,
        metric["metric"],
        value=metric["value"],
        coverage=metric["coverage"],
        quality_score=metric["quality"]["score"],
        completeness=metric["completeness"],
    )
    return "write" if applied.state == "available" else "gate_refused"
