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
        (0.9, "available", None),
        (1.0, "available", None),
        (1.1, "available", None),
    ],
)
def test_metric_policy_does_not_compare_duration_hours_to_rainfall_cutoff(value, state, reason):
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


def test_analysis_request_rejects_internal_revision_lookup_keys():
    from pydantic import ValidationError

    from app.domains.geo.rainfall.router import AnalysisRequest

    with pytest.raises(ValidationError):
        AnalysisRequest(request_fingerprint="request", policy_revision="", data_revision="data")
    with pytest.raises(ValidationError):
        AnalysisRequest(
            scope={"kind": "zone", "id": "z1", "version": "1"},
            year=2026,
            request_fingerprint="request",
            policy_revision="policy",
            data_revision="data",
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


# ===========================================================================
# lluvia-insights slice 2b (real PG): disclosure-time summary end-to-end,
# the policy-revision bump, and the stale-revision serve + labelled requeue
# ===========================================================================

# The value RAINFALL_METRIC_POLICY_REVISION carried before lluvia-insights
# added annual.normal/percentile/antecedents and re-based their thresholds.
# Pinned as a literal on purpose: the bump is the mechanism that makes the
# enriched envelope LAND (design.md D3), so a slice that forgets it must fail
# here rather than ship a silently discarded snapshot.
_PREVIOUS_POLICY_REVISION = "rainfall-v2-2026-08"


def _daily_source_rows(start: date, count: int, value: float):
    from app.domains.geo.rainfall.ports import SourceInterval

    rows = []
    for offset in range(count):
        day = start + timedelta(days=offset)
        day_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        rows.append(SourceInterval(day_start, day_start + timedelta(days=1), value, "mm", "v3-nrt"))
    return rows


def _seed_outbox_for_request(db, *, scope_id: str, year: int, status: str = "pending"):
    """An outbox row whose ``request_fingerprint`` is the one the ROUTER
    derives for ``POST /analyses`` with this scope/year, so a revision built
    from it is reachable by a real request."""
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.service import analysis_request_fingerprint

    scope = {"kind": "zone", "id": scope_id, "version": "v1"}
    fingerprint = analysis_request_fingerprint({"scope": scope, "year": year})
    outbox = RainfallOutbox(
        source_id="chirps-v3-sat",
        role="daily",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        year=year,
        work_labels=["analysis_missing"],
        interval_start=datetime(year, 1, 1, tzinfo=UTC),
        interval_end=datetime(year + 1, 1, 1, tzinfo=UTC),
        status=status,
        request_fingerprint=fingerprint,
    )
    db.add(outbox)
    db.flush()
    batch = {
        "source_id": "chirps-v3-sat",
        "provider_revision": "v3-nrt",
        "unit": "mm",
        "cadence_seconds": 86400.0,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"scale_m": 5500, "provider_revision": "v3-nrt"},
        "discrepancies": [],
        "checksum": f"sha256:fixture-{scope_id}",
    }
    return outbox, batch, fingerprint, scope


