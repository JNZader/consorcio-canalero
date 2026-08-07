"""Focused contracts for the Rainfall v2 deterministic backend slice."""

from datetime import UTC, date, datetime, timedelta

import pytest


def test_scope_keeps_stable_zone_and_basin_identity_and_rejects_direct_targets():
    from app.domains.geo.rainfall.scope import (
        ScopeRef,
        UnsupportedDirectScope,
        executable_scope,
    )

    zone = executable_scope(ScopeRef(kind="zone", id="approved-zone-4", version="z3"))
    basin = executable_scope(ScopeRef(kind="basin", id="basin-4", version="aabbcc"))
    assert (zone.kind, zone.id, zone.version, zone.regional_estimate) == (
        "zone",
        "approved-zone-4",
        "z3",
        False,
    )
    assert basin.kind == "basin"
    with pytest.raises(UnsupportedDirectScope, match="parcel"):
        executable_scope(ScopeRef(kind="parcel", nomenclature="01-02"))
    with pytest.raises(UnsupportedDirectScope, match="geometry"):
        executable_scope(ScopeRef(kind="geometry", geometry={"type": "Polygon"}))


def test_parcel_resolution_is_ordered_regional_and_requires_a_choice_when_ambiguous():
    from app.domains.geo.rainfall.scope import (
        AnalysisScope,
        AmbiguousScope,
        NoScopeMatch,
        ScopeRef,
        resolve_parcel,
    )

    choices = (
        AnalysisScope("zone", "approved-zone-4", "z3", regional_estimate=True),
        AnalysisScope("basin", "basin-4", "aabbcc", regional_estimate=True),
    )
    parcel = ScopeRef(kind="parcel", nomenclature="01-02")
    assert resolve_parcel(parcel, choices, selected=choices[1]) == choices[1]
    with pytest.raises(AmbiguousScope):
        resolve_parcel(parcel, choices)
    with pytest.raises(NoScopeMatch):
        resolve_parcel(parcel, ())


def test_temporal_rules_use_local_calendar_year_same_date_and_cross_year_antecedents():
    from app.domains.geo.rainfall.temporal import comparison_end, antecedent_dates

    assert comparison_end(2025, date(2026, 3, 20)) == date(2025, 12, 31)
    assert comparison_end(2026, date(2026, 3, 20)) == date(2026, 3, 20)
    assert antecedent_dates(date(2026, 1, 2), 7) == (
        date(2025, 12, 27),
        date(2026, 1, 2),
    )


def test_event_peak_and_duration_require_aligned_complete_single_wet_run():
    from app.domains.geo.rainfall.temporal import EventSuppressed, event_peak_and_duration

    start = datetime(2026, 1, 1, tzinfo=UTC)
    cadence = timedelta(minutes=30)
    intervals = tuple(
        (start + cadence * index, value) for index, value in enumerate((0.0, 2.0, 3.0, 0.0))
    )
    peak, duration = event_peak_and_duration(
        start=start,
        end=start + cadence * 4,
        cadence=cadence,
        intervals=tuple(intervals),
        duration_threshold=1.0,
        rolling_window=timedelta(hours=1),
    )
    assert peak == 5.0
    assert duration == timedelta(hours=1)
    with pytest.raises(EventSuppressed, match="complete"):
        event_peak_and_duration(
            start=start,
            end=start + cadence * 4,
            cadence=cadence,
            intervals=((start, 1.0),),
            duration_threshold=1.0,
            rolling_window=timedelta(hours=1),
        )
    with pytest.raises(EventSuppressed):
        event_peak_and_duration(
            start=start,
            end=start + cadence * 4,
            cadence=cadence,
            intervals=tuple(intervals),
            duration_threshold=1.0,
            rolling_window=timedelta(minutes=45),
        )


