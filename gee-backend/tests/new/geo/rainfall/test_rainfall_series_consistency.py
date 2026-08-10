"""Integration coverage for slice 3a's series module (real PG).

The revision row is immutable and forever servable, while the series is read
LIVE from the interval store through the same supersession anti-join, so the
same revision id can serve a card whose total disagrees with its own chart.
design.md D3 closes that with a server-side pin: recompute
``compute.data_revision_for`` over EXACTLY the keys and window the build read
(the D6-widened ``[year_start - 90d, year_end)``) and compare it with the
row's stored ``data_revision``. Errors are one-directional by construction --
nothing reports consistent unless the digests are equal.

Lluvia insights slice 3a: series module + consistency pin + ``data_revision``
exposure.
"""

import hashlib
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION, asset_name_for
from app.domains.geo.rainfall.models import RainfallOutbox
from app.domains.geo.rainfall.ports import SourceInterval
from app.domains.geo.rainfall.repository import RainfallRepository, persist_intervals

_ZONE_FAMILY = "v3-nrt"


def _daily_rows(
    start: date, count: int, value: float, *, provider_revision: str = "v3-final"
) -> list[SourceInterval]:
    rows = []
    for offset in range(count):
        day = start + timedelta(days=offset)
        day_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        rows.append(
            SourceInterval(day_start, day_start + timedelta(days=1), value, "mm", provider_revision)
        )
    return rows


def _persist_zone_rows(db, *, scope_id: str, rows) -> None:
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=rows,
    )
    db.flush()


def _build_revision(db, *, scope_id: str, year: int, now: datetime):
    """Materialize one revision through the REAL production path, so the pin
    is compared against a digest this repository actually wrote."""
    from app.domains.geo.rainfall import tasks

    fingerprint = hashlib.sha256(f"fp-series-{scope_id}-{year}".encode()).hexdigest()
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
    batch = {
        "source_id": "chirps-v3-sat",
        # The build takes its revision FAMILY from the adapter batch, while
        # the pin derives it from the persisted rows (design.md D3 step 2,
        # LIB-101) -- the ingest path writes both from the same value, so the
        # fixtures keep them equal exactly as production does.
        "provider_revision": _ZONE_FAMILY,
        "unit": "mm",
        "cadence_seconds": 86400.0,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"scale_m": 5500, "provider_revision": _ZONE_FAMILY},
        "discrepancies": [],
        "checksum": f"sha256:fixture-{scope_id}",
    }
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)
    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    return revision


# ---------------------------------------------------------------------------
# 3a.1-3a.4: the pin
# ---------------------------------------------------------------------------


def test_untouched_intervals_report_consistent_true(db):
    """3a.1 (spec: "Series still matches its revision") -- nothing moved
    after the revision was stored, so the recomputed digest equals the stored
    one and the series is served with no inconsistency reason."""
    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a1-untouched"
    year = 2025
    now = datetime(year, 1, 21, 12, 0, tzinfo=UTC)  # comparison_end = Jan 21
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(date(year, 1, 1), 20, 2.0, provider_revision=_ZONE_FAMILY),
    )
    revision = _build_revision(db, scope_id=scope_id, year=year, now=now)

    series = build_series(db, revision)

    assert series["consistent_with_snapshot"] is True
    assert series["consistency_reason"] is None
    # Echoes, from the served row and its own envelope -- never recomputed
    # from the live store, which is the thing the pin is checking.
    assert series["data_revision"] == revision.data_revision
    assert series["analysis_revision_id"] == str(revision.id)
    assert series["comparison_end"] == revision.snapshot["comparison_end"]
    selected = revision.snapshot["annual"]["selected"]
    assert series["available_through"] == selected["provenance"]["available_through"]

    # The daily points ARE the selected metric, day by day: the last
    # cumulative is exactly what annual.selected totalled.
    points = series["points"]
    assert [point["date"] for point in points] == [
        (date(year, 1, 1) + timedelta(days=offset)).isoformat() for offset in range(20)
    ]
    assert points[-1]["accumulated"] == pytest.approx(selected["value"])
    assert all(point["state"] == "available" for point in points)
    assert all(point["mm"] == pytest.approx(2.0) for point in points)


