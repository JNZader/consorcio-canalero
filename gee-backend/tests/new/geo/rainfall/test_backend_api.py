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
