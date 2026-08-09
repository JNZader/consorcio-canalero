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
from typing import Any

from app.domains.geo.rainfall import temporal
from app.domains.geo.rainfall.adapters.manifests import CANDIDATE_MANIFESTS
from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY, RAINFALL_METRIC_POLICY_REVISION
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
) -> dict[str, Any]:
    """Build the v1 snapshot envelope: root keys are a subset of
    ``SNAPSHOT_ROOT_KEYS``, shipping only ``annual.selected`` (decision 5).

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

    provenance = {
        "source_id": source_id,
        "source_class": _source_class_for(source_id),
        "method": "sum",
        "nominal_resolution": f"{scale_m}m",
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
        "annual": {"selected": annual_metric},
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
