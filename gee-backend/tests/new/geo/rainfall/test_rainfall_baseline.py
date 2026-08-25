"""Historical baseline persistence under the provider-asset scope key (D1).

Slice 1 of lluvia-insights: the baseline key is
``scope_kind="provider_asset"``, ``scope_id=<resolved asset>``,
``scope_version=BASELINE_ASSET_VERSION`` -- fixed, never a zoning version,
so a zone republication cannot orphan 30 years of evidence.
"""

from datetime import UTC, date, datetime, timedelta

import pytest


def test_provider_asset_scope_key_persists_and_reads_back(db):
    from app.domains.geo.rainfall.adapters.gee_client import (
        BASELINE_ASSET_VERSION,
        DEFAULT_ZONE_ASSET,
        asset_name_for,
    )
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import intervals_in_window, persist_intervals

    # The baseline key IS the resolved asset, unchanged by which scope kind
    # or id a caller resolved it from.
    asset = asset_name_for("provider_asset", DEFAULT_ZONE_ASSET)
    assert asset == DEFAULT_ZONE_ASSET

    start = datetime(1991, 1, 1, tzinfo=UTC)
    rows = [SourceInterval(start, start + timedelta(days=1), 12.5, "mm", "v3-final")]
    persisted = persist_intervals(
        db,
        source_id="chirps-v3-final",
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        rows=rows,
    )
    assert persisted == {"inserted": 1, "unchanged": 0, "superseded": 0}

    readback = intervals_in_window(
        db,
        source_id="chirps-v3-final",
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        start=start,
        end=start + timedelta(days=1),
    )
    assert len(readback) == 1
    assert readback[0].value == 12.5
    assert readback[0].scope_kind == "provider_asset"
    assert readback[0].scope_version == BASELINE_ASSET_VERSION


def test_baseline_cumulatives_returns_per_year_totals(db):
    from sqlalchemy import text

    from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import baseline_cumulatives, persist_intervals

    asset = "baseline-test-asset-per-year-totals"
    source_id = "chirps-v3-final"

    def _rows(year: int, values: list[float]) -> list[SourceInterval]:
        start = datetime(year, 3, 1, tzinfo=UTC)
        return [
            SourceInterval(
                start + timedelta(days=i), start + timedelta(days=i + 1), value, "mm", "v3-final"
            )
            for i, value in enumerate(values)
        ]

    values_by_year = {1991: [1.0, 2.0, 3.0], 1992: [4.0, 5.0], 1993: [0.5]}
    for year, values in values_by_year.items():
        persist_intervals(
            db,
            source_id=source_id,
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            rows=_rows(year, values),
        )

    # LI1-002 (review-ledger.md): a row landing exactly on the year
    # boundary (1991-01-01T00:00Z) is the case `date_part('year',
    # timestamptz)` mis-groups under a non-UTC session TZ -- Postgres
    # converts a `timestamptz` to the session's `TimeZone` setting BEFORE
    # extracting the field. Under America/Argentina/Buenos_Aires (UTC-3)
    # that instant is 1990-12-31T21:00 local, so the un-pinned expression
    # would file it under 1990 -- a year outside `expected_days_by_year`,
    # which is exactly the `KeyError` every real backfill row hits at
    # repository.py:305 (a real backfill always writes a Jan-1 row).
    boundary_value = 100.0
    boundary_start = datetime(1991, 1, 1, tzinfo=UTC)
    persist_intervals(
        db,
        source_id=source_id,
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        rows=[
            SourceInterval(
                boundary_start, boundary_start + timedelta(days=1), boundary_value, "mm", "v3-final"
            )
        ],
    )
    values_by_year = {**values_by_year, 1991: [*values_by_year[1991], boundary_value]}

    # One cutoff date per baseline year, past every persisted row so they
    # all fall inside the window (matches temporal.baseline_dates' shape).
    dates = [date(year, 3, 10) for year in values_by_year]

    # Non-UTC session TZ, scoped to this test's transaction: the `db`
    # fixture wraps the whole test in one transaction that gets rolled
    # back afterward, and per Postgres semantics a plain `SET` issued
    # inside a transaction that later rolls back reverts with it -- this
    # cannot leak into other tests sharing the pooled connection. Only the
    # boundary row above can move: every other persisted row sits in
    # March, safely mid-year in both UTC and Buenos Aires local time.
    db.execute(text("SET TIME ZONE 'America/Argentina/Buenos_Aires'"))

    result = baseline_cumulatives(db, source_id=source_id, asset=asset, dates=dates)

    assert result.keys() == {1991, 1992, 1993}
    for year, values in values_by_year.items():
        total, matched, expected = result[year]
        assert total == pytest.approx(sum(values))  # matches a manual SQL sum
        assert matched == len(values)
        window_start = datetime(year, 1, 1, tzinfo=UTC)
        window_end = datetime(year, 3, 11, tzinfo=UTC)
        assert expected == (window_end - window_start).days