def test_superseded_slot_reports_data_revision_moved(db):
    """3a.2 (spec: "Daily data was corrected after the analysis was stored")
    -- an NRT correction supersedes one slot INSIDE the build window: the
    revision id has not moved, the numbers behind it have."""
    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a2-superseded"
    year = 2025
    now = datetime(year, 1, 21, 12, 0, tzinfo=UTC)
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(date(year, 1, 1), 20, 2.0, provider_revision=_ZONE_FAMILY),
    )
    revision = _build_revision(db, scope_id=scope_id, year=year, now=now)
    assert build_series(db, revision)["consistent_with_snapshot"] is True

    # The correction: same slot, a different value, same family -> a
    # `v3-nrt+r1` row lands and the old one is marked superseded.
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(date(year, 1, 5), 1, 9.0, provider_revision=_ZONE_FAMILY),
    )

    series = build_series(db, revision)

    assert series["consistent_with_snapshot"] is False
    assert series["consistency_reason"] == "data_revision_moved"
    # The corrected value is what the series shows -- the fresher evidence is
    # served WITH the disclosure, never silently swapped or withheld.
    corrected = next(point for point in series["points"] if point["date"] == "2025-01-05")
    assert corrected["mm"] == pytest.approx(9.0)


def test_two_nonsuperseded_families_report_interval_family_ambiguous(db):
    """3a.3 -- ``intervals_in_window`` deliberately does not filter by
    revision family, so the pin's rule is that the read rows MUST map to
    exactly one. Two live families make the build's own family
    unreconstructable, and an unreconstructable digest reports INCONSISTENT
    with its own reason rather than guessing."""
    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a3-two-families"
    year = 2025
    now = datetime(year, 1, 21, 12, 0, tzinfo=UTC)
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(date(year, 1, 1), 20, 2.0, provider_revision=_ZONE_FAMILY),
    )
    revision = _build_revision(db, scope_id=scope_id, year=year, now=now)

    # A DIFFERENT slot under a different family: neither row is superseded,
    # so the window now holds two live families.
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(date(year, 1, 21), 1, 2.0, provider_revision="v3-final"),
    )

    series = build_series(db, revision)

    assert series["consistent_with_snapshot"] is False
    # Ambiguity is decided BEFORE the digest comparison: the planted row also
    # moves the digest, and the reported reason must be the one that made the
    # comparison impossible, not the one that would have followed from it.
    assert series["consistency_reason"] == "interval_family_ambiguous"


def test_pin_uses_d6_widened_read_window(db):
    """3a.4 -- the pin recomputes over the BUILD's read window
    ``[year_start - 90d, year_end)`` (D6), not the displayed calendar-year
    window. A prior-year row planted after the build is invisible to the
    display and MUST still move the pin; a display-window recompute would
    report this exact case as consistent."""
    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a4-widened-window"
    year = 2025
    now = datetime(year, 1, 21, 12, 0, tzinfo=UTC)
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(date(year, 1, 1), 20, 2.0, provider_revision=_ZONE_FAMILY),
    )
    revision = _build_revision(db, scope_id=scope_id, year=year, now=now)
    before = build_series(db, revision)
    assert before["consistent_with_snapshot"] is True

    # 2024-12-15: inside [2024-10-03, 2025-01-01) -- the D6 widening the
    # antecedents need, and outside the displayed calendar year entirely.
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(date(year - 1, 12, 15), 1, 7.0, provider_revision=_ZONE_FAMILY),
    )

    after = build_series(db, revision)

    assert after["consistent_with_snapshot"] is False
    assert after["consistency_reason"] == "data_revision_moved"
    # The display is unchanged: same 20 calendar-year points, no prior-year
    # day leaked into the chart.
    assert [point["date"] for point in after["points"]] == [
        point["date"] for point in before["points"]
    ]
    assert all(point["date"].startswith("2025-") for point in after["points"])


def _interval_store_selects(db, scope_id: str, call) -> tuple[list[str], list[str]]:
    """Run *call* while counting the SELECTs it executes against
    ``rainfall_interval_value``, split into the ones bound to *scope_id* and
    everything else (LI3A-003).

    Observing the guarantee requires observing the DATABASE, not the answer:
    a build that read the interval store twice and got the same rows both
    times is indistinguishable, from the outside, from one that read it once.
    Filtering by the bound ``scope_id`` separates the selected-scope read from
    the baseline curve's read, which legitimately hits the same table under a
    different key (``scope_kind='provider_asset'``).
    """
    from sqlalchemy import event

    def _bound_values(parameters) -> list:
        if isinstance(parameters, dict):
            return list(parameters.values())
        if isinstance(parameters, list | tuple):
            flat: list = []
            for item in parameters:
                if isinstance(item, dict):
                    flat.extend(item.values())
                else:
                    flat.append(item)
            return flat
        return []

    scoped: list[str] = []
    other: list[str] = []

    def _record(_conn, _cursor, statement, parameters, _context, _executemany) -> None:
        if not statement.lstrip().upper().startswith("SELECT"):
            return
        if "rainfall_interval_value" not in statement.lower():
            return
        (scoped if scope_id in _bound_values(parameters) else other).append(statement)

    db.flush()  # so no autoflush INSERT lands inside the observed window
    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", _record)
    try:
        call()
    finally:
        event.remove(bind, "before_cursor_execute", _record)
    return scoped, other


