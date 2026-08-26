"""The persisted extreme-event catalog: the table, the append-only guard, the
two migrations and the LOUD writer (lluvia-eventos-extremos, slice B1b).

Everything here is REAL Postgres. The pure detector suite lives next door in
`test_rainfall_detector.py` (B1a) and never touches a `Session`; this file is
the other half — nothing in it is a claim about arithmetic, everything is a
claim about what the database accepts, refuses, and keeps.

Three properties carry the slice, and each one is a constraint that would
STOP CONSTRAINING silently if it were written the obvious way:

* the identity unique index is PARTIAL (`WHERE provenance = 'detected'`), so
  it is a statement about detected identity only — and, MEASURED here, no
  behavioural test can tell it apart from a full one, because `tier` is NULL
  on every curated row and `NULL != NULL` in a unique index either way (D2,
  with the correction recorded on the two tests that pin it);
* `persist_events` RAISES on a conflicting row rather than `ON CONFLICT DO
  NOTHING`, because DO NOTHING converts every disagreement between two
  computations of one identity into permanent silence (D7);
* append-only is enforced at FLUSH by `_IMMUTABLE_TYPES`, not by grepping
  source text for `update(` — a source-text guard matches
  `with_for_update(` on day one and never sees an attribute mutation (D13).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION
from app.domains.geo.rainfall.ports import SourceInterval
from app.domains.geo.rainfall.repository import persist_intervals

SOURCE_ID = "chirps-v3-final"


def _persist_baseline_days(db, *, asset, days, source_id=SOURCE_ID, revision="v3-final"):
    """One persisted daily row per ``(date, value)`` pair under the baseline key.

    Mirrors `test_rainfall_baseline.py`'s helper of the same name rather than
    importing it: this slice's rollback boundary is supposed to be this file
    plus the model, the repository and two migrations, and a cross-file import
    of another suite's private helper quietly widens it.
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


# ===========================================================================
# 2.1 / 2.3 -- D14: the span read widens BY PARAMETER, and only by parameter
# ===========================================================================


def test_the_default_baseline_read_still_stops_at_2020_12_31(db):
    """2.1, a CHARACTERIZATION PIN (it passes on first run; its RED is mutant
    m6, `span_start`/`span_end` defaulting to the DETECTOR span).

    D14 widens this read for the detector and for nothing else. The card's
    bounds are load-bearing — the archived predecessor's D2 proves it: the
    2021-2025 backfill landed under the SAME provider-asset key, so a default
    that moved would silently widen the ranked distribution past the period
    every served envelope keeps naming "1991-2020". Every current caller must
    be byte-unchanged, which is exactly what a no-argument call asserts.
    """
    from app.domains.geo.rainfall.repository import (
        BASELINE_SPAN_END,
        BASELINE_SPAN_START,
        baseline_daily_values,
    )

    assert BASELINE_SPAN_START == datetime(1991, 1, 1, tzinfo=UTC)
    assert BASELINE_SPAN_END == datetime(2021, 1, 1, tzinfo=UTC)

    asset = "catalog-default-span-unchanged"
    _persist_baseline_days(
        db,
        asset=asset,
        days=[
            (date(1990, 12, 31), 111.0),  # below the start
            (date(1991, 1, 1), 1.0),  # the first admitted day
            (date(2020, 12, 31), 2.0),  # the last admitted day (`<`, not `<=`)
            (date(2021, 1, 1), 222.0),  # excluded by the default bound
            (date(2025, 12, 31), 333.0),  # the detector span's last day
        ],
    )

    assert baseline_daily_values(db, source_id=SOURCE_ID, asset=asset) == (
        (date(1991, 1, 1), 1.0),
        (date(2020, 12, 31), 2.0),
    )


def test_the_detector_span_reads_2021_2025_under_the_same_key_and_guards(db):
    """2.3: called with the detector span the read returns the rows the default
    bound excludes — same provider-asset key, same supersession anti-join, same
    strict duplicate guard. The boundary is asserted in both directions:
    2025-12-31 is IN and 2026-01-01 is OUT (the end stays EXCLUSIVE).
    """
    from app.domains.geo.rainfall.detector import (
        DETECTOR_CLIMATOLOGY_END,
        DETECTOR_CLIMATOLOGY_START,
    )
    from app.domains.geo.rainfall.repository import baseline_daily_values

    asset = "catalog-detector-span"
    _persist_baseline_days(
        db,
        asset=asset,
        days=[
            (date(1990, 12, 31), 111.0),
            (date(1991, 1, 1), 1.0),
            (date(2020, 12, 31), 2.0),
            (date(2021, 1, 1), 3.0),
            (date(2025, 12, 31), 4.0),
            (date(2026, 1, 1), 222.0),
        ],
    )
    # A correction inside the widened part of the span: the anti-join has to
    # serve 9.0 once, not 3.0 and not both.
    assert (
        _persist_baseline_days(db, asset=asset, days=[(date(2021, 1, 1), 9.0)])["superseded"] == 1
    )

    widened = baseline_daily_values(
        db,
        source_id=SOURCE_ID,
        asset=asset,
        span_start=DETECTOR_CLIMATOLOGY_START,
        span_end=DETECTOR_CLIMATOLOGY_END,
    )

    assert widened == (
        (date(1991, 1, 1), 1.0),
        (date(2020, 12, 31), 2.0),
        (date(2021, 1, 1), 9.0),
        (date(2025, 12, 31), 4.0),
    )


def test_the_widened_span_keeps_the_strict_duplicate_guard(db):
    """2.3's second half: the guard `baseline_cumulatives` STRUCTURALLY cannot
    see (its windows stop at each year's cutoff) is exactly the guard the
    detector span depends on. A duplicated slot inflates a window total while
    leaving the window looking complete, so the rank moves and nothing
    discloses it — and a catalog row is permanent.
    """
    from app.domains.geo.rainfall.detector import (
        DETECTOR_CLIMATOLOGY_END,
        DETECTOR_CLIMATOLOGY_START,
    )
    from app.domains.geo.rainfall.repository import (
        DuplicateBaselineSlotError,
        baseline_daily_values,
    )

    asset = "catalog-detector-span-duplicate"
    _persist_baseline_days(db, asset=asset, days=[(date(2023, 5, 4), 5.0)])
    # A second NON-superseded row for the same slot, planted under a foreign
    # revision family so `persist_intervals`' correction path is not what
    # writes it (that path supersedes, which is the case the anti-join covers).
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
            "start": datetime(2023, 5, 4, tzinfo=UTC),
            "end": datetime(2023, 5, 5, tzinfo=UTC),
        },
    )

    with pytest.raises(DuplicateBaselineSlotError):
        baseline_daily_values(
            db,
            source_id=SOURCE_ID,
            asset=asset,
            span_start=DETECTOR_CLIMATOLOGY_START,
            span_end=DETECTOR_CLIMATOLOGY_END,
        )


