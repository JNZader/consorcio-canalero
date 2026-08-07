"""Snapshot serialization keeps JSON and CSV state/provenance semantics identical."""

import csv
import json
from io import StringIO
from math import isfinite
from typing import Any

from pydantic import ValidationError

from app.domains.geo.rainfall.policy import MetricThresholdPolicy, apply_metric_policy
from app.domains.geo.rainfall.schemas import MetricResult


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
    except ValidationError:
        return _unavailable(raw, "metric_contract_invalid")
    if metric.revision != expected_revision:
        return _unavailable(raw, "policy_revision_mismatch")
    if metric.state in {"suppressed", "unavailable"}:
        return {**raw, "value": None}
    if policy is None:
        return _unavailable(raw, "policy_unavailable")
    score = metric.quality.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not isfinite(score):
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


def normalize_snapshot(
    snapshot: dict[str, Any], *, expected_policy_revision: str
) -> dict[str, Any]:
    """Validate and apply one approved policy before JSON or CSV disclosure."""
    policy = _metric_policy(snapshot, expected_policy_revision)

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            if "metric" in value or "value" in value:
                return _normalize_metric(value, policy, expected_policy_revision)
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    return normalize(snapshot)


def metric_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten nested metric groups without coercing a missing value to zero."""
    return [
        dict(metric)
        for group in snapshot.values()
        if isinstance(group, dict)
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