def test_build_series_reads_the_interval_store_exactly_once(db):
    """LI3A-003: "ONE read backs both the pin and the displayed points" is a
    claim about how many times ``build_series`` queries the interval store,
    and only a count can falsify it. A split read is a real window: a
    correction landing between the two queries makes the chart show data the
    pin has already declared untouched, and every behavioral assertion still
    passes because both reads return the same rows in a quiet test.

    The baseline curve's own read is present in this fixture on purpose --
    it hits the SAME table under the provider-asset key -- so the count is
    proven to be scope-specific rather than "the only query there was"."""
    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a-one-read"
    asset = asset_name_for("zone", scope_id)
    now = datetime(_CURVE_YEAR, 3, 2, 12, 0, tzinfo=UTC)
    _seed_full_baseline(db, asset=asset, cutoff=_CURVE_CUTOFF)
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(
            date(_CURVE_YEAR, 1, 1),
            _days_through(_CURVE_CUTOFF, _CURVE_YEAR),
            3.0,
            provider_revision=_ZONE_FAMILY,
        ),
    )
    revision = _build_revision(db, scope_id=scope_id, year=_CURVE_YEAR, now=now)

    series: dict = {}
    scoped, other = _interval_store_selects(
        db, scope_id, lambda: series.update(build_series(db, revision))
    )

    assert len(scoped) == 1, scoped
    # The baseline read is the deliberate SECOND read of a DIFFERENT key, and
    # its presence is what proves the filter above is not matching nothing.
    assert len(other) == 1, other
    assert series["normal_curve_state"] == "available"
    assert series["consistent_with_snapshot"] is True


def test_series_points_and_pin_read_the_same_resolved_set(db):
    """The BEHAVIORAL half of the one-read guarantee: an interval planted
    after the build is visible to the display AND to the pin. It cannot
    falsify a split read on its own -- two reads of the same quiet database
    return the same rows -- which is what
    ``test_build_series_reads_the_interval_store_exactly_once`` above exists
    to observe. What this one still pins is the gap contract: a day with no
    evidence is ``None``, never a fabricated zero, and the running total stays
    flat across it."""
    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a-same-source"
    year = 2025
    now = datetime(year, 1, 21, 12, 0, tzinfo=UTC)
    gap_day = date(year, 1, 11)
    rows = [
        row
        for row in _daily_rows(date(year, 1, 1), 20, 2.0, provider_revision=_ZONE_FAMILY)
        if row.interval_start.date() != gap_day
    ]
    _persist_zone_rows(db, scope_id=scope_id, rows=rows)
    revision = _build_revision(db, scope_id=scope_id, year=year, now=now)

    before = build_series(db, revision)
    assert before["consistent_with_snapshot"] is True
    missing = next(point for point in before["points"] if point["date"] == gap_day.isoformat())
    assert missing["mm"] is None
    assert missing["state"] == "unavailable"
    # Jan 1 - Jan 10 at 2.0 mm: the total carries across the hole rather than
    # inventing a value for it.
    assert missing["accumulated"] == pytest.approx(20.0)

    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(gap_day, 1, 5.0, provider_revision=_ZONE_FAMILY),
    )

    after = build_series(db, revision)

    filled = next(point for point in after["points"] if point["date"] == gap_day.isoformat())
    assert filled["mm"] == pytest.approx(5.0)
    assert filled["state"] == "available"
    # Visible to the display AND to the pin -- one read, two projections.
    assert after["consistent_with_snapshot"] is False
    assert after["consistency_reason"] == "data_revision_moved"


def test_series_ends_at_the_clipped_window_not_the_calendar_comparison_end(db):
    """Provider lag is the documented steady state (design.md D5/D6
    amendments), so the series stops at the last published day and echoes
    that clipped ``available_through``, while ``comparison_end`` stays the
    calendar date. Days the provider has not reached are not emitted as empty
    points that a chart would read as a dry spell."""
    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a-lagged-tail"
    year = 2025
    now = datetime(year, 1, 25, 12, 0, tzinfo=UTC)  # comparison_end = Jan 25
    _persist_zone_rows(  # published only through Jan 20: a 5-day lag
        db,
        scope_id=scope_id,
        rows=_daily_rows(date(year, 1, 1), 20, 2.0, provider_revision=_ZONE_FAMILY),
    )
    revision = _build_revision(db, scope_id=scope_id, year=year, now=now)

    series = build_series(db, revision)

    assert series["comparison_end"] == "2025-01-25"
    assert series["available_through"] == datetime(year, 1, 21, tzinfo=UTC).isoformat()
    points = series["points"]
    assert points[-1]["date"] == "2025-01-20"
    assert len(points) == 20
    assert points[-1]["accumulated"] == pytest.approx(
        revision.snapshot["annual"]["selected"]["value"]
    )