# ===========================================================================
# 2.4 - 2.7 -- D2/D8/D13: what the table accepts, refuses, and keeps
# ===========================================================================

SCOPE = {
    "source_id": SOURCE_ID,
    "scope_kind": "provider_asset",
    "scope_id": "zona_cc_ampliada",
    "scope_version": BASELINE_ASSET_VERSION,
}

#: The sealed block a detected row carries. A literal here rather than a call
#: into `detector.DETECTION_CONSTANTS`: these tests are about the SCHEMA, and a
#: schema test that imports the value under test cannot fail when that value
#: moves. `test_rainfall_detector.py` owns the digest lockstep.
SEALED = {
    "climatology_span_start": "1991-01-01",
    "climatology_span_end": "2026-01-01",
    "window_lengths": [1, 3, 7],
    "gap_days": 1,
    "min_window_samples": 3650,
    "tier_percentiles": {"extrema": 99.75, "alta": 98.8},
    "constants_digest": "fixture-digest",
}


def _detected(**overrides):
    """A complete detected row, i.e. one that satisfies `ck_detected_complete`."""
    from app.domains.geo.rainfall.models import RainfallExtremeEvent

    values = {
        **SCOPE,
        "detector_revision": "rev-under-test",
        "provenance": "detected",
        "event_key": "ext_20150312",
        "tier": "extrema",
        "start_date": date(2015, 3, 12),
        "end_date": date(2015, 3, 15),
        "peak_date": date(2015, 3, 14),
        "max_percentile": 99.81,
        "fired_windows": {
            "d3": {"peak_end": "2015-03-14", "peak_total_mm": 180.0, "percentile": 99.81}
        },
        "sealed_detection_params": SEALED,
        "climatology_span_start": date(1991, 1, 1),
        "climatology_span_end": date(2026, 1, 1),
    }
    values.update(overrides)
    return RainfallExtremeEvent(**values)


def _curated(**overrides):
    """A curated anchor, i.e. one that satisfies `ck_curated_unranked`."""
    from app.domains.geo.rainfall.models import RainfallExtremeEvent

    values = {
        **SCOPE,
        "detector_revision": "curated",
        "provenance": "curated",
        "event_key": "mar_2015",
        "tier": None,
        "start_date": date(2015, 3, 15),
        "end_date": date(2015, 3, 15),
        "curated_payload": {"name": "Inundacion Marzo 2015", "severity": "alta"},
    }
    values.update(overrides)
    return RainfallExtremeEvent(**values)


@contextmanager
def _savepoint(db):
    """Contain an expected constraint violation.

    A refused flush poisons the ambient transaction, so every "the database
    says no" assertion runs inside a SAVEPOINT the assertion itself rolls back.
    Without it the FIRST refusal in a test would make every later statement
    fail with `InFailedSqlTransaction` — an error that looks like a second
    finding and is really the first one's shadow.
    """
    nested = db.begin_nested()
    try:
        yield
    finally:
        nested.rollback()


def test_the_identity_index_admits_curated_rows_and_refuses_a_second_detected_one(db):
    """2.4 (D2), behaviour — and an honest statement of what behaviour can and
    cannot see here.

    Two curated rows at one identity are accepted; two detected rows at one
    identity are refused. Both halves are asserted because the pair is the
    served rule.

    **MEASURED, and it corrects the design's stated rationale:** these two
    halves hold IDENTICALLY under a plain (non-partial) unique index, so this
    test does NOT distinguish partial from full — mutating the `WHERE` clause
    away leaves it green (recorded in the B1b mutant table as m2a). The reason
    is the one the design gives and then under-reads: `tier` is NULL on every
    curated row and `NULL != NULL` in a Postgres unique index, so a full index
    admits those rows anyway, and `ck_curated_unranked` makes a non-NULL
    curated `tier` unrepresentable in the first place. The `WHERE` clause is
    therefore an INTENT and SCOPE statement (the index covers detected identity
    only), not a behavioural difference — which is precisely why it needs the
    separate structural pin below rather than a behavioural test that would
    quietly agree with either schema.
    """
    db.add(_curated(event_key="mar_2015"))
    db.add(_curated(event_key="mar_2015_again"))
    db.flush()

    db.add(_detected())
    db.flush()
    with pytest.raises(IntegrityError), _savepoint(db):
        db.add(_detected(event_key="ext_20150312_again"))
        db.flush()


def test_the_identity_index_is_partial_on_detected_rows(db):
    """2.4 (D2), the STRUCTURE, read back from Postgres itself.

    Asserted against `pg_indexes.indexdef` — the database's own normalized
    rendering, not the source text that produced it — because the test above
    proves a behavioural assertion cannot tell the two schemas apart. Without
    this pin the ratified partial index could be widened in both the model and
    the migration with the whole suite staying green: the constraint would keep
    existing, keep being named in the design, and index every curated row it
    was explicitly scoped to leave alone.
    """
    definition = db.execute(
        text(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_rainfall_extreme_event_identity'"
        )
    ).scalar_one()

    assert "CREATE UNIQUE INDEX" in definition
    assert " WHERE " in definition, f"the identity index is not partial at all: {definition}"
    # Matched on the predicate's PARTS rather than on one exact rendering:
    # Postgres prints the `varchar` comparison as `((provenance)::text =
    # 'detected'::text)`, and pinning that spelling would turn a column-type
    # change into a puzzling failure in a test about scope.
    predicate = definition.split(" WHERE ", 1)[1]
    assert "provenance" in predicate and "'detected'" in predicate, predicate


