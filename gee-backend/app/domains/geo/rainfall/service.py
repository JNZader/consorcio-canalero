"""Snapshot serialization keeps JSON and CSV state/provenance semantics identical."""

import csv
import hashlib
import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from math import isfinite
from typing import Any

from pydantic import ValidationError

from app.domains.geo.rainfall.metrics import record_event
from app.domains.geo.rainfall.models import RainfallOutbox
from app.domains.geo.rainfall.policy import MetricThresholdPolicy, apply_metric_policy
from app.domains.geo.rainfall.schemas import MetricResult

METRIC_GROUPS = ("annual", "antecedents", "intensity")

RAINFALL_HISTORICAL_SOURCE = "chirps-v3-final"
RAINFALL_DAILY_SOURCE = "sqpe-obs"
RAINFALL_INTENSITY_SOURCE = "sinarame-rqpe"
# Task 3.18: matches adapters/manifests.py's validation-role candidate
# (`smn-gauge`, singular) -- was `smn-gauges`, a typo that never matched.
RAINFALL_VALIDATION_SOURCE = "smn-gauge"

# decision 6: skip request-path re-enqueue when a `done` row for the same
# key completed within this window, regardless of whether a revision
# exists -- see queue_missing_analysis. Engineering guess tuned to the 5s
# frontend poll; confirm against real GEE quota headroom (Open Questions).
RAINFALL_RECOMPUTE_COOLDOWN = timedelta(minutes=10)


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
    from app.domains.geo.rainfall.repository import recent_done

    fingerprint = request_fingerprint or _default_request_fingerprint(
        scope=scope, year=year, event_window=event_window
    )
    source = resolve_missing_work_source(event_window, year, requested_role=requested_role)

    # decision 6: a recent `done` row for this key skips re-enqueue
    # REGARDLESS of whether a revision exists -- a time-bounded skip stops
    # the per-poll GEE burn while letting a done-without-revision heal
    # itself once the cooldown lapses.
    recent = recent_done(
        db,
        source_id=source["source_id"],
        role=source["role"],
        scope_kind=scope.kind,
        scope_id=scope.id,
        scope_version=scope.version,
        year=year,
        since=datetime.now(UTC) - RAINFALL_RECOMPUTE_COOLDOWN,
    )
    if recent is not None:
        record_event(
            "rainfall.outbox.cooldown",
            source_id=source["source_id"],
            role=source["role"],
            scope_kind=scope.kind,
            scope_id=scope.id,
            scope_version=scope.version,
            year=year,
            outbox_id=str(recent.id),
        )
        return {
            "status": "queued",
            "outbox_id": str(recent.id),
            "scope": {"kind": scope.kind, "id": scope.id, "version": scope.version},
            "year": year,
            "labels": recent.work_labels,
        }

    existing = (
        db.query(RainfallOutbox)
        .filter_by(
            source_id=source["source_id"],
            role=source["role"],
            scope_kind=scope.kind,
            scope_id=scope.id,
            scope_version=scope.version,
            year=year,
            status="pending",
        )
        .first()
    )
    if existing is not None:
        record_event(
            "rainfall.outbox.reused",
            source_id=source["source_id"],
            role=source["role"],
            scope_kind=scope.kind,
            scope_id=scope.id,
            scope_version=scope.version,
            year=year,
            labels=existing.work_labels,
        )
        return {
            "status": "queued",
            "outbox_id": str(existing.id),
            "scope": {"kind": scope.kind, "id": scope.id, "version": scope.version},
            "year": year,
            "labels": existing.work_labels,
        }

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
    db.flush()
    db.commit()
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


def metric_rows_csv(rows: list[dict[str, Any]]) -> str:
    """Serialize every displayed field; null stays blank and nested evidence stays JSON."""
    fields = tuple(sorted({key for row in rows for key in row}))
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(value, sort_keys=True)
                if isinstance(value, (dict, list, tuple))
                else value
                for key, value in row.items()
            }
        )
    return output.getvalue()