def test_baseline_cumulatives_omits_years_with_no_persisted_rows(db):
    """A year with zero matched rows is absent, never a fabricated zero."""
    from app.domains.geo.rainfall.repository import baseline_cumulatives

    result = baseline_cumulatives(
        db,
        source_id="chirps-v3-final",
        asset="baseline-test-asset-empty",
        dates=[date(1991, 6, 1), date(1992, 6, 1)],
    )
    assert result == {}


def test_baseline_cumulatives_raises_on_a_duplicated_interval_slot(db):
    """LI2A-005 (slice 2b amendment A3): ``build_snapshot`` treats a
    duplicated ``interval_start`` as a broken invariant worth raising on,
    because ``intervals_in_window``'s anti-join is supposed to guarantee at
    most one non-superseded row per slot. ``baseline_cumulatives`` reads
    through the SAME anti-join and inherits the SAME invariant, but had no
    guard -- so a duplicate silently inflated BOTH ``total_mm`` and
    ``matched_days`` (the year still looked complete), quietly biasing
    ``annual.normal`` and every percentile ranked against it."""
    from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION
    from app.domains.geo.rainfall.models import RainfallIntervalValue
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import baseline_cumulatives, persist_intervals

    asset = "baseline-test-asset-duplicated-slot"
    source_id = "chirps-v3-final"
    day = datetime(1991, 5, 1, tzinfo=UTC)
    persist_intervals(
        db,
        source_id=source_id,
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        rows=[SourceInterval(day, day + timedelta(days=1), 10.0, "mm", "v3-final")],
    )

    # A SECOND non-superseded row for the same slot. `uq_rainfall_interval_
    # revision` permits it (provider_revision is part of the key), and no
    # `rainfall_interval_lifecycle` row marks either side superseded -- the
    # exact residue of a correction whose supersession link never landed
    # (persist_intervals only records the link for ids RETURNING reports).
    db.add(
        RainfallIntervalValue(
            source_id=source_id,
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

    with pytest.raises(ValueError, match="duplicat"):
        baseline_cumulatives(db, source_id=source_id, asset=asset, dates=[date(1991, 5, 2)])


def test_zoning_republication_does_not_orphan_baseline(db):
    """A zone's own scope_version bump (a republished zoning) is invisible
    to the baseline key: it is never part of it (1.2/1.4)."""
    from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION, asset_name_for
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import baseline_cumulatives, persist_intervals

    asset_before = asset_name_for("zone", "any-zone-id")
    asset_after = asset_name_for("zone", "any-zone-id")
    assert asset_before == asset_after

    source_id = "chirps-v3-final"
    start = datetime(1995, 6, 1, tzinfo=UTC)
    persist_intervals(
        db,
        source_id=source_id,
        scope_kind="provider_asset",
        scope_id=asset_before,
        scope_version=BASELINE_ASSET_VERSION,
        rows=[SourceInterval(start, start + timedelta(days=1), 7.0, "mm", "v3-final")],
    )

    before = baseline_cumulatives(
        db, source_id=source_id, asset=asset_before, dates=[date(1995, 6, 5)]
    )
    # Simulate a zoning republication: the request scope's own version
    # bumps elsewhere, but the resolved asset -- and therefore the baseline
    # read -- is unaffected, because the read key never carried it.
    after = baseline_cumulatives(
        db, source_id=source_id, asset=asset_after, dates=[date(1995, 6, 5)]
    )

    assert before == after
    assert before[1995][0] == pytest.approx(7.0)


def test_persist_analysis_revision_resolves_mapped_baseline_and_passes_it_through(db, monkeypatch):
    """1.8's actual GREEN behavior for a MAPPED scope: build_snapshot
    receives the resolved repository.baseline_cumulatives dict, not just
    the unmapped-basin baseline=None branch (proven separately above)."""
    import hashlib

    from app.domains.geo.rainfall import compute, tasks
    from app.domains.geo.rainfall.adapters.gee_client import (
        BASELINE_ASSET_VERSION,
        asset_name_for,
    )
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import persist_intervals

    captured: dict = {}
    real_build_snapshot = compute.build_snapshot

    def spy_build_snapshot(**kwargs):
        captured.update(kwargs)
        return real_build_snapshot(**kwargs)

    monkeypatch.setattr(compute, "build_snapshot", spy_build_snapshot)

    scope_id = "zone-mapped-baseline-wiring"
    asset = asset_name_for("zone", scope_id)

    baseline_start = datetime(1991, 3, 10, tzinfo=UTC)
    persist_intervals(
        db,
        source_id="chirps-v3-final",
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        rows=[
            SourceInterval(
                baseline_start, baseline_start + timedelta(days=1), 9.0, "mm", "v3-final"
            )
        ],
    )

    selected_start = datetime(2024, 6, 1, tzinfo=UTC)
    persist_intervals(
        db,
        source_id="chirps-v3-final",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=[
            SourceInterval(
                selected_start, selected_start + timedelta(days=1), 1.0, "mm", "v3-final"
            )
        ],
    )
    db.flush()

    fingerprint = hashlib.sha256(b"fp-mapped-baseline-wiring").hexdigest()
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
    db.flush()

    batch = {
        "source_id": "chirps-v3-final",
        "scope_kind": "zone",
        "scope_id": scope_id,
        "year": 2024,
        "intervals": 1,
        "persisted": 1,
        "superseded": 0,
        "provider_revision": "v3-final",
        "unit": "mm",
        "cadence_seconds": 86400.0,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"scale_m": 5500, "provider_revision": "v3-final"},
        "discrepancies": [],
        "checksum": "sha256:fixture-mapped-baseline-wiring",
    }

    # Comparison_end lands in mid-September Buenos Aires local time either
    # way (no UTC/local day-boundary ambiguity), well after the persisted
    # 1991-03-10 baseline row.
    now = datetime(2024, 9, 15, 12, 0, tzinfo=UTC)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    assert "baseline" in captured
    assert captured["baseline"] is not None
    assert 1991 in captured["baseline"]
    total, matched, _expected = captured["baseline"][1991]
    assert total == pytest.approx(9.0)
    assert matched == 1


def test_unmapped_basin_raises_unknown_provider_scope():
    """Regression pin for the precondition tasks._persist_analysis_revision
    (1.8) relies on: an unmapped basin's own asset resolution raises,
    rather than silently reducing over the wrong geometry."""
    from app.domains.geo.rainfall.adapters.gee_client import UnknownProviderScope, asset_name_for

    with pytest.raises(UnknownProviderScope, match="no GEE asset mapped"):
        asset_name_for("basin", "an-unmapped-basin-id")


def test_persist_analysis_revision_suppresses_baseline_for_unmapped_basin(db):
    """1.8: an unmapped basin's asset-resolution failure must not become a
    build crash (design.md D1) -- build_snapshot receives baseline=None and
    the revision still writes normally."""
    import hashlib

    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import RainfallRepository, persist_intervals

    def _daily_intervals(*, start_day: int, values: list[float]) -> list[SourceInterval]:
        rows = []
        for offset, value in enumerate(values):
            start = datetime(2024, 1, start_day + offset, tzinfo=UTC)
            rows.append(SourceInterval(start, start + timedelta(days=1), value, "mm", "v3-final"))
        return rows

    fingerprint = hashlib.sha256(b"fp-unmapped-basin").hexdigest()

    rows = _daily_intervals(start_day=1, values=[1.0, 2.0, 3.0])
    persist_intervals(
        db,
        source_id="chirps-v3-final",
        scope_kind="basin",
        scope_id="unmapped-basin-77",
        scope_version="v1",
        rows=rows,
    )
    db.flush()

    outbox = RainfallOutbox(
        source_id="chirps-v3-final",
        role="historical",
        scope_kind="basin",
        scope_id="unmapped-basin-77",
        scope_version="v1",
        year=2024,
        work_labels=["analysis_missing"],
        interval_start=datetime(2024, 1, 1, tzinfo=UTC),
        interval_end=datetime(2025, 1, 1, tzinfo=UTC),
        status="pending",
        request_fingerprint=fingerprint,
    )
    db.add(outbox)
    db.flush()

    batch = {
        "source_id": "chirps-v3-final",
        "scope_kind": "basin",
        "scope_id": "unmapped-basin-77",
        "year": 2024,
        "intervals": 3,
        "persisted": 3,
        "superseded": 0,
        "provider_revision": "v3-final",
        "unit": "mm",
        "cadence_seconds": 86400.0,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"scale_m": 5500, "provider_revision": "v3-final"},
        "discrepancies": [],
        "checksum": "sha256:fixture-unmapped-basin",
    }

    result = tasks._persist_analysis_revision(
        db, outbox_id=str(outbox.id), batch=batch, now=datetime(2024, 6, 15, tzinfo=UTC)
    )

    assert result["decision"] == "write"
    assert result["revision_id"] is not None

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    assert revision.snapshot["annual"]["selected"]["state"] == "available"


