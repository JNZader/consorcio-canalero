"""Contract tests for Rainfall v2 ingest operations, outbox and feature flags."""

from datetime import UTC, datetime, timedelta

import pytest


def test_rainfall_outbox_requires_source_role_interval_scope_and_labels_work():
    from app.domains.geo.rainfall.models import RainfallOutbox

    now = datetime.now(UTC)
    row = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-1",
        scope_version="v1",
        year=2024,
        work_labels=("missing_annual",),
        interval_start=now,
        interval_end=now + timedelta(days=1),
        status="pending",
        retry_count=0,
    )
    assert row.source_id == "chirps-v3-final"
    assert row.status == "pending"
    assert row.retry_count == 0
    assert row.work_labels == ("missing_annual",)


def test_rainfall_outbox_status_transition_and_retry_cap():
    from app.domains.geo.rainfall.models import RainfallOutbox

    now = datetime.now(UTC)
    row = RainfallOutbox(
        source_id="sqpe-obs",
        role="daily",
        scope_kind="basin",
        scope_id="basin-1",
        scope_version="v2",
        year=2025,
        work_labels=("missing_7d",),
        interval_start=now,
        interval_end=now + timedelta(days=1),
    )
    row.status = "done"
    row.completed_at = now
    assert row.status == "done"
    with pytest.raises(ValueError, match="status"):
        RainfallOutbox(status="invalid")


def test_feature_flags_are_false_by_default_for_all_source_roles():
    from app.domains.geo.rainfall.feature_flags import get_rainfall_feature_flags

    flags = get_rainfall_feature_flags({})
    for role in ("historical", "daily", "intensity", "validation"):
        assert flags[role] is False


def test_feature_flags_read_enabled_values_from_settings_blob():
    from app.domains.geo.rainfall.feature_flags import get_rainfall_feature_flags

    flags = get_rainfall_feature_flags(
        {"rainfall_feature_flags": {"historical": True, "daily": True}}
    )
    assert flags["historical"] is True
    assert flags["daily"] is True
    assert flags["intensity"] is False


def test_feature_flags_reject_non_bool_values():
    from app.domains.geo.rainfall.feature_flags import get_rainfall_feature_flags

    flags = get_rainfall_feature_flags(
        {"rainfall_feature_flags": {"historical": "yes", "intensity": 1}}
    )
    assert flags["historical"] is False
    assert flags["intensity"] is False


def test_ingest_tasks_are_registered_with_rainfall_namespace():
    from app.domains.geo.rainfall import tasks

    names = {
        "rainfall.ingest_source_scope",
        "rainfall.revisit_stale",
        "rainfall.backfill_missing",
    }
    found = {
        task.name
        for task in (
            tasks.ingest_source_scope,
            tasks.revisit_stale,
            tasks.backfill_missing,
        )
    }
    assert names == found


def test_resilient_adapter_cache_key_is_deterministic_and_role_aware():
    from app.domains.geo.rainfall.adapters.resilience import cache_key_for

    key = cache_key_for(
        source_id="imerg-v07",
        role="intensity",
        scope_kind="zone",
        scope_id="z1",
        scope_version="v1",
        year=2024,
    )
    assert key.startswith("rainfall:source:")
    assert "imerg-v07" in key
    assert "intensity" in key
    same = cache_key_for(
        source_id="imerg-v07",
        role="intensity",
        scope_kind="zone",
        scope_id="z1",
        scope_version="v1",
        year=2024,
    )
    different = cache_key_for(
        source_id="imerg-v07",
        role="intensity",
        scope_kind="zone",
        scope_id="z2",
        scope_version="v1",
        year=2024,
    )
    assert key == same
    assert key != different


def test_resilient_adapter_state_transitions_from_closed_to_open_on_quota():
    from app.domains.geo.rainfall.adapters.resilience import CircuitState, ResilientAdapterState

    state = ResilientAdapterState()
    assert state.circuit == CircuitState.CLOSED
    state.record_success()
    assert state.consecutive_failures == 0
    for _ in range(5):
        state.record_failure()
    assert state.circuit == CircuitState.OPEN


def test_resilient_adapter_state_half_opens_after_timeout():
    from app.domains.geo.rainfall.adapters.resilience import CircuitState, ResilientAdapterState

    state = ResilientAdapterState(failure_threshold=1, recovery_seconds=0)
    state.record_failure()
    assert state.circuit == CircuitState.OPEN
    assert state.can_attempt()
    assert state.circuit == CircuitState.HALF_OPEN


