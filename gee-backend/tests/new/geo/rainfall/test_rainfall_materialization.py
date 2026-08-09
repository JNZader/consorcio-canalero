"""Rainfall v2 materialization: persistence, supersession, chained compute,
revisit sweeps, year-rollover finalization and their end-to-end wiring.

Real PostgreSQL throughout (the ``db`` fixture) — the partial unique indexes
and the advisory-lock concurrency guarantees this change relies on exist
nowhere else. The append-only *trigger*
(``trg_rainfall_interval_value_immutable``) is raw SQL created by the
``lluvia_v2_001_evidence_foundation`` migration, not by ``Base.metadata``,
so this module's harness (``conftest.py``'s ``create_all`` schema) never
creates it and this file makes no claim that the trigger fires. Append-only
enforcement in this harness comes only from the ORM ``before_flush`` guard
(``models.py`` ``_prevent_rainfall_audit_mutation``), which inspects
``session.dirty``/``session.deleted`` and therefore never gates an INSERT —
consistent with every write path exercised here being an ``INSERT ..  ON
CONFLICT DO NOTHING`` (never an UPDATE or a DELETE). Provider I/O is faked
at the ``GeeZonalClient`` boundary only (same harness as
``test_provider_adapters.py``), so the adapter, the zonal batch builder, the
persistence write path and the compute layer all run for real.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.domains.geo.rainfall.models import (
    RainfallBackfillCheckpoint,
    RainfallIntervalLifecycle,
    RainfallIntervalValue,
)
from app.domains.geo.rainfall.ports import SourceBatch, SourceInterval

ZONE_KWARGS = {"scope_kind": "zone", "scope_id": "z1", "scope_version": "v1"}


def _daily_intervals(
    *, start_day: int, values: list[float], provider_revision: str = "v3-final", month: int = 1
) -> list[SourceInterval]:
    """Build consecutive UTC-daily ``SourceInterval`` rows starting at day *start_day*."""
    intervals = []
    for offset, value in enumerate(values):
        day = start_day + offset
        start = datetime(2024, month, day, tzinfo=UTC)
        intervals.append(
            SourceInterval(start, start + timedelta(days=1), value, "mm", provider_revision)
        )
    return intervals


def _count_interval_rows(
    db, *, source_id: str = "chirps-v3-final", scope_id: str | None = None
) -> int:
    query = (
        select(func.count())
        .select_from(RainfallIntervalValue)
        .where(RainfallIntervalValue.source_id == source_id)
    )
    if scope_id is not None:
        query = query.where(RainfallIntervalValue.scope_id == scope_id)
    return db.scalar(query)


# ---------------------------------------------------------------------------
# Task 1.1 — Interval Persistence on Ingest: re-ingest is idempotent
# ---------------------------------------------------------------------------


def test_reingest_is_idempotent(db):
    from app.domains.geo.rainfall.repository import persist_intervals

    rows = _daily_intervals(start_day=1, values=[1.5, 0.0, 3.25])

    persist_intervals(db, source_id="chirps-v3-final", rows=rows, **ZONE_KWARGS)
    db.flush()

    # Re-running the identical ingest must not raise and must not duplicate.
    result = persist_intervals(db, source_id="chirps-v3-final", rows=rows, **ZONE_KWARGS)
    db.flush()

    # R3-001: assert the full classification, not just the row count — a
    # count-only assertion passes even against an implementation whose
    # window-bound regression silently absorbs a real correction into the
    # bulk ON-CONFLICT skip (the count would still equal len(rows)).
    assert result["inserted"] == 0
    assert result["unchanged"] == len(rows)
    assert _count_interval_rows(db) == len(rows)


def test_persist_intervals_corrects_a_non_first_slot_in_a_multi_slot_batch(db):
    """R3-001: the idempotence test above only ever exercises an
    all-unchanged batch. This proves classification distinguishes slots
    WITHIN one batch — restating day 3 alone must not be absorbed by the
    other two unchanged slots into a bulk skip."""
    from app.domains.geo.rainfall.repository import intervals_in_window, persist_intervals

    original = _daily_intervals(start_day=1, values=[1.0, 2.0, 3.0], provider_revision="v3-nrt")
    persist_intervals(db, source_id="chirps-v3-sat", rows=original, **ZONE_KWARGS)
    db.flush()

    restated = _daily_intervals(start_day=1, values=[1.0, 2.0, 3.9], provider_revision="v3-nrt")
    result = persist_intervals(db, source_id="chirps-v3-sat", rows=restated, **ZONE_KWARGS)
    db.flush()

    assert result["inserted"] == 1
    assert result["unchanged"] == 2
    assert result["superseded"] == 1

    current = intervals_in_window(
        db,
        source_id="chirps-v3-sat",
        start=restated[0].interval_start,
        end=restated[-1].interval_end,
        **ZONE_KWARGS,
    )
    assert [row.value for row in current] == [1.0, 2.0, 3.9]
    assert [row.provider_revision for row in current] == ["v3-nrt", "v3-nrt", "v3-nrt+r1"]


def test_reingest_after_synthetic_supersession_with_no_successor_hits_conflict_path(db):
    """R3-001: forced-conflict-path regression. A slot whose only row is
    marked ``superseded`` with no real successor (a state the write
    algorithm itself never produces — ``record_supersession`` only ever
    runs for ids ``RETURNING`` confirms landed) makes
    ``intervals_in_window`` classify the slot as ABSENT even though a row
    with the identical ``(source_id, scope, window, provider_revision)``
    tuple already exists on disk. Re-persisting the identical interval must
    still resolve through the ``ON CONFLICT DO NOTHING`` path without
    raising, proving the INSERT statement itself — not just the
    classification read — is conflict-safe."""
    from app.domains.geo.rainfall.repository import intervals_in_window, persist_intervals

    rows = _daily_intervals(start_day=1, values=[2.0])
    persist_intervals(db, source_id="chirps-v3-final", rows=rows, **ZONE_KWARGS)
    db.flush()

    original = intervals_in_window(
        db,
        source_id="chirps-v3-final",
        start=rows[0].interval_start,
        end=rows[0].interval_end,
        **ZONE_KWARGS,
    )[0]

    db.add(
        RainfallIntervalLifecycle(
            interval_value_id=original.id,
            superseded_by_id=uuid4(),
            event_type="superseded",
            expires_at=None,
        )
    )
    db.flush()

    assert (
        intervals_in_window(
            db,
            source_id="chirps-v3-final",
            start=rows[0].interval_start,
            end=rows[0].interval_end,
            **ZONE_KWARGS,
        )
        == []
    )

    result = persist_intervals(db, source_id="chirps-v3-final", rows=rows, **ZONE_KWARGS)
    db.flush()

    # The classification read said "absent" and the write attempted a
    # duplicate-tuple INSERT; ON CONFLICT DO NOTHING absorbed it, RETURNING
    # reported nothing landed, and nothing raised.
    assert result["inserted"] == 0
    assert _count_interval_rows(db) == 1


# ---------------------------------------------------------------------------
# Task 1.3 — absent slot classifies as an INSERT
# ---------------------------------------------------------------------------


def test_persist_intervals_inserts_absent_slot(db):
    from app.domains.geo.rainfall.repository import intervals_in_window, persist_intervals

    rows = _daily_intervals(start_day=1, values=[2.0])

    result = persist_intervals(db, source_id="chirps-v3-final", rows=rows, **ZONE_KWARGS)
    db.flush()

    assert result["inserted"] == 1
    current = intervals_in_window(
        db,
        source_id="chirps-v3-final",
        start=rows[0].interval_start,
        end=rows[0].interval_end,
        **ZONE_KWARGS,
    )
    assert len(current) == 1
    assert current[0].provider_revision == "v3-final"
    assert current[0].value == 2.0


# ---------------------------------------------------------------------------
# Task 1.4 — a value equal at 6 decimal places is a no-op
# ---------------------------------------------------------------------------


def test_persist_intervals_unchanged_slot_writes_nothing(db):
    from app.domains.geo.rainfall.repository import persist_intervals

    first = _daily_intervals(start_day=1, values=[1.5])
    persist_intervals(db, source_id="chirps-v3-final", rows=first, **ZONE_KWARGS)
    db.flush()

    # Re-fetched value differs only past the 6th decimal place.
    restated = _daily_intervals(start_day=1, values=[1.5000001])
    result = persist_intervals(db, source_id="chirps-v3-final", rows=restated, **ZONE_KWARGS)
    db.flush()

    assert result["inserted"] == 0
    assert result["unchanged"] == 1
    assert _count_interval_rows(db) == 1
    lifecycle_count = db.scalar(select(func.count()).select_from(RainfallIntervalLifecycle))
    assert lifecycle_count == 0


# ---------------------------------------------------------------------------
# Task 1.5 — a changed slot appends a correction row + lifecycle evidence
# ---------------------------------------------------------------------------


def test_persist_intervals_changed_slot_appends_correction_and_lifecycle_row(db):
    from app.domains.geo.rainfall.repository import intervals_in_window, persist_intervals

    # CHIRPS pins one revision string per source_id and restates values
    # behind it (chirps.py:26-29) — both fetches carry the same family.
    original = _daily_intervals(start_day=1, values=[1.0], provider_revision="v3-nrt")
    persist_intervals(db, source_id="chirps-v3-sat", rows=original, **ZONE_KWARGS)
    db.flush()

    restated = _daily_intervals(start_day=1, values=[1.8], provider_revision="v3-nrt")
    result = persist_intervals(db, source_id="chirps-v3-sat", rows=restated, **ZONE_KWARGS)
    db.flush()

    assert result["inserted"] == 1
    assert result["superseded"] == 1
    # The original row is retained unchanged — this is append-only evidence.
    assert _count_interval_rows(db, source_id="chirps-v3-sat") == 2

    current = intervals_in_window(
        db,
        source_id="chirps-v3-sat",
        start=restated[0].interval_start,
        end=restated[0].interval_end,
        **ZONE_KWARGS,
    )
    assert len(current) == 1
    assert current[0].value == 1.8
    assert current[0].provider_revision == "v3-nrt+r1"

    lifecycle_rows = list(db.scalars(select(RainfallIntervalLifecycle)))
    assert len(lifecycle_rows) == 1
    lifecycle = lifecycle_rows[0]
    assert lifecycle.event_type == "superseded"
    assert lifecycle.superseded_by_id == current[0].id

    original_row = db.scalar(
        select(RainfallIntervalValue).where(RainfallIntervalValue.provider_revision == "v3-nrt")
    )
    assert original_row is not None
    assert original_row.value == 1.0
    assert lifecycle.interval_value_id == original_row.id


# ---------------------------------------------------------------------------
# Task 1.6 — a second correction chains off the first
# ---------------------------------------------------------------------------


def test_second_correction_chains_off_first(db):
    from app.domains.geo.rainfall.repository import intervals_in_window, persist_intervals

    first = _daily_intervals(start_day=1, values=[1.0], provider_revision="v3-nrt")
    persist_intervals(db, source_id="chirps-v3-sat", rows=first, **ZONE_KWARGS)
    db.flush()

    second = _daily_intervals(start_day=1, values=[1.8], provider_revision="v3-nrt")
    persist_intervals(db, source_id="chirps-v3-sat", rows=second, **ZONE_KWARGS)
    db.flush()

    third = _daily_intervals(start_day=1, values=[2.4], provider_revision="v3-nrt")
    result = persist_intervals(db, source_id="chirps-v3-sat", rows=third, **ZONE_KWARGS)
    db.flush()

    assert result["inserted"] == 1
    assert result["superseded"] == 1

    current = intervals_in_window(
        db,
        source_id="chirps-v3-sat",
        start=third[0].interval_start,
        end=third[0].interval_end,
        **ZONE_KWARGS,
    )
    assert len(current) == 1
    assert current[0].provider_revision == "v3-nrt+r2"
    assert current[0].value == 2.4

    assert _count_interval_rows(db, source_id="chirps-v3-sat") == 3
    lifecycle_rows = list(db.scalars(select(RainfallIntervalLifecycle)))
    assert len(lifecycle_rows) == 2

    superseded_by_map = {row.interval_value_id: row.superseded_by_id for row in lifecycle_rows}
    r1_row = db.scalar(
        select(RainfallIntervalValue).where(RainfallIntervalValue.provider_revision == "v3-nrt+r1")
    )
    assert r1_row is not None
    assert superseded_by_map[r1_row.id] == current[0].id


# ---------------------------------------------------------------------------
# Task 1.7 — intervals_in_window anti-joins superseded rows, ordered by
# interval_start, at most one row per slot
# ---------------------------------------------------------------------------


def test_intervals_in_window_excludes_superseded_rows(db):
    from app.domains.geo.rainfall.repository import intervals_in_window, persist_intervals

    # Two slots: day 1 gets corrected, day 2 stays untouched.
    original = _daily_intervals(start_day=1, values=[1.0, 5.0], provider_revision="v3-nrt")
    persist_intervals(db, source_id="chirps-v3-sat", rows=original, **ZONE_KWARGS)
    db.flush()

    restated_day1 = _daily_intervals(start_day=1, values=[1.8], provider_revision="v3-nrt")
    persist_intervals(db, source_id="chirps-v3-sat", rows=restated_day1, **ZONE_KWARGS)
    db.flush()

    current = intervals_in_window(
        db,
        source_id="chirps-v3-sat",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 3, tzinfo=UTC),
        **ZONE_KWARGS,
    )

    # At most one non-superseded row per slot, ordered by interval_start —
    # the corrected day 1 row, then the untouched day 2 row.
    assert [row.interval_start for row in current] == [
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2024, 1, 2, tzinfo=UTC),
    ]
    assert [row.value for row in current] == [1.8, 5.0]
    assert [row.provider_revision for row in current] == ["v3-nrt+r1", "v3-nrt"]
    # The superseded original day-1 row is excluded even though the table
    # still holds it (append-only evidence): 3 rows on disk, 2 served.
    assert _count_interval_rows(db, source_id="chirps-v3-sat") == 3


# ---------------------------------------------------------------------------
# R3-004 — "+r" reservation and the provider_revision-family 1:1 invariant
# ---------------------------------------------------------------------------


def test_source_interval_rejects_plus_in_provider_revision():
    """'+r<n>' is reserved for correction rows persist_intervals mints
    internally (design.md 'NRT Correction Supersession'); an adapter must
    never be able to hand one in directly, or it could collide with, or be
    mistaken for, a correction row the write path itself produced."""
    from app.domains.geo.rainfall.ports import SourceInterval

    start = datetime(2024, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match=r"\+"):
        SourceInterval(start, start + timedelta(days=1), 1.0, "mm", "v3-nrt+r1")


def test_persist_intervals_raises_on_provider_revision_family_mismatch(db):
    """persist_intervals's 'changed' branch must not silently re-stamp a
    foreign-family value with the incumbent's family: one source_id maps
    to exactly one provider_revision family (design.md decision 7). A
    caller handing back a different family for an existing slot has a bug
    and must be told loudly, not have its revision discarded."""
    from app.domains.geo.rainfall.repository import persist_intervals

    original = _daily_intervals(start_day=1, values=[1.0], provider_revision="v3-nrt")
    persist_intervals(db, source_id="chirps-v3-sat", rows=original, **ZONE_KWARGS)
    db.flush()

    foreign_family = _daily_intervals(start_day=1, values=[1.8], provider_revision="v3-final")
    with pytest.raises(ValueError, match="family mismatch"):
        persist_intervals(db, source_id="chirps-v3-sat", rows=foreign_family, **ZONE_KWARGS)


# ---------------------------------------------------------------------------
# Task 1.8 — ingest_source_scope threads an optional db without committing
# ---------------------------------------------------------------------------


def _fixture_batch() -> SourceBatch:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return SourceBatch(
        source_id="chirps-v3-final",
        scope_kind="zone",
        scope_id="z1",
        scope_version="v1",
        cadence=timedelta(days=1),
        intervals=(SourceInterval(start, start + timedelta(days=1), 3.0, "mm", "v3-final"),),
        coverage=1.0,
        completeness=1.0,
        quality={"provider_revision": "v3-final"},
        discrepancies=(),
        checksum="sha256:fixture",
    )


def test_ingest_source_scope_writes_without_commit_when_given_db(db, monkeypatch):
    from app.domains.geo.rainfall import tasks

    batch = _fixture_batch()
    monkeypatch.setattr(tasks, "_role_enabled", lambda role, db=None: True)
    monkeypatch.setattr(tasks, "_concrete_fetch", lambda source_id: lambda **_kwargs: batch)

    result = tasks.ingest_source_scope(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="z1",
        scope_version="v1",
        year=2024,
        db=db,
    )

    assert result["persisted"] == 1
    assert result["superseded"] == 0
    assert result["intervals"] == 1
    # Written on the given session but NOT committed — a fresh connection
    # must not see it yet (decision 2: given a db, write, never commit).
    assert _count_interval_rows(db, source_id="chirps-v3-final") == 1
    with SessionLocal() as fresh:
        assert _count_interval_rows(fresh, source_id="chirps-v3-final") == 0


def test_ingest_source_scope_opens_own_session_and_commits_when_db_is_none(db, monkeypatch):
    # `db` is unused directly here (this test asserts on a fresh SessionLocal
    # connection on purpose) but requesting it guarantees test_engine's
    # create_all() has run — see the note on the transaction-sharing test below.
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.repository import intervals_in_window

    batch = _fixture_batch()
    monkeypatch.setattr(tasks, "_role_enabled", lambda role, db=None: True)
    monkeypatch.setattr(tasks, "_concrete_fetch", lambda source_id: lambda **_kwargs: batch)

    # R3-002: a dedicated scope_id (like `zone-txn-share` at task 1.9's test
    # below) keeps this test's real `SessionLocal()` commit — the only
    # write in this module the `db` fixture's rollback does NOT undo — off
    # the exact `z1` slot the sibling tests above assert an absolute,
    # source-only row count over. No DELETE-based cleanup: the dedicated
    # scope makes the committed row inert to every other test regardless of
    # execution order, and the previous `finally`-only cleanup never ran
    # when the preceding assertion raised, which is exactly the leak this
    # scope isolation removes the need for.
    result = tasks.ingest_source_scope(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-own-session-commit",
        scope_version="v1",
        year=2024,
    )

    assert result["persisted"] == 1
    with SessionLocal() as fresh:
        landed = intervals_in_window(
            fresh,
            source_id="chirps-v3-final",
            scope_kind="zone",
            scope_id="zone-own-session-commit",
            scope_version="v1",
            start=batch.intervals[0].interval_start,
            end=batch.intervals[0].interval_end,
        )
        assert len(landed) == 1
        assert landed[0].value == batch.intervals[0].value


# ---------------------------------------------------------------------------
# Task 1.9 — backfill_missing shares one transaction with ingest
# ---------------------------------------------------------------------------


def test_backfill_missing_shares_transaction_with_ingest(db, monkeypatch):
    # `db` is unused directly — backfill_missing opens its own SessionLocal()
    # — but requesting the fixture guarantees test_engine's create_all() has
    # run, matching the existing test_ingest_ops.py pattern for SessionLocal-
    # only tests (e.g. test_backfill_missing_passes_role_to_ingest_source_scope).
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.repository import persist_intervals

    filters = {
        "source_id": "chirps-v3-final",
        "role": "historical",
        "scope_kind": "zone",
        "scope_id": "zone-txn-share",
        "scope_version": "v1",
        "year": 2024,
    }

    def failing_ingest(*, db, **_kwargs):
        # Write through the SAME session backfill_missing opened, then fail
        # before backfill_missing gets a chance to commit anything.
        row = _daily_intervals(start_day=1, values=[9.9])[0]
        persist_intervals(
            db,
            source_id="chirps-v3-final",
            scope_kind="zone",
            scope_id="zone-txn-share",
            scope_version="v1",
            rows=[row],
        )
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "ingest_source_scope", failing_ingest)

    with pytest.raises(RuntimeError, match="boom"):
        tasks.backfill_missing(**filters)

    # Neither the checkpoint nor the interval survive — proving both writes
    # were on the SAME uncommitted transaction (all-or-nothing), not two
    # independently committed sessions.
    with SessionLocal() as fresh:
        assert (
            fresh.query(RainfallBackfillCheckpoint)
            .filter_by(
                source_id="chirps-v3-final",
                role="historical",
                scope_kind="zone",
                scope_id="zone-txn-share",
                scope_version="v1",
                year=2024,
            )
            .first()
            is None
        )
        # Scoped to this test's own scope_id (R3-002): an absolute,
        # source_id-only count would also see the row task 1.8's
        # own-session test commits under a different, unrelated scope.
        assert (
            _count_interval_rows(fresh, source_id="chirps-v3-final", scope_id="zone-txn-share") == 0
        )


# ===========================================================================
# Phase 2 (PR 2) — Compute
# ===========================================================================

# ---------------------------------------------------------------------------
# Task 2.2 — RainfallOutbox.request_fingerprint column
# ---------------------------------------------------------------------------


def test_outbox_model_has_request_fingerprint_column(db):
    from app.domains.geo.rainfall.models import RainfallOutbox

    now = datetime(2024, 1, 1, tzinfo=UTC)
    row = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-fingerprint-column",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        interval_start=now,
        interval_end=now + timedelta(days=365),
        request_fingerprint="a" * 64,
    )
    db.add(row)
    db.flush()

    fetched = db.get(RainfallOutbox, row.id)
    assert fetched.request_fingerprint == "a" * 64

    # Nullable: a legacy row (decision 4b) is a valid row with no fingerprint.
    legacy = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-fingerprint-legacy",
        scope_version="v1",
        year=2023,
        work_labels=["analysis_missing"],
        interval_start=now,
        interval_end=now + timedelta(days=365),
    )
    db.add(legacy)
    db.flush()
    assert db.get(RainfallOutbox, legacy.id).request_fingerprint is None


# ---------------------------------------------------------------------------
# Task 2.3 — queue_missing_analysis stores the router-computed fingerprint
# ---------------------------------------------------------------------------


def test_queue_missing_analysis_stores_router_computed_fingerprint(db):
    """decision 4: the router already computes ``analysis_request_fingerprint``
    for its ``get_snapshot`` lookup (router.py:130) — passing that exact
    value into ``queue_missing_analysis`` removes the drift class a second,
    independent computation could introduce."""
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.scope import AnalysisScope
    from app.domains.geo.rainfall.service import queue_missing_analysis

    scope = AnalysisScope(kind="zone", id="zone-fp-router", version="v1", regional_estimate=False)
    fingerprint = "deadbeef" * 8

    result = queue_missing_analysis(
        db,
        scope=scope,
        year=2024,
        labels=("analysis_missing",),
        request_fingerprint=fingerprint,
    )
    db.flush()

    row = db.get(RainfallOutbox, result["outbox_id"])
    assert row.request_fingerprint == fingerprint


def test_queue_missing_analysis_recomputes_fingerprint_when_not_passed(db):
    """Backward-compat fallback (decision 4): a caller that does not pass
    ``request_fingerprint`` still gets a stored fingerprint, computed from
    the same canonical shape router.py builds — including omitting
    ``event_window`` entirely rather than setting it to ``None``, because
    ``analysis_request_fingerprint``'s JSON canonicalization treats a
    present-but-null key differently from an absent one."""
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.scope import AnalysisScope
    from app.domains.geo.rainfall.service import (
        analysis_request_fingerprint,
        queue_missing_analysis,
    )

    scope = AnalysisScope(kind="zone", id="zone-fp-fallback", version="v1", regional_estimate=False)
    expected = analysis_request_fingerprint(
        {"scope": {"kind": "zone", "id": "zone-fp-fallback", "version": "v1"}, "year": 2024}
    )

    result = queue_missing_analysis(db, scope=scope, year=2024, labels=("analysis_missing",))
    db.flush()

    row = db.get(RainfallOutbox, result["outbox_id"])
    assert row.request_fingerprint == expected


# ---------------------------------------------------------------------------
# Task 2.9 — persist_revision is idempotent on an identical data_revision
# ---------------------------------------------------------------------------


def test_persist_revision_is_idempotent_on_identical_data_revision(db):
    from app.domains.geo.rainfall.models import RainfallAnalysisRevision
    from app.domains.geo.rainfall.repository import persist_revision

    snapshot = {"scope": {"kind": "zone", "id": "z1", "version": "v1"}, "year": 2024}

    first_id = persist_revision(
        db,
        request_fingerprint="fp-persist-revision",
        policy_revision="policy-v1",
        data_revision="data-v1",
        snapshot=snapshot,
    )
    db.flush()

    # Identical (fingerprint, policy_revision, data_revision) -> a no-op
    # returning the existing id, not a second row.
    second_id = persist_revision(
        db,
        request_fingerprint="fp-persist-revision",
        policy_revision="policy-v1",
        data_revision="data-v1",
        snapshot=snapshot,
    )
    db.flush()

    assert first_id == second_id
    count = db.scalar(
        select(func.count())
        .select_from(RainfallAnalysisRevision)
        .where(RainfallAnalysisRevision.request_fingerprint == "fp-persist-revision")
    )
    assert count == 1


def test_persist_revision_writes_a_new_row_on_changed_data_revision(db):
    """Triangulation: a different data_revision under the same fingerprint
    is a genuinely new row, not absorbed by the idempotent path above."""
    from app.domains.geo.rainfall.models import RainfallAnalysisRevision
    from app.domains.geo.rainfall.repository import persist_revision

    snapshot = {"scope": {"kind": "zone", "id": "z1", "version": "v1"}, "year": 2024}

    first_id = persist_revision(
        db,
        request_fingerprint="fp-persist-revision-2",
        policy_revision="policy-v1",
        data_revision="data-v1",
        snapshot=snapshot,
    )
    db.flush()

    second_id = persist_revision(
        db,
        request_fingerprint="fp-persist-revision-2",
        policy_revision="policy-v1",
        data_revision="data-v2",
        snapshot=snapshot,
    )
    db.flush()

    assert first_id != second_id
    count = db.scalar(
        select(func.count())
        .select_from(RainfallAnalysisRevision)
        .where(RainfallAnalysisRevision.request_fingerprint == "fp-persist-revision-2")
    )
    assert count == 2


# ---------------------------------------------------------------------------
# Task 2.10 — build_analysis writes one revision that passes normalize_snapshot
# ---------------------------------------------------------------------------


def _fixture_batch_evidence(**overrides) -> dict:
    payload = {
        "source_id": "chirps-v3-final",
        "scope_kind": "zone",
        "scope_id": "zone-build-analysis",
        "year": 2024,
        "intervals": 3,
        "persisted": 3,
        "superseded": 0,
        "provider_revision": "v3-final",
        "unit": "mm",
        "cadence_seconds": 86400.0,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {
            "catalog_id": "UCSB-CHC/CHIRPS/V3/DAILY_RNL",
            "band": "precipitation",
            "reduction": "mean",
            "scale_m": 5500,
            "provider_revision": "v3-final",
        },
        "discrepancies": [],
        "checksum": "sha256:fixture",
    }
    payload.update(overrides)
    return payload


def test_build_analysis_writes_one_revision_and_passes_normalize_snapshot(db):
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.repository import RainfallRepository, persist_intervals
    from app.domains.geo.rainfall.service import normalize_snapshot

    rows = _daily_intervals(start_day=1, values=[1.0, 2.0, 3.0])
    persist_intervals(
        db,
        source_id="chirps-v3-final",
        scope_kind="zone",
        scope_id="zone-build-analysis",
        scope_version="v1",
        rows=rows,
    )
    db.flush()

    outbox = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-build-analysis",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        interval_start=datetime(2024, 1, 1, tzinfo=UTC),
        interval_end=datetime(2025, 1, 1, tzinfo=UTC),
        status="pending",
        request_fingerprint="fp-build-analysis",
    )
    db.add(outbox)
    db.flush()

    result = tasks.build_analysis(
        outbox_id=str(outbox.id),
        batch=_fixture_batch_evidence(),
        db=db,
        now=datetime(2024, 6, 15, tzinfo=UTC),
    )
    db.flush()

    assert result["revision_id"]

    revision = RainfallRepository().get_snapshot(db, "fp-build-analysis")
    assert revision is not None
    normalized = normalize_snapshot(
        revision.snapshot, expected_policy_revision=revision.policy_revision
    )
    assert normalized["annual"]["selected"]["state"] in {"available", "unavailable"}
    assert normalized["scope"] == {"kind": "zone", "id": "zone-build-analysis", "version": "v1"}


def test_build_analysis_raises_when_outbox_row_has_no_fingerprint(db):
    """decision 4b: a legacy null-fingerprint row is the CALLER's
    (_process_outbox_row, task 2.11) responsibility to derive or skip
    before ever calling build_analysis; a direct call with none set is a
    programming error and must be loud, not silently compute nothing."""
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox

    outbox = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-no-fingerprint",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        interval_start=datetime(2024, 1, 1, tzinfo=UTC),
        interval_end=datetime(2025, 1, 1, tzinfo=UTC),
        status="pending",
    )
    db.add(outbox)
    db.flush()

    with pytest.raises(ValueError, match="request_fingerprint"):
        tasks.build_analysis(
            outbox_id=str(outbox.id),
            batch=_fixture_batch_evidence(),
            db=db,
            now=datetime(2024, 6, 15, tzinfo=UTC),
        )


# ---------------------------------------------------------------------------
# Task 2.11 — _process_outbox_row chains build_analysis before status="done"
# ---------------------------------------------------------------------------


def test_process_outbox_row_chains_build_analysis_before_done(db, monkeypatch):
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.repository import RainfallRepository

    batch = _fixture_batch()
    monkeypatch.setattr(tasks, "_role_enabled", lambda role, db=None: True)
    monkeypatch.setattr(tasks, "_concrete_fetch", lambda source_id: lambda **_kwargs: batch)

    fingerprint = "fp-chain-test"
    row = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-chain-test",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        interval_start=datetime(2024, 1, 1, tzinfo=UTC),
        interval_end=datetime(2025, 1, 1, tzinfo=UTC),
        status="pending",
        request_fingerprint=fingerprint,
    )
    db.add(row)
    db.flush()

    real_build_analysis = tasks.build_analysis
    status_at_call_time: dict[str, str] = {}

    def spy_build_analysis(**kwargs):
        # Captured BEFORE delegating to the real implementation: proves
        # the chain calls build_analysis while the row is still "pending",
        # not after status="done" is already set (decision 1).
        status_at_call_time["status"] = row.status
        return real_build_analysis(**kwargs)

    monkeypatch.setattr(tasks, "build_analysis", spy_build_analysis)

    result = tasks._process_outbox_row(row, db, datetime(2024, 6, 15, tzinfo=UTC))

    assert result == "done"
    assert row.status == "done"
    assert row.completed_at is not None
    assert status_at_call_time["status"] == "pending"

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None


def test_legacy_null_fingerprint_row_skips_compute(db, monkeypatch):
    """decision 4b: a row whose interval bounds are NOT the year bounds
    (a legacy or event-window shape) cannot safely derive a full-year
    fingerprint. It must still reach "done" (ingest itself succeeded) but
    skip compute entirely, writing no revision."""
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallAnalysisRevision, RainfallOutbox

    batch = _fixture_batch()
    monkeypatch.setattr(tasks, "_role_enabled", lambda role, db=None: True)
    monkeypatch.setattr(tasks, "_concrete_fetch", lambda source_id: lambda **_kwargs: batch)

    row = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-legacy-null-fp",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        interval_start=datetime(2024, 3, 1, tzinfo=UTC),
        interval_end=datetime(2024, 3, 2, tzinfo=UTC),
        status="pending",
    )
    db.add(row)
    db.flush()

    result = tasks._process_outbox_row(row, db, datetime(2024, 6, 15, tzinfo=UTC))

    assert result == "done"
    assert row.status == "done"
    assert row.completed_at is not None
    assert row.request_fingerprint is None

    count = db.scalar(select(func.count()).select_from(RainfallAnalysisRevision))
    assert count == 0


def test_full_year_null_fingerprint_row_derives_and_computes(db, monkeypatch):
    """Triangulation: the OTHER branch of the same decision — a row whose
    bounds ARE the year bounds derives its fingerprint and DOES compute."""
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.repository import RainfallRepository
    from app.domains.geo.rainfall.service import analysis_request_fingerprint

    batch = _fixture_batch()
    monkeypatch.setattr(tasks, "_role_enabled", lambda role, db=None: True)
    monkeypatch.setattr(tasks, "_concrete_fetch", lambda source_id: lambda **_kwargs: batch)

    row = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-derive-fp",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        interval_start=datetime(2024, 1, 1, tzinfo=UTC),
        interval_end=datetime(2025, 1, 1, tzinfo=UTC),
        status="pending",
    )
    db.add(row)
    db.flush()

    result = tasks._process_outbox_row(row, db, datetime(2024, 6, 15, tzinfo=UTC))

    assert result == "done"
    expected_fingerprint = analysis_request_fingerprint(
        {"scope": {"kind": "zone", "id": "zone-derive-fp", "version": "v1"}, "year": 2024}
    )
    assert row.request_fingerprint == expected_fingerprint

    revision = RainfallRepository().get_snapshot(db, expected_fingerprint)
    assert revision is not None


# ---------------------------------------------------------------------------
# Task 2.12 — claim_outbox_row re-claim + per-row commit
# ---------------------------------------------------------------------------


def test_claim_outbox_row_returns_none_when_not_pending(db):
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.repository import claim_outbox_row

    row = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-claim-not-pending",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        status="done",
        next_attempt_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    db.add(row)
    db.flush()

    assert claim_outbox_row(db, outbox_id=row.id, now=datetime.now(UTC)) is None


def test_claim_outbox_row_returns_none_when_not_yet_due(db):
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.repository import claim_outbox_row

    far_future = datetime.now(UTC) + timedelta(hours=1)
    row = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-claim-not-due",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        status="pending",
        next_attempt_at=far_future,
    )
    db.add(row)
    db.flush()

    assert claim_outbox_row(db, outbox_id=row.id, now=datetime.now(UTC)) is None


def test_claim_outbox_row_returns_the_row_when_pending_and_due(db):
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.repository import claim_outbox_row

    row = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-claim-due",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        status="pending",
        next_attempt_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    db.add(row)
    db.flush()

    claimed = claim_outbox_row(db, outbox_id=row.id, now=datetime.now(UTC))
    assert claimed is not None
    assert claimed.id == row.id


def test_claim_outbox_row_uses_python_now_not_frozen_sql_transaction_time(db):
    """Regression: PostgreSQL's ``now()`` is frozen to *transaction start*
    within one transaction (``transaction_timestamp()``), not statement
    time. A row stamped with Python's wall clock via
    ``next_attempt_at=datetime.now(UTC)`` AFTER the shared ``db`` fixture's
    transaction already began would read as "in the future" against a
    frozen SQL ``now()`` and never be claimable within that same
    transaction — reproduced empirically. ``claim_outbox_row`` must compare
    against a Python-side ``now``, not ``func.now()``.
    """
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.repository import claim_outbox_row

    row = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-claim-same-txn-now",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        status="pending",
        next_attempt_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()

    claimed = claim_outbox_row(db, outbox_id=row.id, now=datetime.now(UTC))
    assert claimed is not None
    assert claimed.id == row.id


def test_per_row_commit_survives_a_later_row_failure(db, monkeypatch):
    """decision 2c: commit after each row. A row that fails after another
    succeeded leaves the succeeded row's revision already committed and
    durable — verified from FRESH connections, since the savepoint-scoped
    `db` fixture would otherwise fake durability (same reason the
    Durability Testing Strategy row uses SessionLocal(), not `db`).

    The crash is injected in ``_role_enabled`` — a call OUTSIDE
    ``_process_outbox_row``'s own try/except, i.e. nothing inside the
    consumer catches it — so it propagates straight out of
    ``_process_outbox_batch``, simulating a worker crash mid-batch. Under
    the OLD single-batch-wide-commit design this would roll back row1's
    already-succeeded work too (nothing committed until the very end); a
    per-row commit is what makes this test distinguish the two designs
    instead of passing trivially against either.

    ``db`` is unused directly — this test asserts on fresh SessionLocal()
    connections on purpose — but requesting it guarantees test_engine's
    create_all() has run (same reason task 1.8/1.9's SessionLocal-only
    tests request it above).
    """
    from app.db.session import SessionLocal
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallAnalysisRevision, RainfallOutbox
    from app.domains.geo.rainfall.repository import RainfallRepository

    role_enabled_calls = {"n": 0}

    def flaky_role_enabled(role, db=None):
        role_enabled_calls["n"] += 1
        if role_enabled_calls["n"] == 2:
            raise RuntimeError("simulated crash processing the second row")
        return True

    monkeypatch.setattr(tasks, "_role_enabled", flaky_role_enabled)

    def fake_ingest_source_scope(
        *, source_id, role, scope_kind, scope_id, scope_version, year, db=None
    ):
        return _fixture_batch_evidence(scope_id=scope_id, year=year)

    monkeypatch.setattr(tasks, "ingest_source_scope", fake_ingest_source_scope)

    row1_id = row2_id = None
    try:
        # Two SEPARATE transactions so `created_at` (server_default now())
        # genuinely differs, making the batch's `ORDER BY created_at`
        # deterministic: row1 is claimed and processed before row2.
        with SessionLocal() as setup_db:
            row1 = RainfallOutbox(
                source_id="chirps-v3-final",
                role="historical",
                scope_kind="zone",
                scope_id="zone-commit-survive-1",
                scope_version="v1",
                year=2024,
                work_labels=["analysis_missing"],
                interval_start=datetime(2024, 1, 1, tzinfo=UTC),
                interval_end=datetime(2025, 1, 1, tzinfo=UTC),
                status="pending",
                next_attempt_at=datetime.now(UTC),
                request_fingerprint="fp-commit-survive-1",
            )
            setup_db.add(row1)
            setup_db.commit()
            row1_id = row1.id

        with SessionLocal() as setup_db:
            row2 = RainfallOutbox(
                source_id="chirps-v3-final",
                role="historical",
                scope_kind="zone",
                scope_id="zone-commit-survive-2",
                scope_version="v1",
                year=2024,
                work_labels=["analysis_missing"],
                interval_start=datetime(2024, 1, 1, tzinfo=UTC),
                interval_end=datetime(2025, 1, 1, tzinfo=UTC),
                status="pending",
                next_attempt_at=datetime.now(UTC),
                request_fingerprint="fp-commit-survive-2",
            )
            setup_db.add(row2)
            setup_db.commit()
            row2_id = row2.id

        with SessionLocal() as process_db:
            with pytest.raises(RuntimeError, match="simulated crash"):
                tasks._process_outbox_batch(process_db)

        with SessionLocal() as verify_db:
            fresh_row1 = verify_db.get(RainfallOutbox, row1_id)
            fresh_row2 = verify_db.get(RainfallOutbox, row2_id)
            # row1 was committed on its own, BEFORE the crash on row2 —
            # its success survives the batch aborting.
            assert fresh_row1.status == "done"
            assert fresh_row1.completed_at is not None
            # row2 was never claimed (the crash is in the gate check, before
            # claim_outbox_row runs for it) — still pending, untouched.
            assert fresh_row2.status == "pending"
            assert fresh_row2.retry_count == 0

            revision = RainfallRepository().get_snapshot(verify_db, "fp-commit-survive-1")
            assert revision is not None
    finally:
        with SessionLocal() as cleanup_db:
            cleanup_db.query(RainfallAnalysisRevision).filter_by(
                request_fingerprint="fp-commit-survive-1"
            ).delete()
            ids = [i for i in (row1_id, row2_id) if i is not None]
            if ids:
                cleanup_db.query(RainfallOutbox).filter(RainfallOutbox.id.in_(ids)).delete(
                    synchronize_session=False
                )
            cleanup_db.commit()


# ---------------------------------------------------------------------------
# Task 2.13 — now seam: drives comparison_end, never the backoff clock
# ---------------------------------------------------------------------------


def test_now_seam_drives_comparison_end_without_moving_backoff_clock(db, monkeypatch):
    """design.md Interfaces: `now` threads process_outbox ->
    _process_outbox_batch (resolved once per batch) -> _process_outbox_row
    -> build_analysis, and feeds ONLY temporal.comparison_end /
    buenos_aires_date. completed_at, next_attempt_at and the backoff
    arithmetic stay on the real wall clock."""
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.repository import RainfallRepository

    monkeypatch.setattr(tasks, "_role_enabled", lambda role, db=None: True)
    monkeypatch.setattr(
        tasks, "_concrete_fetch", lambda source_id: lambda **_kwargs: _fixture_batch()
    )

    fingerprint = "fp-now-seam"
    row = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-now-seam",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        interval_start=datetime(2024, 1, 1, tzinfo=UTC),
        interval_end=datetime(2025, 1, 1, tzinfo=UTC),
        status="pending",
        next_attempt_at=datetime(2024, 1, 1, tzinfo=UTC),
        request_fingerprint=fingerprint,
    )
    db.add(row)
    db.flush()

    # Noon UTC = 09:00 Buenos Aires (UTC-3): safely the same calendar day in
    # both zones, so this isn't fragile to the midnight-UTC boundary skew
    # buenos_aires_date's conversion is designed to catch.
    seeded_now = datetime(2024, 3, 10, 12, tzinfo=UTC)
    before_call = datetime.now(UTC)
    result = tasks.process_outbox(db=db, now=seeded_now)
    after_call = datetime.now(UTC)

    assert result["succeeded"] == 1
    db.refresh(row)

    # The disclosure date follows the SEEDED clock (year is current relative
    # to 2024, so comparison_end == the seeded now's own date), not the
    # real wall clock the test actually runs on.
    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    assert revision.snapshot["comparison_end"] == "2024-03-10"

    # completed_at is bounded by the REAL wall-clock window this call ran
    # in, not by the seeded (year-2024) now.
    assert before_call <= row.completed_at <= after_call


def test_now_seam_does_not_move_the_backoff_clock_on_failure(db, monkeypatch):
    """Triangulation: the failure-path bookkeeping (retry_count,
    next_attempt_at) must stay on the real wall clock even when a seeded
    `now` is supplied for the disclosure date."""
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox

    monkeypatch.setattr(tasks, "_role_enabled", lambda role, db=None: True)
    monkeypatch.setattr(
        tasks, "ingest_source_scope", lambda **_kwargs: (_ for _ in ()).throw(ValueError("boom"))
    )

    row = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id="zone-now-seam-failure",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        status="pending",
        next_attempt_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    db.add(row)
    db.flush()

    seeded_now = datetime(1999, 1, 1, tzinfo=UTC)
    before_call = datetime.now(UTC)
    result = tasks.process_outbox(db=db, now=seeded_now)
    after_call = datetime.now(UTC)

    assert result["failed"] == 0
    assert result["delayed"] == 1
    db.refresh(row)
    assert row.status == "pending"
    assert row.retry_count == 1
    # next_attempt_at = real now() + backoff — nowhere near the seeded 1999
    # date, and bounded by the real wall-clock window this call ran in.
    assert row.next_attempt_at > before_call
    assert row.next_attempt_at <= after_call + timedelta(seconds=_expected_backoff_ceiling())


def _expected_backoff_ceiling() -> float:
    from app.domains.geo.rainfall.tasks import _backoff_seconds

    return _backoff_seconds(1) + 1


# ---------------------------------------------------------------------------
# Task 2.14 — E2E: POST -> 202 -> process_outbox -> POST -> 200
# ---------------------------------------------------------------------------


class _FakeGeeClientForE2E:
    """Minimal :class:`GeeZonalClient` stand-in, local to this E2E test —
    only the GEE network boundary is faked (design.md Testing Strategy);
    ``ingest_source_scope`` itself is never monkeypatched, so the real
    adapter, zonal batch builder, resilient-fetch wrapper, persistence and
    compute layer all run."""

    def __init__(self, *, series: list[tuple[datetime, float]]) -> None:
        self.series = series
        self.scale_meters = 5500

    def geometry(self, *, scope_kind: str, scope_id: str) -> object:
        return ("asset", scope_kind, scope_id)

    def zonal_series(self, *, collection_id, start, end, geometry, band):
        return list(self.series)


def test_e2e_post_202_then_200_without_monkeypatching_ingest(db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.auth import require_admin_or_operator
    from app.db.session import get_db
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.adapters.chirps import ChirpsV3Adapter
    from app.domains.geo.rainfall.router import router

    year = 2024  # leap year: 366 daily slots -> full coverage
    year_start = datetime(year, 1, 1, tzinfo=UTC)
    series = [
        (year_start + timedelta(days=offset), 1.0 + (offset % 5) * 0.2) for offset in range(366)
    ]

    def fake_concrete_fetch(source_id):
        if source_id != "chirps-v3-final":
            raise NotImplementedError(f"unexpected source_id in this E2E test: {source_id!r}")
        return ChirpsV3Adapter(gee=_FakeGeeClientForE2E(series=series)).fetch

    monkeypatch.setattr(tasks, "_concrete_fetch", fake_concrete_fetch)

    app = FastAPI()
    app.dependency_overrides[require_admin_or_operator] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    app.include_router(router)
    client = TestClient(app)

    # A past year routes to role="historical"/source_id="chirps-v3-final"
    # (resolve_missing_work_source) -- the wired adapter. The current year
    # would route to "daily"/"sqpe-obs", which stays deliberately unwired
    # until PR 4's flip.
    payload = {"scope": {"kind": "zone", "id": "zone-e2e-202-200", "version": "v1"}, "year": year}

    queued = client.post("/rainfall/analyses", json=payload)
    assert queued.status_code == 202
    assert queued.json()["status"] == "queued"

    result = tasks.process_outbox(db=db)
    assert result["succeeded"] == 1
    assert result["failed"] == 0

    served = client.post("/rainfall/analyses", json=payload)
    assert served.status_code == 200

    body = served.json()
    assert body["scope"] == {"kind": "zone", "id": "zone-e2e-202-200", "version": "v1"}
    assert body["year"] == year
    metric = body["annual"]["selected"]
    assert metric["state"] == "available"
    assert metric["value"] is not None
    assert metric["provenance"]["source_id"] == "chirps-v3-final"
    assert metric["temporal_state"] == "final"


# ---------------------------------------------------------------------------
# R4-001 regression — flush-independent lifecycle writes under production
# autoflush=False
# ---------------------------------------------------------------------------


@pytest.fixture
def db_autoflush_off(test_engine):
    """Production-shape session built from the SAME connection
    infrastructure as the shared ``db`` fixture (``test_engine``), but with
    ``autoflush=False`` like the real ``SessionLocal`` (``app/db/session.py``
    ``sessionmaker(bind=engine, autocommit=False, autoflush=False)``).

    Deliberately NOT the shared ``db`` fixture: ``db``'s
    ``Session(bind=connection)`` defaults to ``autoflush=True``, which
    silently flushes a pending ORM ``db.add`` before the next read and would
    hide the exact R4-001 bug class this module regression-tests — a Core
    write is required precisely because production never flushes for you.
    """
    from sqlalchemy.orm import Session

    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


def test_restated_slot_survives_chained_compute_without_explicit_flush(
    db_autoflush_off, monkeypatch
):
    """Regression for R4-001: a restated (corrected) slot re-ingested
    through ``_process_outbox_row`` — ingest and build_analysis chained in
    ONE transaction, exactly as ``_process_outbox_batch`` runs it in
    production — must not duplicate the slot just because the session never
    autoflushes.

    Before the fix, ``record_supersession`` wrote the lifecycle row via ORM
    ``db.add``, which stays pending in ``session.new`` under
    ``autoflush=False``. The chained ``build_analysis`` call's
    ``intervals_in_window`` anti-join then ran against the DB before that
    pending row ever landed, so it saw BOTH the old and the new revision of
    the slot as "current" and ``build_snapshot`` raised on the duplicate
    ``interval_start`` — see ``review-ledger.md`` R4-001.
    """
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallAnalysisRevision, RainfallOutbox
    from app.domains.geo.rainfall.repository import intervals_in_window, persist_intervals

    db = db_autoflush_off
    scope_id = "zone-r4-001-regression"
    slot_start = datetime(2024, 1, 1, tzinfo=UTC)
    slot_end = datetime(2024, 1, 2, tzinfo=UTC)

    # Leg 1 — baseline ingest (persist_intervals + queue: the accepted
    # alternative to the outbox path for the FIRST pass). persist_intervals'
    # own interval write is already a Core INSERT, so this slot is "current"
    # the instant the call returns — no flush needed to set up the baseline.
    persist_intervals(
        db,
        source_id="chirps-v3-final",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=[SourceInterval(slot_start, slot_end, 1.0, "mm", "v3-final")],
    )

    fingerprint = "fp-r4-001-regression"
    outbox = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        interval_start=datetime(2024, 1, 1, tzinfo=UTC),
        interval_end=datetime(2025, 1, 1, tzinfo=UTC),
        status="pending",
        request_fingerprint=fingerprint,
    )
    db.add(outbox)
    db.flush()  # setup only, to assign outbox.id so build_analysis's
    # db.get() can find it -- not part of the ingest+build chain the
    # R4-001 bug lives in.

    # Leg 2 — re-ingest the SAME slot with a restated value, through the
    # real chained path (``_process_outbox_row``): ingest_source_scope's
    # persist_intervals (changed branch -> a correction row plus a
    # record_supersession lifecycle link) runs immediately followed, in the
    # SAME transaction and with NO intervening flush, by build_analysis's
    # intervals_in_window anti-join read.
    restated_batch = SourceBatch(
        source_id="chirps-v3-final",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        cadence=timedelta(days=1),
        intervals=(SourceInterval(slot_start, slot_end, 2.0, "mm", "v3-final"),),
        coverage=1.0,
        completeness=1.0,
        quality={"provider_revision": "v3-final"},
        discrepancies=(),
        checksum="sha256:restated",
    )
    monkeypatch.setattr(tasks, "_role_enabled", lambda role, db=None: True)
    monkeypatch.setattr(
        tasks, "_concrete_fetch", lambda source_id: lambda **_kwargs: restated_batch
    )

    result = tasks._process_outbox_row(outbox, db, datetime(2024, 6, 15, tzinfo=UTC))

    assert result == "done"
    assert outbox.status == "done"

    revision_count = db.scalar(
        select(func.count())
        .select_from(RainfallAnalysisRevision)
        .where(RainfallAnalysisRevision.request_fingerprint == fingerprint)
    )
    assert revision_count == 1

    current = intervals_in_window(
        db,
        source_id="chirps-v3-final",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        start=slot_start,
        end=slot_end,
    )
    assert len(current) == 1
    assert current[0].value == 2.0