def test_tier_is_in_the_identity_key_so_both_tiers_persist_at_one_start_date(db):
    """2.5 (D2): the proposal's key omitted `tier` and collided on the very
    first real run. Detection runs once per tier and an `alta` span is a
    SUPERSET of the `extrema` spans it contains, so one `start_date` routinely
    hosts one row of each — the ratified behaviour (spec R1 S2), not an edge.
    """
    db.add(_detected(tier="extrema", event_key="ext_20150312"))
    db.add(_detected(tier="alta", event_key="alt_20150312", max_percentile=99.1))
    db.flush()

    from app.domains.geo.rainfall.models import RainfallExtremeEvent

    tiers = sorted(
        row.tier
        for row in db.query(RainfallExtremeEvent).filter_by(start_date=date(2015, 3, 12)).all()
    )
    assert tiers == ["alta", "extrema"]


def test_a_second_row_reusing_one_event_key_is_refused_even_at_a_new_identity(db):
    """2.4 (D2): `uq_rainfall_extreme_event_key`, exercised on the collision it
    exists to prevent rather than on the one the identity index already covers.

    `event_key` is the SERVED id — what the imagery bridge resolves a request
    through — so two rows wearing one key inside a generation make that lookup
    ambiguous, and an append-only table cannot repair the ambiguity later. The
    distinguishing case is a DIFFERENT identity reusing a key: `tier` differs
    here, so the partial identity index is satisfied and lets both rows past.
    Only the `event_key` unique refuses, which is why this test asserts the
    constraint by NAME (F-10's pattern) — an unnamed `IntegrityError` here
    would be indistinguishable from the identity index doing the work, and the
    key unique could then be dropped with the suite staying green.
    """
    db.add(_detected(tier="extrema", event_key="ext_20150312"))
    db.flush()

    with pytest.raises(IntegrityError) as raised, _savepoint(db):
        db.add(_detected(tier="alta", event_key="ext_20150312", max_percentile=99.1))
        db.flush()
    _assert_refused_by(raised, "uq_rainfall_extreme_event_key")


def test_the_serving_index_exists_for_the_generation_ordered_read(db):
    """2.4 (D12), STRUCTURE, read back from Postgres.

    The serving read is "one generation, optionally one tier, newest first", and
    an index is a PERFORMANCE contract: dropping it changes no result, so no
    behavioural test in this file can notice. Pinned for exactly the reason the
    partial identity index is pinned — the difference is that here even a
    sequential scan returns the right rows, so without this the index could
    vanish from both the model and the migration and the only symptom would be
    a slow serving endpoint in production.
    """
    definition = db.execute(
        text(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_rainfall_extreme_event_serving'"
        )
    ).scalar_one()

    # Matched on the columns and the ordering, not on one exact rendering: see
    # `test_the_identity_index_is_partial_on_detected_rows` for why pinning
    # Postgres' spelling turns a column-type change into a puzzling failure.
    assert "detector_revision" in definition, definition
    assert "tier" in definition, definition
    assert "start_date DESC" in definition, f"the newest-first ordering is gone: {definition}"


def test_a_persisted_catalog_row_refuses_mutation_and_deletion_at_flush(db):
    """2.7 (D13): append-only enforced at RUNTIME.

    Asserted on the FLUSH, not on a grep. The rejected r1 guard searched module
    source for `update(`, which matched the pre-existing `with_for_update(` in
    `repository.py` on day one and never saw the real hazard: ORM attribute
    mutation, which never spells `update(` at all.
    """
    row = _detected()
    db.add(row)
    db.flush()

    with pytest.raises(ValueError, match="append-only"), _savepoint(db):
        row.max_percentile = 42.0
        db.flush()

    with pytest.raises(ValueError, match="append-only"), _savepoint(db):
        db.delete(row)
        db.flush()


def _assert_refused_by(raised, constraint):
    """ "The database said no" sharpened into "THIS constraint said no".

    `psycopg2` exposes the offending constraint on the driver error's
    `diag`, and without reading it a refusal test passes on ANY
    `IntegrityError` — including one raised by a constraint the case was not
    written about (a NOT NULL, the unique index, a leftover FK). That is how a
    parametrization keeps reporting seven green cases while the CHECK it names
    no longer exists: something else refuses the row and the test cannot tell
    the difference.
    """
    name = raised.value.orig.diag.constraint_name
    assert name == constraint, f"refused by {name!r}, expected {constraint!r}: {raised.value}"


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        ("detected row with no tier", {"tier": None}),
        ("detected row with no max_percentile", {"max_percentile": None}),
        ("detected row with no fired_windows", {"fired_windows": None}),
        ("detected row with no sealed params", {"sealed_detection_params": None}),
        ("detected row with no peak_date", {"peak_date": None}),
        ("detected row with no climatology span start", {"climatology_span_start": None}),
        # The span is half-open, so its two ends are two separate obligations:
        # a row carrying only a start describes no period at all, and
        # `clipped_at_span_end` — derived, never stored (D8) — is a function of
        # the END. Asserted rather than assumed to follow from the start case.
        ("detected row with no climatology span end", {"climatology_span_end": None}),
        ("detected row carrying a curated payload", {"curated_payload": {"name": "x"}}),
    ],
)
def test_ck_detected_complete_refuses_a_half_ranked_detected_row(db, label, overrides):
    """2.6 (D8): a detected row without its evidence is a claim with nothing
    behind it. The CHECK is provenance-CONDITIONAL, so this refusal cannot be
    expressed as plain NOT NULL columns — those would make the curated seed
    unsatisfiable, and spec R6 forbids fabricating a statistic to satisfy it.
    """
    with pytest.raises(IntegrityError) as raised, _savepoint(db):
        db.add(_detected(**overrides))
        db.flush()
    _assert_refused_by(raised, "ck_detected_complete")


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        ("curated row carrying a tier", {"tier": "alta"}),
        ("curated row carrying a percentile", {"max_percentile": 99.9}),
        ("curated row carrying fired windows", {"fired_windows": {"d1": {}}}),
        ("curated row carrying sealed params", {"sealed_detection_params": SEALED}),
        ("curated row carrying a peak date", {"peak_date": date(2015, 3, 15)}),
        (
            "curated row carrying a climatology span start",
            {"climatology_span_start": date(1991, 1, 1)},
        ),
        # Both ends again, and for the sharper reason on this side: a curated
        # anchor was never ranked against ANY climatology, so a span end on one
        # is an invented provenance for a number that does not exist.
        ("curated row carrying a climatology span end", {"climatology_span_end": date(2026, 1, 1)}),
        ("curated row with no payload at all", {"curated_payload": None}),
    ],
)
def test_ck_curated_unranked_refuses_a_curated_row_wearing_statistics(db, label, overrides):
    """2.6 (D8, spec R6): the other half of the conditional pair. A curated
    anchor was never ranked, so any statistic on it is invented — and an
    invented statistic in an append-only catalog is permanent.
    """
    with pytest.raises(IntegrityError) as raised, _savepoint(db):
        db.add(_curated(**overrides))
        db.flush()
    _assert_refused_by(raised, "ck_curated_unranked")