# ===========================================================================
# lluvia-antecedente-referencia, slice S1b -- `baseline_daily_values`
#
# The rolling-window reference (design.md D2) needs the baseline as a RAW
# DAILY SERIES, not as `baseline_cumulatives`' per-year aggregate: a
# fixed-length window has no year anchor, so there is no year-start GROUP BY
# for a January-crossing window to be split across. Same provider-asset key,
# same supersession anti-join, same strict duplicate guard -- and explicitly
# bounded to [1991-01-01, 2021-01-01), because the 2021-2025 backfill has
# landed under that SAME key (verified on the box, tasks.md phase 0).
# ===========================================================================


def _persist_baseline_days(db, *, asset, days, source_id="chirps-v3-final", revision="v3-final"):
    """Persist one daily row per ``(date, value)`` pair under the baseline key."""
    from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION
    from app.domains.geo.rainfall.ports import SourceInterval
    from app.domains.geo.rainfall.repository import persist_intervals

    rows = []
    for day, value in days:
        start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        rows.append(SourceInterval(start, start + timedelta(days=1), value, "mm", revision))
    return persist_intervals(
        db,
        source_id=source_id,
        scope_kind="provider_asset",
        scope_id=asset,
        scope_version=BASELINE_ASSET_VERSION,
        rows=rows,
    )


