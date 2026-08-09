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
    assert "analysis_missing" in body["labels"]
    assert "role:historical" in body["labels"]


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


# -----------------------------------------------------------------------------
# Finding A: outbox insert must be committed durably
# -----------------------------------------------------------------------------


def test_queue_missing_analysis_commits_outbox_row():
    from app.db.session import SessionLocal
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.scope import AnalysisScope
    from app.domains.geo.rainfall.service import queue_missing_analysis

    scope = AnalysisScope(kind="zone", id="zone-1", version="v1", regional_estimate=False)
    with SessionLocal() as db:
        result = queue_missing_analysis(db, scope=scope, year=2024, labels=("analysis_missing",))

    with SessionLocal() as fresh:
        row = fresh.get(RainfallOutbox, result["outbox_id"])
        assert row is not None
        assert row.status == "pending"
        assert row.source_id == "chirps-v3-final"
        fresh.delete(row)
        fresh.commit()


# -----------------------------------------------------------------------------
# Finding C: duplicate outbox rows must be prevented / idempotent enqueue
# -----------------------------------------------------------------------------


def test_queue_missing_analysis_is_idempotent_for_pending_row(db):
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.scope import AnalysisScope
    from app.domains.geo.rainfall.service import queue_missing_analysis

    scope = AnalysisScope(kind="zone", id="zone-1", version="v1", regional_estimate=False)
    first = queue_missing_analysis(db, scope=scope, year=2024, labels=("analysis_missing",))
    db.commit()
    second = queue_missing_analysis(db, scope=scope, year=2024, labels=("analysis_missing",))

    assert first["outbox_id"] == second["outbox_id"]
    assert db.query(RainfallOutbox).filter_by(status="pending").count() == 1


def test_pending_unique_constraint_allows_reenqueue_after_done(db):
    from uuid import uuid4

    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.scope import AnalysisScope
    from app.domains.geo.rainfall.service import queue_missing_analysis

    scope = AnalysisScope(kind="zone", id="zone-1", version="v1", regional_estimate=False)
    done_row = RainfallOutbox(
        id=uuid4(),
        source_id="chirps-v3-final",
        role="historical",
        scope_kind=scope.kind,
        scope_id=scope.id,
        scope_version=scope.version,
        year=2024,
        status="done",
        # rainfall-materialization PR3 decision 6: a `done` row within
        # RAINFALL_RECOMPUTE_COOLDOWN (10 min) now skips re-enqueue on
        # purpose (see test_rainfall_materialization.py's
        # test_repeated_post_skips_reenqueue_after_recent_done). Backdating
        # past the cooldown keeps THIS test's own point intact: the
        # pending-only partial unique index still allows a fresh pending
        # row once the previous attempt is done.
        completed_at=datetime.now(UTC) - timedelta(minutes=20),
    )
    db.add(done_row)
    db.commit()

    queued = queue_missing_analysis(db, scope=scope, year=2024, labels=("analysis_missing",))
    assert queued["outbox_id"] != str(done_row.id)
    assert db.query(RainfallOutbox).filter_by(status="pending").count() == 1


# -----------------------------------------------------------------------------
# Finding G: source/role resolution from request and year
# -----------------------------------------------------------------------------


def test_resolve_missing_work_source_uses_intensity_for_event_window():
    from app.domains.geo.rainfall.service import resolve_missing_work_source

    event_window = {
        "start": "2024-03-01T00:00:00Z",
        "end": "2024-03-02T00:00:00Z",
    }
    resolved = resolve_missing_work_source(event_window, year=2024)

    assert resolved["role"] == "intensity"
    assert resolved["source_id"] == "sinarame-rqpe"
    assert resolved["interval_start"] == datetime(2024, 3, 1, 0, 0, tzinfo=UTC)
    assert resolved["interval_end"] == datetime(2024, 3, 2, 0, 0, tzinfo=UTC)


def test_resolve_missing_work_source_uses_daily_for_current_year():
    from app.domains.geo.rainfall.service import resolve_missing_work_source

    current_year = datetime.now(UTC).year
    resolved = resolve_missing_work_source(None, year=current_year)

    assert resolved["role"] == "daily"
    assert resolved["source_id"] == "sqpe-obs"
    assert resolved["interval_start"] == datetime(current_year, 1, 1, 0, 0, tzinfo=UTC)
    assert resolved["interval_end"] == datetime(current_year + 1, 1, 1, 0, 0, tzinfo=UTC)


def test_resolve_missing_work_source_uses_historical_for_past_year():
    from app.domains.geo.rainfall.service import resolve_missing_work_source

    resolved = resolve_missing_work_source(None, year=2022)

    assert resolved["role"] == "historical"
    assert resolved["source_id"] == "chirps-v3-final"
    assert resolved["interval_start"] == datetime(2022, 1, 1, 0, 0, tzinfo=UTC)
    assert resolved["interval_end"] == datetime(2023, 1, 1, 0, 0, tzinfo=UTC)