# ---------------------------------------------------------------------------
# 3a.8: the normal curve
# ---------------------------------------------------------------------------

# 2024 is a leap year, so the window below CROSSES February 29 -- the one day
# the normal curve cannot be keyed on, because only 8 of the 30 baseline years
# have it (temporal.baseline_years_for).
_CURVE_YEAR = 2024
_CURVE_CUTOFF = date(_CURVE_YEAR, 3, 2)
_LEAP_BASELINE_YEARS = 8  # 1992, 1996, 2000, 2004, 2008, 2012, 2016, 2020


def _days_through(cutoff_month_day: date, year: int) -> int:
    """Jan 1 .. the same month/day of *year*, inclusive -- computed per year
    so leap and non-leap baseline years are each counted on their own
    calendar instead of a single hand-rolled constant (the leap-year fixture
    bug slice 2a hit in its own 2a.13)."""
    return (date(year, cutoff_month_day.month, cutoff_month_day.day) - date(year, 1, 1)).days + 1


def test_normal_curve_last_point_equals_annual_normal_value(db):
    """3a.8 (design.md D3) -- the normal curve is the day-resolved form of
    the SAME aggregate ``annual.normal`` publishes, averaged over exactly its
    eligible-year set, so its last point must equal that value. It is keyed
    by ``(month, day)``: February 29 carries no curve point (22 of the 30
    baseline years do not have that day), but the rain that fell on it still
    accumulates inside the leap years' own running totals -- otherwise the
    last point could not match."""
    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a8-normal-curve"
    asset = asset_name_for("zone", scope_id)
    now = datetime(_CURVE_YEAR, 3, 2, 12, 0, tzinfo=UTC)  # comparison_end = Mar 2

    for baseline_year in range(1991, 2021):
        persist_intervals(
            db,
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            rows=_daily_rows(
                date(baseline_year, 1, 1), _days_through(_CURVE_CUTOFF, baseline_year), 1.0
            ),
        )
    selected_days = _days_through(_CURVE_CUTOFF, _CURVE_YEAR)
    assert selected_days == 62  # 31 + 29 + 2
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(
            date(_CURVE_YEAR, 1, 1), selected_days, 3.0, provider_revision=_ZONE_FAMILY
        ),
    )
    revision = _build_revision(db, scope_id=scope_id, year=_CURVE_YEAR, now=now)
    normal = revision.snapshot["annual"]["normal"]
    assert normal["state"] == "available"

    series = build_series(db, revision)
    points = {point["date"]: point for point in series["points"]}

    # 22 non-leap years reach 61 mm by Mar 2, 8 leap years reach 62.
    expected_normal = ((30 - _LEAP_BASELINE_YEARS) * 61.0 + _LEAP_BASELINE_YEARS * 62.0) / 30
    assert normal["value"] == pytest.approx(expected_normal)
    # LI3A-001: the acceptance rule below is now also a runtime structural
    # check, so a served curve says so.
    assert series["normal_curve_state"] == "available"
    last = points["2024-03-02"]
    assert last["normal_accumulated"] == pytest.approx(normal["value"])
    assert last["accumulated"] == pytest.approx(revision.snapshot["annual"]["selected"]["value"])

    # February 29 is a real day of the SELECTED year and is reported as one;
    # it simply has no baseline normal to compare against.
    feb29 = points["2024-02-29"]
    assert feb29["mm"] == pytest.approx(3.0)
    assert feb29["state"] == "available"
    assert feb29["normal_accumulated"] is None

    # ... and the leap day's own baseline rain is NOT dropped: every year is
    # at 59 mm by Feb 28, while by Mar 1 the 8 leap years are one day ahead.
    assert points["2024-02-28"]["normal_accumulated"] == pytest.approx(59.0)
    assert points["2024-03-01"]["normal_accumulated"] == pytest.approx(
        ((30 - _LEAP_BASELINE_YEARS) * 60.0 + _LEAP_BASELINE_YEARS * 61.0) / 30
    )