@pytest.mark.parametrize(
    ("label", "factory_overrides", "constraint"),
    [
        (
            "curated provenance without the revision sentinel",
            ("curated", {"detector_revision": "rev-under-test"}),
            "ck_curated_revision_sentinel",
        ),
        (
            "detected provenance wearing the curated sentinel",
            ("detected", {"detector_revision": "curated"}),
            "ck_curated_revision_sentinel",
        ),
        (
            "a tier outside the ratified domain",
            ("detected", {"tier": "catastrofica"}),
            "ck_tier_domain",
        ),
        (
            "a provenance outside the domain",
            ("detected", {"provenance": "guessed"}),
            "ck_provenance_domain",
        ),
        (
            "end_date before start_date",
            ("detected", {"end_date": date(2015, 3, 11)}),
            "ck_dates_ordered",
        ),
        (
            "peak_date before the span",
            ("detected", {"peak_date": date(2015, 3, 1)}),
            "ck_dates_ordered",
        ),
        (
            "peak_date after the span",
            ("detected", {"peak_date": date(2015, 3, 20)}),
            "ck_dates_ordered",
        ),
    ],
)
def test_the_domain_and_ordering_checks_refuse_an_uninterpretable_row(
    db, label, factory_overrides, constraint
):
    """2.6: `ck_curated_revision_sentinel`, `ck_tier_domain`,
    `ck_provenance_domain` and `ck_dates_ordered`.

    The sentinel pair is what makes "curated rows vanish on a revision bump"
    STRUCTURALLY impossible rather than policy-dependent, and it is a CHECK in
    BOTH directions: a detected row wearing `'curated'` would be swept up by
    every curated read for free.
    """
    provenance, overrides = factory_overrides
    factory = _detected if provenance == "detected" else _curated
    with pytest.raises(IntegrityError) as raised, _savepoint(db):
        db.add(factory(**overrides))
        db.flush()
    # Four DIFFERENT constraints are exercised here; without naming the one that
    # fired, every case would be satisfied by any of the other three, and three
    # of them could be dropped with this test still reporting seven passes.
    _assert_refused_by(raised, constraint)


# ===========================================================================
# 2.8 - 2.10 -- D7: the writer is LOUD
# ===========================================================================


def _event(**overrides):
    """A `DetectedEvent` the writer can be handed."""
    from app.domains.geo.rainfall.detector import DetectedEvent, FiredWindow

    values = {
        "tier": "extrema",
        "start_date": date(2015, 3, 12),
        "end_date": date(2015, 3, 15),
        "peak_date": date(2015, 3, 14),
        "max_percentile": 99.81,
        "fired_windows": (
            FiredWindow(days=3, peak_end=date(2015, 3, 14), peak_total_mm=180.0, percentile=99.81),
        ),
        "climatology_span_start": date(1991, 1, 1),
        "climatology_span_end": date(2026, 1, 1),
    }
    values.update(overrides)
    return DetectedEvent(**values)


@contextmanager
def _write_log(db):
    """Record every statement the ambient connection emits.

    A SPY that delegates -- the statements still reach real Postgres -- because
    "inserts, updates and deletes NOTHING" (spec R2 S1) is a claim about what
    the database was ASKED to do. A row-count comparison cannot make it: an
    `UPDATE` that rewrites a row in place, or a delete-then-reinsert, leaves the
    count identical and the catalog rewritten.
    """
    seen: list[str] = []

    def _record(_conn, _cursor, statement, _parameters, _context, _executemany):
        seen.append(statement)

    bind = db.get_bind()
    sa_event.listen(bind, "before_cursor_execute", _record)
    try:
        yield seen
    finally:
        sa_event.remove(bind, "before_cursor_execute", _record)


def _writes_touching_the_catalog(statements):
    return [
        statement
        for statement in statements
        if statement.lstrip()[:6].upper() in {"INSERT", "UPDATE", "DELETE"}
        and "rainfall_extreme_event" in statement
    ]


def _persist(db, events, **overrides):
    from app.domains.geo.rainfall.repository import persist_events

    kwargs = {**SCOPE, "events": events}
    kwargs.update(overrides)
    return persist_events(db, **kwargs)


def test_persist_events_inserts_when_no_row_holds_the_identity(db):
    """2.8(a): the plain case, plus the row's self-description.

    The sealed block travels ON THE ROW (D5) with its digest, so a reader can
    tell what parameters produced this statistic without finding, and trusting,
    the code that wrote it.
    """
    from app.domains.geo.rainfall.detector import (
        DETECTION_CONSTANTS,
        DETECTOR_CONSTANTS_DIGEST,
        DETECTOR_REVISION,
    )
    from app.domains.geo.rainfall.models import RainfallExtremeEvent

    assert _persist(db, [_event()]) == {"inserted": 1, "skipped": 0}
    db.flush()

    row = db.query(RainfallExtremeEvent).one()
    assert row.provenance == "detected"
    assert row.detector_revision == DETECTOR_REVISION
    assert row.event_key == "ext_20150312"
    assert row.tier == "extrema"
    assert row.start_date == date(2015, 3, 12)
    assert row.end_date == date(2015, 3, 15)
    assert row.peak_date == date(2015, 3, 14)
    assert row.max_percentile == pytest.approx(99.81)
    assert row.fired_windows == {
        "d3": {"peak_end": "2015-03-14", "peak_total_mm": 180.0, "percentile": 99.81}
    }
    assert row.climatology_span_start == date(1991, 1, 1)
    assert row.climatology_span_end == date(2026, 1, 1)
    assert row.sealed_detection_params["constants_digest"] == DETECTOR_CONSTANTS_DIGEST
    assert row.sealed_detection_params["gap_days"] == DETECTION_CONSTANTS["gap_days"]
    assert row.sealed_detection_params["tier_percentiles"] == dict(
        DETECTION_CONSTANTS["tier_percentiles"]
    )