def test_metric_rows_keep_null_distinct_from_zero_and_csv_matches_json_states():
    from app.domains.geo.rainfall.service import metric_rows, metric_rows_csv

    row = {
        "metric": "p24h",
        "value": 0.0,
        "state": "available",
        "reason": None,
        "unit": "mm",
    }
    unavailable = {
        **row,
        "metric": "p30",
        "value": None,
        "state": "unavailable",
        "reason": "no_source",
    }
    rows = metric_rows({"intensity": {"p24h": row, "p30": unavailable}})
    assert [item["value"] for item in rows] == [0.0, None]
    assert "" in metric_rows_csv(rows).splitlines()[-1]


def test_router_exposes_only_authenticated_rainfall_contract_routes():
    from app.domains.geo.rainfall.router import router

    routes = {(route.path, tuple(route.methods or ())) for route in router.routes}
    assert ("/rainfall/scopes:resolve", ("POST",)) in routes
    assert ("/rainfall/analyses", ("POST",)) in routes
    assert ("/rainfall/analyses/{revision}.csv", ("GET",)) in routes


def test_rolling_totals_require_every_cadence_interval_and_support_daily_windows():
    from app.domains.geo.rainfall.temporal import EventSuppressed, rolling_total

    end = datetime(2026, 1, 2, tzinfo=UTC)
    cadence = timedelta(hours=1)
    intervals = tuple((end - cadence * (24 - index), 1.0) for index in range(24))
    assert (
        rolling_total(end=end, window=timedelta(hours=24), cadence=cadence, intervals=intervals)
        == 24.0
    )
    with pytest.raises(EventSuppressed, match="complete"):
        rolling_total(
            end=end, window=timedelta(hours=24), cadence=cadence, intervals=intervals[:-1]
        )
    with pytest.raises(EventSuppressed, match="complete"):
        rolling_total(
            end=end,
            window=timedelta(hours=24),
            cadence=cadence,
            intervals=(intervals[0], *intervals),
        )


def test_csv_serialization_preserves_provenance_and_reason_columns():
    from app.domains.geo.rainfall.service import metric_rows_csv

    csv_text = metric_rows_csv(
        [
            {
                "metric": "annual",
                "value": None,
                "state": "unavailable",
                "reason": "no_source",
                "provenance": {"source_id": "none"},
            }
        ]
    )
    assert "provenance" in csv_text.splitlines()[0]
    assert "no_source" in csv_text


def test_parcel_selection_requires_the_complete_kind_id_version_tuple():
    from app.domains.geo.rainfall.scope import AnalysisScope, NoScopeMatch, ScopeRef, resolve_parcel

    parcel = ScopeRef(kind="parcel", nomenclature="01-02")
    zone_v1 = AnalysisScope("zone", "zone-4", "1", regional_estimate=True)
    zone_v2 = AnalysisScope("zone", "zone-4", "2", regional_estimate=True)
    assert resolve_parcel(parcel, (zone_v1, zone_v2), selected=zone_v2) == zone_v2
    with pytest.raises(NoScopeMatch):
        resolve_parcel(
            parcel, (zone_v1, zone_v2), selected=AnalysisScope("zone", "zone-4", "3", True)
        )