def _rainfall_client(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.auth import require_admin_or_operator
    from app.db.session import get_db
    from app.domains.geo.rainfall.router import router

    app = FastAPI()
    app.dependency_overrides[require_admin_or_operator] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    app.include_router(router)
    return TestClient(app)


def test_summary_disagrees_from_build_time_completeness_end_to_end(db):
    """2b.5 (spec: "Policy suppresses a metric the raw data would have
    supported"): the STORED envelope reports ``annual.selected`` available --
    ``build_snapshot`` is pure and never applies policy -- while the served
    disclosure suppresses it for coverage. The summary must describe what is
    served, not what was built."""
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.repository import RainfallRepository, persist_intervals
    from app.domains.geo.rainfall.service import (
        SUMMARY_AVAILABLE_PREFIX,
        SUMMARY_MISSING_PREFIX,
    )

    scope_id = "zone-2b5-summary-disagreement"
    year = 2025
    now = datetime(year, 2, 20, 12, 0, tzinfo=UTC)  # comparison_end = Feb 20

    # 10 published days, then a 21-day hole, then one more day: the window
    # runs to the LAST published day (Feb 1), so completeness is 11/32 --
    # under `annual`'s 0.8 coverage threshold -- while the raw metric still
    # reports `available` with a real summed value.
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=[
            *_daily_source_rows(date(year, 1, 1), 10, 3.0),
            *_daily_source_rows(date(year, 2, 1), 1, 3.0),
        ],
    )
    db.flush()

    outbox, batch, fingerprint, scope = _seed_outbox_for_request(db, scope_id=scope_id, year=year)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    stored = RainfallRepository().get_snapshot(db, fingerprint)
    assert stored is not None
    # Build time: available, with a value. This is the disagreement's source.
    assert stored.snapshot["annual"]["selected"]["state"] == "available"
    assert stored.snapshot["annual"]["selected"]["value"] == pytest.approx(33.0)
    assert "summary" not in stored.snapshot

    response = _rainfall_client(db).post("/rainfall/analyses", json={"scope": scope, "year": year})
    assert response.status_code == 200
    body = response.json()

    # Disclosure time: suppressed -- and the narrative says so.
    assert body["annual"]["selected"]["state"] == "suppressed"
    assert body["annual"]["selected"]["reason"] == "coverage_below_threshold"
    summary = body["summary"]
    assert "Acumulado del año (suprimida: coverage_below_threshold)" in summary
    available_sentence, _, missing_sentence = summary.partition(SUMMARY_MISSING_PREFIX)
    assert "Acumulado del año" not in available_sentence
    assert SUMMARY_AVAILABLE_PREFIX not in missing_sentence
    # The built value never reaches the reader through the narrative either.
    assert "33.0" not in summary


def _restamped(snapshot: dict, revision: str) -> dict:
    """The same envelope as if it had been built under *revision*: the
    embedded ``metric_policy`` AND every metric's own ``revision`` move
    together, which is what keeps an older row self-consistent under its own
    policy (`_normalize_metric` rejects any metric whose revision does not
    match the row's)."""
    restamped = {
        **snapshot,
        "metric_policy": {**snapshot["metric_policy"], "revision": revision},
    }
    for group in ("annual", "antecedents"):
        restamped[group] = {
            name: {**metric, "revision": revision} for name, metric in snapshot[group].items()
        }
    return restamped


def _built_snapshot(*, scope_id: str, year: int, now: datetime, rows, batch: dict) -> dict:
    from app.domains.geo.rainfall.compute import build_snapshot
    from app.domains.geo.rainfall.scope import AnalysisScope

    return build_snapshot(
        scope=AnalysisScope(kind="zone", id=scope_id, version="v1", regional_estimate=False),
        year=year,
        role="daily",
        source_id="chirps-v3-sat",
        intervals=[(row.interval_start, row.interval_end, row.value) for row in rows],
        batch=batch,
        now=now,
    )


def test_revision_bump_lands_enriched_envelope_not_conflict_skipped(db):
    """2b.6 (design.md D3): ``data_revision`` hashes source/family/scope/
    year/comparison_end/intervals only, so for a key whose evidence has not
    moved a rebuild would hit ``ON CONFLICT DO NOTHING`` and the enriched
    envelope would NEVER land. ``policy_revision`` is the second column of
    ``uq_rainfall_analysis_snapshot``, which is what makes the bump
    load-bearing rather than cosmetic."""
    from app.domains.geo.rainfall import tasks, temporal
    from app.domains.geo.rainfall.compute import data_revision_for
    from app.domains.geo.rainfall.models import RainfallAnalysisRevision
    from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY_REVISION
    from app.domains.geo.rainfall.repository import persist_intervals, persist_revision
    from app.domains.geo.rainfall.scope import AnalysisScope
    from sqlalchemy import select

    # The bump itself: without it, everything below collides by construction.
    assert RAINFALL_METRIC_POLICY_REVISION != _PREVIOUS_POLICY_REVISION

    scope_id = "zone-2b6-revision-bump"
    year = 2025
    now = datetime(year, 2, 20, 12, 0, tzinfo=UTC)
    rows = _daily_source_rows(date(year, 1, 1), 51, 3.0)

    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=rows,
    )
    db.flush()
    outbox, batch, fingerprint, _scope = _seed_outbox_for_request(db, scope_id=scope_id, year=year)

    # The key is already `done` under the OLD policy revision, carrying
    # EXACTLY the data_revision a rebuild recomputes -- the whole point is
    # that the evidence has not moved, so policy_revision is provably the
    # only difference. (If this prediction were wrong the run would end with
    # two DIFFERENT data_revisions, which the assertion below catches.)
    scope = AnalysisScope(kind="zone", id=scope_id, version="v1", regional_estimate=False)
    unmoved_data_revision = data_revision_for(
        "chirps-v3-sat",
        "v3-nrt",
        scope,
        year,
        temporal.comparison_end(year, temporal.buenos_aires_date(now)),
        [(row.interval_start, row.value) for row in rows],
    )
    incumbent_id = persist_revision(
        db,
        request_fingerprint=fingerprint,
        policy_revision=_PREVIOUS_POLICY_REVISION,
        data_revision=unmoved_data_revision,
        snapshot=_restamped(
            _built_snapshot(scope_id=scope_id, year=year, now=now, rows=rows, batch=batch),
            _PREVIOUS_POLICY_REVISION,
        ),
    )

    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    stored = db.scalars(
        select(RainfallAnalysisRevision).where(
            RainfallAnalysisRevision.request_fingerprint == fingerprint
        )
    ).all()
    assert len(stored) == 2, [(row.policy_revision, row.data_revision) for row in stored]
    # Identical evidence -- only the policy revision moved.
    assert {row.data_revision for row in stored} == {unmoved_data_revision}
    assert {row.policy_revision for row in stored} == {
        _PREVIOUS_POLICY_REVISION,
        RAINFALL_METRIC_POLICY_REVISION,
    }
    landed = next(row for row in stored if row.id != incumbent_id)
    assert landed.policy_revision == RAINFALL_METRIC_POLICY_REVISION
    # ... and it is the ENRICHED envelope, which is what the bump bought.
    assert set(landed.snapshot["annual"]) == {"selected", "normal", "percentile"}
    assert set(landed.snapshot["antecedents"]) == {"d7", "d30", "d90"}


