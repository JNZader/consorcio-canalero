"""Integration coverage for slice 2a's new metrics (real PG): every new
metric has a policy threshold (D4), normal/percentile share the SAME
comparison_end annual.selected discloses (D4/D5), and antecedents.d90
suppresses -- not short-sums -- on an incomplete prior-year tail (D6).

Lluvia insights slice 2a: annual.normal/percentile + antecedents.d7/d30/d90.
"""

import hashlib
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION, asset_name_for
from app.domains.geo.rainfall.models import RainfallOutbox
from app.domains.geo.rainfall.ports import SourceInterval
from app.domains.geo.rainfall.repository import RainfallRepository, persist_intervals


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


def _build_outbox_and_batch(
    db, *, scope_id: str, year: int, source_id: str = "chirps-v3-sat", role: str = "daily"
):
    fingerprint = hashlib.sha256(f"fp-{scope_id}-{year}".encode()).hexdigest()
    outbox = RainfallOutbox(
        source_id=source_id,
        role=role,
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
        "source_id": source_id,
        "scope_kind": "zone",
        "scope_id": scope_id,
        "year": year,
        "intervals": 0,
        "persisted": 0,
        "superseded": 0,
        "provider_revision": "v3-nrt",
        "unit": "mm",
        "cadence_seconds": 86400.0,
        "coverage": 1.0,
        "completeness": 1.0,
        "quality": {"scale_m": 5500, "provider_revision": "v3-nrt"},
        "discrepancies": [],
        "checksum": f"sha256:fixture-{scope_id}",
    }
    return outbox, batch, fingerprint


def test_no_metric_suppressed_as_policy_threshold_unset(db):
    """2a.12 (spec: "Complete analysis has no unthresholded metric") --
    full-coverage analysis: every new metric is available, none suppressed
    as policy_threshold_unset."""
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY_REVISION
    from app.domains.geo.rainfall.service import normalize_snapshot

    scope_id = "zone-2a12-full-coverage"
    asset = asset_name_for("zone", scope_id)
    year = 2025

    # comparison_end = Apr 15 (day 105 of a non-leap year) -- far enough
    # into the year that antecedents.d90's window ([Jan 11, Apr 16)) stays
    # entirely inside it, keeping the fixture footprint small.
    now = datetime(year, 4, 15, 12, 0, tzinfo=UTC)
    comparison_end_exclusive = datetime(year, 4, 16, tzinfo=UTC)
    days_needed = (comparison_end_exclusive - datetime(year, 1, 1, tzinfo=UTC)).days

    # All 30 baseline years, complete through the SAME month/day -- well
    # above MIN_BASELINE_YEARS=20, and completeness=1.0 clears the 0.8
    # quality threshold (D4) with margin.
    for baseline_year in range(1991, 2021):
        persist_intervals(
            db,
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            rows=_daily_rows(date(baseline_year, 1, 1), days_needed, 5.0),
        )

    # The selected zone/year: full daily coverage through comparison_end.
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=_daily_rows(date(year, 1, 1), days_needed, 3.0, provider_revision="v3-nrt"),
    )
    db.flush()

    outbox, batch, fingerprint = _build_outbox_and_batch(db, scope_id=scope_id, year=year)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    normalized = normalize_snapshot(
        revision.snapshot, expected_policy_revision=RAINFALL_METRIC_POLICY_REVISION
    )

    checked = {
        "annual.normal": normalized["annual"]["normal"],
        "annual.percentile": normalized["annual"]["percentile"],
        "antecedents.d7": normalized["antecedents"]["d7"],
        "antecedents.d30": normalized["antecedents"]["d30"],
        "antecedents.d90": normalized["antecedents"]["d90"],
    }
    for name, metric in checked.items():
        assert metric["reason"] != "policy_threshold_unset", (name, metric)
        assert metric["state"] == "available", (name, metric)