def test_resolve_missing_work_source_uses_validation_when_explicitly_requested():
    from app.domains.geo.rainfall.service import resolve_missing_work_source

    resolved = resolve_missing_work_source(None, year=2024, requested_role="validation")

    assert resolved["role"] == "validation"
    # rainfall-materialization PR3 task 3.18: fixed the "smn-gauges" typo to
    # match adapters/manifests.py's validation-role candidate ("smn-gauge").
    assert resolved["source_id"] == "smn-gauge"


# -----------------------------------------------------------------------------
# Finding B: outbox consumer task transitions rows correctly
# -----------------------------------------------------------------------------


def test_process_outbox_task_is_registered():
    from app.domains.geo.rainfall import tasks

    assert tasks.process_outbox.name == "rainfall.process_outbox"


def test_process_outbox_transitions_pending_rows_to_done(db, monkeypatch):
    from uuid import uuid4

    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox

    row = RainfallOutbox(
        id=uuid4(),
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-1",
        scope_version="v1",
        year=2024,
        status="pending",
        next_attempt_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()

    calls = []

    def fake_ingest(**kwargs):
        calls.append(kwargs)
        return {"intervals": 3}

    monkeypatch.setattr(tasks, "ingest_source_scope", fake_ingest)
    result = tasks.process_outbox(db=db)

    assert result["processed"] == 1
    assert result["succeeded"] == 1
    assert result["failed"] == 0
    db.refresh(row)
    assert row.status == "done"
    assert row.completed_at is not None
    assert calls[0]["source_id"] == "chirps-v3-final"
    assert calls[0]["role"] == "historical"


def test_process_outbox_marks_failed_after_max_retries(db, monkeypatch):
    from uuid import uuid4

    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox

    row = RainfallOutbox(
        id=uuid4(),
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-1",
        scope_version="v1",
        year=2024,
        status="pending",
        retry_count=4,
        next_attempt_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()

    monkeypatch.setattr(
        tasks,
        "ingest_source_scope",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("boom")),
    )
    result = tasks.process_outbox(db=db)

    assert result["processed"] == 1
    assert result["succeeded"] == 0
    assert result["failed"] == 1
    db.refresh(row)
    assert row.status == "failed"
    assert row.retry_count == 5
    assert row.next_attempt_at > datetime.now(UTC)
    assert "boom" in (row.last_error or "")


def test_process_outbox_delays_pending_row_after_recoverable_error(db, monkeypatch):
    from uuid import uuid4

    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox

    row = RainfallOutbox(
        id=uuid4(),
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-1",
        scope_version="v1",
        year=2024,
        status="pending",
        retry_count=1,
        next_attempt_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()

    monkeypatch.setattr(
        tasks,
        "ingest_source_scope",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("boom")),
    )
    result = tasks.process_outbox(db=db)

    assert result["processed"] == 1
    assert result["succeeded"] == 0
    assert result["failed"] == 0
    db.refresh(row)
    assert row.status == "pending"
    assert row.retry_count == 2
    assert row.next_attempt_at > datetime.now(UTC)
    assert "boom" in (row.last_error or "")


def test_process_outbox_respects_batch_limit(db, monkeypatch):
    from uuid import uuid4

    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox

    for i in range(55):
        db.add(
            RainfallOutbox(
                id=uuid4(),
                source_id="chirps-v3-final",
                role="historical",
                scope_kind="zone",
                scope_id=f"zone-{i}",
                scope_version="v1",
                year=2024,
                status="pending",
                next_attempt_at=datetime.now(UTC),
            )
        )
    db.flush()

    monkeypatch.setattr(tasks, "ingest_source_scope", lambda **_kwargs: {"intervals": 1})
    result = tasks.process_outbox(db=db)

    assert result["processed"] <= 50
    assert db.query(RainfallOutbox).filter_by(status="done").count() == result["processed"]


# -----------------------------------------------------------------------------
# Finding F: backfill_missing must pass role to ingest_source_scope
# -----------------------------------------------------------------------------


def test_backfill_missing_passes_role_to_ingest_source_scope(db, monkeypatch):
    from app.domains.geo.rainfall import tasks

    calls = []

    def fake_ingest(**kwargs):
        calls.append(kwargs)
        return {"intervals": 5}

    monkeypatch.setattr(tasks, "ingest_source_scope", fake_ingest)
    result = tasks.backfill_missing(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-1",
        scope_version="v1",
        year=2024,
    )

    assert result["status"] == "completed"
    assert len(calls) == 1
    assert calls[0]["role"] == "historical"