def test_stale_policy_revision_served_and_requeued(db):
    """2b.7/2b.8 (design.md D3): past-year keys already `done` are never
    revisited by either sweep, so the request path is where a superseded
    policy revision has to be noticed. The stored row is STILL served -- it
    is self-consistent, normalized with its OWN policy_revision -- and a
    refresh is enqueued labelled ``policy_revision_stale``, bounded by
    ``recent_done``'s cooldown rather than fired once per poll."""
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.repository import persist_intervals, persist_revision
    from app.domains.geo.rainfall.service import analysis_request_fingerprint
    from sqlalchemy import select

    scope_id = "zone-2b7-stale-policy"
    year = 2025
    now = datetime(year, 2, 20, 12, 0, tzinfo=UTC)
    rows = _daily_source_rows(date(year, 1, 1), 51, 3.0)

    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=rows,
    )
    db.flush()

    scope = {"kind": "zone", "id": scope_id, "version": "v1"}
    fingerprint = analysis_request_fingerprint({"scope": scope, "year": year})
    batch = {
        "source_id": "chirps-v3-sat",
        "provider_revision": "v3-nrt",
        "unit": "mm",
        "cadence_seconds": 86400.0,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"scale_m": 5500, "provider_revision": "v3-nrt"},
        "discrepancies": [],
        "checksum": f"sha256:fixture-{scope_id}",
    }
    # The only stored revision for this key was written under the SUPERSEDED
    # policy revision, and is fully self-consistent under it.
    persist_revision(
        db,
        request_fingerprint=fingerprint,
        policy_revision=_PREVIOUS_POLICY_REVISION,
        data_revision="a" * 64,
        snapshot=_restamped(
            _built_snapshot(scope_id=scope_id, year=year, now=now, rows=rows, batch=batch),
            _PREVIOUS_POLICY_REVISION,
        ),
    )

    def _pending():
        return db.scalars(
            select(RainfallOutbox)
            .where(RainfallOutbox.scope_id == scope_id)
            .where(RainfallOutbox.status == "pending")
        ).all()

    assert _pending() == []

    client = _rainfall_client(db)
    response = client.post("/rainfall/analyses", json={"scope": scope, "year": year})

    # Served, not 503'd and not swapped for a 202: the row is self-consistent
    # under its own policy revision, so it stays a usable answer.
    assert response.status_code == 200
    body = response.json()
    assert body["metric_policy"]["revision"] == _PREVIOUS_POLICY_REVISION
    assert body["annual"]["selected"]["state"] == "available"

    queued = _pending()
    assert len(queued) == 1
    assert "policy_revision_stale" in queued[0].work_labels

    # Bounded, not per-poll: a second poll finds the pending refresh ...
    assert client.post("/rainfall/analyses", json={"scope": scope, "year": year}).status_code == 200
    assert len(_pending()) == 1

    # ... and once that refresh is `done` inside the cooldown window, the
    # request path still refuses to spend another fetch on it.
    refresh = queued[0]
    refresh.status = "done"
    refresh.completed_at = datetime.now(UTC)
    db.flush()
    assert client.post("/rainfall/analyses", json={"scope": scope, "year": year}).status_code == 200
    assert _pending() == []