def test_normal_and_percentile_share_selected_comparison_end(db):
    """2a.13: annual.normal/percentile's baseline windows are cut off at
    EXACTLY the same comparison_end date annual.selected discloses -- data
    persisted AFTER that date must not leak into the baseline average."""
    from app.domains.geo.rainfall import tasks

    scope_id = "zone-2a13-shared-cutoff"
    asset = asset_name_for("zone", scope_id)
    year = 2025
    now = datetime(year, 1, 20, 12, 0, tzinfo=UTC)  # comparison_end = Jan 20
    # Jan 20 is BEFORE Feb 29 in every calendar -- the cutoff day-count is
    # exactly 20 for every baseline year regardless of which are leap
    # years, so a single constant is genuinely correct here (unlike a
    # later-month cutoff, which would need a per-year leap adjustment).
    cutoff_days = 20  # Jan 1 .. Jan 20 inclusive

    for baseline_year in range(1991, 2021):
        # Cutoff-window data (counted) ...
        persist_intervals(
            db,
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            rows=_daily_rows(date(baseline_year, 1, 1), cutoff_days, 5.0),
        )
        # ... + a deliberately huge tail AFTER the cutoff date, which must
        # NOT be counted if normal genuinely shares annual.selected's cutoff.
        persist_intervals(
            db,
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            rows=_daily_rows(date(baseline_year, 1, 1) + timedelta(days=cutoff_days), 5, 1000.0),
        )

    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=_daily_rows(date(year, 1, 1), cutoff_days, 3.0, provider_revision="v3-nrt"),
    )
    db.flush()

    outbox, batch, fingerprint = _build_outbox_and_batch(db, scope_id=scope_id, year=year)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    snapshot = revision.snapshot

    assert snapshot["comparison_end"] == date(year, 1, 20).isoformat()
    normal = snapshot["annual"]["normal"]
    # Exactly the cutoff-window sum -- the post-cutoff 1000.0/day tail did
    # NOT leak into the baseline average.
    assert normal["value"] == pytest.approx(5.0 * cutoff_days)
    assert normal["state"] == "available"


def test_d90_suppressed_with_reason_when_prior_year_incomplete(db):
    """2a.14: comparison_end early in the year makes d90's window reach
    into the PRIOR year (D6); if that prior-year tail is incomplete, d90
    suppresses with its own reason -- never a short sum -- while d7 (fully
    inside the current year) stays available."""
    from app.domains.geo.rainfall import tasks

    scope_id = "zone-2a14-prior-year-gap"
    year = 2025
    now = datetime(year, 1, 20, 12, 0, tzinfo=UTC)  # comparison_end = Jan 20, 2025

    # This year's own data: complete Jan 1 - Jan 20.
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=_daily_rows(date(year, 1, 1), 20, 1.0, provider_revision="v3-nrt"),
    )
    # Prior year's tail: d90's window needs ~Oct 23, 2024 .. Dec 31, 2024
    # (the D6-widened read reaches back to Oct 3, 2024); persist a generous
    # over-cover of it, EXCEPT one day -- a genuine gap inside the window.
    prior_tail = _daily_rows(date(year - 1, 10, 1), 92, 1.0, provider_revision="v3-final")
    del prior_tail[45]  # Nov 15, 2024 -- squarely inside the needed window
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=prior_tail,
    )
    db.flush()

    outbox, batch, fingerprint = _build_outbox_and_batch(db, scope_id=scope_id, year=year)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    snapshot = revision.snapshot

    d90 = snapshot["antecedents"]["d90"]
    assert d90["state"] == "suppressed"
    assert d90["value"] is None
    assert d90["reason"] == "antecedent_window_incomplete"

    d7 = snapshot["antecedents"]["d7"]
    assert d7["state"] == "available"
    assert d7["value"] == pytest.approx(7.0)

    # LI2A-001: D6's "annual.selected provably unaffected by the widened
    # read" claim, pinned by assertion rather than by argument. The 91
    # prior-year rows persisted above are inside the D6-widened READ window
    # but outside `build_snapshot`'s own `in_window` filter, so the annual
    # total must stay exactly the 20 current-year days at 1.0mm, at
    # completeness 1.0 (window_end == last_interval_end == Jan 21).
    selected = snapshot["annual"]["selected"]
    assert selected["state"] == "available"
    assert selected["value"] == pytest.approx(20.0)
    assert selected["completeness"] == pytest.approx(1.0)