def test_no_normal_curve_when_the_baseline_is_suppressed(db):
    """Counterexample to 3a.8: with no baseline persisted, ``annual.normal``
    suppresses -- and the curve must be ABSENT rather than a mean over the
    empty set, which would draw a flat zero line beside a real year.

    LI3A-001: absent for that reason is ``"suppressed"``, which the response
    reports DISTINCTLY from ``"integrity_refused"``. Both render as
    ``normal_accumulated: null``, so without the state field an operator
    cannot tell an honest absence from a refused lie."""
    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a8-no-baseline"
    year = 2025
    now = datetime(year, 1, 21, 12, 0, tzinfo=UTC)
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(date(year, 1, 1), 20, 2.0, provider_revision=_ZONE_FAMILY),
    )
    revision = _build_revision(db, scope_id=scope_id, year=year, now=now)
    assert revision.snapshot["annual"]["normal"]["state"] == "suppressed"

    series = build_series(db, revision)

    assert all(point["normal_accumulated"] is None for point in series["points"])
    assert series["normal_curve_state"] == "suppressed"


# ---------------------------------------------------------------------------
# LI3A-001: the curve must not be able to lie while the pin stamps consistent
# ---------------------------------------------------------------------------


def _seed_full_baseline(db, *, asset: str, cutoff: date) -> None:
    """1991-2020 daily baseline at 1.0 mm/day through *cutoff*'s month/day."""
    for baseline_year in range(1991, 2021):
        persist_intervals(
            db,
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            rows=_daily_rows(date(baseline_year, 1, 1), _days_through(cutoff, baseline_year), 1.0),
        )


def _curve_refusal_event(caplog) -> dict:
    """The single ``rainfall.series.normal_curve_refused`` payload."""
    import json

    payloads = [
        json.loads(record.getMessage().split(" ", 1)[1])
        for record in caplog.records
        if record.getMessage().startswith("rainfall.series.normal_curve_refused ")
    ]
    assert len(payloads) == 1, payloads
    return payloads[0]


def test_a_duplicated_baseline_slot_refuses_the_curve_instead_of_inflating_it(db, caplog):
    """LI3A-001, the sibling guard: ``baseline_cumulatives`` REFUSES a
    duplicated ``interval_start`` (LI2A-005/LI2B-004) because a duplicate
    inflates the total while hiding itself. ``baseline_curve_rows`` reads the
    same rows through the same anti-join and simply summed them into the
    curve, so a duplicate that lands AFTER a revision is stored inflates the
    chart's normal line while the card's ``annual.normal.value`` -- computed
    once, at build time -- stays put. Nothing rebuilds a finalized past year,
    so that disagreement is permanent, and the pin would still stamp
    ``consistent_with_snapshot: true`` because it hashes only the SELECTED
    scope's intervals, not the baseline's."""
    import logging

    from app.domains.geo.rainfall.models import RainfallIntervalValue
    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-li3a001-duplicate-baseline"
    asset = asset_name_for("zone", scope_id)
    now = datetime(_CURVE_YEAR, 3, 2, 12, 0, tzinfo=UTC)
    _seed_full_baseline(db, asset=asset, cutoff=_CURVE_CUTOFF)
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(
            date(_CURVE_YEAR, 1, 1),
            _days_through(_CURVE_CUTOFF, _CURVE_YEAR),
            3.0,
            provider_revision=_ZONE_FAMILY,
        ),
    )
    revision = _build_revision(db, scope_id=scope_id, year=_CURVE_YEAR, now=now)
    stored_normal = revision.snapshot["annual"]["normal"]
    assert stored_normal["state"] == "available"
    clean = build_series(db, revision)
    assert clean["normal_curve_state"] == "available"

    # AFTER the build: a second non-superseded row for one baseline slot --
    # the residue of a correction whose supersession link never landed (the
    # same shape LI2B-004's fixture plants).
    duplicated_day = datetime(1991, 1, 5, tzinfo=UTC)
    db.add(
        RainfallIntervalValue(
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            interval_start=duplicated_day,
            interval_end=duplicated_day + timedelta(days=1),
            provider_revision="v3-final+r1",
            value=500.0,
            unit="mm",
        )
    )
    db.flush()

    caplog.set_level(logging.INFO, logger="rainfall")
    series = build_series(db, revision)

    # Refused, and refused DISTINCTLY from an honest absence.
    assert series["normal_curve_state"] == "integrity_refused"
    assert all(point["normal_accumulated"] is None for point in series["points"])
    event = _curve_refusal_event(caplog)
    assert event["reason"] == "duplicate_baseline_slot"
    assert event["revision_id"] == str(revision.id)

    # Nothing else moves: the stored card value, the selected-year points and
    # the pin are all untouched -- the baseline store is not what the pin
    # hashes, which is exactly why the curve needed its own guard.
    assert revision.snapshot["annual"]["normal"]["value"] == pytest.approx(stored_normal["value"])
    assert [point["accumulated"] for point in series["points"]] == [
        point["accumulated"] for point in clean["points"]
    ]
    assert series["consistent_with_snapshot"] is True
    assert series["consistency_reason"] is None