def test_the_alta_tier_gets_its_own_event_key_prefix(db):
    """2.8(a), the other half of the served-id shape (D2): `ext_` / `alt_`.

    Both tiers share a `start_date` by design, so a single prefix would collide
    on `uq_rainfall_extreme_event_key` — the key the imagery bridge resolves an
    id through — the first time an `alta` span contained an `extrema` one.
    """
    from app.domains.geo.rainfall.models import RainfallExtremeEvent

    assert _persist(db, [_event(), _event(tier="alta", max_percentile=99.1)]) == {
        "inserted": 2,
        "skipped": 0,
    }
    db.flush()

    assert sorted(row.event_key for row in db.query(RainfallExtremeEvent).all()) == [
        "alt_20150312",
        "ext_20150312",
    ]


def test_a_second_identical_run_writes_absolutely_nothing(db):
    """2.8(b) / spec R2 S1: the property the whole slice exists to make true.

    Asserted on the STATEMENTS, not on `count(*)` — see `_write_log`.

    **`expire_all()` is the assertion, not tidiness.** The comparison this test
    exists to exercise is between a freshly computed payload and one that came
    BACK FROM POSTGRES — the tuple-to-list trip through the JSON codec is the
    whole reason `repository._jsonable` exists. Without the expiry the second
    `_persist` compares against whatever the identity map still holds, i.e.
    against the very Python object the first run built, and the round trip is
    never exercised at all. Measured, not reasoned about: with the row held by a
    strong reference, dropping the normalization from `seal_detection_params`
    leaves this test GREEN (recorded in the B1b mutant table as m-F1). It goes
    red today only because the session's identity map is WEAKLY referenced and
    CPython happens to collect the row after the flush — a pass that depends on
    refcount timing is not a pass. Expiring first makes the read deterministic
    and the mutant reliably lethal.
    """
    assert _persist(db, [_event()]) == {"inserted": 1, "skipped": 0}
    db.flush()
    db.expire_all()

    with _write_log(db) as statements:
        assert _persist(db, [_event()]) == {"inserted": 0, "skipped": 1}
        db.flush()

    assert _writes_touching_the_catalog(statements) == []


def test_a_row_differing_in_any_single_field_aborts_the_run_loudly(db):
    """2.8(c) / D7: the finding this slice was rejected once for missing.

    `ON CONFLICT DO NOTHING` passes a test that only checks "no duplicate rows",
    which is why that test is not this one. DO NOTHING converts every
    disagreement between two computations of ONE identity into silence and
    seals the first computation forever — in an append-only table, forever is
    literal. The row that disagrees must be NAMED, and the run must stop.

    Parametrized over one differing field at a time, because a comparison that
    only looks at the percentile is indistinguishable from a correct one until
    the day an end date moves.

    Covers every entry of `_COMPARED_FIELDS` that a caller can actually make
    diverge from here, which is all of them but two:

    * `sealed_detection_params` diverges through a different kwarg
      (`detection_constants`, independent of `detector_revision`) and has its
      own test below — it is the REAL-WORLD path, not a contrived one.
    * `event_key` is DEAD BY CONSTRUCTION and deliberately has no test. It is
      computed as `f"{prefix}_{start_date}"` from `tier` and `start_date`, and
      both of those are part of the identity the lookup selected on, so a row
      found at one identity can never carry a different key. A test would have
      to fabricate a row the writer cannot emit and would then assert on the
      fabrication rather than on the writer. It stays in `_COMPARED_FIELDS`
      because the comparison must not depend on that derivation staying true.
    """
    from app.domains.geo.rainfall.repository import CatalogDivergenceError

    assert _persist(db, [_event()]) == {"inserted": 1, "skipped": 0}
    db.flush()
    db.expire_all()

    for field, diverged in (
        ("max_percentile", _event(max_percentile=99.82)),
        ("end_date", _event(end_date=date(2015, 3, 16))),
        ("peak_date", _event(peak_date=date(2015, 3, 13))),
        ("climatology_span_start", _event(climatology_span_start=date(1990, 1, 1))),
        ("climatology_span_end", _event(climatology_span_end=date(2027, 1, 1))),
    ):
        with _write_log(db) as statements:
            with pytest.raises(CatalogDivergenceError) as raised, _savepoint(db):
                _persist(db, [diverged])
                db.flush()
        assert field in str(raised.value), (
            f"the divergence message must name the differing field ({field}): {raised.value}"
        )
        assert "ext_20150312" in str(raised.value), "and the identity it disagrees about"
        assert _writes_touching_the_catalog(statements) == [], (
            "a diverging run must abort, not write half a generation"
        )


def test_a_diverging_fired_windows_payload_is_a_divergence_too(db):
    """2.8(c), the JSON field specifically. It is the one whose comparison a
    naive implementation gets wrong for free: the value round-trips through
    Postgres as a plain `dict` of `list`s, so comparing the ORM object to the
    detector's tuple-shaped payload without normalizing declares every second
    run divergent — and a writer that cries wolf on every run gets its guard
    deleted, which is how the silence comes back.
    """
    from app.domains.geo.rainfall.detector import FiredWindow
    from app.domains.geo.rainfall.repository import CatalogDivergenceError

    _persist(db, [_event()])
    db.flush()

    diverged = _event(
        fired_windows=(
            FiredWindow(days=3, peak_end=date(2015, 3, 14), peak_total_mm=180.0, percentile=99.81),
            FiredWindow(days=7, peak_end=date(2015, 3, 15), peak_total_mm=260.0, percentile=99.2),
        )
    )
    with pytest.raises(CatalogDivergenceError, match="fired_windows"), _savepoint(db):
        _persist(db, [diverged])
        db.flush()


def test_constants_moved_without_a_revision_bump_is_a_divergence(db):
    """2.8(c), the `sealed_detection_params` half — and the one divergence path
    that is not contrived.

    `persist_events` takes `detector_revision` and `detection_constants` as
    INDEPENDENT keyword arguments. D5's lockstep is a discipline about editing
    the detector module, not a signature that makes the pair inseparable, so a
    caller can hand over bumped constants under the OLD revision — which is
    exactly what a constants edit that forgot its revision bump looks like from
    in here. The identity resolves to the existing row, the sealed block does
    not, and that is precisely the case `ON CONFLICT DO NOTHING` would bury:
    one revision string permanently serving two different tellings of the same
    weather, with the second one's parameters lost.
    """
    from app.domains.geo.rainfall.repository import CatalogDivergenceError

    assert _persist(db, [_event()]) == {"inserted": 1, "skipped": 0}
    db.flush()
    db.expire_all()

    moved = {**dict(SEALED), "gap_days": 2}
    moved.pop("constants_digest")
    with _write_log(db) as statements:
        with pytest.raises(CatalogDivergenceError) as raised, _savepoint(db):
            _persist(db, [_event()], detection_constants=moved)
            db.flush()

    assert "sealed_detection_params" in str(raised.value), str(raised.value)
    assert "ext_20150312" in str(raised.value), "and the identity it disagrees about"
    assert _writes_touching_the_catalog(statements) == []