def test_antecedents_clip_to_last_available_interval_under_provider_lag(db):
    """LI2A-002: the provider lags behind the calendar by design, so the
    antecedent window anchors at ``min(comparison_end, last_interval_end)``
    -- the SAME clip ``annual.selected`` already applies -- never at a
    calendar day nobody has published yet. Anchored rigidly at
    comparison_end, `temporal.rolling_total`'s exact-slot-set check would
    suppress every antecedent on every current-year build, since the slot
    for "today" does not exist while the provider lags."""
    from app.domains.geo.rainfall import tasks

    scope_id = "zone-li2a002-lagged-tail"
    year = 2025
    now = datetime(year, 4, 15, 12, 0, tzinfo=UTC)  # comparison_end = Apr 15
    # Published only through Apr 12 -- a 3-day provider lag, the documented
    # steady state (design.md D6 amendment).
    days_persisted = (date(year, 4, 12) - date(year, 1, 1)).days + 1  # Jan 1 .. Apr 12
    assert days_persisted == 102

    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=_daily_rows(date(year, 1, 1), days_persisted, 2.0, provider_revision="v3-nrt"),
    )
    db.flush()

    outbox, batch, fingerprint = _build_outbox_and_batch(db, scope_id=scope_id, year=year)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    snapshot = revision.snapshot

    # The disclosed comparison_end stays the CALENDAR date (owner decision:
    # calendar comparison_end + available_through disclosure) ...
    assert snapshot["comparison_end"] == date(year, 4, 15).isoformat()
    # ... while the effective end -- the last published day's interval_end,
    # Apr 13T00:00Z -- is what the antecedent windows and their
    # available_through actually disclose.
    end_effective = datetime(year, 4, 13, tzinfo=UTC)

    for name, days in (("d7", 7), ("d30", 30), ("d90", 90)):
        metric = snapshot["antecedents"][name]
        assert metric["state"] == "available", (name, metric)
        assert metric["value"] == pytest.approx(2.0 * days), (name, metric)
        assert metric["reason"] is None, (name, metric)
        assert metric["interval_end"] == end_effective.isoformat(), (name, metric)
        assert metric["interval_start"] == (end_effective - timedelta(days=days)).isoformat(), (
            name,
            metric,
        )
        # The honest availability disclosure: the clipped end, never the
        # calendar comparison_end the provider has not reached.
        assert metric["provenance"]["available_through"] == end_effective.isoformat(), (
            name,
            metric,
        )

    # annual.selected is measured over the same clipped window and is
    # unaffected by the antecedent anchor change.
    selected = snapshot["annual"]["selected"]
    assert selected["state"] == "available"
    assert selected["value"] == pytest.approx(2.0 * days_persisted)
    assert selected["completeness"] == pytest.approx(1.0)
    assert selected["provenance"]["available_through"] == end_effective.isoformat()


def test_antecedent_gap_inside_the_clipped_window_still_suppresses(db):
    """LI2A-002 counterexample: clipping the anchor must NOT soften the
    exact-slot-set check. A genuine hole INSIDE the clipped window still
    suppresses with ``antecedent_window_incomplete`` -- never a short sum
    -- while a longer window unaffected by that hole stays available."""
    from app.domains.geo.rainfall import tasks

    scope_id = "zone-li2a002-clipped-gap"
    year = 2025
    now = datetime(year, 4, 15, 12, 0, tzinfo=UTC)  # comparison_end = Apr 15
    days_persisted = (date(year, 4, 12) - date(year, 1, 1)).days + 1  # Jan 1 .. Apr 12

    rows = _daily_rows(date(year, 1, 1), days_persisted, 2.0, provider_revision="v3-nrt")
    # Apr 9 -- squarely inside the clipped d7 window [Apr 6, Apr 13).
    gap_day = date(year, 4, 9)
    rows = [row for row in rows if row.interval_start.date() != gap_day]
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=rows,
    )
    db.flush()

    outbox, batch, fingerprint = _build_outbox_and_batch(db, scope_id=scope_id, year=year)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    snapshot = revision.snapshot

    d7 = snapshot["antecedents"]["d7"]
    assert d7["state"] == "suppressed"
    assert d7["value"] is None
    assert d7["reason"] == "antecedent_window_incomplete"
    # The gap is inside d30/d90's windows too -- the exact-slot-set check is
    # window-wide, so both suppress for the same reason rather than
    # short-summing around the hole.
    for name in ("d30", "d90"):
        metric = snapshot["antecedents"][name]
        assert metric["state"] == "suppressed", (name, metric)
        assert metric["reason"] == "antecedent_window_incomplete", (name, metric)