def test_a_curve_that_disagrees_with_the_stored_normal_is_refused(db, caplog):
    """LI3A-001, the acceptance cross-check on its own: design.md D3's rule is
    that the curve's last point EQUALS ``annual.normal.value``. That was an
    acceptance criterion checked by one test on one fixture; here it becomes a
    runtime structural check, so ANY future divergence -- a cutoff drift, a
    baseline row superseded after the build, a fourth defect nobody has found
    yet -- refuses the curve instead of drawing a line that contradicts the
    card it sits beside."""
    import logging

    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-li3a001-crosscheck"
    asset = asset_name_for("zone", scope_id)
    now = datetime(_CURVE_YEAR, 3, 2, 12, 0, tzinfo=UTC)
    _seed_full_baseline(db, asset=asset, cutoff=_CURVE_CUTOFF)
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(
            date(_CURVE_YEAR, 1, 1),
            _days_through(_CURVE_CUTOFF, _CURVE_YEAR),
            3.0,
            provider_revision=_ZONE_FAMILY,
        ),
    )
    revision = _build_revision(db, scope_id=scope_id, year=_CURVE_YEAR, now=now)

    # A stored row is append-only and ORM-guarded against update, so the
    # corrupted envelope is injected through the same revision-shaped
    # stand-in the runaway-window test uses -- with the REAL `data_revision`,
    # so the pin still passes and the two checks are provably independent.
    corrupted = {**revision.snapshot}
    annual = {**corrupted["annual"]}
    normal = {**annual["normal"]}
    normal["value"] = normal["value"] + 10.0
    annual["normal"] = normal
    corrupted["annual"] = annual

    caplog.set_level(logging.INFO, logger="rainfall")
    series = build_series(db, _fake_revision(corrupted, data_revision=revision.data_revision))

    assert series["normal_curve_state"] == "integrity_refused"
    assert all(point["normal_accumulated"] is None for point in series["points"])
    assert _curve_refusal_event(caplog)["reason"] == "last_point_disagrees_with_stored_normal"
    # The pin speaks about the SELECTED scope and is unaffected: one response
    # can honestly carry a valid pin and a refused curve at the same time.
    assert series["consistent_with_snapshot"] is True


# ---------------------------------------------------------------------------
# Counterexample self-check: absence, boundaries, session time zone, and a
# snapshot too broken to illustrate
# ---------------------------------------------------------------------------


def test_window_before_the_first_published_day_has_no_cumulative(db):
    """Absence: the disclosure window opens on January 1 whether or not the
    provider published that day. A leading unpublished stretch carries NO
    cumulative -- ``null``, not ``0.0``, which a chart would draw as a real
    dry start to the year."""
    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a-late-start"
    year = 2025
    now = datetime(year, 1, 21, 12, 0, tzinfo=UTC)
    _persist_zone_rows(  # nothing before Jan 6
        db,
        scope_id=scope_id,
        rows=_daily_rows(date(year, 1, 6), 15, 2.0, provider_revision=_ZONE_FAMILY),
    )
    revision = _build_revision(db, scope_id=scope_id, year=year, now=now)

    points = build_series(db, revision)["points"]

    assert [point["date"] for point in points[:5]] == [f"2025-01-0{day}" for day in range(1, 6)]
    assert all(point["mm"] is None for point in points[:5])
    assert all(point["accumulated"] is None for point in points[:5])
    assert all(point["state"] == "unavailable" for point in points[:5])
    assert points[5]["accumulated"] == pytest.approx(2.0)


def test_no_resolved_rows_report_ambiguous_rather_than_guessing_a_family(db):
    """Absence, at the pin: with nothing left to read, the build's revision
    FAMILY cannot be reconstructed at all (the build took it from the adapter
    batch, which no longer exists). "Not exactly one family" covers zero as
    well as two, so this reports inconsistent with its own reason instead of
    guessing a family and producing a digest that might accidentally match."""
    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a-no-rows"
    year = 2025
    now = datetime(year, 1, 21, 12, 0, tzinfo=UTC)
    revision = _build_revision(db, scope_id=scope_id, year=year, now=now)
    assert revision.snapshot["annual"]["selected"]["state"] == "unavailable"

    series = build_series(db, revision)

    assert series["consistent_with_snapshot"] is False
    assert series["consistency_reason"] == "interval_family_ambiguous"
    # The window is still disclosed honestly: every day of it, all empty.
    assert len(series["points"]) == 21  # Jan 1 .. Jan 21, the calendar end
    assert all(point["mm"] is None for point in series["points"])