def test_baseline_daily_values_returns_one_value_per_persisted_day(db):
    """2.1: one ``(date, value)`` per persisted baseline day, ordered, under
    the same provider-asset key and the same supersession anti-join
    ``baseline_cumulatives`` reads through -- a superseded row is invisible
    here for exactly the reason it is invisible there."""
    from sqlalchemy import text

    from app.domains.geo.rainfall.repository import baseline_daily_values

    asset = "baseline-daily-values-shape"
    _persist_baseline_days(
        db,
        asset=asset,
        days=[(date(1991, 3, 1), 1.5), (date(1991, 3, 2), 2.5), (date(1995, 7, 9), 4.0)],
    )
    # A correction for 1991-03-02: `persist_intervals` appends the new row and
    # marks the old one superseded, so the anti-join must serve 9.0 -- ONE
    # entry for that day, not two and not the stale 2.5.
    superseded = _persist_baseline_days(db, asset=asset, days=[(date(1991, 3, 2), 9.0)])
    assert superseded["superseded"] == 1

    result = baseline_daily_values(db, source_id="chirps-v3-final", asset=asset)

    assert result == (
        (date(1991, 3, 1), 1.5),
        (date(1991, 3, 2), 9.0),
        (date(1995, 7, 9), 4.0),
    )

    # A different asset under the same source is a different baseline.
    assert baseline_daily_values(db, source_id="chirps-v3-final", asset="no-such-asset") == ()
    # And a different source under the same asset likewise.
    assert baseline_daily_values(db, source_id="chirps-v3-sat", asset=asset) == ()

    # LI3A-005, asserted on the boundary day: `interval_start` comes back from
    # psycopg2 rendered in the SESSION's zone, so a bare `.date()` files
    # 1991-01-01T00:00Z under 1990-12-31 whenever that zone is west of UTC --
    # the day the whole span starts on. `temporal.utc_day` is the only reader.
    # The `db` fixture rolls this transaction back, so the SET cannot leak.
    _persist_baseline_days(db, asset=asset, days=[(date(1991, 1, 1), 7.25)])
    db.execute(text("SET TIME ZONE 'America/Argentina/Buenos_Aires'"))

    bucketed = dict(baseline_daily_values(db, source_id="chirps-v3-final", asset=asset))
    assert date(1991, 1, 1) in bucketed
    assert date(1990, 12, 31) not in bucketed
    assert bucketed[date(1991, 1, 1)] == pytest.approx(7.25)


