"""Snapshot serialization keeps JSON and CSV state/provenance semantics identical."""

import csv
import hashlib
import json
from io import StringIO
from math import isfinite
from typing import Any

from pydantic import ValidationError

from app.domains.geo.rainfall.policy import MetricThresholdPolicy, apply_metric_policy
from app.domains.geo.rainfall.schemas import MetricResult

METRIC_GROUPS = ("annual", "antecedents", "intensity")
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
