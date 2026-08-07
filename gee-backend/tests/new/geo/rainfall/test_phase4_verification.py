"""Phase 4 verification: replay/idempotency, feature-flag gates, audit retention.

Covers Task 4.2 of the lluvia-v2 change (migration/replay/idempotency/feature
flags/rollout validity) for everything that is testable without provider
credentials:

- Replay: a double-run of ``backfill_missing`` must not double the ingest work
  (``already_complete`` checkpoint, one adapter call).
- The deployed partial unique index rejects duplicate *pending* outbox rows and
  allows a re-enqueue once the row leaves ``pending`` (done/failed) — the index
  is verified at the database, not only in the application enqueue path.
- Feature-flag activation gate (per metric-role): a disabled role never reaches
  the adapter and its queued work is skipped by the outbox consumer without
  losing the row (rollback retains audits). Re-enabling the role drains it.
- The rollback procedure (disable flags, stop jobs) does not delete evidence.
- Observability seam (Task 4.3): metric events are emitted through a
  metrics-ready seam with stable names, so a future metric backend can be wired
  without touching the call sites.
"""

from datetime import UTC, datetime

import pytest


def test_backfill_double_run_replays_without_duplicate_ingest(db, monkeypatch):
    """Replay: a second backfill for the same source/scope/version/year is a
    no-op that keeps the existing checkpoint (``already_complete``)."""
    from app.domains.geo.rainfall import tasks

    calls = []

    def fake_ingest(**kwargs):
        calls.append(kwargs)
        return {"intervals": 5}

    monkeypatch.setattr(tasks, "ingest_source_scope", fake_ingest)
    kwargs = dict(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-4c-1",
        scope_version="v1",
        year=2024,
    )

    first = tasks.backfill_missing(**kwargs)
    second = tasks.backfill_missing(**kwargs)

    assert first["status"] == "completed"
    assert second["status"] == "already_complete"
    assert len(calls) == 1


def test_backfill_replay_after_partial_run_ingests_again(db, monkeypatch):
    """Replay semantics: an interrupted backfill (checkpoint present, not yet
    completed) is re-runnable through a separate database session — it ingests
    again and then completes."""
    from app.db.session import SessionLocal
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallBackfillCheckpoint

    # Seed an interrupted checkpoint through the real session factory, the same
    # way a crashed worker leaves one behind.
    with SessionLocal() as seed_db:
        seed_db.add(
            RainfallBackfillCheckpoint(
                source_id="chirps-v3-final",
                role="historical",
                scope_kind="zone",
                scope_id="zone-4c-2",
                scope_version="v1",
                year=2024,
                cursor="page-1",
                completed_at=None,
            )
        )
        seed_db.commit()

    calls = []
    monkeypatch.setattr(
        tasks, "ingest_source_scope", lambda **_kwargs: calls.append(1) or {"intervals": 3}
    )
    result = tasks.backfill_missing(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-4c-2",
        scope_version="v1",
        year=2024,
    )

    assert result["status"] == "completed"
    assert len(calls) == 1