def test_baseline_span_constants_are_the_d2_values_and_the_end_is_exclusive(db):
    """2.3: the span is `[1991-01-01, 2021-01-01)` -- module CONSTANTS (task
    4.5 mutation-gates them by name) and an EXCLUSIVE upper bound. A `<=`
    admits 2021-01-01 into a distribution the served envelope keeps calling
    "1991-2020"."""
    from app.domains.geo.rainfall.repository import (
        BASELINE_SPAN_END,
        BASELINE_SPAN_START,
        baseline_daily_values,
    )

    assert BASELINE_SPAN_START == datetime(1991, 1, 1, tzinfo=UTC)
    assert BASELINE_SPAN_END == datetime(2021, 1, 1, tzinfo=UTC)

    asset = "baseline-daily-values-span-edges"
    _persist_baseline_days(
        db,
        asset=asset,
        days=[
            (date(1990, 12, 31), 111.0),  # below the span start
            (date(1991, 1, 1), 1.0),  # the first admitted day
            (date(2020, 12, 31), 2.0),  # the last admitted day
            (date(2021, 1, 1), 222.0),  # the first excluded day (`<`, not `<=`)
        ],
    )

    assert baseline_daily_values(db, source_id="chirps-v3-final", asset=asset) == (
        (date(1991, 1, 1), 1.0),
        (date(2020, 12, 31), 2.0),
    )