def test_a_revision_bump_appends_and_leaves_the_previous_generation_readable(db):
    """2.9 / spec R2 S2: append, never rewrite.

    The curated half is asserted explicitly because it is the STRUCTURAL reason
    the sentinel exists rather than a NULL: curated rows live under
    `detector_revision = 'curated'`, so they are untouched by a bump instead of
    being retained by policy.
    """
    from app.domains.geo.rainfall.detector import DETECTOR_REVISION
    from app.domains.geo.rainfall.models import RainfallExtremeEvent

    db.add(_curated())
    _persist(db, [_event()])
    db.flush()

    bumped_constants = {**dict(SEALED), "tier_percentiles": {"extrema": 99.9, "alta": 99.0}}
    bumped_constants.pop("constants_digest")
    assert _persist(
        db,
        [_event(max_percentile=99.95)],
        detector_revision="rainfall-extreme-v2-test",
        detection_constants=bumped_constants,
    ) == {"inserted": 1, "skipped": 0}
    db.flush()

    rows = {row.detector_revision: row for row in db.query(RainfallExtremeEvent).all()}
    assert set(rows) == {DETECTOR_REVISION, "rainfall-extreme-v2-test", "curated"}
    # Each generation still reads under its OWN sealed parameters.
    assert rows[DETECTOR_REVISION].sealed_detection_params["tier_percentiles"] == {
        "extrema": 99.75,
        "alta": 98.8,
    }
    assert rows["rainfall-extreme-v2-test"].sealed_detection_params["tier_percentiles"] == {
        "extrema": 99.9,
        "alta": 99.0,
    }
    assert rows[DETECTOR_REVISION].max_percentile == pytest.approx(99.81)
    # The curated anchor survived the bump untouched, payload and all.
    assert rows["curated"].curated_payload["name"] == "Inundacion Marzo 2015"
    assert rows["curated"].tier is None


# ===========================================================================
# 2.11 / 2.12 -- the two migrations, replayed against real Postgres
#
# These run `alembic upgrade` against a THROWAWAY database, never against the
# shared `test_engine` one: that schema is built by `Base.metadata.create_all`
# and already holds `rainfall_extreme_event`, so `op.create_table` would
# collide on "relation already exists". The precedent, helpers and the reason
# are `tests/new/conocimiento/test_rag_migrations.py`'s.
#
# The distinction matters beyond plumbing: every OTHER test in this file
# exercises the schema the MODEL declares. Only these exercise the schema a
# DEPLOY actually gets, and the parity test below is what keeps the two from
# drifting into disagreement while each looks correct on its own.
# ===========================================================================

_CATALOG_HEAD = "lluvia_ext_002"
_CATALOG_BASE = "conocimiento_007"  # measured with `alembic heads` at apply (task 0.3)