def test_router_requires_auth_and_global_csrf_contract_for_scope_resolution():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.middleware import CSRFProtectionMiddleware
    from app.domains.geo.rainfall.router import router

    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    app.include_router(router)
    client = TestClient(app)
    payload = {"kind": "zone", "id": "z1", "version": "1"}
    assert client.post("/rainfall/scopes:resolve", json=payload).status_code == 401
    assert (
        client.post(
            "/rainfall/scopes:resolve", content="{}", headers={"Origin": "https://invalid.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/rainfall/scopes:resolve", content="{}", headers={"Origin": "http://localhost:3000"}
        ).status_code
        == 415
    )


def test_temporal_conversion_and_baseline_keep_buenos_aires_same_date_and_leap_rule():
    from app.domains.geo.rainfall.temporal import baseline_dates, buenos_aires_date

    assert buenos_aires_date(datetime(2026, 1, 1, 2, tzinfo=UTC)) == date(2025, 12, 31)
    assert baseline_dates(date(2024, 2, 29)) == tuple(
        date(year, 2, 29) for year in range(1992, 2021, 4)
    )


def test_metric_policy_is_versioned_and_keeps_failed_metrics_isolated():
    from app.domains.geo.rainfall.policy import MetricThresholdPolicy, apply_metric_policy

    policy = MetricThresholdPolicy(
        revision="coverage-quality-v1",
        minimum_coverage_by_metric={"annual": 0.8, "peak": 1.0},
        minimum_quality_by_metric={"annual": 0.7, "peak": 0.9},
        duration_threshold=1.0,
    )
    annual = apply_metric_policy(
        policy, "annual", value=0.0, coverage=0.8, quality_score=0.7, completeness=0.8
    )
    peak = apply_metric_policy(
        policy, "peak", value=12.0, coverage=0.9, quality_score=0.95, completeness=0.9
    )

    assert annual.state == "available"
    assert annual.value == 0.0
    assert peak.state == "suppressed"
    assert peak.value is None
    assert peak.reason == "coverage_below_threshold"


def test_metric_policy_fails_closed_when_a_metric_threshold_is_missing():
    from app.domains.geo.rainfall.policy import MetricThresholdPolicy, apply_metric_policy

    policy = MetricThresholdPolicy(
        revision="coverage-quality-v1",
        minimum_coverage_by_metric={},
        minimum_quality_by_metric={},
        duration_threshold=None,
    )

    result = apply_metric_policy(
        policy, "duration", value=3.0, coverage=1.0, quality_score=1.0, completeness=1.0
    )

    assert result.state == "suppressed"
    assert result.value is None
    assert result.reason == "policy_threshold_unset"


@pytest.mark.parametrize(
    ("coverage", "quality", "duration"),
    [(-0.1, 0.7, 1.0), (0.8, 1.1, 1.0), (0.8, 0.7, -1.0)],
)
def test_metric_policy_rejects_out_of_domain_thresholds(coverage, quality, duration):
    from app.domains.geo.rainfall.policy import MetricThresholdPolicy, apply_metric_policy

    policy = MetricThresholdPolicy(
        revision="coverage-quality-v1",
        minimum_coverage_by_metric={"duration": coverage},
        minimum_quality_by_metric={"duration": quality},
        duration_threshold=duration,
    )

    result = apply_metric_policy(
        policy, "duration", value=3.0, coverage=1.0, quality_score=1.0, completeness=1.0
    )

    assert (result.state, result.value, result.reason) == (
        "suppressed",
        None,
        "policy_threshold_invalid",
    )


@pytest.mark.parametrize(
    ("value", "state", "reason"),
    [
        (0.9, "suppressed", "duration_below_threshold"),
        (1.0, "available", None),
        (1.1, "available", None),
    ],
)
def test_metric_policy_applies_duration_threshold_at_the_boundary(value, state, reason):
    from app.domains.geo.rainfall.policy import MetricThresholdPolicy, apply_metric_policy

    policy = MetricThresholdPolicy(
        revision="coverage-quality-v1",
        minimum_coverage_by_metric={"duration": 0.8},
        minimum_quality_by_metric={"duration": 0.7},
        duration_threshold=1.0,
    )

    result = apply_metric_policy(
        policy, "duration", value=value, coverage=1.0, quality_score=1.0, completeness=1.0
    )

    assert (result.state, result.value, result.reason) == (
        state,
        value if state == "available" else None,
        reason,
    )


def test_analysis_request_rejects_oversized_body_before_snapshot_lookup():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.auth import require_admin_or_operator
    from app.domains.geo.rainfall.router import router

    app = FastAPI()
    app.dependency_overrides[require_admin_or_operator] = lambda: None
    app.include_router(router)
    client = TestClient(app)
    response = client.post(
        "/rainfall/analyses",
        content='"' + "x" * 16_385 + '"',
        headers={"content-type": "application/json", "content-length": "16385"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "rainfall request body exceeds limit"


def test_analysis_request_requires_a_versioned_policy_and_complete_request_contract():
    from pydantic import ValidationError

    from app.domains.geo.rainfall.router import AnalysisRequest

    with pytest.raises(ValidationError):
        AnalysisRequest(request_fingerprint="request", policy_revision="", data_revision="data")
    with pytest.raises(ValidationError):
        AnalysisRequest(
            request_fingerprint="request", policy_revision="policy", data_revision="data", extra="x"
        )


def test_snapshot_normalization_applies_policy_and_fails_closed_for_invalid_provenance():
    from app.domains.geo.rainfall.service import metric_rows, normalize_snapshot

    snapshot = {
        "metric_policy": {
            "revision": "coverage-quality-v1",
            "minimum_coverage_by_metric": {"annual": 0.8},
            "minimum_quality_by_metric": {"annual": 0.7},
            "duration_threshold": 1.0,
        },
        "annual": {
            "selected": {
                "metric": "annual",
                "value": 18.0,
                "unit": "mm",
                "state": "available",
                "interval_start": "2026-01-01T00:00:00Z",
                "interval_end": "2026-01-02T00:00:00Z",
                "coverage": 0.7,
                "completeness": 1.0,
                "quality": {"score": 0.9},
                "discrepancies": [],
                "temporal_state": "final",
                "revision": "coverage-quality-v1",
                "provenance": {
                    "source_id": "radar",
                    "source_class": "estimated_radar",
                    "method": "sum",
                    "nominal_resolution": "1km",
                    "aggregation": "daily",
                    "spatial_scope": "zone",
                    "freshness": "2026-01-02T00:00:00Z",
                    "available_through": "2026-01-02T00:00:00Z",
                },
                "fallback_used": False,
            },
            "normal": {
                "metric": "normal",
                "value": 20.0,
                "unit": "mm",
                "state": "available",
                "interval_start": "2026-01-01T00:00:00Z",
                "interval_end": "2026-01-02T00:00:00Z",
                "coverage": 1.0,
                "completeness": 1.0,
                "quality": {"score": 0.9},
                "discrepancies": [],
                "temporal_state": "final",
                "revision": "coverage-quality-v1",
                "provenance": {"source_id": "radar"},
                "fallback_used": False,
            },
        },
    }

    normalized = normalize_snapshot(snapshot, expected_policy_revision="coverage-quality-v1")
    rows = metric_rows(normalized)

    assert rows[0]["value"] is None
    assert rows[0]["state"] == "suppressed"
    assert rows[0]["reason"] == "coverage_below_threshold"
    assert rows[1]["value"] is None
    assert rows[1]["state"] == "unavailable"
    assert rows[1]["reason"] == "metric_contract_invalid"


def test_snapshot_normalization_denies_invalid_quality_and_missing_thresholds_in_csv_rows():
    from app.domains.geo.rainfall.service import metric_rows, metric_rows_csv, normalize_snapshot

    def metric(name, value, score):
        return {
            "metric": name,
            "value": value,
            "unit": "mm",
            "state": "available",
            "interval_start": "2026-01-01T00:00:00Z",
            "interval_end": "2026-01-02T00:00:00Z",
            "coverage": 1.0,
            "completeness": 1.0,
            "quality": {"score": score},
            "discrepancies": [],
            "temporal_state": "final",
            "revision": "v1",
            "provenance": {
                "source_id": "radar",
                "source_class": "estimated_radar",
                "method": "sum",
                "nominal_resolution": "1km",
                "aggregation": "daily",
                "spatial_scope": "zone",
                "freshness": "2026-01-02T00:00:00Z",
                "available_through": "2026-01-02T00:00:00Z",
            },
            "fallback_used": False,
        }

    normalized = normalize_snapshot(
        {
            "metric_policy": {
                "revision": "v1",
                "minimum_coverage_by_metric": {"annual": 0.8},
                "minimum_quality_by_metric": {"annual": 0.7},
                "duration_threshold": 1.0,
            },
            "annual": {
                "annual": metric("annual", 21.0, True),
                "normal": metric("normal", 20.0, 0.9),
            },
        },
        expected_policy_revision="v1",
    )
    rows = metric_rows(normalized)

    assert [(row["state"], row["value"]) for row in rows] == [
        ("unavailable", None),
        ("suppressed", None),
    ]
    assert "21.0" not in metric_rows_csv(rows)
    assert "20.0" not in metric_rows_csv(rows)


def test_snapshot_normalization_suppresses_metric_like_dicts_missing_the_metric_name():
    from app.domains.geo.rainfall.service import metric_rows, metric_rows_csv, normalize_snapshot

    normalized = normalize_snapshot(
        {"annual": {"selected": {"value": 21.0, "state": "available", "unit": "mm"}}},
        expected_policy_revision="v1",
    )
    rows = metric_rows(normalized)

    assert normalized["annual"]["selected"] == {
        "metric": "unknown",
        "value": None,
        "state": "unavailable",
        "reason": "metric_contract_invalid",
    }
    assert rows == [normalized["annual"]["selected"]]
    assert "21.0" not in metric_rows_csv(rows)


@pytest.mark.parametrize(
    ("value", "expected_value", "expected_state", "expected_reason", "csv_value"),
    [
        (True, None, "unavailable", "metric_contract_invalid", "1.0"),
        (False, None, "unavailable", "metric_contract_invalid", "0.0"),
        ("21.0", None, "unavailable", "metric_contract_invalid", "21.0"),
        (21, 21.0, "available", None, "21.0"),
        (21.5, 21.5, "available", None, "21.5"),
        (None, None, "unavailable", "metric_value_unavailable", None),
    ],
)
def test_snapshot_normalization_never_coerces_non_numeric_metric_values(
    value, expected_value, expected_state, expected_reason, csv_value
):
    from app.domains.geo.rainfall.service import metric_rows, metric_rows_csv, normalize_snapshot

    metric = {
        "metric": "annual",
        "value": value,
        "unit": "mm",
        "state": "available" if value is not None else "partial",
        "interval_start": "2026-01-01T00:00:00Z",
        "interval_end": "2026-01-02T00:00:00Z",
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"score": 0.9},
        "discrepancies": [],
        "temporal_state": "final",
        "revision": "v1",
        "provenance": {
            "source_id": "radar",
            "source_class": "estimated_radar",
            "method": "sum",
            "nominal_resolution": "1km",
            "aggregation": "daily",
            "spatial_scope": "zone",
            "freshness": "2026-01-02T00:00:00Z",
            "available_through": "2026-01-02T00:00:00Z",
        },
        "fallback_used": False,
    }
    normalized = normalize_snapshot(
        {
            "metric_policy": {
                "revision": "v1",
                "minimum_coverage_by_metric": {"annual": 0.8},
                "minimum_quality_by_metric": {"annual": 0.7},
                "duration_threshold": 1.0,
            },
            "annual": {"selected": metric},
        },
        expected_policy_revision="v1",
    )
    row = metric_rows(normalized)[0]

    assert (row["value"], row["state"], row["reason"]) == (
        expected_value,
        expected_state,
        expected_reason,
    )
    if csv_value is not None:
        assert (csv_value in metric_rows_csv([row])) is (expected_value is not None)


@pytest.mark.parametrize("field", ["coverage", "completeness"])
@pytest.mark.parametrize(
    "raw_evidence",
    [
        pytest.param(True, id="bool"),
        pytest.param("1.0", id="numeric-string"),
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="positive-infinity"),
        pytest.param(float("-inf"), id="negative-infinity"),
    ],
)
def test_snapshot_normalization_rejects_raw_coverage_or_completeness_coercion(field, raw_evidence):
    from csv import DictReader
    from io import StringIO

    from app.domains.geo.rainfall.service import metric_rows, metric_rows_csv, normalize_snapshot

    metric = {
        "metric": "annual",
        "value": 21.0,
        "unit": "mm",
        "state": "available",
        "interval_start": "2026-01-01T00:00:00Z",
        "interval_end": "2026-01-02T00:00:00Z",
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"score": 0.9},
        "discrepancies": [],
        "temporal_state": "final",
        "revision": "v1",
        "provenance": {
            "source_id": "radar",
            "source_class": "estimated_radar",
            "method": "sum",
            "nominal_resolution": "1km",
            "aggregation": "daily",
            "spatial_scope": "zone",
            "freshness": "2026-01-02T00:00:00Z",
            "available_through": "2026-01-02T00:00:00Z",
        },
        "fallback_used": False,
    }
    metric[field] = raw_evidence
    normalized = normalize_snapshot(
        {
            "metric_policy": {
                "revision": "v1",
                "minimum_coverage_by_metric": {"annual": 0.8},
                "minimum_quality_by_metric": {"annual": 0.7},
                "duration_threshold": 1.0,
            },
            "annual": {"selected": metric},
        },
        expected_policy_revision="v1",
    )
    row = metric_rows(normalized)[0]
    csv_row = next(DictReader(StringIO(metric_rows_csv([row]))))

    assert (row["value"], row["state"], row["reason"]) == (
        None,
        "unavailable",
        "metric_contract_invalid",
    )
    assert (csv_row["value"], csv_row["state"], csv_row["reason"]) == (
        "",
        "unavailable",
        "metric_contract_invalid",
    )


