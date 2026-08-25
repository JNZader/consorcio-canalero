"""Regressions for the slice-2b resilience-lens fix round (LI2B-001..005).

Every test here pins a request-path or build-path DEGRADATION contract: what
the system must keep doing when a build refuses to write, a row goes terminal
`failed`, an enqueue blows up mid-transaction, or the baseline evidence is
corrupt. All of them run against real PostgreSQL through the `db` fixture,
because the failures they pin are transaction-level (savepoints, aborted
transactions, `COALESCE`-ordered reads) and a SQLite or mock double would
report green on the exact bug.
"""

import json
import logging
from datetime import UTC, date, datetime, timedelta

import pytest

# The value RAINFALL_METRIC_POLICY_REVISION carried before lluvia-insights
# bumped it (mirrors test_backend_api.py's own pinned literal): a snapshot
# stored under it is the "stale policy revision" the read path must serve AND
# schedule a bounded refresh for.
_PREVIOUS_POLICY_REVISION = "rainfall-v2-2026-08"


def _daily_source_rows(start: date, count: int, value: float):
    from app.domains.geo.rainfall.ports import SourceInterval

    rows = []
    for offset in range(count):
        day = start + timedelta(days=offset)
        day_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        rows.append(SourceInterval(day_start, day_start + timedelta(days=1), value, "mm", "v3-nrt"))
    return rows