def test_baseline_daily_values_excludes_rows_dated_2021_and_later(db):
    """2.4: the whole reason the bounds are load-bearing rather than hygiene.

    The 2021-2025 backfill shares the `(chirps-v3-final, <asset>, v1)` key
    with the 1991-2020 baseline -- verified on the box (tasks.md phase 0:
    12,784 rows, 35 years 1991-2025, every year at its exact calendar day
    count). So an UNBOUNDED read silently widens the distribution past the
    period the envelope names.

    Asserted on all three surfaces the widening reaches, because they are NOT
    equally protected and saying so is the point:

    * the read's own result -- the contract every consumer inherits;
    * the ABSOLUTE-mode distribution, which infers its span from ``min``/
      ``max`` of the series it is handed and therefore has NO bound of its
      own: this read's upper bound is its ONLY protection;
    * the seasonal ``normal``, where the bound is defence in depth --
      ``seasonal_climatology`` is also given ``span_end`` and an explicit year
      set, so this value alone cannot prove the bound holds (verified by
      mutation: deleting the upper bound leaves the normal untouched).
    """
    from app.domains.geo.rainfall.climatology import (
        absolute_window_samples,
        seasonal_climatology,
        window_normal,
    )
    from app.domains.geo.rainfall.repository import (
        BASELINE_SPAN_END,
        BASELINE_SPAN_START,
        baseline_daily_values,
    )

    asset = "baseline-daily-values-excludes-2021"
    baseline_years = range(1991, 2021)
    _persist_baseline_days(
        db,
        asset=asset,
        days=[(date(year, 6, 15), 10.0) for year in baseline_years],
    )

    def _read():
        return baseline_daily_values(db, source_id="chirps-v3-final", asset=asset)

    def _normal(daily) -> float | None:
        clim = seasonal_climatology(
            daily=daily,
            days=1,
            anchor=date(2024, 6, 15),
            years=baseline_years,
            span_start=BASELINE_SPAN_START.date(),
            span_end=BASELINE_SPAN_END.date(),
        )
        return window_normal(clim, min_years=20)

    before_daily = _read()
    before_absolute = absolute_window_samples(daily=before_daily, days=1)
    before_normal = _normal(before_daily)
    assert before_normal == pytest.approx(10.0)
    assert before_absolute[-1].end == date(2020, 6, 15)

    # The backfill lands: five post-2020 years under the SAME key, wet enough
    # that a widened distribution could not possibly go unnoticed.
    _persist_baseline_days(
        db,
        asset=asset,
        days=[(date(year, 6, 15), 500.0) for year in range(2021, 2026)],
    )

    after_daily = _read()
    assert after_daily == before_daily
    after_absolute = absolute_window_samples(daily=after_daily, days=1)
    assert after_absolute[-1].end == date(2020, 6, 15)
    assert len(after_absolute) == len(before_absolute)
    assert _normal(after_daily) == pytest.approx(before_normal)


def test_baseline_daily_values_raises_on_a_duplicated_non_superseded_slot(db):
    """2.5: STRICT, deliberately not `baseline_curve_rows`' tolerance
    (repository.py:422-466, dedup at series.py:289). A workbook curve that
    draws one duplicated day slightly wrong still beats no curve; a RANKED
    statistic cannot take that trade, because a duplicated slot inflates the
    window total silently and the window still looks complete."""
    from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION
    from app.domains.geo.rainfall.models import RainfallIntervalValue
    from app.domains.geo.rainfall.repository import (
        DuplicateBaselineSlotError,
        baseline_daily_values,
    )

    asset = "baseline-daily-values-duplicated-slot"
    day = datetime(1994, 8, 3, tzinfo=UTC)
    _persist_baseline_days(db, asset=asset, days=[(day.date(), 10.0)])
    # A SECOND non-superseded row for the same slot: the residue of a
    # correction whose supersession link never landed.
    db.add(
        RainfallIntervalValue(
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            interval_start=day,
            interval_end=day + timedelta(days=1),
            provider_revision="v3-final+r1",
            value=9.0,
            unit="mm",
        )
    )
    db.flush()

    with pytest.raises(DuplicateBaselineSlotError, match="duplicat") as raised:
        baseline_daily_values(db, source_id="chirps-v3-final", asset=asset)

    # Still a ValueError (the LI2A-005 contract) and it carries the numbers
    # the caller's event payload needs, so nobody re-parses the message.
    assert isinstance(raised.value, ValueError)
    assert (raised.value.year, raised.value.matched, raised.value.distinct_slots) == (1994, 2, 1)
    assert raised.value.asset == asset


# ---------------------------------------------------------------------------
# S1b -- the build's OWN containment for the window baseline (design.md D2)
# ---------------------------------------------------------------------------