@pytest.fixture
def catalog_migration_db(monkeypatch):
    """A fresh database stamped at this chain's parent + an Alembic Config."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    from app.config import settings
    from app.core.health import ALEMBIC_INI_PATH
    from tests.new.conocimiento.test_rag_migrations import (
        _create_throwaway_database,
        _drop_database,
    )

    fresh_url, dbname = _create_throwaway_database(settings.database_url)
    monkeypatch.setattr(settings, "database_url", fresh_url)

    cfg = Config(str(ALEMBIC_INI_PATH))
    # STAMPED at the parent rather than replayed from base: an unrelated
    # existing migration runs `CREATE EXTENSION pgrouting`, which the default
    # test image does not have. Stamping scopes the run to exactly this
    # slice's two revisions, which is what is under test.
    command.stamp(cfg, _CATALOG_BASE)
    engine = create_engine(fresh_url)

    yield cfg, engine

    engine.dispose()
    _drop_database(settings.database_url, dbname)


def _catalog_rows(engine):
    with engine.connect() as conn:
        return {
            row.event_key: row
            for row in conn.execute(text("SELECT * FROM rainfall_extreme_event ORDER BY event_key"))
        }


def test_the_migrations_create_the_table_and_seed_the_three_curated_anchors(
    catalog_migration_db,
):
    """2.11 / 2.12: the seed lands under the REAL CHECKs.

    This is r1's schema failure asserted rather than argued: r1 declared the
    statistics NOT NULL and then required this very migration to insert three
    rows that have none of them. The only ways to satisfy that schema were to
    invent numbers for a never-ranked event (spec R6 forbids it) or to fail the
    migration. So the assertion is not "the insert ran" but "the insert ran
    while every statistic stayed NULL".
    """
    from alembic import command

    cfg, engine = catalog_migration_db
    command.upgrade(cfg, _CATALOG_HEAD)

    rows = _catalog_rows(engine)
    assert sorted(rows) == ["feb_2017", "mar_2015", "sep_2025"]
    for row in rows.values():
        assert row.provenance == "curated"
        assert row.detector_revision == "curated"
        assert row.tier is None
        assert row.max_percentile is None
        assert row.fired_windows is None
        assert row.sealed_detection_params is None
        assert row.peak_date is None
        assert row.climatology_span_start is None
        assert row.climatology_span_end is None
        # A curated anchor is a single day: `end_date = start_date` (D8).
        assert row.end_date == row.start_date

    assert rows["mar_2015"].start_date == date(2015, 3, 15)
    assert rows["feb_2017"].start_date == date(2017, 2, 20)
    assert rows["sep_2025"].start_date == date(2025, 9, 5)

    assert rows["mar_2015"].curated_payload == {
        "name": "Inundacion Marzo 2015",
        "description": "Evento historico para revisar con Landsat 8/Landsat 7 y Sentinel-1",
        "severity": "alta",
        "sensor": "landsat8",
        "max_cloud": 80,
        "days_buffer": 30,
    }
    assert rows["feb_2017"].curated_payload == {
        "name": "Inundacion Febrero 2017",
        "description": "Gran inundacion que afecto Bell Ville y zona rural",
        "severity": "alta",
        "sensor": "sentinel2",
    }
    assert rows["sep_2025"].curated_payload == {
        "name": "Inundacion Septiembre 2025",
        "description": "Evento de anegamiento por lluvias intensas",
        "severity": "media",
    }


def test_mar_2015_carries_its_buffer_explicitly_not_by_epoch_coincidence(
    catalog_migration_db,
):
    """2.11: `days_buffer: 30` is STORED, and the other two anchors store none.

    Today `mar_2015`'s 30 days coincide with the epoch default the router
    applies to any pre-2020 event, and `test_imagery_dispatcher.py` asserts
    `30` — so an anchor that inherited the number instead of carrying it would
    make that existing assertion accidental, and it would silently become 15
    the day the epoch rule moved. The distinguishing assertion is the pair: 30
    present on `mar_2015`, ABSENT on the other two (they really do rely on the
    default, and pinning a value on them would invent one).
    """
    from alembic import command

    cfg, engine = catalog_migration_db
    command.upgrade(cfg, _CATALOG_HEAD)

    rows = _catalog_rows(engine)
    assert rows["mar_2015"].curated_payload["days_buffer"] == 30
    assert "days_buffer" not in rows["feb_2017"].curated_payload
    assert "days_buffer" not in rows["sep_2025"].curated_payload


# RETIRED IN B2b, as designed. `test_the_seeded_anchors_still_say_what_the
# _router_literal_says` compared the `lluvia_ext_002` seed against
# `router_gee_support.HISTORIC_FLOODS`, because while both existed a drift
# between them was a deployment answering the same question two ways. B2b
# deleted the literal, so the seed is now the ONLY source and there is nothing
# left for it to disagree with. Its successors: the seed's own content is
# pinned by `test_mar_2015_carries_its_buffer_explicitly_not_by_epoch_coincidence`,
# and what the endpoints do with those rows by
# `geo/rainfall/test_rainfall_catalog_serving.py` (the list) and
# `geo/rainfall/test_rainfall_catalog_bridge.py` (the imagery bridge).


def test_the_deployed_schema_refuses_what_the_model_schema_refuses(catalog_migration_db):
    """2.11/2.12: the CHECKs and the PARTIAL identity index exist in the schema
    a DEPLOY builds, not only in the one `create_all` builds from the model.

    Two sources of truth for one table is the shape this repository's own
    migration docstrings warn about; the migration cannot import the model (it
    is a frozen snapshot by construction), so the guard is that both schemas
    are exercised against real Postgres and compared below.
    """
    from alembic import command
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    cfg, engine = catalog_migration_db
    command.upgrade(cfg, _CATALOG_HEAD)

    detected = (
        "INSERT INTO rainfall_extreme_event (id, source_id, scope_kind, scope_id, "
        "scope_version, detector_revision, provenance, event_key, tier, start_date, "
        "end_date, peak_date, max_percentile, fired_windows, sealed_detection_params, "
        "climatology_span_start, climatology_span_end) VALUES "
        "(gen_random_uuid(), 'chirps-v3-final', 'provider_asset', 'zona_cc_ampliada', "
        "'v1', 'rev', 'detected', :event_key, :tier, DATE '2015-03-12', DATE '2015-03-15', "
        "DATE '2015-03-14', 99.8, '{}'::json, '{}'::json, DATE '1991-01-01', "
        "DATE '2026-01-01')"
    )
    with engine.begin() as conn:
        # `ck_curated_unranked`: a curated row wearing a statistic.
        with pytest.raises(SAIntegrityError):
            with conn.begin_nested():
                conn.execute(
                    text(
                        "INSERT INTO rainfall_extreme_event (id, source_id, scope_kind, "
                        "scope_id, scope_version, detector_revision, provenance, event_key, "
                        "start_date, end_date, max_percentile, curated_payload) VALUES "
                        "(gen_random_uuid(), 'chirps-v3-final', 'provider_asset', "
                        "'zona_cc_ampliada', 'v1', 'curated', 'curated', 'invented', "
                        "DATE '2015-03-15', DATE '2015-03-15', 99.9, '{}'::json)"
                    )
                )
        # The identity index is PARTIAL: two detected rows collide...
        conn.execute(text(detected), {"event_key": "ext_20150312", "tier": "extrema"})
        with pytest.raises(SAIntegrityError):
            with conn.begin_nested():
                conn.execute(text(detected), {"event_key": "ext_20150312_b", "tier": "extrema"})
        # ...while the seeded curated rows, all with a NULL tier, do not.
        conn.execute(
            text(
                "INSERT INTO rainfall_extreme_event (id, source_id, scope_kind, scope_id, "
                "scope_version, detector_revision, provenance, event_key, start_date, "
                "end_date, curated_payload) VALUES (gen_random_uuid(), 'chirps-v3-final', "
                "'provider_asset', 'zona_cc_ampliada', 'v1', 'curated', 'curated', "
                "'mar_2015_second', DATE '2015-03-15', DATE '2015-03-15', '{}'::json)"
            )
        )


def _schema_shape(connection):
    # COLUMNS FIRST, and they are not decoration. `pg_constraint` does not
    # expose NOT NULL at all in PG16 (it is an attribute flag, `attnotnull`, not
    # a catalogued constraint), so a parity check built only on constraints and
    # indexes cannot see a column that is nullable in the migration and NOT NULL
    # in the model — nor a renamed column, a `String(64)` that drifted to
    # `String(128)`, a type change, or a server default present on one side
    # only. The test this feeds is named "the same schema"; before this it
    # measured two thirds of one.
    columns = connection.execute(
        text(
            "SELECT column_name, data_type, character_maximum_length, is_nullable, "
            "column_default FROM information_schema.columns "
            "WHERE table_name = 'rainfall_extreme_event' ORDER BY column_name"
        )
    ).all()
    constraints = connection.execute(
        text(
            "SELECT conname, pg_get_constraintdef(oid) AS def FROM pg_constraint "
            "WHERE conrelid = 'rainfall_extreme_event'::regclass ORDER BY conname"
        )
    ).all()
    indexes = connection.execute(
        text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE tablename = 'rainfall_extreme_event' ORDER BY indexname"
        )
    ).all()
    return (
        [(name, definition) for name, definition in constraints],
        [(name, definition) for name, definition in indexes],
        [tuple(column) for column in columns],
    )


def test_the_migrated_schema_and_the_model_schema_are_the_same_schema(
    catalog_migration_db, test_engine
):
    """2.12: the parity guard.

    The migration cannot import the model, so the CHECK expressions and the
    partial index exist twice by necessity. Postgres itself is the arbiter:
    both schemas are built for real and compared through
    `pg_get_constraintdef` / `pg_indexes`, which normalize whatever the two
    sources spelled differently. A constraint dropped from the migration only —
    the failure mode where every model-level test stays green and the deploy
    ships an unconstrained table — fails HERE and nowhere else.
    """
    from alembic import command

    cfg, migrated_engine = catalog_migration_db
    command.upgrade(cfg, _CATALOG_HEAD)

    with migrated_engine.connect() as conn:
        migrated = _schema_shape(conn)
    with test_engine.connect() as conn:
        modelled = _schema_shape(conn)

    assert migrated[0] == modelled[0], "constraints differ between migration and model"
    assert migrated[1] == modelled[1], "indexes differ between migration and model"
    assert migrated[2] == modelled[2], "columns differ between migration and model"


def test_downgrading_both_revisions_leaves_no_catalog_behind(catalog_migration_db):
    """2.14's rollback boundary, EXECUTED rather than promised in prose:
    `upgrade head` then `downgrade -2` returns the schema to its parent.
    """
    from alembic import command
    from sqlalchemy import inspect

    cfg, engine = catalog_migration_db
    command.upgrade(cfg, _CATALOG_HEAD)
    assert "rainfall_extreme_event" in inspect(engine).get_table_names()

    command.downgrade(cfg, "-2")

    assert "rainfall_extreme_event" not in inspect(engine).get_table_names()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
            _CATALOG_BASE
        )


def test_both_catalog_revisions_are_ancestors_of_the_single_head():
    """2.12: one head, and this chain is on the mainline of it.

    Deliberately NOT `heads == ["lluvia_ext_002"]`: pinning the tip forces every
    later unit to edit this assertion, and an assertion routinely edited to make
    a suite pass stops being read as evidence (the `conocimiento` U7 lesson).
    The invariant that matters is that these two revisions were not stranded on
    a fork — `alembic upgrade head` refuses outright against two heads, which
    turns the deploy's healthcheck into the outage.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from app.core.health import ALEMBIC_INI_PATH

    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI_PATH)))
    heads = list(script.get_heads())
    assert len(heads) == 1, f"the migration tree forked: {heads}"

    mainline = {revision.revision for revision in script.iterate_revisions(heads[0], "base")}
    assert {"lluvia_ext_001", _CATALOG_HEAD} <= mainline
    # And the ids fit `alembic_version.version_num VARCHAR(32)`, the reason the
    # `conocimiento_007` precedent keeps ids short while filenames stay long.
    assert all(len(revision) <= 32 for revision in ("lluvia_ext_001", _CATALOG_HEAD))