def _batch(scope_id: str) -> dict:
    return {
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


def _restamped(snapshot: dict, revision: str) -> dict:
    """The same envelope as if it had been built under *revision* -- the
    embedded ``metric_policy`` AND every metric's own ``revision`` move
    together, which is what keeps an older row self-consistent under its own
    policy."""
    restamped = {
        **snapshot,
        "metric_policy": {**snapshot["metric_policy"], "revision": revision},
    }
    for group in ("annual", "antecedents"):
        restamped[group] = {
            name: {**metric, "revision": revision} for name, metric in snapshot[group].items()
        }
    return restamped


def _built_snapshot(*, scope_id: str, year: int, now: datetime, rows) -> dict:
    from app.domains.geo.rainfall.compute import build_snapshot
    from app.domains.geo.rainfall.scope import AnalysisScope

    return build_snapshot(
        scope=AnalysisScope(kind="zone", id=scope_id, version="v1", regional_estimate=False),
        year=year,
        role="daily",
        source_id="chirps-v3-sat",
        intervals=[(row.interval_start, row.interval_end, row.value) for row in rows],
        batch=_batch(scope_id),
        now=now,
    )


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


def _event_payload(caplog, event_name: str) -> dict:
    for record in caplog.records:
        if record.name == "rainfall" and record.message.startswith(f"{event_name} "):
            return json.loads(record.message[len(event_name) + 1 :])
    raise AssertionError(
        f"no {event_name!r} event captured; got {[r.message for r in caplog.records]}"
    )


def _seed_stale_revision(db, *, scope_id: str, year: int, now: datetime):
    """Persist daily intervals plus ONE stored revision for the router's own
    fingerprint, written under the SUPERSEDED policy revision -- the state
    that makes ``read_analysis`` take its stale-requeue branch."""
    from app.domains.geo.rainfall.repository import persist_intervals, persist_revision
    from app.domains.geo.rainfall.service import analysis_request_fingerprint

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
    persist_revision(
        db,
        request_fingerprint=fingerprint,
        policy_revision=_PREVIOUS_POLICY_REVISION,
        data_revision="b" * 64,
        snapshot=_restamped(
            _built_snapshot(scope_id=scope_id, year=year, now=now, rows=rows),
            _PREVIOUS_POLICY_REVISION,
        ),
    )
    return scope, fingerprint


def _requeue_key(*, scope_id: str, year: int) -> dict:
    """The outbox key ``queue_missing_analysis`` will resolve for a full-year
    request on this scope/year. Derived, never hardcoded: the source/role pair
    depends on whether *year* is the CURRENT year on the real clock, and the
    cooldown reads are keyed on exactly this tuple."""
    from app.domains.geo.rainfall.service import resolve_missing_work_source

    work = resolve_missing_work_source(None, year)
    return {
        "source_id": work["source_id"],
        "role": work["role"],
        "scope_kind": "zone",
        "scope_id": scope_id,
        "scope_version": "v1",
        "year": year,
        "interval_start": work["interval_start"],
        "interval_end": work["interval_end"],
    }


def _pending_rows(db, scope_id: str):
    from sqlalchemy import select

    from app.domains.geo.rainfall.models import RainfallOutbox

    return db.scalars(
        select(RainfallOutbox)
        .where(RainfallOutbox.scope_id == scope_id)
        .where(RainfallOutbox.status == "pending")
    ).all()


def _backdate(db, row, *, column: str, stamp: datetime) -> None:
    """Push a timestamp into the past through a Core UPDATE.

    An ORM attribute assignment would be overwritten by TimestampMixin's
    ``onupdate=func.now()`` on ``updated_at``; a Core UPDATE that names the
    column explicitly in its SET clause is not touched by that default. The
    assertion is part of the helper on purpose -- a silently ignored backdate
    would turn every cooldown-expiry test below into a tautology.
    """
    from sqlalchemy import update

    from app.domains.geo.rainfall.models import RainfallOutbox

    db.execute(
        update(RainfallOutbox)
        .where(RainfallOutbox.id == row.id)
        .values(**{column: stamp})
        .execution_options(synchronize_session=False)
    )
    db.expire(row)
    assert getattr(row, column) == stamp, f"{column} backdate did not stick"


# ===========================================================================
# LI2B-001 — a terminal `failed` row must not be re-enqueued every poll
# ===========================================================================


def test_failed_row_serves_the_stale_snapshot_without_requeueing_inside_the_cooldown(db, caplog):
    """LI2B-001: a key whose newest terminal outbox row is `failed` matched
    NEITHER the recent-`done` cooldown nor the pending pre-check, so every
    poll started a fresh MAX_RETRIES cycle -- and for a deterministic
    compute-time failure (ingest succeeds, so the adapter breaker never
    trips) that is an unbounded full-year GEE fetch loop for as long as
    anyone keeps the panel open."""
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.tasks import MAX_RETRIES

    scope_id = "zone-li2b001-failed-cooldown"
    year = 2025
    now = datetime(year, 2, 20, 12, 0, tzinfo=UTC)
    scope, _fingerprint = _seed_stale_revision(db, scope_id=scope_id, year=year, now=now)

    key = _requeue_key(scope_id=scope_id, year=year)
    failed = RainfallOutbox(
        **key,
        work_labels=["analysis_missing", f"role:{key['role']}"],
        status="failed",
        retry_count=MAX_RETRIES,
        last_error="ValueError: baseline_cumulatives received duplicated interval_start slots",
    )
    db.add(failed)
    db.flush()

    caplog.set_level(logging.INFO, logger="rainfall")
    response = _rainfall_client(db).post("/rainfall/analyses", json={"scope": scope, "year": year})

    # The read is still answered from the stored revision -- a failed
    # background build never degrades the served answer.
    assert response.status_code == 200
    assert response.json()["metric_policy"]["revision"] == _PREVIOUS_POLICY_REVISION

    # ... and it spends no new GEE quota on a key that just exhausted its
    # retries seconds ago.
    assert _pending_rows(db, scope_id) == []
    db.expire(failed)
    assert failed.status == "failed"
    assert failed.retry_count == MAX_RETRIES

    cooldown = _event_payload(caplog, "rainfall.outbox.cooldown")
    assert cooldown["reason"] == "terminal_failed"
    assert cooldown["outbox_id"] == str(failed.id)


def test_failed_row_older_than_the_cooldown_enqueues_exactly_one_refresh(db):
    """The other half of LI2B-001: the suppression is a COOLDOWN, not a
    tombstone. Once it lapses the read path heals the key with exactly one
    new work item, and the pending pre-check keeps the next poll from adding
    a second."""
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.service import RAINFALL_FAILED_REQUEUE_COOLDOWN
    from app.domains.geo.rainfall.tasks import MAX_RETRIES

    scope_id = "zone-li2b001-failed-expired"
    year = 2025
    now = datetime(year, 2, 20, 12, 0, tzinfo=UTC)
    scope, _fingerprint = _seed_stale_revision(db, scope_id=scope_id, year=year, now=now)

    key = _requeue_key(scope_id=scope_id, year=year)
    failed = RainfallOutbox(
        **key,
        work_labels=["analysis_missing", f"role:{key['role']}"],
        status="failed",
        retry_count=MAX_RETRIES,
        last_error="RuntimeError: transient",
    )
    db.add(failed)
    db.flush()
    _backdate(
        db,
        failed,
        column="updated_at",
        stamp=datetime.now(UTC) - RAINFALL_FAILED_REQUEUE_COOLDOWN - timedelta(minutes=1),
    )

    client = _rainfall_client(db)
    assert client.post("/rainfall/analyses", json={"scope": scope, "year": year}).status_code == 200

    queued = _pending_rows(db, scope_id)
    assert len(queued) == 1
    assert "policy_revision_stale" in queued[0].work_labels

    # Idempotent under repeated polls: the pending pre-check owns this now.
    assert client.post("/rainfall/analyses", json={"scope": scope, "year": year}).status_code == 200
    assert len(_pending_rows(db, scope_id)) == 1


# ===========================================================================
# LI2B-002 — an enqueue failure must not 500 a read already in memory
# ===========================================================================


def test_enqueue_failure_serves_the_snapshot_and_leaves_the_session_usable(db, monkeypatch, caplog):
    """LI2B-002: the snapshot is already in memory when the stale-requeue
    fires. A SQLAlchemyError there used to propagate and 500 the read; worse,
    the failed statement leaves the transaction ABORTED (SQLSTATE 25P02), so
    anything that touches the same session afterwards fails too -- which is
    why a bare try/except is not the fix and the enqueue needs its own
    SAVEPOINT."""
    from sqlalchemy import text

    from app.domains.geo.rainfall import router as rainfall_router

    scope_id = "zone-li2b002-enqueue-failure"
    year = 2025
    now = datetime(year, 2, 20, 12, 0, tzinfo=UTC)
    scope, _fingerprint = _seed_stale_revision(db, scope_id=scope_id, year=year, now=now)

    def _explode(session, **_kwargs):
        # A REAL aborted transaction, not a bare raise: this is the state
        # that poisons every later statement on the same session.
        session.execute(text("SELECT * FROM rainfall_table_that_does_not_exist"))

    monkeypatch.setattr(rainfall_router, "queue_missing_analysis", _explode)

    caplog.set_level(logging.INFO, logger="rainfall")
    response = _rainfall_client(db).post("/rainfall/analyses", json={"scope": scope, "year": year})

    assert response.status_code == 200
    assert response.json()["metric_policy"]["revision"] == _PREVIOUS_POLICY_REVISION

    failure = _event_payload(caplog, "rainfall.analysis.requeue_failed")
    assert failure["error_type"] == "ProgrammingError"
    assert failure["scope_id"] == scope_id
    assert failure["year"] == year

    # The proof that the savepoint did its job: a plain query on the SAME
    # session still works. Without it this raises InFailedSqlTransaction.
    assert db.execute(text("SELECT 1")).scalar() == 1


# ===========================================================================
# LI2B-003 — a non-write build decision must be observable and back off
# ===========================================================================


def test_non_write_decision_stamps_an_outcome_marker_on_the_done_row(db, monkeypatch):
    """LI2B-003: ``revision_write_decision`` can return `latched` or
    `gate_refused` -- both write NOTHING -- yet ``_process_outbox_row``
    marked the row `done` unconditionally, so the served snapshot stayed
    stale with no record on the row of WHY, and the request path had no way
    to tell a productive `done` from a refusal."""
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.service import outcome_label

    key = _requeue_key(scope_id="zone-li2b003-marker", year=2025)
    row = RainfallOutbox(**key, work_labels=["analysis_missing"], request_fingerprint="c" * 64)
    db.add(row)
    db.flush()

    monkeypatch.setattr(tasks, "ingest_source_scope", lambda **_kwargs: _batch("marker"))
    monkeypatch.setattr(
        tasks,
        "build_analysis",
        lambda **_kwargs: {
            "revision_id": None,
            "data_revision": "d" * 64,
            "decision": "gate_refused",
        },
    )

    assert tasks._process_outbox_row(row, db, datetime.now(UTC)) == "done"
    assert row.status == "done"
    assert outcome_label("gate_refused") in row.work_labels
    # The work labels the row was queued with survive alongside it.
    assert "analysis_missing" in row.work_labels


def test_gate_refused_done_row_backs_off_for_a_day_while_a_normal_done_row_does_not(db, caplog):
    """The read-path half of LI2B-003. A refusal cannot be healed by
    retrying sooner -- only by upstream data improving -- so its re-enqueue
    cadence is aligned with the daily write-gate sweep, not with the 10-minute
    recompute cooldown that governs a productive `done`."""
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.service import outcome_label

    year = 2025
    now = datetime(year, 2, 20, 12, 0, tzinfo=UTC)
    half_an_hour_ago = datetime.now(UTC) - timedelta(minutes=30)

    # (a) refused: outside the 10-minute window, inside the daily one.
    refused_scope_id = "zone-li2b003-refused"
    refused_scope, _ = _seed_stale_revision(db, scope_id=refused_scope_id, year=year, now=now)
    refused_key = _requeue_key(scope_id=refused_scope_id, year=year)
    refused = RainfallOutbox(
        **refused_key,
        work_labels=["analysis_missing", outcome_label("gate_refused")],
        status="done",
        completed_at=half_an_hour_ago,
    )
    db.add(refused)

    # (b) the control: same age, same everything, no refusal marker.
    plain_scope_id = "zone-li2b003-plain"
    plain_scope, _ = _seed_stale_revision(db, scope_id=plain_scope_id, year=year, now=now)
    plain_key = _requeue_key(scope_id=plain_scope_id, year=year)
    plain = RainfallOutbox(
        **plain_key,
        work_labels=["analysis_missing"],
        status="done",
        completed_at=half_an_hour_ago,
    )
    db.add(plain)
    db.flush()

    caplog.set_level(logging.INFO, logger="rainfall")
    client = _rainfall_client(db)
    assert (
        client.post("/rainfall/analyses", json={"scope": refused_scope, "year": year}).status_code
        == 200
    )
    assert _pending_rows(db, refused_scope_id) == []
    cooldown = _event_payload(caplog, "rainfall.outbox.cooldown")
    assert cooldown["reason"] == "non_write_gate_refused"

    assert (
        client.post("/rainfall/analyses", json={"scope": plain_scope, "year": year}).status_code
        == 200
    )
    assert len(_pending_rows(db, plain_scope_id)) == 1


# ===========================================================================
# LI2B-004 — a duplicated baseline slot must degrade, not kill, the build
# ===========================================================================


def test_duplicate_baseline_slots_degrade_normal_and_percentile_only(db, caplog):
    """LI2B-004: ``baseline_cumulatives``'s duplicate guard raised a bare
    ``ValueError`` that ``_persist_analysis_revision`` did not catch, so a
    duplicate in ONE baseline year killed the whole build -- annual,
    antecedents and intensity included -- permanently, since a retry cannot
    un-duplicate data. It is also the sharpest feeder of LI2B-001's loop."""
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION, asset_name_for
    from app.domains.geo.rainfall.models import RainfallAnalysisRevision, RainfallIntervalValue
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import persist_intervals
    from app.domains.geo.rainfall.service import analysis_request_fingerprint

    scope_id = "zone-li2b004-duplicate-baseline"
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

    # One baseline year with a duplicated slot: two non-superseded rows for
    # the same `interval_start` under different provider revisions -- the
    # residue of a correction whose supersession link never landed.
    asset = asset_name_for("zone", scope_id)
    duplicated_day = datetime(1991, 1, 5, tzinfo=UTC)
    persist_intervals(
        db,
        source_id="chirps-v3-final",
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        rows=[
            SourceInterval(
                duplicated_day, duplicated_day + timedelta(days=1), 8.0, "mm", "v3-final"
            )
        ],
    )
    db.add(
        RainfallIntervalValue(
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            interval_start=duplicated_day,
            interval_end=duplicated_day + timedelta(days=1),
            provider_revision="v3-final+r1",
            value=9.0,
            unit="mm",
        )
    )
    db.flush()

    scope = {"kind": "zone", "id": scope_id, "version": "v1"}
    fingerprint = analysis_request_fingerprint({"scope": scope, "year": year})
    # The BUILD key, not the request-path key: `_persist_analysis_revision`
    # reads intervals under the row's OWN source_id, so it has to name the
    # source the fixture actually persisted (chirps-v3-sat / daily), not the
    # historical pair `resolve_missing_work_source` would pick for a past year.
    outbox = tasks.RainfallOutbox(
        source_id="chirps-v3-sat",
        role="daily",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        year=year,
        interval_start=datetime(year, 1, 1, tzinfo=UTC),
        interval_end=datetime(year + 1, 1, 1, tzinfo=UTC),
        work_labels=["analysis_missing"],
        request_fingerprint=fingerprint,
    )
    db.add(outbox)
    db.flush()

    caplog.set_level(logging.INFO, logger="rainfall")
    result = tasks._persist_analysis_revision(
        db, outbox_id=str(outbox.id), batch=_batch(scope_id), now=now
    )

    # The build LANDS -- the duplicate costs exactly the two metrics that
    # read the baseline, not the whole analysis.
    assert result["decision"] == "write"
    assert result["revision_id"] is not None
    stored = db.get(RainfallAnalysisRevision, result["revision_id"]).snapshot
    assert stored["annual"]["selected"]["state"] == "available"
    assert stored["annual"]["selected"]["value"] == pytest.approx(153.0)
    # S2a: nine antecedent metrics. The three TOTALS are what this test is
    # about -- they must survive the ANNUAL baseline read's duplicate -- and
    # the six reference metrics are named explicitly so this pin keeps failing
    # the day the key set moves again.
    assert set(stored["antecedents"]) == {
        "d7",
        "d7_normal",
        "d7_percentile",
        "d30",
        "d30_normal",
        "d30_percentile",
        "d90",
        "d90_normal",
        "d90_percentile",
    }
    for metric in ("normal", "percentile"):
        assert stored["annual"][metric]["state"] == "suppressed"
        assert stored["annual"][metric]["reason"] == "baseline_evidence_invalid"

    duplicate = _event_payload(caplog, "rainfall.baseline.duplicate_slots")
    assert duplicate["baseline_year"] == 1991
    assert duplicate["matched_rows"] == 2
    assert duplicate["distinct_slots"] == 1
    assert duplicate["asset"] == asset
    assert duplicate["scope_id"] == scope_id


def test_duplicate_baseline_guard_still_raises_at_the_repository_boundary(db):
    """The degradation above lives in the TASK, not in the repository: the
    read itself must still fail loudly for every other caller (LI2A-005's
    original guard), and it now fails with a dedicated exception type rather
    than a bare ValueError nobody can catch selectively."""
    from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION
    from app.domains.geo.rainfall.models import RainfallIntervalValue
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import (
        DuplicateBaselineSlotError,
        baseline_cumulatives,
        persist_intervals,
    )

    asset = "baseline-li2b004-repository-boundary"
    day = datetime(1991, 5, 1, tzinfo=UTC)
    persist_intervals(
        db,
        source_id="chirps-v3-final",
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        rows=[SourceInterval(day, day + timedelta(days=1), 10.0, "mm", "v3-final")],
    )
    db.add(
        RainfallIntervalValue(
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            interval_start=day,
            interval_end=day + timedelta(days=1),
            provider_revision="v3-final+r1",
            value=10.0,
            unit="mm",
        )
    )
    db.flush()

    with pytest.raises(DuplicateBaselineSlotError, match="duplicat") as raised:
        baseline_cumulatives(db, source_id="chirps-v3-final", asset=asset, dates=[date(1991, 5, 2)])
    # Still a ValueError, so the pre-existing contract test keeps holding.
    assert isinstance(raised.value, ValueError)
    assert (raised.value.year, raised.value.matched, raised.value.distinct_slots) == (1991, 2, 1)


# ===========================================================================
# LI2B-005 — the new events are catalogued in the observability workbook
# ===========================================================================


def _workbook_text() -> str:
    from pathlib import Path

    # tests/new/geo/rainfall/<this file> -> parents[4] is gee-backend,
    # parents[5] the repo root that owns docs/.
    return (
        Path(__file__).resolve().parents[5] / "docs" / "lluvia-v2-observability-workbook.md"
    ).read_text(encoding="utf-8")


def _section(workbook: str, heading: str) -> str:
    """The body of one ``### `` section, up to the next heading of any level."""
    lines = workbook.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(f"### {heading}"))
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].startswith("#") and not lines[index].startswith("####")
        ),
        len(lines),
    )
    return "\n".join(lines[start + 1 : end])