def test_series_dates_do_not_shift_under_a_non_utc_session_timezone(db):
    """Time/state: ``psycopg2`` renders a ``timestamptz`` in the SESSION's
    zone, so bucketing days off the returned datetime is session-TZ-dependent
    unless it is normalized -- the same defect class as LI1-002's
    ``date_part`` grouping, which shifted a January 1 boundary row into the
    previous year under UTC-3."""
    from sqlalchemy import text

    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a-session-tz"
    year = 2025
    now = datetime(year, 1, 21, 12, 0, tzinfo=UTC)
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(date(year, 1, 1), 20, 2.0, provider_revision=_ZONE_FAMILY),
    )
    revision = _build_revision(db, scope_id=scope_id, year=year, now=now)

    # Session-scoped, reverted by the `db` fixture's own rollback.
    db.execute(text("SET TIME ZONE 'America/Argentina/Buenos_Aires'"))
    points = build_series(db, revision)["points"]

    assert points[0]["date"] == "2025-01-01"
    assert points[-1]["date"] == "2025-01-20"
    assert all(point["state"] == "available" for point in points)


def test_baseline_cutoff_does_not_shift_under_a_non_utc_session_timezone(db):
    """Time/state, on the COMPUTE side (LI3A-005): ``compute._cutoff_date``
    reads the last covered day off ``window_end``, which under provider lag is
    ``max(interval_end)`` -- a value ``psycopg2`` renders in the SESSION's
    zone. Taking ``.date()`` of it under UTC-3 lands a day early, so the
    baseline is cut one day before the day the selected year actually reaches.

    The visible symptom is the acceptance rule itself: the normal curve
    (cut at the series' own UTC-normalized end) no longer meets
    ``annual.normal.value`` (cut at the build's shifted end). Latent in
    production only because the deployment's Postgres runs UTC.
    """
    from sqlalchemy import text

    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a-compute-tz"
    asset = asset_name_for("zone", scope_id)
    cutoff = date(_CURVE_YEAR, 3, 2)
    now = datetime(_CURVE_YEAR, 3, 5, 12, 0, tzinfo=UTC)  # comparison_end = Mar 5

    # The session zone is set BEFORE the build, so the BUILD reads its
    # intervals rendered at UTC-3 -- unlike the series-side test above, which
    # only shifts the read path.
    db.execute(text("SET TIME ZONE 'America/Argentina/Buenos_Aires'"))

    for baseline_year in range(1991, 2021):
        persist_intervals(
            db,
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            rows=_daily_rows(date(baseline_year, 1, 1), _days_through(cutoff, baseline_year), 1.0),
        )
    # Published only through Mar 2 while the calendar end is Mar 5: the 3-day
    # lag is what makes `window_end` come from the database instead of from
    # Python's own UTC-constructed calendar end.
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(
            date(_CURVE_YEAR, 1, 1),
            _days_through(cutoff, _CURVE_YEAR),
            3.0,
            provider_revision=_ZONE_FAMILY,
        ),
    )
    revision = _build_revision(db, scope_id=scope_id, year=_CURVE_YEAR, now=now)
    normal = revision.snapshot["annual"]["normal"]
    assert normal["state"] == "available"

    series = build_series(db, revision)
    points = series["points"]

    # 22 non-leap years reach 61 mm by Mar 2, 8 leap years reach 62 -- the same
    # arithmetic as 3a.8. A cutoff shifted one day early yields 60/61 instead.
    expected_normal = ((30 - _LEAP_BASELINE_YEARS) * 61.0 + _LEAP_BASELINE_YEARS * 62.0) / 30
    assert normal["value"] == pytest.approx(expected_normal)
    assert points[-1]["date"] == "2024-03-02"
    assert points[-1]["normal_accumulated"] == pytest.approx(normal["value"])


def _fake_revision(snapshot: dict, *, data_revision: str = "d" * 64):
    """A revision-shaped stand-in for states a REAL row cannot reach: rows are
    append-only and rejected by an ORM guard on update (models.py), so a
    corrupt or runaway envelope cannot be produced by writing one."""
    from types import SimpleNamespace
    from uuid import uuid4

    return SimpleNamespace(id=uuid4(), data_revision=data_revision, snapshot=snapshot)