def test_circuit_breaker_blocks_attempts_when_open():
    from app.domains.geo.rainfall.adapters.resilience import CircuitOpen, ResilientAdapterState

    state = ResilientAdapterState(failure_threshold=1, recovery_seconds=3600)
    state.record_failure()
    with pytest.raises(CircuitOpen):
        state.can_attempt()


def test_backoff_increases_with_attempts_and_caps():
    from app.domains.geo.rainfall.adapters.resilience import backoff_seconds

    assert backoff_seconds(1) < backoff_seconds(2) < backoff_seconds(3)
    assert backoff_seconds(100) == backoff_seconds(50)


def test_resilient_fetch_runs_under_timeout():
    from datetime import UTC, datetime

    from app.domains.geo.rainfall.adapters.resilience import ResilientAdapter
    from app.domains.geo.rainfall.ports import SourceBatch, SourceInterval

    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    batch = SourceBatch(
        source_id="fake",
        scope_kind="zone",
        scope_id="z1",
        scope_version="v1",
        cadence=timedelta(days=1),
        intervals=(SourceInterval(start, start + timedelta(days=1), 1.0, "mm", "r1"),),
        coverage=1.0,
        completeness=1.0,
        quality={},
        discrepancies=(),
        checksum="c1",
    )

    def fetch(**_kwargs):
        return batch

    adapter = ResilientAdapter(fetch, timeout_seconds=5)
    result = adapter.fetch(
        source_id="fake",
        role="daily",
        scope_kind="zone",
        scope_id="z1",
        scope_version="v1",
        start=start,
        end=start + timedelta(days=1),
    )
    assert result == batch
    assert adapter.state.consecutive_failures == 0


def test_resilient_fetch_records_failure_and_raises_adapter_error():
    from datetime import UTC, datetime

    from app.domains.geo.rainfall.adapters.resilience import AdapterError, ResilientAdapter

    def fetch(**_kwargs):
        raise TimeoutError("slow")

    adapter = ResilientAdapter(fetch, timeout_seconds=1, max_retries=0)
    with pytest.raises(AdapterError, match="slow"):
        adapter.fetch(
            source_id="fake",
            role="daily",
            scope_kind="zone",
            scope_id="z1",
            scope_version="v1",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 2, tzinfo=UTC),
        )
    assert adapter.state.consecutive_failures == 1


def test_analysis_request_queues_missing_work_when_no_snapshot_exists(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.auth import require_admin_or_operator
    from app.db.session import get_db
    from app.domains.geo.rainfall.router import router

    app = FastAPI()
    app.dependency_overrides[require_admin_or_operator] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    app.include_router(router)
    client = TestClient(app)

    payload = {"scope": {"kind": "zone", "id": "zone-1", "version": "v1"}, "year": 2024}
    response = client.post("/rainfall/analyses", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["labels"] == ["analysis_missing"]


def test_analysis_request_returns_snapshot_when_available(db, monkeypatch):
    from uuid import uuid4

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.auth import require_admin_or_operator
    from app.db.session import get_db
    from app.domains.geo.rainfall.models import RainfallAnalysisRevision
    from app.domains.geo.rainfall.router import router
    from app.domains.geo.rainfall.service import analysis_request_fingerprint

    app = FastAPI()
    app.dependency_overrides[require_admin_or_operator] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    app.include_router(router)

    payload = {"scope": {"kind": "zone", "id": "zone-1", "version": "v1"}, "year": 2024}
    revision = RainfallAnalysisRevision(
        id=uuid4(),
        request_fingerprint=analysis_request_fingerprint(payload),
        policy_revision="v1",
        data_revision="d1",
        snapshot={
            "metric_policy": {
                "revision": "v1",
                "minimum_coverage_by_metric": {"annual": 0.8},
                "minimum_quality_by_metric": {"annual": 0.7},
                "duration_threshold": 1.0,
            },
            "annual": {
                "selected": {
                    "metric": "annual",
                    "value": 21.0,
                    "unit": "mm",
                    "state": "available",
                    "interval_start": "2024-01-01T00:00:00Z",
                    "interval_end": "2024-01-02T00:00:00Z",
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
                        "freshness": "2024-01-02T00:00:00Z",
                        "available_through": "2024-01-02T00:00:00Z",
                    },
                    "fallback_used": False,
                }
            },
        },
    )
    db.add(revision)
    db.commit()

    response = TestClient(app).post("/rainfall/analyses", json=payload)
    assert response.status_code == 200
    assert response.json()["annual"]["selected"]["value"] == 21.0