def _tables(section: str) -> list[list[list[str]]]:
    """Every markdown table in *section*, as a list of rows of cells.

    A table is one CONTIGUOUS run of ``|``-prefixed lines; a blank line or a
    paragraph between two runs makes them two tables. That is exactly the
    distinction this file needs: an event row pasted after a value table's
    last row is inside THAT table, however plausible it looks in a diff.
    """
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            current.append([cell.strip() for cell in stripped.strip("|").split("|")])
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def _table_with_header(section: str, first_header_cell: str) -> list[list[str]]:
    """The one table in *section* whose header row starts with that cell."""
    matches = [table for table in _tables(section) if table and table[0][0] == first_header_cell]
    assert len(matches) == 1, (
        f"expected exactly one table headed {first_header_cell!r}, found {len(matches)}"
    )
    return matches[0]


def _data_rows(table: list[list[str]]) -> list[list[str]]:
    """Rows below the header and its ``|---|`` separator."""
    return [row for row in table[1:] if not set("".join(row)) <= set("- :")]


def test_every_new_rainfall_event_is_documented_in_the_observability_workbook():
    """metrics.py's docstring names the workbook as THE contract for what an
    event means; an event that fires in production but appears nowhere in
    that catalogue is undocumented by construction.

    JDA-004 / JDB-002: a bare substring match is not enough to keep that
    contract. ``rainfall.analysis.requeue_failed`` was documented for months
    while sitting INSIDE the ``consistency_reason`` value table one section
    below -- present to a substring search, absent from the event catalogue,
    and rendered to a reader as a third enum value the API can never emit.
    So the assertion is structural: the event must be a row of the EVENT
    table of the section that owns it.
    """
    workbook = _workbook_text()

    for event, heading in (
        ("rainfall.analysis.policy_revision_stale", "2.1"),
        ("rainfall.analysis.requeue_failed", "2.1"),
        ("rainfall.baseline.duplicate_slots", "2.3"),
        ("rainfall.window_baseline.duplicate_slots", "2.3"),
    ):
        table = _table_with_header(_section(workbook, heading), "Event")
        assert any(row[0] == f"`{event}`" for row in _data_rows(table)), (
            f"{event} is not a row of the §{heading} event table"
        )
    # The gate-refusal marker's own semantics (LI2B-003), not just its event.
    assert "outcome:gate_refused" in workbook


def test_the_consistency_reason_table_lists_only_consistency_reasons():
    """The other half of the same defect (JDA-004 / JDB-002).

    ``consistency_reason`` is a THREE-state enum (``null`` plus the two below)
    and the table is the reader's list of what the field can hold. Anything
    else in its first column reads as a fourth value -- an operator grepping
    for a served ``consistency_reason`` would find an event name and go
    looking for a state that does not exist.
    """
    table = _table_with_header(_section(_workbook_text(), "2.1"), "`consistency_reason`")

    assert {row[0] for row in _data_rows(table)} == {
        "`data_revision_moved`",
        "`interval_family_ambiguous`",
    }