def test_a_runaway_disclosure_window_is_clamped_to_the_analysis_year(db):
    """Boundary: the day loop is driven by the snapshot's own
    ``available_through``, so a nonsense value must not turn a chart request
    into an unbounded loop. A disclosure window can never legitimately outrun
    the analysis year, and the clamp says so."""
    from app.domains.geo.rainfall.series import build_series

    scope_id = "zone-3a-runaway-window"
    year = 2025
    now = datetime(year, 1, 21, 12, 0, tzinfo=UTC)
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(date(year, 1, 1), 20, 2.0, provider_revision=_ZONE_FAMILY),
    )
    stored = _build_revision(db, scope_id=scope_id, year=year, now=now)
    runaway = {**stored.snapshot}
    selected = {**runaway["annual"]["selected"]}
    selected["provenance"] = {
        **selected["provenance"],
        "available_through": "3000-01-01T00:00:00+00:00",
    }
    runaway["annual"] = {**runaway["annual"], "selected": selected}

    points = build_series(db, _fake_revision(runaway))["points"]

    assert len(points) == 365  # 2025, the analysis year, and not one day more
    assert points[-1]["date"] == "2025-12-31"


def test_a_snapshot_too_broken_to_describe_itself_is_refused_not_charted(db):
    """Partial failure: a stored envelope the router would already 503 on
    must not be illustrated with a chart built from guesses. The series
    refuses with the same ``SnapshotContractError`` the CSV export raises, and
    the route maps it to the same 503 rather than a 500."""
    from app.domains.geo.rainfall.repository import RainfallRepository
    from app.domains.geo.rainfall.series import build_series
    from app.domains.geo.rainfall.service import SnapshotContractError

    broken = _fake_revision({"scope": {"kind": "zone", "id": "z", "version": "v1"}, "year": 2025})

    with pytest.raises(SnapshotContractError):
        build_series(db, broken)

    original = RainfallRepository.get_revision
    try:
        RainfallRepository.get_revision = lambda self, session, revision_id: broken
        response = _rainfall_client(db).get(f"/rainfall/analyses/{broken.id}/series")
    finally:
        RainfallRepository.get_revision = original

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# 3a.13: the route
# ---------------------------------------------------------------------------


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


def test_series_route_serves_the_pin_and_404s_on_an_unknown_revision(db):
    """3a.13 -- resolved from the revision id, so it inherits the CSV route's
    404 semantics; the response carries the two deterministic pin fields and
    the three echoes the client cross-checks against its own snapshot."""
    from uuid import uuid4

    scope_id = "zone-3a13-route"
    year = 2025
    now = datetime(year, 1, 21, 12, 0, tzinfo=UTC)
    _persist_zone_rows(
        db,
        scope_id=scope_id,
        rows=_daily_rows(date(year, 1, 1), 20, 2.0, provider_revision=_ZONE_FAMILY),
    )
    revision = _build_revision(db, scope_id=scope_id, year=year, now=now)
    client = _rainfall_client(db)

    response = client.get(f"/rainfall/analyses/{revision.id}/series")

    assert response.status_code == 200
    body = response.json()
    assert body["consistent_with_snapshot"] is True
    assert body["consistency_reason"] is None
    assert body["data_revision"] == revision.data_revision
    assert body["comparison_end"] == "2025-01-21"
    assert body["available_through"] == datetime(year, 1, 21, tzinfo=UTC).isoformat()
    assert body["year"] == year
    assert body["scope"] == revision.snapshot["scope"]
    assert len(body["points"]) == 20

    assert client.get(f"/rainfall/analyses/{uuid4()}/series").status_code == 404


def test_series_route_requires_authentication():
    """3a.13 -- the route sits under the router-level
    ``require_admin_or_operator`` dependency, exactly like the CSV export it
    is modelled on; nothing about a series is public."""
    from uuid import uuid4

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.domains.geo.rainfall.router import router

    app = FastAPI()
    app.include_router(router)

    assert TestClient(app).get(f"/rainfall/analyses/{uuid4()}/series").status_code == 401


def test_series_served_event_is_documented_in_the_observability_workbook():
    """LI2B-005's rule, applied to this slice's own new event: metrics.py
    names the workbook as THE contract for what an event means, so an event
    that fires in production and appears nowhere in that catalogue is
    undocumented by construction."""
    from pathlib import Path

    workbook = (
        Path(__file__).resolve().parents[5] / "docs" / "lluvia-v2-observability-workbook.md"
    ).read_text(encoding="utf-8")

    assert "`rainfall.series.served`" in workbook
    assert "consistent_with_snapshot" in workbook
    # LI3A-001's refusal event, and the state field that makes an honest
    # absence distinguishable from a refused curve.
    assert "`rainfall.series.normal_curve_refused`" in workbook
    assert "normal_curve_state" in workbook
    assert "integrity_refused" in workbook
    # LI3A-002: the ambiguity row must describe BOTH shapes it fires for --
    # the zero-evidence revision (benign) and two live families (a
    # decision-7 invariant breach).
    assert "Zero resolved rows" in workbook
    assert "Two or more live families" in workbook