def _event_payload(caplog, event_name: str) -> dict:
    import json

    for record in caplog.records:
        if record.name == "rainfall" and record.message.startswith(f"{event_name} "):
            return json.loads(record.message[len(event_name) + 1 :])
    raise AssertionError(
        f"no {event_name!r} event captured; got {[r.message for r in caplog.records]}"
    )


def _event_names(caplog) -> set[str]:
    return {
        record.message.split(" ", 1)[0] for record in caplog.records if record.name == "rainfall"
    }


def _selected_year_rows(year: int, count: int, value: float):
    from app.domains.geo.rainfall.ports import SourceInterval

    rows = []
    for offset in range(count):
        start = datetime(year, 1, 1, tzinfo=UTC) + timedelta(days=offset)
        rows.append(SourceInterval(start, start + timedelta(days=1), value, "mm", "v3-nrt"))
    return rows


def _outbox_for(db, *, scope_id: str, year: int):
    from app.domains.geo.rainfall.models import RainfallOutbox
    from app.domains.geo.rainfall.service import analysis_request_fingerprint

    fingerprint = analysis_request_fingerprint(
        {"scope": {"kind": "zone", "id": scope_id, "version": "v1"}, "year": year}
    )
    outbox = RainfallOutbox(
        source_id="chirps-v3-sat",
        role="daily",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        year=year,
        work_labels=["analysis_missing"],
        interval_start=datetime(year, 1, 1, tzinfo=UTC),
        interval_end=datetime(year + 1, 1, 1, tzinfo=UTC),
        status="pending",
        request_fingerprint=fingerprint,
    )
    db.add(outbox)
    db.flush()
    return outbox


def _nrt_batch(scope_id: str) -> dict:
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


def test_a_duplicated_window_baseline_slot_degrades_only_the_window_reference(db, caplog):
    """2.6 + 2.8: the containment, and the divergence that makes it necessary.

    The duplicated slot sits in JUNE 1991, past that baseline year's own
    cutoff -- so ``baseline_cumulatives`` cannot see it (its windows stop at
    each year's cutoff) and the wider daily read can. Both reads look at the
    same evidence and answer differently, on purpose: each degrades only the
    metrics it feeds.

    So the annual pair must NOT be relabelled ``baseline_evidence_invalid``
    here, the antecedent totals must still build, the workbook curve's own
    (deliberately tolerant) read must still answer, and the revision must
    LAND. Without a handler of its own the exception escapes
    ``_persist_analysis_revision`` and reinstates LI2B-004: a key that no
    retry can ever build, feeding the re-enqueue loop.
    """
    import logging

    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION, asset_name_for
    from app.domains.geo.rainfall.models import RainfallAnalysisRevision, RainfallIntervalValue
    from app.domains.geo.rainfall.repository import baseline_curve_rows, persist_intervals

    scope_id = "zone-s1b-window-baseline-duplicate"
    year = 2025
    now = datetime(year, 2, 20, 12, 0, tzinfo=UTC)
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=_selected_year_rows(year, 51, 3.0),
    )

    asset = asset_name_for("zone", scope_id)
    duplicated_day = datetime(1991, 6, 15, tzinfo=UTC)
    _persist_baseline_days(db, asset=asset, days=[(duplicated_day.date(), 8.0)])
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

    outbox = _outbox_for(db, scope_id=scope_id, year=year)
    caplog.set_level(logging.INFO, logger="rainfall")
    result = tasks._persist_analysis_revision(
        db, outbox_id=str(outbox.id), batch=_nrt_batch(scope_id), now=now
    )

    # (0) The build LANDS. This is the whole of LI2B-004's lesson.
    assert result["decision"] == "write"
    assert result["revision_id"] is not None
    stored = db.get(RainfallAnalysisRevision, result["revision_id"]).snapshot

    # (a) The three antecedent TOTALS still build -- they read the selected
    #     year's own intervals and never touch the baseline.
    assert set(stored["antecedents"]) == {"d7", "d30", "d90"}
    assert stored["antecedents"]["d7"]["state"] == "available"
    assert stored["antecedents"]["d7"]["value"] == pytest.approx(21.0)
    assert stored["antecedents"]["d30"]["state"] == "available"
    assert stored["annual"]["selected"]["value"] == pytest.approx(153.0)

    # (b) The ANNUAL pair keeps its own honest answer. This fixture is thin,
    #     so it is `baseline_years_below_minimum` -- what matters is that it
    #     is NOT the window read's failure wearing the annual read's label,
    #     which is exactly what one shared `try` would produce.
    for metric in ("normal", "percentile"):
        assert stored["annual"][metric]["state"] == "suppressed"
        assert stored["annual"][metric]["reason"] == "baseline_years_below_minimum"
    assert "rainfall.baseline.duplicate_slots" not in _event_names(caplog)

    # (c) The workbook normal curve's own read still answers over the same
    #     evidence: it is deliberately tolerant (series.py:289 dedups), and a
    #     curve drawn one day wrong beats no curve. The ranked statistic
    #     cannot take that trade -- same evidence, two honest answers.
    assert baseline_curve_rows(
        db, source_id="chirps-v3-final", asset=asset, dates=[date(1991, 12, 31)]
    )

    # (d) The degradation is LOUD. Suppression alone reads to an operator as
    #     an ordinary thin baseline, so the event carries the numbers.
    event = _event_payload(caplog, "rainfall.window_baseline.duplicate_slots")
    assert event["baseline_year"] == 1991
    assert event["matched_rows"] == 2
    assert event["distinct_slots"] == 1
    assert event["asset"] == asset
    assert event["scope_id"] == scope_id
    assert event["year"] == year