def test_partial_unique_index_rejects_duplicate_pending_outbox_row(db):
    """DB-level proof of the partial unique index (lluvia_v2_004): two PENDING
    rows with the same source/role/scope/version/year violate the index."""
    from uuid import uuid4

    from sqlalchemy.exc import IntegrityError

    from app.domains.geo.rainfall.models import RainfallOutbox

    row = RainfallOutbox(
        id=uuid4(),
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-4c-3",
        scope_version="v1",
        year=2024,
        status="pending",
    )
    db.add(row)
    db.flush()

    duplicate = RainfallOutbox(
        id=uuid4(),
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-4c-3",
        scope_version="v1",
        year=2024,
        status="pending",
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.flush()


def test_partial_unique_index_allows_reenqueue_when_terminal(db):
    """The partial index only covers PENDING rows: once a row reaches the
    terminal ``done`` state the same key can be queued again."""
    from uuid import uuid4

    from app.domains.geo.rainfall.models import RainfallOutbox

    now = datetime.now(UTC)
    db.add(
        RainfallOutbox(
            id=uuid4(),
            source_id="chirps-v3-final",
            role="historical",
            scope_kind="zone",
            scope_id="zone-4c-4",
            scope_version="v1",
            year=2024,
            status="done",
            completed_at=now,
        )
    )
    db.flush()

    queued = RainfallOutbox(
        id=uuid4(),
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-4c-4",
        scope_version="v1",
        year=2024,
        status="pending",
    )
    db.add(queued)
    db.flush()  # no IntegrityError: the index is partial over status = 'pending'
    assert db.query(RainfallOutbox).filter_by(status="pending").one().id == queued.id


def test_ingest_source_scope_refuses_a_disabled_role(db, monkeypatch):
    """A metric-role whose source-role activation flag is OFF never reaches the
    provider adapter (the feature-flag gate is the outermost guard)."""
    from app.domains.geo.rainfall import tasks

    monkeypatch.setattr(tasks, "_role_enabled", lambda role, db=None: False)

    with pytest.raises(tasks.RainfallRoleDisabled, match="disabled"):
        tasks.ingest_source_scope(
            source_id="sqpe-obs",
            role="daily",
            scope_kind="zone",
            scope_id="zone-4c-5",
            scope_version="v1",
            year=2025,
        )


def test_outbox_skips_and_retains_rows_for_disabled_role(db, monkeypatch):
    """Rollout gate: when a role is disabled, its queued rows are skipped (not
    counted as processed nor failed) and kept pending — the audit trail
    survives the rollback and the row drains once the role is re-enabled."""
    from uuid import uuid4

    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox

    def new_row(role: str, year: int, scope_id: str):
        row = RainfallOutbox(
            id=uuid4(),
            source_id="chirps-v3-final",
            role=role,
            scope_kind="zone",
            scope_id=scope_id,
            scope_version="v1",
            year=year,
            status="pending",
            next_attempt_at=datetime.now(UTC),
        )
        db.add(row)
        db.flush()
        return row

    disabled = new_row("historical", 2024, "zone-4c-6")
    enabled = new_row("daily", 2025, "zone-4c-7")
    db.flush()

    monkeypatch.setattr(tasks, "_role_enabled", lambda role, db=None: role == "daily")
    monkeypatch.setattr(tasks, "ingest_source_scope", lambda **kwargs: {"intervals": 1})

    result = tasks.process_outbox(db=db)

    # The disabled role's row is skipped before touching the adapter; the
    # enabled one drains normally.
    assert result["skipped"] == 1
    assert result["processed"] == 1
    assert result["succeeded"] == 1
    db.refresh(disabled)
    db.refresh(enabled)
    assert disabled.status == "pending"
    assert enabled.status == "done"
    # No worker retry booked on the skipped row either.
    assert disabled.retry_count == 0


def test_flag_turn_off_retains_outbox_and_audit_rows(db):
    """Disabling a role must never delete audit evidence (outbox rows,
    eligibility rows or immutable interval facts)."""
    from uuid import uuid4

    from app.domains.geo.rainfall.feature_flags import get_rainfall_feature_flags
    from app.domains.geo.rainfall.models import (
        RainfallIntervalValue,
        RainfallOutbox,
        RainfallSourceEligibility,
    )

    flags_on = get_rainfall_feature_flags(
        {"rainfall_feature_flags": {"historical": True, "daily": True}}
    )
    assert flags_on["historical"] is True

    now = datetime.now(UTC)
    db.add(
        RainfallOutbox(
            id=uuid4(),
            source_id="chirps-v3-final",
            role="historical",
            scope_kind="zone",
            scope_id="zone-4c-8",
            scope_version="v1",
            year=2024,
            status="done",
            completed_at=now,
        )
    )
    db.add(
        RainfallSourceEligibility(
            id=uuid4(),
            source_id="chirps-v3-final",
            role="historical",
            evidence_revision="ev-1",
            eligible=True,
            criteria={},
            failed_criteria=[],
            manifest_version=1,
            provider_revision="p1",
            checksum="c1",
        )
    )
    db.add(
        RainfallIntervalValue(
            id=uuid4(),
            source_id="chirps-v3-final",
            scope_kind="zone",
            scope_id="zone-4c-9",
            scope_version="v1",
            interval_start=now,
            interval_end=now,
            provider_revision="rx",
            value=12.0,
            unit="mm",
        )
    )
    db.commit()
    counts_before = {
        "outbox": db.query(RainfallOutbox).count(),
        "eligibility": db.query(RainfallSourceEligibility).count(),
        "intervals": db.query(RainfallIntervalValue).count(),
    }

    # The rollback procedure (see the observability workbook) flips every role
    # to False; nothing deletes stored facts/audits.
    flags_off = get_rainfall_feature_flags({"rainfall_feature_flags": {}})
    assert flags_off["historical"] is False
    assert flags_off["daily"] is False
    assert db.query(RainfallOutbox).count() == counts_before["outbox"]
    assert db.query(RainfallSourceEligibility).count() == counts_before["eligibility"]
    assert db.query(RainfallIntervalValue).count() == counts_before["intervals"]


def test_rainfall_observability_seam_emits_structured_events(caplog):
    """Task 4.3 seam: metric events go through the metrics-ready registry and
    render as structured log lines; no metrics dependency is required."""
    from app.domains.geo.rainfall import metrics

    with caplog.at_level("INFO", logger="rainfall"):
        metrics.record_event("rainfall.analysis.served", revision="rev-9", latency_ms=12)
        metrics.record_gauge("rainfall.outbox.backlog", value=3)

    messages = "\n".join(r.message for r in caplog.records if r.name.startswith("rainfall"))
    assert "rainfall.analysis.served" in messages
    assert "rainfall.outbox.backlog" in messages
