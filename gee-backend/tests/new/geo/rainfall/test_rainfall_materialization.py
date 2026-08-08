"""Rainfall v2 materialization: persistence, supersession, chained compute,
revisit sweeps, year-rollover finalization and their end-to-end wiring.

Real PostgreSQL throughout (the ``db`` fixture) — the append-only trigger,
the partial unique indexes and the advisory-lock concurrency guarantees this
change relies on exist nowhere else. Provider I/O is faked at the
``GeeZonalClient`` boundary only (same harness as
``test_provider_adapters.py``), so the adapter, the zonal batch builder, the
persistence write path and the compute layer all run for real.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.domains.geo.rainfall.models import (
    RainfallIntervalLifecycle,
    RainfallIntervalValue,
)
from app.domains.geo.rainfall.ports import SourceInterval

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


def _count_interval_rows(db, *, source_id: str = "chirps-v3-final") -> int:
    return db.scalar(
        select(func.count())
        .select_from(RainfallIntervalValue)
        .where(RainfallIntervalValue.source_id == source_id)
    )


# ---------------------------------------------------------------------------
# Task 1.1 — Interval Persistence on Ingest: re-ingest is idempotent
# ---------------------------------------------------------------------------


def test_reingest_is_idempotent(db):
    from app.domains.geo.rainfall.repository import persist_intervals

    rows = _daily_intervals(start_day=1, values=[1.5, 0.0, 3.25])

    persist_intervals(db, source_id="chirps-v3-final", rows=rows, **ZONE_KWARGS)
    db.flush()

    # Re-running the identical ingest must not raise and must not duplicate.
    persist_intervals(db, source_id="chirps-v3-final", rows=rows, **ZONE_KWARGS)
    db.flush()

    assert _count_interval_rows(db) == len(rows)


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