def test_the_window_baseline_is_read_during_the_build_and_spends_no_provider_call(db, monkeypatch):
    """2.9 (spec R1 S3): the reference is built from PERSISTED interval rows
    only. The read happens inside the build -- asserted, not assumed, since a
    read nobody calls cannot degrade anything -- and no adapter and no GEE
    client is touched while it does."""
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.adapters import gee_client
    from app.domains.geo.rainfall.adapters.chirps import ChirpsV3Adapter
    from app.domains.geo.rainfall.adapters.imerg import ImergV07Adapter
    from app.domains.geo.rainfall.adapters.gee_client import asset_name_for
    from app.domains.geo.rainfall import repository
    from app.domains.geo.rainfall.repository import persist_intervals

    def _forbidden(*args, **kwargs):
        raise AssertionError("the reference build must spend no provider call")

    monkeypatch.setattr(tasks, "_concrete_fetch", _forbidden)
    monkeypatch.setattr(ChirpsV3Adapter, "fetch", _forbidden)
    monkeypatch.setattr(ImergV07Adapter, "fetch", _forbidden)
    monkeypatch.setattr(gee_client.GeeZonalClient, "__init__", _forbidden)

    scope_id = "zone-s1b-window-baseline-no-fetch"
    year = 2025
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=_selected_year_rows(year, 51, 3.0),
    )
    asset = asset_name_for("zone", scope_id)
    _persist_baseline_days(
        db, asset=asset, days=[(date(1991, 6, 15), 8.0), (date(1992, 6, 15), 12.0)]
    )
    db.flush()

    calls: list[tuple[str, str]] = []
    real_read = repository.baseline_daily_values

    def spy(db_, *, source_id, asset):
        calls.append((source_id, asset))
        return real_read(db_, source_id=source_id, asset=asset)

    monkeypatch.setattr(repository, "baseline_daily_values", spy)

    outbox = _outbox_for(db, scope_id=scope_id, year=year)
    result = tasks._persist_analysis_revision(
        db,
        outbox_id=str(outbox.id),
        batch=_nrt_batch(scope_id),
        now=datetime(year, 2, 20, 12, 0, tzinfo=UTC),
    )

    assert result["decision"] == "write"
    assert calls == [("chirps-v3-final", asset)]