# ---------------------------------------------------------------------------
# LI2A-101 (slice 2b amendment A1): the baseline comparison is cut at the
# SAME effective end annual.selected totals through, not at the raw calendar
# comparison_end. Both fixtures below deliberately avoid February 29 (the
# whole window sits inside Jan 1 - Feb 20), so every baseline year -- leap or
# not -- has exactly the same day count and the expected totals are
# year-invariant arithmetic rather than a per-year leap adjustment.
# ---------------------------------------------------------------------------

_A1_LOW_YEARS = range(1991, 2006)  # 15 baseline years at 1.0 mm/day
_A1_HIGH_YEARS = range(2006, 2021)  # 15 baseline years at 5.0 mm/day
_A1_DAYS_TO_FEB_17 = 48  # Jan 1 .. Feb 17 inclusive, in EVERY year
_A1_TAIL_DAYS = 3  # Feb 18, 19, 20 -- past a 3-day-lagged effective end
_A1_TAIL_VALUE = 1000.0  # deliberately huge: leaking it is unmissable


def _seed_a1_baseline(db, *, asset: str) -> None:
    """30 baseline years, each complete Jan 1 - Feb 17 at its own tier value,
    plus a Feb 18-20 tail so heavy that including it dwarfs everything else."""
    for years, value in ((_A1_LOW_YEARS, 1.0), (_A1_HIGH_YEARS, 5.0)):
        for baseline_year in years:
            persist_intervals(
                db,
                source_id="chirps-v3-final",
                scope_kind="provider_asset",
                scope_id=asset,
                scope_version=BASELINE_ASSET_VERSION,
                rows=_daily_rows(date(baseline_year, 1, 1), _A1_DAYS_TO_FEB_17, value),
            )
            persist_intervals(
                db,
                source_id="chirps-v3-final",
                scope_kind="provider_asset",
                scope_id=asset,
                scope_version=BASELINE_ASSET_VERSION,
                rows=_daily_rows(date(baseline_year, 2, 18), _A1_TAIL_DAYS, _A1_TAIL_VALUE),
            )