@pytest.mark.parametrize("field", ["coverage", "completeness"])
@pytest.mark.parametrize("boundary", [0.0, 1.0])
@pytest.mark.parametrize(
    ("value", "input_state", "expected_value", "expected_state", "expected_reason"),
    [
        (21.0, "available", 21.0, "available", None),
        (None, "partial", None, "unavailable", "metric_value_unavailable"),
    ],
)
def test_snapshot_normalization_preserves_finite_evidence_boundaries_and_null_values(
    field, boundary, value, input_state, expected_value, expected_state, expected_reason
):
    from csv import DictReader
    from io import StringIO

    from app.domains.geo.rainfall.service import metric_rows, metric_rows_csv, normalize_snapshot

    metric = {
        "metric": "annual",
        "value": value,
        "unit": "mm",
        "state": input_state,
        "interval_start": "2026-01-01T00:00:00Z",
        "interval_end": "2026-01-02T00:00:00Z",
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"score": 0.9},
        "discrepancies": [],
        "temporal_state": "final",
        "revision": "v1",
        "provenance": {
            "source_id": "radar",
            "source_class": "estimated_radar",
            "method": "sum",
            "nominal_resolution": "1km",
            "aggregation": "daily",
            "spatial_scope": "zone",
            "freshness": "2026-01-02T00:00:00Z",
            "available_through": "2026-01-02T00:00:00Z",
        },
        "fallback_used": False,
    }
    metric[field] = boundary
    normalized = normalize_snapshot(
        {
            "metric_policy": {
                "revision": "v1",
                "minimum_coverage_by_metric": {"annual": boundary},
                "minimum_quality_by_metric": {"annual": 0.7},
                "duration_threshold": 1.0,
            },
            "annual": {"selected": metric},
        },
        expected_policy_revision="v1",
    )
    row = metric_rows(normalized)[0]
    csv_row = next(DictReader(StringIO(metric_rows_csv([row]))))

    assert (row["value"], row["state"], row["reason"]) == (
        expected_value,
        expected_state,
        expected_reason,
    )
    assert (csv_row["value"], csv_row["state"], csv_row["reason"]) == (
        "" if expected_value is None else str(expected_value),
        expected_state,
        "" if expected_reason is None else expected_reason,
    )
