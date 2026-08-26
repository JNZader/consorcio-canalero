"""The full-span runbook CLI: labelled aborts, idempotence, and the report
(lluvia-eventos-extremos, slice B1c).

Real Postgres throughout. `test_rainfall_detector.py` (B1a) owns the arithmetic
and `test_rainfall_catalog.py` (B1b) owns the schema and the writer; this file
owns the one thing neither can assert — what the OPERATOR sees, and what the
catalog holds afterwards, when a run stops.

Three properties carry the slice:

* **the run is full-span, always** (D6). The incremental mode was CUT, so the
  absence of a `--since`/`--from` flag is a guard, not an omission: without it
  the mode comes back as a "restoration" and every row it writes is sealed
  under a span it never ranked against;
* **a stop leaves ZERO rows**, including rows for events computed BEFORE the
  stop. `persist_events` `db.add()`s as it walks the batch and raises on the
  first divergence, so the rows added before it are pending in the session —
  not written, but written by any later `flush()`/`commit()`. "Zero rows
  written" is therefore a property of the CALLER, and it is asserted here from
  a session that never held those pending rows;
* **the intra-batch identity hazard is closed WITHOUT autoflush** (B1b verify,
  finding (b)). Production's `SessionLocal` is `autoflush=False`; the suite's
  `db` fixture is `autoflush=True`. Under autoflush an intra-batch duplicate
  identity is found by `persist_events`' own lookup and reported as a named
  `CatalogDivergenceError`; in production nothing flushes, the lookup sees
  nothing, and the collision surfaces at `commit()` as a raw `IntegrityError`
  with no field list. Every CLI test below therefore runs on a
  PRODUCTION-SHAPED session (`autoflush=False`) — a test written against the
  `db` fixture alone cannot see this.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION
from app.domains.geo.rainfall.ports import SourceInterval
from app.domains.geo.rainfall.repository import persist_intervals

SOURCE_ID = "chirps-v3-final"

#: The seeded record starts on the frozen span's first day and is long enough
#: to clear `MIN_WINDOW_SAMPLES = 3650` at every window length, so the CLI runs
#: on its REAL defaults — no injected floor, no injected percentile. The real
#: zone asset holds 12,784 days; this holds 4,000, which is the smallest record
#: that still exercises the shipped constants.
SPAN_FIRST_DAY = date(1991, 1, 1)
SEEDED_DAYS = 4000

#: Wet spells planted at known offsets: (offset, daily total). Spaced far apart
#: so `GAP_DAYS = 1` cannot merge them, and varied in shape so the batch holds
#: both single-day and multi-day events at more than one tier.
_SPELLS = (
    (200, 260.0),
    (201, 240.0),
    (202, 150.0),
    (900, 300.0),
    (1500, 210.0),
    (1501, 205.0),
    (2300, 120.0),
    (2301, 130.0),
    (2302, 140.0),
    (2303, 135.0),
    (2304, 125.0),
    (2305, 130.0),
    (2306, 120.0),
    (3000, 280.0),
    (3001, 190.0),
    (3700, 265.0),
)


def _persist_baseline_days(db, *, asset, days, source_id=SOURCE_ID, revision="v3-final"):
    """One persisted daily row per ``(date, value)`` pair under the baseline key.

    Duplicated from `test_rainfall_catalog.py` rather than imported, for the
    same reason that file duplicated it: the slice's rollback boundary is meant
    to be one module plus one test file, and a cross-file import of another
    suite's private helper quietly widens it.
    """
    rows = [
        SourceInterval(
            datetime(day.year, day.month, day.day, tzinfo=UTC),
            datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=1),
            value,
            "mm",
            revision,
        )
        for day, value in days
    ]
    return persist_intervals(
        db,
        source_id=source_id,
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        rows=rows,
    )


def _full_span_series(first_day=SPAN_FIRST_DAY, length=SEEDED_DAYS):
    """A quiet record with the planted spells laid over it."""
    series = {first_day + timedelta(days=offset): 1.0 + (offset % 5) for offset in range(length)}
    for offset, value in _SPELLS:
        series[first_day + timedelta(days=offset)] = value
    return sorted(series.items())


@pytest.fixture
def cli_sessions(db):
    """A PRODUCTION-SHAPED session factory on the test's own connection.

    `autoflush=False`, exactly like `app.db.session.SessionLocal`, so the
    intra-batch hazard the B1b verify measured is reachable here. Bound to the
    `db` fixture's connection so seeded-but-uncommitted baseline rows are
    visible to the CLI and the whole thing still rolls back with the test.

    `join_transaction_mode="create_savepoint"` is LOAD-BEARING and was measured,
    not assumed: SQLAlchemy's default for a Session bound to a Connection that
    is already in a transaction is `"conditional_savepoint"`, which here
    degrades to rollback-only — so the CLI's `session.rollback()` would roll
    back the OUTER test transaction, taking the fixture's own planted rows with
    it. Under that default the rollback tests pass for the wrong reason (the
    catalog is empty because EVERYTHING was rolled back, including data the
    test seeded before the run) and cannot distinguish a CLI that rolls back
    from one that wipes the database.
    """
    connection = db.get_bind()
    return sessionmaker(bind=connection, autoflush=False, join_transaction_mode="create_savepoint")


@pytest.fixture
def fresh_reader(db):
    """A session that never held the CLI's pending rows.

    Task 3.4(a) is explicit that the emptiness assertion must not be made on the
    aborting session's own state: that session cannot distinguish "not written"
    from "not flushed yet". This one can, because nothing was ever added to it.
    """
    connection = db.get_bind()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()


def _catalog_rows(session):
    from app.domains.geo.rainfall.models import RainfallExtremeEvent

    session.expire_all()
    return session.query(RainfallExtremeEvent).all()


def _run(monkeypatch, capsys, cli_sessions, *, asset, argv=None):
    """Run the CLI the way the runbook does and return (exit code, out, err)."""
    from app.domains.geo.rainfall import detector_cli

    argv = ["--asset", asset, *(argv or [])]
    code = detector_cli.main(argv, session_factory=cli_sessions)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _reported_event_counts(out):
    """The ``events after merge`` block of the run's own stdout, parsed.

    Read off the PRINTED report rather than off a returned dict: the operator's
    gate is the text, and a report object that disagreed with what was printed
    would be invisible to a test that only inspected the object.
    """
    lines = out.splitlines()
    start = lines.index("events after merge:")
    counts: dict[str, int] = {}
    for line in lines[start + 1 :]:
        if not line.startswith("  "):
            break
        tier, _, total = line.strip().partition(": ")
        counts[tier] = int(total)
    return counts


def _plant_control_row(db, *, asset, event_key="control_row"):
    """One curated row that the run must NOT touch.

    Every "the catalog is empty afterwards" assertion is passed by a CLI that
    wipes the table, and by a rollback that took the fixture's own rows with it.
    A planted row that must SURVIVE is what separates "the aborted batch wrote
    nothing" from "nothing is there".
    """
    db.execute(
        text(
            "INSERT INTO rainfall_extreme_event "
            "(id, source_id, scope_kind, scope_id, scope_version, detector_revision, "
            " provenance, event_key, start_date, end_date, curated_payload) "
            "VALUES (gen_random_uuid(), :source_id, 'provider_asset', :asset, :version, "
            " 'curated', 'curated', :event_key, DATE '2017-02-20', DATE '2017-02-20', "
            " '{}'::json)"
        ),
        {
            "source_id": SOURCE_ID,
            "asset": f"{asset}-control",
            "version": BASELINE_ASSET_VERSION,
            "event_key": event_key,
        },
    )
    db.flush()
    return event_key


def _catalog_writes(db):
    """Statements the ambient connection emitted against the catalog table."""
    seen: list[str] = []

    def _record(_conn, _cursor, statement, _parameters, _context, _executemany):
        seen.append(statement)

    return seen, _record


# ===========================================================================
# 3.1 -- the runbook shape, and the absence that keeps the mode CUT
# ===========================================================================


def test_the_cli_carries_the_same_exit_code_labels_as_the_backfill_runner():
    """3.1: LABELLED exits, and the same labels the deployment already runs.

    Two runbooks in one package answering the same condition with different
    numbers is how an operator's `|| exit 1` wrapper ends up treating a stop as
    a success. Asserted against `backfill_cli`'s values, not against literals.
    """
    from app.domains.geo.rainfall import backfill_cli, detector_cli

    assert detector_cli.EXIT_OK == backfill_cli.EXIT_OK == 0
    assert detector_cli.EXIT_STOPPED == backfill_cli.EXIT_STOPPED == 1
    assert detector_cli.EXIT_INVALID_RANGE == backfill_cli.EXIT_INVALID_RANGE
    assert detector_cli.EXIT_OK != detector_cli.EXIT_STOPPED
    # `EXIT_REPORT_FAILED` is deliberately NOT shared: it means the opposite of
    # a stop (the rows are committed), so it must not collide with one.
    assert detector_cli.EXIT_REPORT_FAILED not in (
        detector_cli.EXIT_OK,
        detector_cli.EXIT_STOPPED,
        detector_cli.EXIT_INVALID_RANGE,
    )


def test_main_reaches_for_the_deployment_session_factory_when_nobody_passes_one():
    """3.1 / B1c verify F6: the DEFAULT is the binding nothing else asserts.

    Every test here injects `cli_sessions`, so the production wiring -- the
    thing the runbook's `python -m ...` invocation actually uses -- is exercised
    by no test at all. A default of `None`, or of some other factory, passes the
    entire suite and fails on the box the first time it is hand-run.
    """
    import inspect

    from app.db.session import SessionLocal
    from app.domains.geo.rainfall import detector_cli

    default = inspect.signature(detector_cli.main).parameters["session_factory"].default
    assert default is SessionLocal


def test_an_inverted_frozen_span_exits_invalid_range_before_reading_anything(
    db, cli_sessions, monkeypatch, capsys
):
    """3.1 / B1c verify F8: the guard is REACHED, not merely present.

    The constant equality above says the number is 2; it says nothing about the
    guard existing. Deleting the whole `SPAN_START >= SPAN_END` block leaves the
    suite green and turns a defective constants block into an empty read, which
    every reader downstream renders as "no events" -- a fabricated absence in
    the one runbook that writes permanent rows.

    The read itself is replaced by a refusal, because "invalid range" has to be
    decided BEFORE the baseline is touched.
    """
    from app.domains.geo.rainfall import detector_cli

    def _refuse(*_args, **_kwargs):
        raise AssertionError("the run read the baseline under an inverted span")

    monkeypatch.setattr(detector_cli, "baseline_daily_values", _refuse)
    start, end = detector_cli.SPAN_START, detector_cli.SPAN_END
    monkeypatch.setattr(detector_cli, "SPAN_START", end)
    monkeypatch.setattr(detector_cli, "SPAN_END", start)

    code, out, err = _run(monkeypatch, capsys, cli_sessions, asset="detector-cli-inverted-span")

    assert code == detector_cli.EXIT_INVALID_RANGE
    assert "invalid range" in err
    assert out.strip() == ""


@pytest.mark.parametrize(
    "forbidden",
    ["--since", "--from", "--start", "--start-year", "--end", "--end-year", "--incremental"],
)
def test_the_parser_exposes_no_incremental_or_span_flag(forbidden):
    """3.1, an ABSENCE GUARD (labelled as such — it passes on first run).

    D6 CUT the incremental mode: the climatology span is frozen to whole
    calendar years, so every run ranks against the same distribution and reads
    the same rows, and advancing the span requires a revision bump that
    regenerates the whole generation anyway. The mode bought one bounded read
    and cost two of the review's four hardest findings.

    A run that could be told to start "from" somewhere would seal rows under a
    span it never ranked against. The guard is here so that restoring the flag
    is a decision somebody has to argue with, not a convenience.
    """
    from app.domains.geo.rainfall import detector_cli

    options = {
        option
        for action in detector_cli.build_parser()._actions
        for option in action.option_strings
    }
    assert forbidden not in options


def test_the_runbook_docstring_says_how_to_run_it_and_why_there_is_no_incremental_mode():
    """3.1: the docstring IS the runbook (`backfill_cli:1-26`'s discipline).

    Also an absence guard's other half: the reason the flag is missing has to
    be readable at the place a future reader would add it back.
    """
    from app.domains.geo.rainfall import detector_cli

    doc = detector_cli.__doc__ or ""
    assert "docker compose exec backend python -m app.domains.geo.rainfall.detector_cli" in doc
    assert "incremental" in doc.lower()
    assert "NOT a Beat" in doc


def test_the_cli_never_reaches_for_the_default_card_span():
    """3.1 / D14: the read is made with the DETECTOR span, explicitly.

    `baseline_daily_values` defaults to the CARD's `[1991, 2021)` bounds, which
    are load-bearing for the antecedent-reference envelope and must not move.
    A CLI that omitted the arguments would silently rank 1991-2020 and drop
    `sep_2025` from the catalog with nothing to read as an error.
    """
    from app.domains.geo.rainfall import detector_cli
    from app.domains.geo.rainfall.detector import (
        DETECTOR_CLIMATOLOGY_END,
        DETECTOR_CLIMATOLOGY_START,
    )
    from app.domains.geo.rainfall.repository import BASELINE_SPAN_END

    assert detector_cli.SPAN_START is DETECTOR_CLIMATOLOGY_START
    assert detector_cli.SPAN_END is DETECTOR_CLIMATOLOGY_END
    assert detector_cli.SPAN_END != BASELINE_SPAN_END


# ===========================================================================
# 3.2 / 3.3 -- the full-span run: idempotent, and free of provider quota
# ===========================================================================


def _dump(session):
    return {
        row.event_key: (
            row.tier,
            row.start_date,
            row.end_date,
            row.peak_date,
            row.max_percentile,
            row.fired_windows,
            row.sealed_detection_params,
            row.detector_revision,
        )
        for row in _catalog_rows(session)
    }


def test_the_full_span_run_twice_leaves_a_byte_identical_catalog(
    db, cli_sessions, fresh_reader, monkeypatch, capsys
):
    """3.2 / spec R2 S1: the second pass inserts, updates and deletes NOTHING.

    Compared as a canonicalized dump rather than as a row count — a count-only
    assertion stays green while a field silently moves — AND on the statements
    the connection emitted, because an `UPDATE` that rewrites a row in place
    leaves the count identical and the catalog rewritten.
    """
    asset = "detector-cli-idempotent"
    _persist_baseline_days(db, asset=asset, days=_full_span_series())
    db.flush()

    first_code, first_out, _ = _run(monkeypatch, capsys, cli_sessions, asset=asset)
    assert first_code == 0, first_out
    before = _dump(fresh_reader)
    assert before, "the seeded record must produce at least one event to compare"

    seen, recorder = _catalog_writes(db)
    bind = db.get_bind()
    sa_event.listen(bind, "before_cursor_execute", recorder)
    try:
        second_code, second_out, _ = _run(monkeypatch, capsys, cli_sessions, asset=asset)
    finally:
        sa_event.remove(bind, "before_cursor_execute", recorder)

    assert second_code == 0, second_out
    assert _dump(fresh_reader) == before
    assert [
        statement
        for statement in seen
        if statement.lstrip()[:6].upper() in {"INSERT", "UPDATE", "DELETE"}
        and "rainfall_extreme_event" in statement
    ] == []
    assert "inserted=0" in second_out


def test_the_full_span_run_issues_no_adapter_and_no_gee_call(
    db, cli_sessions, fresh_reader, monkeypatch, capsys
):
    """3.3 / spec R2 S3: zero provider quota, asserted on the CALLS.

    Not on a log line — a log line is a claim the code makes about itself. Every
    public callable in the three provider-facing modules is replaced with one
    that raises, so a call cannot be quiet.
    """
    from app.domains.geo.rainfall.adapters import chirps, gee_client, zonal

    def _refuse(*_args, **_kwargs):
        raise AssertionError("the detector run reached a provider adapter")

    for module in (chirps, gee_client, zonal):
        for name in dir(module):
            if name.startswith("_"):
                continue
            attribute = getattr(module, name)
            if callable(attribute) and getattr(attribute, "__module__", None) == module.__name__:
                monkeypatch.setattr(module, name, _refuse)

    asset = "detector-cli-no-quota"
    _persist_baseline_days(db, asset=asset, days=_full_span_series())
    db.flush()

    code, out, _ = _run(monkeypatch, capsys, cli_sessions, asset=asset)
    assert code == 0, out
    assert _catalog_rows(fresh_reader)


# ===========================================================================
# 3.4 -- DuplicateBaselineSlotError, and the ROLLBACK obligation
# ===========================================================================


def test_a_duplicate_baseline_slot_stops_the_run_labelled_and_writes_nothing(
    db, cli_sessions, fresh_reader, monkeypatch, capsys
):
    """3.4: the abort is NAMED, exits STOPPED, and the catalog is untouched.

    A catalog row is permanent, so unlike a snapshot metric the detector never
    degrades past a duplicated slot: the duplicate inflates a window total while
    leaving the window looking complete, so the rank moves and nothing discloses
    it.
    """
    asset = "detector-cli-duplicate-slot"
    _persist_baseline_days(db, asset=asset, days=_full_span_series())
    control = _plant_control_row(db, asset=asset)
    db.execute(
        text(
            "INSERT INTO rainfall_interval_value "
            "(id, source_id, scope_kind, scope_id, scope_version, interval_start, "
            " interval_end, provider_revision, value, unit) "
            "VALUES (gen_random_uuid(), :source_id, 'provider_asset', :asset, :version, "
            " :start, :end, 'v3-final-duplicate', 6.0, 'mm')"
        ),
        {
            "source_id": SOURCE_ID,
            "asset": asset,
            "version": BASELINE_ASSET_VERSION,
            "start": datetime(1991, 7, 19, tzinfo=UTC),
            "end": datetime(1991, 7, 20, tzinfo=UTC),
        },
    )
    db.flush()

    code, out, err = _run(monkeypatch, capsys, cli_sessions, asset=asset)

    assert code == 1
    assert "STOPPED" in err
    assert "reason=duplicate_baseline_slot" in err
    # The CONTROL row survives: "the catalog is empty" is also what a CLI that
    # wiped the table, or a rollback that swallowed the outer transaction,
    # would leave behind.
    assert [row.event_key for row in _catalog_rows(fresh_reader)] == [control]
    assert out.strip() == ""


def test_a_divergence_mid_batch_rolls_back_the_events_computed_before_it(
    db, cli_sessions, fresh_reader, monkeypatch, capsys
):
    """3.4(a), the INHERITED obligation: zero rows, including the ones already
    `db.add()`ed before the abort.

    `persist_events` adds each non-diverging event as it walks the batch and
    raises on the first one that disagrees. Those pending rows are not written
    — until any later `flush()` or `commit()` writes them. So the CLI must
    `session.rollback()` before exiting, and the emptiness must be read from a
    session that never held them (`fresh_reader`).

    The divergence is planted on the LAST event of the batch, by raw SQL so the
    append-only flush guard is not what refuses it, so that the maximum number
    of events is pending when the abort fires. A test that planted it on the
    FIRST event would pass with no rollback at all.
    """
    from app.domains.geo.rainfall import detector_cli
    from app.domains.geo.rainfall.detector import DETECTOR_REVISION
    from app.domains.geo.rainfall.models import RainfallExtremeEvent

    asset = "detector-cli-mid-batch-divergence"
    _persist_baseline_days(db, asset=asset, days=_full_span_series())
    db.flush()

    planned = detector_cli.plan_events(_read_daily(db, asset))
    assert len(planned) >= 3, "the fixture must produce a batch, not a single event"
    last = planned[-1]

    db.add(
        RainfallExtremeEvent(
            source_id=SOURCE_ID,
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            detector_revision=DETECTOR_REVISION,
            provenance="detected",
            tier=last.tier,
            event_key=detector_cli.event_key(last),
            start_date=last.start_date,
            end_date=last.end_date,
            peak_date=last.peak_date,
            # The one field that disagrees.
            max_percentile=last.max_percentile - 1.0,
            fired_windows=last.fired_windows_payload,
            sealed_detection_params={"planted": True},
            climatology_span_start=last.climatology_span_start,
            climatology_span_end=last.climatology_span_end,
        )
    )
    db.flush()

    code, out, err = _run(monkeypatch, capsys, cli_sessions, asset=asset)

    assert code == 1
    assert "reason=catalog_divergence" in err
    assert "max_percentile" in err
    # ONLY the planted row survives: nothing the aborted batch computed landed.
    rows = _catalog_rows(fresh_reader)
    assert len(rows) == 1
    assert rows[0].sealed_detection_params == {"planted": True}
    assert out.strip() == ""


def _read_daily(db, asset):
    from app.domains.geo.rainfall.detector import (
        DETECTOR_CLIMATOLOGY_END,
        DETECTOR_CLIMATOLOGY_START,
    )
    from app.domains.geo.rainfall.repository import baseline_daily_values

    return baseline_daily_values(
        db,
        source_id=SOURCE_ID,
        asset=asset,
        span_start=DETECTOR_CLIMATOLOGY_START,
        span_end=DETECTOR_CLIMATOLOGY_END,
    )


def test_an_intra_batch_identity_repeat_is_resolved_without_autoflush(
    db, cli_sessions, fresh_reader, monkeypatch, capsys
):
    """3.4(b), the second INHERITED obligation.

    Production is `autoflush=False`, so `persist_events`' identity lookup does
    NOT see rows added earlier in the same batch. Two identical events at one
    identity would both be added and collide at `commit()` as a raw
    `IntegrityError` on `uq_rainfall_extreme_event_identity` — a different type,
    from a different place, with no named field list.

    The CLI closes it before handing the batch over: identical repeats collapse
    to one row. Asserted on a `autoflush=False` session, which is the only place
    the hazard exists.

    It also pins the OTHER half of that resolution, which is the whole reason
    the module exists (B1c verify, F1): the report must describe the rows that
    were WRITTEN, not a third recomputation of the batch. When `main` let
    `calibration_report` re-run `plan_events` itself, the doubled batch here
    produced a catalog of N rows and a printed report of 2N — a recomputation
    with nothing comparing it against the persisted result, which is precisely
    the failure an append-only catalog's runbook exists to prevent.
    """
    from app.domains.geo.rainfall import detector_cli

    asset = "detector-cli-intra-batch-repeat"
    _persist_baseline_days(db, asset=asset, days=_full_span_series())
    db.flush()

    real_plan = detector_cli.plan_events

    def _doubled(daily):
        planned = real_plan(daily)
        return tuple(event for event in planned for _ in range(2))

    monkeypatch.setattr(detector_cli, "plan_events", _doubled)

    code, out, err = _run(monkeypatch, capsys, cli_sessions, asset=asset)

    assert code == 0, err
    keys = [row.event_key for row in _catalog_rows(fresh_reader)]
    assert len(keys) == len(set(keys))
    assert f"inserted={len(keys)}" in out
    # The report describes the RESOLVED batch -- the rows the catalog now holds.
    reported = _reported_event_counts(out)
    assert sum(reported.values()) == len(keys)


def test_an_intra_batch_identity_disagreement_stops_labelled_with_zero_rows(
    db, cli_sessions, fresh_reader, monkeypatch, capsys
):
    """3.4(b)'s other half: a repeat that DISAGREES is not a repeat.

    Collapsing it would pick a winner by list order and seal it forever. It is
    a divergence between two computations of one identity — the same fact
    `CatalogDivergenceError` exists for — so it stops the same way, labelled,
    with nothing written.
    """
    from app.domains.geo.rainfall import detector_cli
    from dataclasses import replace

    asset = "detector-cli-intra-batch-disagreement"
    _persist_baseline_days(db, asset=asset, days=_full_span_series())
    control = _plant_control_row(db, asset=asset)

    real_plan = detector_cli.plan_events

    def _contradictory(daily):
        planned = real_plan(daily)
        twin = replace(planned[-1], max_percentile=planned[-1].max_percentile - 0.5)
        return (*planned, twin)

    monkeypatch.setattr(detector_cli, "plan_events", _contradictory)

    code, out, err = _run(monkeypatch, capsys, cli_sessions, asset=asset)

    assert code == 1
    assert "reason=catalog_divergence" in err
    assert "within a single run" in err.lower()
    assert [row.event_key for row in _catalog_rows(fresh_reader)] == [control]
    assert out.strip() == ""


def test_an_integrity_error_at_commit_stops_labelled_as_catalog_integrity(
    db, cli_sessions, fresh_reader, monkeypatch, capsys
):
    """3.4(b)'s production shape, and the one stop reason no test reached.

    `catalog_integrity` exists because production is `autoflush=False`: when the
    in-module resolution does not catch a collision, it surfaces at `commit()`
    as a raw `IntegrityError` on `uq_rainfall_extreme_event_identity` -- a
    different type, from a different place, with no field list. The suite could
    not reach it (the fixture's own resolution closes the hazard first), so the
    entry could be deleted with everything green and the deployment would answer
    a duplicate identity with a bare traceback.

    Forced here through the writer, with the batch's rows already pending, so
    the rollback obligation is exercised on this path too.
    """
    from app.domains.geo.rainfall import detector_cli

    asset = "detector-cli-integrity"
    _persist_baseline_days(db, asset=asset, days=_full_span_series())
    control = _plant_control_row(db, asset=asset)

    real_persist = detector_cli.persist_events

    def _persist_then_collide(session, **kwargs):
        real_persist(session, **kwargs)
        raise IntegrityError(
            "INSERT INTO rainfall_extreme_event ...",
            {},
            Exception(
                "duplicate key value violates unique constraint "
                '"uq_rainfall_extreme_event_identity"'
            ),
        )

    monkeypatch.setattr(detector_cli, "persist_events", _persist_then_collide)

    code, out, err = _run(monkeypatch, capsys, cli_sessions, asset=asset)

    assert code == detector_cli.EXIT_STOPPED
    assert "STOPPED" in err
    assert "reason=catalog_integrity" in err
    assert "uq_rainfall_extreme_event_identity" in err
    assert [row.event_key for row in _catalog_rows(fresh_reader)] == [control]
    assert out.strip() == ""


def test_an_unexpected_failure_stops_labelled_with_a_traceback_and_zero_rows(
    db, cli_sessions, fresh_reader, monkeypatch, capsys
):
    """B1c verify F4: `build_parser`'s "never a bare traceback" made TRUE.

    Only four exception types were labelled; anything else -- an `OperationalError`
    on a dropped connection, a `KeyError` from a future refactor -- escaped
    `main` as a raw traceback with exit code 1 borrowed from the interpreter, so
    an operator's `|| exit 1` wrapper could not tell it from a named stop.

    Zero rows already held on this path (`Session.__exit__` discards an
    uncommitted session), but it is asserted anyway, with a planted control row:
    the guarantee has to survive the catch-all being added, not depend on it.
    """
    from app.domains.geo.rainfall import detector_cli

    asset = "detector-cli-unexpected"
    _persist_baseline_days(db, asset=asset, days=_full_span_series())
    control = _plant_control_row(db, asset=asset)

    def _explode(_daily):
        raise RuntimeError("the shape of a failure nobody enumerated")

    monkeypatch.setattr(detector_cli, "plan_events", _explode)

    code, out, err = _run(monkeypatch, capsys, cli_sessions, asset=asset)

    assert code == detector_cli.EXIT_STOPPED
    assert "STOPPED" in err
    assert "reason=unexpected" in err
    # The diagnosis still reaches stderr -- labelled is not the same as swallowed.
    assert "Traceback (most recent call last)" in err
    assert "the shape of a failure nobody enumerated" in err
    assert [row.event_key for row in _catalog_rows(fresh_reader)] == [control]
    assert out.strip() == ""


def test_a_report_that_fails_to_render_never_claims_the_run_wrote_nothing(
    db, cli_sessions, fresh_reader, monkeypatch, capsys
):
    """B1c verify F3: the "exit 1 = ZERO rows written" contract, on every path.

    The report is rendered AFTER `db.commit()`, so a rendering failure happens
    with the rows already permanent. Letting that exit `EXIT_STOPPED` -- or
    letting it escape as a traceback whose exit code is also 1 -- would tell the
    operator the exact opposite of what the catalog now holds, and the documented
    reaction to a stop is "re-run it", which is only safe because a stop wrote
    nothing.

    So a post-commit rendering failure gets its own code, `EXIT_REPORT_FAILED`,
    and says so: the rows ARE written and the run must NOT be read as aborted.
    """
    from app.domains.geo.rainfall import detector_cli

    asset = "detector-cli-report-render-failure"
    _persist_baseline_days(db, asset=asset, days=_full_span_series())
    db.flush()

    def _explode(_report):
        raise RuntimeError("the report could not be rendered")

    monkeypatch.setattr(detector_cli, "format_report", _explode)

    code, out, err = _run(monkeypatch, capsys, cli_sessions, asset=asset)

    assert code == detector_cli.EXIT_REPORT_FAILED
    assert code not in (detector_cli.EXIT_OK, detector_cli.EXIT_STOPPED)
    assert "reason=report_render_failed" in err
    assert "STOPPED" not in err, "a committed run is not a stop"
    assert "Traceback (most recent call last)" in err
    # The rows the operator was never shown are nonetheless there, and the
    # message has to be readable as saying so.
    assert _catalog_rows(fresh_reader)
    assert "committed" in err.lower()
    assert out.strip() == ""


def test_the_help_and_the_docstring_document_the_post_commit_report_exit(monkeypatch):
    """B1c verify F3's other half: an exit code an operator cannot read about is
    an undocumented number in a wrapper script.
    """
    from app.domains.geo.rainfall import detector_cli

    help_text = detector_cli.build_parser().format_help()
    assert "report_render_failed" in help_text
    assert str(detector_cli.EXIT_REPORT_FAILED) in help_text
    doc = detector_cli.__doc__ or ""
    assert "report_render_failed" in doc


# ===========================================================================
# 3.5 -- InsufficientClimatologyError: the fabricated absence that never lands
# ===========================================================================


def test_a_record_below_the_sample_floor_stops_labelled_rather_than_not_firing(
    db, cli_sessions, fresh_reader, monkeypatch, capsys
):
    """3.5: a short record aborts with a NAMED reason.

    The two shapes this test refuses, explicitly:

    * a silent non-fire — an empty catalog and a catalog that could not be
      computed are different facts, and in a permanent table the first one is a
      fabricated absence;
    * a `TypeError` comparing `None` to a float, which is what an unguarded
      `absolute_window_percentile` answer produces.
    """
    asset = "detector-cli-short-record"
    _persist_baseline_days(db, asset=asset, days=_full_span_series(length=500))
    control = _plant_control_row(db, asset=asset)

    code, out, err = _run(monkeypatch, capsys, cli_sessions, asset=asset)

    assert code == 1
    assert "reason=insufficient_climatology" in err
    assert "TypeError" not in err
    assert [row.event_key for row in _catalog_rows(fresh_reader)] == [control]
    assert out.strip() == ""


# ===========================================================================
# 3.6 -- the gold anchors: surfaced, one verdict each, never dropped
# ===========================================================================


def test_the_three_gold_anchors_are_the_ones_the_curated_seed_holds():
    """3.6 / B1c verify F7: the anchor set IS the seed's, keys AND dates.

    Written as a literal, this test was a THIRD copy of the same three dates
    (the seed's `ANCHORS`, the CLI's `GOLD_ANCHORS`, and itself), which is the
    shape where a curated date moves in the seed and the validation gate keeps
    checking the old one -- silently reporting "no detectado" for an anchor the
    catalog holds on a different day. Bound to the seed instead, so a curated
    date can only move in one place.
    """
    from app.db.migrations.versions.lluvia_ext_002_seed_curated_flood_anchors import ANCHORS
    from app.domains.geo.rainfall import detector_cli

    seeded = {key: date.fromisoformat(day) for key, day, _payload in ANCHORS}

    assert dict(detector_cli.GOLD_ANCHORS) == seeded


def test_every_anchor_gets_an_explicit_verdict_even_when_none_is_detected():
    """3.6: non-detection is a SURFACED finding, never a silent drop.

    The verdict map is keyed by every anchor unconditionally. A comprehension
    that only recorded the anchors it found would report an all-clear run and a
    run that detected nothing identically.
    """
    from app.domains.geo.rainfall import detector_cli

    verdicts = detector_cli.anchor_verdicts(())

    assert set(verdicts) == set(detector_cli.GOLD_ANCHORS)
    assert all(verdict["detected"] is False for verdict in verdicts.values())
    assert all(verdict["windows"] == () for verdict in verdicts.values())


def test_a_detected_span_covering_an_anchor_reports_its_tier_and_windows():
    """3.6: a detection carries the evidence, so "detected" can be checked.

    Inclusive at BOTH ends — an anchor on an event's last day is inside it, and
    a half-open comparison would report the 2017 anchor as unconfirmed for the
    one span most likely to contain it.
    """
    from app.domains.geo.rainfall import detector_cli
    from app.domains.geo.rainfall.detector import DetectedEvent, FiredWindow

    event = DetectedEvent(
        tier="alta",
        start_date=date(2017, 2, 18),
        end_date=date(2017, 2, 20),
        peak_date=date(2017, 2, 20),
        max_percentile=99.1,
        fired_windows=(
            FiredWindow(days=3, peak_end=date(2017, 2, 20), peak_total_mm=90.0, percentile=99.1),
        ),
        climatology_span_start=date(1991, 1, 1),
        climatology_span_end=date(2026, 1, 1),
    )

    verdicts = detector_cli.anchor_verdicts((event,))

    assert verdicts["feb_2017"]["detected"] is True
    assert verdicts["feb_2017"]["tier"] == "alta"
    assert verdicts["feb_2017"]["windows"] == ("d3",)
    assert verdicts["feb_2017"]["span"] == (date(2017, 2, 18), date(2017, 2, 20))
    assert verdicts["mar_2015"]["detected"] is False
    assert verdicts["sep_2025"]["detected"] is False


def test_the_report_names_every_anchor_with_its_verdict(db, cli_sessions, monkeypatch, capsys):
    """3.6: the operator reads the verdicts on the run's own output.

    The seeded record stops in 2001, so all three anchors are legitimately
    unconfirmed here — and all three are still PRINTED. That is the property:
    an unconfirmed anchor is visible, not absent.
    """
    asset = "detector-cli-anchor-report"
    _persist_baseline_days(db, asset=asset, days=_full_span_series())
    db.flush()

    code, out, err = _run(monkeypatch, capsys, cli_sessions, asset=asset)

    assert code == 0, err
    for anchor in ("mar_2015", "feb_2017", "sep_2025"):
        assert anchor in out
    assert out.count("no detectado") == 3
    # No curated row was seeded for this scope, and the section SAYS so: three
    # "no detectado" lines look identical whether the seed ran or never did.
    assert "seed ausente" in out


def test_the_anchor_section_stops_saying_the_seed_is_absent_once_it_is_there(
    db, cli_sessions, monkeypatch, capsys
):
    """3.6 / B1c verify S12: the note is a MEASUREMENT of the catalog.

    A note that printed unconditionally would be one more constant. Same run,
    same anchors, one curated row planted in the run's own scope -- and the
    header changes.
    """
    asset = "detector-cli-anchor-report-seeded"
    _persist_baseline_days(db, asset=asset, days=_full_span_series())
    db.execute(
        text(
            "INSERT INTO rainfall_extreme_event "
            "(id, source_id, scope_kind, scope_id, scope_version, detector_revision, "
            " provenance, event_key, start_date, end_date, curated_payload) "
            "VALUES (gen_random_uuid(), :source_id, 'provider_asset', :asset, :version, "
            " 'curated', 'curated', 'feb_2017', DATE '2017-02-20', DATE '2017-02-20', "
            " '{}'::json)"
        ),
        {"source_id": SOURCE_ID, "asset": asset, "version": BASELINE_ASSET_VERSION},
    )
    db.flush()

    code, out, err = _run(monkeypatch, capsys, cli_sessions, asset=asset)

    assert code == 0, err
    assert "gold anchors:" in out
    assert "seed ausente" not in out


# ===========================================================================
# 3.7 -- span-edge clipping is disclosed, and a wider span appends
# ===========================================================================


def test_an_event_reaching_the_frozen_span_end_is_recorded_clipped_and_disclosed(
    db, cli_sessions, fresh_reader, monkeypatch, capsys
):
    """3.7 / D7: the row ends on 2025-12-31 and the run SAYS it may be cut.

    `clipped_at_span_end` is derived (`end_date == span_end - 1 day`), never
    stored: the same event under a wider span in a later revision is a different
    row, and a stored flag would go stale the moment the span moved. So the
    disclosure has to reach the operator through the run's report.
    """
    asset = "detector-cli-span-edge"
    first = date(2025, 12, 31) - timedelta(days=SEEDED_DAYS - 1)
    series = dict(_full_span_series(first_day=first))
    for offset in range(3):
        series[date(2025, 12, 31) - timedelta(days=offset)] = 300.0
    _persist_baseline_days(db, asset=asset, days=sorted(series.items()))
    db.flush()

    code, out, err = _run(monkeypatch, capsys, cli_sessions, asset=asset)

    assert code == 0, err
    ends = {row.event_key: row.end_date for row in _catalog_rows(fresh_reader)}
    clipped = [key for key, end in ends.items() if end == date(2025, 12, 31)]
    assert clipped, "the fixture must produce an event reaching the span's last day"
    assert "clipped_at_span_end" in out
    for key in clipped:
        assert key in out


def test_a_wider_span_at_a_new_revision_appends_and_keeps_the_clipped_row(db):
    """3.7's second half / spec R2 S2: append-only across a span move.

    Not run through the CLI: the CLI is full-span-FROZEN by design (D6), so a
    wider span is a revision bump, which is a constants change plus a digest
    bump — an audited move, not a flag. What must hold is the append: both rows
    are retained, each under its own sealed span.
    """
    from app.domains.geo.rainfall.detector import DETECTOR_REVISION, detect_events
    from app.domains.geo.rainfall.models import RainfallExtremeEvent
    from app.domains.geo.rainfall.repository import persist_events

    asset = "detector-cli-wider-span"
    first = date(2025, 12, 31) - timedelta(days=SEEDED_DAYS - 1)
    series = dict(_full_span_series(first_day=first))
    for offset in range(3):
        series[date(2025, 12, 31) - timedelta(days=offset)] = 300.0
    # The days the frozen span cannot see, which complete the same event.
    for offset in range(1, 4):
        series[date(2026, 1, 1) + timedelta(days=offset - 1)] = 300.0
    _persist_baseline_days(db, asset=asset, days=sorted(series.items()))
    db.flush()

    scope = {
        "source_id": SOURCE_ID,
        "scope_kind": "provider_asset",
        "scope_id": asset,
        "scope_version": BASELINE_ASSET_VERSION,
    }
    narrow = _read_daily(db, asset)
    narrow_events = detect_events(daily=narrow, tier="extrema")
    persist_events(db, **scope, events=narrow_events)
    db.flush()

    wide = [entry for entry in sorted(series.items())]
    wide_events = detect_events(
        daily=wide,
        tier="extrema",
        climatology_span=(first, date(2027, 1, 1)),
    )
    persist_events(
        db,
        **scope,
        events=wide_events,
        detector_revision="rainfall-extreme-v2-test",
    )
    db.flush()

    revisions = {row.detector_revision for row in db.query(RainfallExtremeEvent).all()}
    assert revisions == {DETECTOR_REVISION, "rainfall-extreme-v2-test"}
    clipped = [
        row for row in db.query(RainfallExtremeEvent).all() if row.end_date == date(2025, 12, 31)
    ]
    assert clipped, "the frozen-span generation keeps its clipped row"


# ===========================================================================
# 3.9 -- the calibration report is a MEASUREMENT, not a printed constant
# ===========================================================================


def test_the_calibration_report_counts_what_the_detector_actually_produced(
    db, cli_sessions, fresh_reader, monkeypatch, capsys
):
    """3.9: every number in the report is recomputed here and compared.

    The failure this pins is a report that prints the design's MODELLED ~30 /
    ~150 — or any other constant — while the run produced something else. The
    whole point of the task is that D4's clustering factor is a model and this
    is the measurement, so a report that cannot disagree with the model is
    worthless as a gate.

    NOTE, recorded rather than blurred: the numbers this asserts are the numbers
    of the SEEDED 4,000-day record, not of the real 12,784-day zone asset. The
    real calibration is a box run; this test proves the harness measures.
    """
    from app.domains.geo.rainfall import detector_cli
    from app.domains.geo.rainfall.detector import (
        TIER_PERCENTILES,
        count_firing_end_days,
        detect_events,
    )

    asset = "detector-cli-calibration"
    _persist_baseline_days(db, asset=asset, days=_full_span_series())
    db.flush()

    code, out, err = _run(monkeypatch, capsys, cli_sessions, asset=asset)
    assert code == 0, err

    daily = _read_daily(db, asset)
    report = detector_cli.calibration_report(daily)

    assert report["baseline_days"] == len(daily) == SEEDED_DAYS
    for tier in TIER_PERCENTILES:
        expected_events = len(detect_events(daily=daily, tier=tier))
        assert report["events_after_merge"][tier] == expected_events
        assert report["firing_end_days"][tier] == count_firing_end_days(daily=daily, tier=tier)
        # The firing counts are the PRE-merge half of the pair, so they can
        # never be below the post-merge event count: D1's merge only ever joins
        # end-days into fewer spans. A report that inverted the two, or read one
        # off the other, breaks here.
        assert sum(report["firing_end_days"][tier].values()) >= expected_events > 0
        # And the printed run says the same thing the harness measured.
        assert f"{tier}: {expected_events}" in out

    assert report["events_after_merge"] != {"extrema": 30, "alta": 150}


def test_the_report_is_recomputed_per_run_rather_than_read_off_the_row_count(
    db, cli_sessions, monkeypatch, capsys
):
    """3.9's mutant surface, made reachable: two DIFFERENT records must report
    two different measurements.

    A report that printed a constant, or that echoed back the design's model,
    would be identical for both.
    """
    from app.domains.geo.rainfall import detector_cli

    quiet = "detector-cli-calibration-quiet"
    _persist_baseline_days(
        db,
        asset=quiet,
        days=[
            (SPAN_FIRST_DAY + timedelta(days=offset), 1.0 + (offset % 5))
            for offset in range(SEEDED_DAYS)
        ],
    )
    loud = "detector-cli-calibration-loud"
    _persist_baseline_days(db, asset=loud, days=_full_span_series())
    db.flush()

    quiet_report = detector_cli.calibration_report(_read_daily(db, quiet))
    loud_report = detector_cli.calibration_report(_read_daily(db, loud))

    assert quiet_report["events_after_merge"] != loud_report["events_after_merge"]
    assert sum(loud_report["events_after_merge"].values()) > sum(
        quiet_report["events_after_merge"].values()
    )
    # Both halves of the pair, not just the merged one: a constant hidden in
    # `count_firing_end_days` would leave the firing table identical for two
    # records that plainly are not, and the merged counts alone would not see
    # it.
    assert quiet_report["firing_end_days"] != loud_report["firing_end_days"]