def test_baseline_is_cut_at_the_effective_end_not_the_calendar_comparison_end(db):
    """LI2A-101 (amendment A1): under provider lag -- the documented steady
    state -- ``annual.selected`` totals through the CLIPPED window end while
    the baseline used to be cut at the raw calendar ``comparison_end``. That
    ranks a short selected year against full-through-today baselines and
    biases the percentile low, violating D5's own same-date principle. The
    baseline cutoff now follows the same effective end the selected total
    uses."""
    from app.domains.geo.rainfall import tasks

    scope_id = "zone-a1-lagged-baseline-cutoff"
    asset = asset_name_for("zone", scope_id)
    year = 2025
    now = datetime(year, 2, 20, 12, 0, tzinfo=UTC)  # comparison_end = Feb 20

    _seed_a1_baseline(db, asset=asset)
    # The selected year lags 3 days behind the calendar: published through
    # Feb 17, so window_end == Feb 18T00:00Z and the effective end is Feb 17.
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=_daily_rows(date(year, 1, 1), _A1_DAYS_TO_FEB_17, 2.0, provider_revision="v3-nrt"),
    )
    db.flush()

    outbox, batch, fingerprint = _build_outbox_and_batch(db, scope_id=scope_id, year=year)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    snapshot = revision.snapshot

    # The DISCLOSED comparison_end stays the calendar date (the owner's
    # 2026-08-08 decision, unchanged) -- only the cutoff the comparison is
    # actually made at follows the evidence.
    assert snapshot["comparison_end"] == date(year, 2, 20).isoformat()

    selected = snapshot["annual"]["selected"]
    assert selected["value"] == pytest.approx(2.0 * _A1_DAYS_TO_FEB_17)  # 96.0
    assert (
        selected["provenance"]["available_through"] == datetime(year, 2, 18, tzinfo=UTC).isoformat()
    )

    # Baseline totals through Feb 17: 48 x 1.0 = 48.0 (15 years) and
    # 48 x 5.0 = 240.0 (15 years) -> mean 144.0. Cut at the CALENDAR Feb 20
    # instead, every year would also carry the 3 x 1000.0 tail (3048.0 /
    # 3240.0 -> mean 3144.0).
    normal = snapshot["annual"]["normal"]
    assert normal["state"] == "available"
    assert normal["value"] == pytest.approx(144.0)

    # The rank is the load-bearing half: against Feb-17 baselines the
    # selected 96.0 sits 16th of the 31-value combined sample -> exactly the
    # median, 100 * 16 / 32. Against calendar-Feb-20 baselines (every one of
    # them >= 3048.0) it would rank LAST, 100 * 1 / 32 = 3.125 -- the low
    # bias this amendment exists to remove.
    percentile = snapshot["annual"]["percentile"]
    assert percentile["state"] == "available"
    assert percentile["value"] == pytest.approx(50.0)

    # The disclosed baseline envelope ends at the same effective cutoff.
    expected_envelope_end = datetime(2020, 2, 18, tzinfo=UTC).isoformat()
    assert normal["interval_end"] == expected_envelope_end
    assert normal["provenance"]["available_through"] == expected_envelope_end
    assert percentile["interval_end"] == expected_envelope_end


def test_baseline_cutoff_equals_the_calendar_comparison_end_when_there_is_no_lag(db):
    """A1's no-regression half: with the provider caught up,
    ``window_end == comparison_end_exclusive``, so the effective cutoff IS
    the calendar ``comparison_end`` and the baseline behaves exactly as it
    did before the amendment -- the tail through Feb 20 is counted."""
    from app.domains.geo.rainfall import tasks

    scope_id = "zone-a1-no-lag-baseline-cutoff"
    asset = asset_name_for("zone", scope_id)
    year = 2025
    now = datetime(year, 2, 20, 12, 0, tzinfo=UTC)  # comparison_end = Feb 20
    days_to_feb_20 = _A1_DAYS_TO_FEB_17 + _A1_TAIL_DAYS  # 51, in every year

    _seed_a1_baseline(db, asset=asset)
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=_daily_rows(date(year, 1, 1), days_to_feb_20, 2.0, provider_revision="v3-nrt"),
    )
    db.flush()

    outbox, batch, fingerprint = _build_outbox_and_batch(db, scope_id=scope_id, year=year)
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=now)

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    snapshot = revision.snapshot

    selected = snapshot["annual"]["selected"]
    assert selected["value"] == pytest.approx(2.0 * days_to_feb_20)  # 102.0
    assert (
        selected["provenance"]["available_through"] == datetime(year, 2, 21, tzinfo=UTC).isoformat()
    )

    # Both tiers now include the 3 x 1000.0 tail: 3048.0 and 3240.0 -> 3144.0.
    normal = snapshot["annual"]["normal"]
    assert normal["state"] == "available"
    assert normal["value"] == pytest.approx(3144.0)
    assert normal["interval_end"] == datetime(2020, 2, 21, tzinfo=UTC).isoformat()

    percentile = snapshot["annual"]["percentile"]
    assert percentile["value"] == pytest.approx(100 * 1 / 32)