def test_current_policy_revision_serves_without_enqueueing_anything(db):
    """The counterexample to 2b.8: a row already on the current revision is
    served with no work enqueued at all -- the requeue is triggered by the
    revision differing, not by every 200."""
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY_REVISION
    from app.domains.geo.rainfall.repository import persist_intervals, persist_revision
    from app.domains.geo.rainfall.service import analysis_request_fingerprint
    from sqlalchemy import select

    scope_id = "zone-2b8-current-policy"
    year = 2025
    now = datetime(year, 2, 20, 12, 0, tzinfo=UTC)
    rows = _daily_source_rows(date(year, 1, 1), 51, 3.0)

    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=rows,
    )
    db.flush()

    scope = {"kind": "zone", "id": scope_id, "version": "v1"}
    fingerprint = analysis_request_fingerprint({"scope": scope, "year": year})
    batch = {
        "source_id": "chirps-v3-sat",
        "provider_revision": "v3-nrt",
        "unit": "mm",
        "cadence_seconds": 86400.0,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"scale_m": 5500, "provider_revision": "v3-nrt"},
        "discrepancies": [],
        "checksum": f"sha256:fixture-{scope_id}",
    }
    persist_revision(
        db,
        request_fingerprint=fingerprint,
        policy_revision=RAINFALL_METRIC_POLICY_REVISION,
        data_revision="b" * 64,
        snapshot=_built_snapshot(scope_id=scope_id, year=year, now=now, rows=rows, batch=batch),
    )

    response = _rainfall_client(db).post("/rainfall/analyses", json={"scope": scope, "year": year})

    assert response.status_code == 200
    assert db.scalars(select(RainfallOutbox).where(RainfallOutbox.scope_id == scope_id)).all() == []


# ===========================================================================
# lluvia-insights slice 3a (real PG): the revision's own content address is
# disclosed, so the client half of the series consistency check can exist
# ===========================================================================


def test_analyses_response_discloses_data_revision(db):
    """3a.11 (design.md D3) -- `data_revision` is a COLUMN on the revision
    row, computed after `build_snapshot` returns, and was disclosed nowhere.
    Without it the promised client-side drift check ("compare the /series echo
    against the snapshot this tab is holding") is impossible to write. The
    router injects it post-normalize from the served row, exactly as it
    already does for `analysis_revision_id`."""
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.repository import RainfallRepository, persist_intervals
    from app.domains.geo.rainfall.service import SNAPSHOT_ROOT_KEYS

    scope_id = "zone-3a11-data-revision"
    year = 2025
    now = datetime(year, 2, 20, 12, 0, tzinfo=UTC)

    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=_daily_source_rows(date(year, 1, 1), 51, 3.0),
    )
    db.flush()

    outbox, batch, fingerprint, scope = _seed_outbox_for_request(db, scope_id=scope_id, year=year)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)
    stored = RainfallRepository().get_snapshot(db, fingerprint)
    assert stored is not None
    # It is NOT part of the stored envelope -- that is the whole reason it
    # needs injecting rather than reading through.
    assert "data_revision" not in stored.snapshot

    response = _rainfall_client(db).post("/rainfall/analyses", json={"scope": scope, "year": year})

    assert response.status_code == 200
    body = response.json()
    assert body["data_revision"] == stored.data_revision
    # The two identities travel together: which row was served, and which
    # evidence that row was built from.
    assert body["analysis_revision_id"] == str(stored.id)
    # 3a.10: SNAPSHOT_ROOT_KEYS is the DECLARED disclosure envelope, so a
    # field the router injects but the allow-list does not name would make
    # that declaration a lie -- and would 503 the moment anything re-validated
    # a served body through `normalize_snapshot`.
    assert set(body) <= SNAPSHOT_ROOT_KEYS
