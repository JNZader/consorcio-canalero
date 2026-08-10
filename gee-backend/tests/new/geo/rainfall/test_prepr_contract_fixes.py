"""Strict-TDD regressions for the PR2B PRE-PR full-4R fix round."""

import asyncio
import csv
from datetime import UTC, datetime
from io import StringIO
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest


def _metric(
    *,
    name: str = "annual",
    value: float | None = 21.0,
    score: object = 0.9,
    interval_start: str = "2026-01-01T00:00:00Z",
    interval_end: str = "2026-01-02T00:00:00Z",
) -> dict[str, Any]:
    return {
        "metric": name,
        "value": value,
        "unit": "mm",
        "state": "available" if value is not None else "partial",
        "interval_start": interval_start,
        "interval_end": interval_end,
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


def _snapshot(metric: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "metric_policy": {
            "revision": "v1",
            "minimum_coverage_by_metric": {"annual": 0.8},
            "minimum_quality_by_metric": {"annual": 0.7},
            "duration_threshold": 1.0,
        },
        "annual": {"selected": metric or _metric()},
    }


def _rainfall_app():
    from fastapi import FastAPI

    from app.auth import require_admin_or_operator
    from app.db.session import get_db
    from app.domains.geo.rainfall.router import router

    app = FastAPI()
    app.dependency_overrides[require_admin_or_operator] = lambda: None
    app.dependency_overrides[get_db] = lambda: object()
    app.include_router(router)
    return app


def test_analysis_request_exposes_scope_year_and_optional_event_window_only():
    from pydantic import ValidationError

    from app.domains.geo.rainfall.router import AnalysisRequest

    request = AnalysisRequest(
        scope={"kind": "zone", "id": "zone-4", "version": "z3"},
        year=2026,
        event_window={
            "start": datetime(2026, 1, 1, tzinfo=UTC),
            "end": datetime(2026, 1, 2, tzinfo=UTC),
        },
    )

    assert request.scope.kind == "zone"
    assert request.year == 2026
    assert request.event_window.start.tzinfo is UTC
    with pytest.raises(ValidationError):
        AnalysisRequest(
            scope={"kind": "zone", "id": "zone-4", "version": "z3"},
            year=2026,
            request_fingerprint="client-controlled",
            policy_revision="old-policy",
            data_revision="old-data",
        )


def test_analysis_openapi_publishes_public_body_without_internal_lookup_keys():
    schema = _rainfall_app().openapi()

    body_schema = schema["paths"]["/rainfall/analyses"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    properties = body_schema["properties"]

    assert set(properties) == {"scope", "year", "event_window"}
    assert {"request_fingerprint", "policy_revision", "data_revision"}.isdisjoint(properties)


def test_analysis_route_server_resolves_fingerprint_and_revision(monkeypatch):
    from fastapi.testclient import TestClient

    from app.domains.geo.rainfall.repository import RainfallRepository
    from app.domains.geo.rainfall.service import analysis_request_fingerprint

    from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY_REVISION

    captured: list[str] = []
    revision_id = uuid4()

    # A row on the CURRENT policy revision -- the ordinary served case this
    # test is about. Task 2b.8 gave the route a second, DB-touching branch
    # for rows on a superseded revision (serve + labelled requeue), which the
    # `object()` session this app fixture injects deliberately cannot serve;
    # that branch has its own real-PG coverage in
    # test_backend_api.py::test_stale_policy_revision_served_and_requeued.
    served = _snapshot()
    served["metric_policy"] = {
        **served["metric_policy"],
        "revision": RAINFALL_METRIC_POLICY_REVISION,
    }
    served["annual"]["selected"]["revision"] = RAINFALL_METRIC_POLICY_REVISION

    def get_snapshot(self, db, request_fingerprint):
        captured.append(request_fingerprint)
        return SimpleNamespace(
            id=revision_id,
            policy_revision=RAINFALL_METRIC_POLICY_REVISION,
            # Slice 3a: `data_revision` is a NOT NULL column on every real
            # `RainfallAnalysisRevision` row (models.py) and the route now
            # discloses it, so the double models it too. A real row could not
            # exist without one.
            data_revision="c" * 64,
            snapshot=served,
        )

    monkeypatch.setattr(RainfallRepository, "get_snapshot", get_snapshot)
    payload = {"scope": {"kind": "zone", "id": "zone-4", "version": "z3"}, "year": 2026}

    response = TestClient(_rainfall_app()).post("/rainfall/analyses", json=payload)

    assert response.status_code == 200, response.text
    assert captured == [analysis_request_fingerprint(payload)]
    assert response.json()["annual"]["selected"]["value"] == 21.0
    # JDB-301: the served envelope must carry the revision id the CSV export
    # contract keys off (router.py read_analysis).
    assert response.json()["analysis_revision_id"] == str(revision_id)
    # Slice 3a (design.md D3): and the content address of the evidence that
    # revision was built from, injected from the same served row -- the two
    # identities the client needs to cross-check a /series response against
    # the snapshot it is holding.
    assert response.json()["data_revision"] == "c" * 64


def test_chunked_oversized_malformed_analysis_body_is_rejected_before_json_parsing():
    from fastapi.testclient import TestClient

    from app.domains.geo.rainfall.router import MAX_RAINFALL_REQUEST_BYTES

    body = b'{"scope":' + b"x" * MAX_RAINFALL_REQUEST_BYTES

    response = TestClient(_rainfall_app()).post(
        "/rainfall/analyses",
        content=(body[index : index + 1024] for index in range(0, len(body), 1024)),
        headers={"content-type": "application/json"},
    )

    assert "content-length" not in {key.lower() for key in response.request.headers}
    assert response.status_code == 413
    assert response.json()["detail"] == "rainfall request body exceeds limit"


def test_malformed_analysis_json_under_limit_is_a_deterministic_422():
    from fastapi.testclient import TestClient

    response = TestClient(_rainfall_app()).post(
        "/rainfall/analyses",
        content=b'{"scope":',
        headers={"content-type": "Application/JSON; Charset=UTF-8"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "rainfall request body must be valid JSON"


def test_analysis_body_disconnect_fails_closed_as_400():
    from fastapi import HTTPException
    from starlette.requests import Request

    from app.domains.geo.rainfall.router import parse_analysis_request

    async def receive() -> dict[str, Any]:
        return {"type": "http.disconnect"}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/rainfall/analyses",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
            "client": ("203.0.113.7", 51234),
        },
        receive,
    )

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(parse_analysis_request(request))

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "rainfall request body disconnected"


def test_duration_policy_uses_threshold_as_wet_interval_cutoff_not_output_hours():
    from app.domains.geo.rainfall.policy import MetricThresholdPolicy, apply_metric_policy

    policy = MetricThresholdPolicy(
        revision="v1",
        minimum_coverage_by_metric={"duration": 1.0, "peak": 1.0},
        minimum_quality_by_metric={"duration": 0.9, "peak": 0.9},
        duration_threshold=1.0,
    )

    duration = apply_metric_policy(
        policy, "duration", value=0.5, coverage=1.0, completeness=1.0, quality_score=1.0
    )
    peak = apply_metric_policy(
        policy, "peak", value=4.0, coverage=1.0, completeness=1.0, quality_score=1.0
    )

    assert (duration.state, duration.value, duration.reason) == ("available", 0.5, None)
    assert (peak.state, peak.value, peak.reason) == ("available", 4.0, None)


@pytest.mark.parametrize(
    "snapshot",
    [
        pytest.param([], id="non-object-root"),
        pytest.param(
            {"metric_policy": _snapshot()["metric_policy"], "annual": {"selected": [_metric()]}},
            id="metric-nested-in-list",
        ),
        pytest.param(
            {
                "metric_policy": _snapshot()["metric_policy"],
                "annual": {"selected": {"nested": _metric()}},
            },
            id="metric-nested-too-deep",
        ),
    ],
)
def test_snapshot_rejects_invalid_root_or_metric_nesting(snapshot):
    from app.domains.geo.rainfall.service import SnapshotContractError, normalize_snapshot

    with pytest.raises(SnapshotContractError, match="snapshot envelope is invalid"):
        normalize_snapshot(snapshot, expected_policy_revision="v1")


def test_snapshot_accepted_traversal_drives_identical_json_and_csv_rows():
    from app.domains.geo.rainfall.service import metric_rows, metric_rows_csv, normalize_snapshot

    normalized = normalize_snapshot(_snapshot(), expected_policy_revision="v1")
    rows = metric_rows(normalized)
    csv_row = next(csv.DictReader(StringIO(metric_rows_csv(rows))))

    assert len(rows) == 1
    assert rows[0]["metric"] == "annual"
    assert rows[0]["value"] == 21.0
    assert (csv_row["metric"], csv_row["value"], csv_row["state"]) == (
        "annual",
        "21.0",
        "available",
    )


def test_mixed_naive_and_aware_metric_bounds_fail_closed_in_json_and_csv():
    from app.domains.geo.rainfall.service import metric_rows, metric_rows_csv, normalize_snapshot

    normalized = normalize_snapshot(
        _snapshot(
            _metric(
                interval_start="2026-01-01T00:00:00",
                interval_end="2026-01-02T00:00:00Z",
            )
        ),
        expected_policy_revision="v1",
    )
    row = metric_rows(normalized)[0]
    csv_row = next(csv.DictReader(StringIO(metric_rows_csv([row]))))

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


@pytest.mark.parametrize(
    "score",
    [
        pytest.param(-0.1, id="below-zero"),
        pytest.param(1.1, id="above-one"),
        pytest.param(True, id="bool"),
        pytest.param("0.9", id="numeric-string"),
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="infinity"),
    ],
)
def test_quality_score_rejects_values_outside_strict_fraction_domain(score):
    from app.domains.geo.rainfall.service import metric_rows, normalize_snapshot

    row = metric_rows(
        normalize_snapshot(_snapshot(_metric(score=score)), expected_policy_revision="v1")
    )[0]

    assert (row["value"], row["state"], row["reason"]) == (
        None,
        "unavailable",
        "metric_quality_invalid",
    )


@pytest.mark.parametrize("score", [0.0, 1.0])
def test_quality_score_preserves_valid_fraction_boundaries(score):
    from app.domains.geo.rainfall.service import metric_rows, normalize_snapshot

    snapshot = _snapshot(_metric(score=score))
    snapshot["metric_policy"]["minimum_quality_by_metric"]["annual"] = score
    row = metric_rows(normalize_snapshot(snapshot, expected_policy_revision="v1"))[0]

    assert (row["value"], row["state"], row["reason"]) == (21.0, "available", None)
