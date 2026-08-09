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
            _count_interval_rows(fresh, source_id="chirps-v3-final", scope_id="zone-txn-share")
            == 0
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