def test_reading_detecting_and_persisting_twice_yields_the_same_catalog(db):
    """Spec R2 S1 end to end WITHIN this slice's boundary: persisted rows ->
    `baseline_daily_values` -> `detect_events` -> `persist_events`, run twice.

    The second pass must insert nothing AND raise nothing — the two halves are
    a pair, because a writer that raises on every re-run is as unusable as one
    that silently duplicates, and only one of the two failures is loud.

    Compared as a CANONICALIZED DUMP rather than as a row count: a count-only
    assertion stays green while a field silently moves. The dump is keyed by
    `event_key`, never ordered by `created_at` — `now()` is the TRANSACTION
    timestamp, so every row written in one transaction shares it and the
    "ordering" would be arbitrary.

    The detector's floors are injected (`min_samples`, `tier_percentiles`) the
    way `test_rainfall_detector.py` injects them: a hand-built series cannot
    reach p99.75 at all, since `100 * mean_rank / (N + 1)` caps below 100 for
    finite N. The rank arithmetic is B1a's subject; what this asserts is that
    the round trip through Postgres is stable.
    """
    from app.domains.geo.rainfall.detector import detect_events
    from app.domains.geo.rainfall.models import RainfallExtremeEvent
    from app.domains.geo.rainfall.repository import baseline_daily_values

    asset = "catalog-round-trip"
    start = date(2021, 1, 1)
    # A quiet 400-day record with two genuine wet spells in it.
    series = {start + timedelta(days=offset): 1.0 + (offset % 7) for offset in range(400)}
    for offset, value in ((120, 210.0), (121, 180.0), (300, 240.0)):
        series[start + timedelta(days=offset)] = value
    _persist_baseline_days(db, asset=asset, days=sorted(series.items()))

    tiers = {"extrema": 99.0, "alta": 96.0}
    daily = baseline_daily_values(
        db,
        source_id=SOURCE_ID,
        asset=asset,
        span_start=datetime(2021, 1, 1, tzinfo=UTC),
        span_end=datetime(2026, 1, 1, tzinfo=UTC),
    )
    events = [
        event
        for tier in tiers
        for event in detect_events(
            daily=daily,
            tier=tier,
            min_samples=100,
            tier_percentiles=tiers,
            climatology_span=(date(2021, 1, 1), date(2026, 1, 1)),
        )
    ]
    assert events, "the fixture series must produce at least one event to compare"

    first = _persist(db, events)
    db.flush()

    def _dump():
        return {
            row.event_key: (
                row.tier,
                row.start_date,
                row.end_date,
                row.peak_date,
                row.max_percentile,
                row.fired_windows,
                row.sealed_detection_params,
            )
            for row in db.query(RainfallExtremeEvent).all()
        }

    before = _dump()
    # Same reason as `test_a_second_identical_run_writes_absolutely_nothing`:
    # the second pass must compare against values Postgres handed back, not
    # against the objects the first pass left in the identity map. Expiring
    # emits no SQL, so the write-log assertion below still measures the writer.
    db.expire_all()
    with _write_log(db) as statements:
        second = _persist(db, events)
        db.flush()

    assert first == {"inserted": len(events), "skipped": 0}
    assert second == {"inserted": 0, "skipped": len(events)}
    assert _writes_touching_the_catalog(statements) == []
    assert _dump() == before
