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

    # Enumerated over the SERVED envelope rather than a hand-written list
    # (SDD lluvia-antecedente-referencia task 4.4): the six antecedent
    # reference metrics joined this group in S2a, and the next key to join it
    # is covered here the day it is emitted rather than the day someone
    # remembers to extend a literal. `apply_metric_policy` suppresses any
    # metric absent from EITHER policy dict as `policy_threshold_unset`
    # (policy.py:163), so this loop is the disclosure-level enumeration of
    # both dicts.
    checked = {
        f"{group}.{name}": metric
        for group in ("annual", "antecedents")
        for name, metric in normalized[group].items()
    }
    assert set(checked) == {
        "annual.selected",
        "annual.normal",
        "annual.percentile",
        "antecedents.d7",
        "antecedents.d7_normal",
        "antecedents.d7_percentile",
        "antecedents.d30",
        "antecedents.d30_normal",
        "antecedents.d30_percentile",
        "antecedents.d90",
        "antecedents.d90_normal",
        "antecedents.d90_percentile",
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
    # Load-bearing for the Ops.6 evidence gate below: a trailing provider lag
    # leaves NOTHING missing inside the clipped window, so completeness is a
    # flat 1.0 and the rank keeps its full standing. Only an INTERNAL hole
    # (the block at the end of this module) shortens the total the percentile
    # ranks. If this assertion ever breaks, the lag clipping regressed -- the
    # evidence gate must not reach it.
    assert selected["completeness"] == pytest.approx(1.0)

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


# ---------------------------------------------------------------------------
# Ops.6 (archive-report.md 2026-08-11 §10): the percentile is coupled to the
# SELECTED year's own evidence inside the clipped window.
#
# `total_value` sums only the slots that are PRESENT, and `weibull_percentile`
# ranks that sum against COMPLETE baselines -- so a selected year holed in the
# middle is short by exactly those days' rain and ranks low for a reason that
# has nothing to do with rainfall. The trailing-lag half of this bias was
# already closed by LI2A-101 above (the window is clipped, so nothing is
# missing inside it); an INTERNAL hole produces the identical bias with no
# guard, and the two disclosure gates were decoupled -- `annual` thresholds on
# its own coverage while `annual_percentile` thresholds on the BASELINE's
# eligible-year fraction, a different quantity entirely -- so the rank
# outlived the total it ranks.
#
# One shared fixture, three evidence bands. The window is Jan 1 - Feb 20, so
# it sits entirely before February 29 and every baseline year -- leap or not
# -- has exactly the same 51-day span (same reason as the A1 block above).
#
# Baseline year 1991+j carries a flat 10.0 + 0.25*j mm/day, so its 51-day
# total is 510 + 12.75*j (510.0 .. 879.75, mean 694.875). The selected year
# carries 14.125 mm/day, a value that falls strictly BETWEEN two baseline
# tiers so no rank is ever decided by a tie. Every quantity here is a dyadic
# fraction, so the arithmetic is exact rather than approximately exact.
# ---------------------------------------------------------------------------

_GAP_YEAR = 2025
_GAP_NOW = datetime(_GAP_YEAR, 2, 20, 12, 0, tzinfo=UTC)  # comparison_end = Feb 20
_GAP_WINDOW_DAYS = 51  # Jan 1 .. Feb 20 inclusive, in EVERY year
_GAP_SELECTED_DAILY = 14.125
_GAP_BASELINE_MEAN = 694.875  # mean(510 + 12.75*j for j in range(30))


def _seed_gap_baseline(db, *, asset: str) -> None:
    for offset, baseline_year in enumerate(range(1991, 2021)):
        persist_intervals(
            db,
            source_id="chirps-v3-final",
            scope_kind="provider_asset",
            scope_id=asset,
            scope_version=BASELINE_ASSET_VERSION,
            rows=_daily_rows(date(baseline_year, 1, 1), _GAP_WINDOW_DAYS, 10.0 + 0.25 * offset),
        )


def _seed_gap_evidence(db, *, scope_id: str, missing_days: int):
    """Seed the shared baseline plus a selected year whose window is complete
    at BOTH ends and holed in the middle, and return the
    ``(outbox, batch, fingerprint)`` a build for that key needs.

    The hole starts on February 1 and never touches January 1 or February 20,
    so ``window_end`` still lands on February 21 and ``expected_slots`` stays
    at the full 51: this is an evidence GAP, not the trailing provider lag
    LI2A-101 already clips for.
    """
    asset = asset_name_for("zone", scope_id)
    _seed_gap_baseline(db, asset=asset)

    rows = _daily_rows(
        date(_GAP_YEAR, 1, 1),
        _GAP_WINDOW_DAYS,
        _GAP_SELECTED_DAILY,
        provider_revision="v3-nrt",
    )
    gap_start = date(_GAP_YEAR, 2, 1)
    gap_end = gap_start + timedelta(days=missing_days)  # exclusive
    rows = [row for row in rows if not (gap_start <= row.interval_start.date() < gap_end)]
    assert len(rows) == _GAP_WINDOW_DAYS - missing_days
    persist_intervals(
        db,
        source_id="chirps-v3-sat",
        scope_kind="zone",
        scope_id=scope_id,
        scope_version="v1",
        rows=rows,
    )
    db.flush()

    return _build_outbox_and_batch(db, scope_id=scope_id, year=_GAP_YEAR)


def _materialize_with_internal_gap(db, *, scope_id: str, missing_days: int) -> tuple[dict, dict]:
    """Seed :func:`_seed_gap_evidence`, build the revision, and return
    ``(stored_snapshot, served_snapshot)``.

    Both snapshots are returned because the gate under test lives at BUILD
    time: the stored envelope is what every reader (JSON, audit CSV, xlsx)
    projects from, and the served one is what the policy finally discloses.
    """
    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY_REVISION
    from app.domains.geo.rainfall.service import normalize_snapshot

    outbox, batch, fingerprint = _seed_gap_evidence(
        db, scope_id=scope_id, missing_days=missing_days
    )
    tasks._persist_analysis_revision(db, outbox_id=str(outbox.id), batch=batch, now=_GAP_NOW)

    revision = RainfallRepository().get_snapshot(db, fingerprint)
    assert revision is not None
    return revision.snapshot, normalize_snapshot(
        revision.snapshot, expected_policy_revision=RAINFALL_METRIC_POLICY_REVISION
    )


def test_complete_selected_year_still_ranks(db):
    """The unchanged half: with every slot present the percentile is served
    exactly as before -- 720.375 mm outranks 17 of the 30 baseline totals, so
    it is the combined sample's 18th of 31 -> 100 * 18 / 32."""
    _stored, served = _materialize_with_internal_gap(
        db, scope_id="zone-ops6-complete", missing_days=0
    )

    selected = served["annual"]["selected"]
    assert selected["state"] == "available"
    assert selected["value"] == pytest.approx(_GAP_WINDOW_DAYS * _GAP_SELECTED_DAILY)  # 720.375
    assert selected["completeness"] == pytest.approx(1.0)

    normal = served["annual"]["normal"]
    assert normal["state"] == "available"
    assert normal["value"] == pytest.approx(_GAP_BASELINE_MEAN)

    percentile = served["annual"]["percentile"]
    assert percentile["state"] == "available"
    assert percentile["reason"] is None
    assert percentile["value"] == pytest.approx(56.25)  # 100 * 18 / 32


def test_ten_percent_internal_gap_suppresses_the_percentile_while_annual_survives(db):
    """The silent band. 5 of 51 days missing -> completeness 0.902, which
    CLEARS ``annual``'s own 0.8 gate, so the total is still disclosed. The
    percentile must not be: 46 days of rain (649.75 mm) ranked against
    51-day baselines lands at 100 * 12 / 32 = 37.5 -- roughly 19 points below
    the 56.25 the same year earns on complete evidence, with nothing
    suppressed and no caveat anywhere on the panel."""
    stored, served = _materialize_with_internal_gap(
        db, scope_id="zone-ops6-gap-10pct", missing_days=5
    )

    selected = served["annual"]["selected"]
    assert selected["state"] == "available"
    assert selected["value"] == pytest.approx(46 * _GAP_SELECTED_DAILY)  # 649.75
    assert selected["completeness"] == pytest.approx(46 / 51)

    # The normal is a pure baseline average -- it ranks nothing, so the
    # selected year's evidence cannot bias it and it stays available.
    normal = served["annual"]["normal"]
    assert normal["state"] == "available"
    assert normal["value"] == pytest.approx(_GAP_BASELINE_MEAN)

    percentile = served["annual"]["percentile"]
    assert percentile["state"] == "suppressed"
    assert percentile["value"] is None
    assert percentile["reason"] == "selected_evidence_below_threshold"

    # The gate belongs to `compute.build_snapshot`, so the STORED envelope
    # already carries the refusal: every reader of that revision -- JSON, the
    # audit CSV, the xlsx sheet -- projects the same suppression, and no
    # disclosure-time policy edit can resurrect a rank built on evidence that
    # was never good enough to rank.
    stored_percentile = stored["annual"]["percentile"]
    assert stored_percentile["state"] == "suppressed"
    assert stored_percentile["value"] is None
    assert stored_percentile["reason"] == "selected_evidence_below_threshold"


def test_twenty_one_percent_internal_gap_suppresses_the_percentile_with_the_total(db):
    """The loud band. 11 of 51 days missing -> completeness 0.784, below
    ``annual``'s 0.8 gate, so the total is suppressed as
    ``coverage_below_threshold``. The rank used to outlive it and report a
    normal year at 100 * 6 / 32 = 18.75 -- one of the driest on record --
    directly beside the admission that the underlying total was too
    incomplete to show."""
    _stored, served = _materialize_with_internal_gap(
        db, scope_id="zone-ops6-gap-21pct", missing_days=11
    )

    selected = served["annual"]["selected"]
    assert selected["state"] == "suppressed"
    assert selected["reason"] == "coverage_below_threshold"
    assert selected["completeness"] == pytest.approx(40 / 51)

    percentile = served["annual"]["percentile"]
    assert percentile["state"] == "suppressed"
    assert percentile["value"] is None
    assert percentile["reason"] == "selected_evidence_below_threshold"


def test_summary_narrates_the_suppressed_percentile_coherently(db):
    """The summary is derived from the states the policy actually served, so
    the coherence invariant carries the new reason for free: the percentile
    can never appear under ``Disponibles`` once its evidence gate refuses."""
    from app.domains.geo.rainfall.service import (
        SUMMARY_AVAILABLE_PREFIX,
        SUMMARY_METRIC_LABELS,
        SUMMARY_MISSING_PREFIX,
    )

    _stored, served = _materialize_with_internal_gap(
        db, scope_id="zone-ops6-summary", missing_days=5
    )
    summary = served["summary"]
    label = SUMMARY_METRIC_LABELS["percentile"]

    available_sentence, _, missing_sentence = summary.partition(SUMMARY_MISSING_PREFIX)
    assert available_sentence.startswith(SUMMARY_AVAILABLE_PREFIX)
    assert label not in available_sentence
    assert f"{label} (suprimida: selected_evidence_below_threshold)" in missing_sentence
    # The total itself cleared its own gate in this band, so the reader is
    # told the accumulation IS available -- which is exactly why a silently
    # biased rank beside it was the dangerous case.
    assert SUMMARY_METRIC_LABELS["selected"] in available_sentence


# ---------------------------------------------------------------------------
# PEG-001: the Ops.6 gate above is decided at BUILD time, so it reaches a
# reader only through a NEW revision row. `data_revision` hashes
# source/family/scope/year/comparison_end/intervals only -- it does NOT hash
# the envelope -- so on a key already materialized under the previous policy
# revision with unmoved evidence the corrected snapshot would hit
# `persist_revision`'s ON CONFLICT DO NOTHING and be discarded, permanently
# for a completed year (neither scheduled sweep revisits a past-year `done`
# key; only the request path notices, and only via the policy revision).
# `policy.RAINFALL_METRIC_POLICY_REVISION` is bumped for exactly that reason,
# and this is the test that the bump is what makes the correction land.
# ---------------------------------------------------------------------------

# The value RAINFALL_METRIC_POLICY_REVISION carried while the percentile was
# still ranked without an evidence gate. A literal on purpose: a future slice
# that changes the built envelope and forgets the bump must fail HERE rather
# than ship a correction the ON CONFLICT silently drops.
_PRE_OPS6_POLICY_REVISION = "rainfall-v2-2026-08-insights"

# What the pre-Ops.6 build served for the 5-of-51 band: 46 present days
# (649.75 mm) outrank 11 of the 30 baseline totals, so the sum is the combined
# sample's 12th of 31 -> 100 * 12 / 32. The same year on complete evidence
# earns 56.25, and that ~19-point gap IS the defect.
_GAP_BIASED_PERCENTILE = 37.5


def _as_pre_ops6_envelope(snapshot: dict) -> dict:
    """The corrected envelope rewritten as the PRE-Ops.6 build wrote it.

    Two edits, both required for the row to be a faithful incumbent. Every
    revision stamp moves to the superseded policy revision -- an older row is
    normalized with its OWN ``policy_revision`` and ``_normalize_metric``
    rejects any metric whose revision disagrees with it, so a half-restamped
    row would serve as ``policy_revision_mismatch`` and prove nothing. And
    ``annual.percentile`` goes back to ``available`` at the biased rank, which
    is the state the gate did not yet exist to refuse.
    """
    restamped = {
        **snapshot,
        "metric_policy": {**snapshot["metric_policy"], "revision": _PRE_OPS6_POLICY_REVISION},
    }
    for group in ("annual", "antecedents"):
        restamped[group] = {
            name: {**metric, "revision": _PRE_OPS6_POLICY_REVISION}
            for name, metric in snapshot[group].items()
        }
    restamped["annual"] = {
        **restamped["annual"],
        "percentile": {
            **restamped["annual"]["percentile"],
            "value": _GAP_BIASED_PERCENTILE,
            "state": "available",
            "reason": None,
        },
    }
    return restamped


def _pre_ops6_incumbent(db, *, scope_id: str, fingerprint: str, batch: dict) -> tuple[str, dict]:
    """INSERT the revision row the pre-Ops.6 build left behind for this key,
    and return its ``(data_revision, snapshot)``.

    The build inputs are re-derived here exactly as
    ``tasks._persist_analysis_revision`` derives them -- the D6-widened
    interval read, the baseline cut at the effective end, the same
    ``data_revision_for`` arguments -- because the point of the fixture is a
    row whose ``data_revision`` is EXACTLY the one the rebuild will recompute.
    If that duplication ever drifts from tasks.py the run ends with two
    DIFFERENT data revisions, which the caller asserts against.

    Written through a plain INSERT rather than by materializing and then
    editing a row: ``rainfall_analysis_revision`` is append-only (models.py
    ``_prevent_rainfall_audit_mutation``), and a fixture has no business being
    the one exception. ``created_at`` is passed explicitly for the same
    reason it cannot be left to the default: PG's ``now()`` is frozen at
    TRANSACTION start and this whole test runs inside one, so both rows would
    tie on the ``created_at DESC, id DESC`` ordering ``get_snapshot`` uses and
    a random UUID would decide the winner. In production the incumbent really
    is older -- the two writes are separate transactions there.
    """
    from app.domains.geo.rainfall import temporal
    from app.domains.geo.rainfall.compute import (
        baseline_cutoff_for,
        build_snapshot,
        data_revision_for,
        revision_family,
    )
    from app.domains.geo.rainfall.models import RainfallAnalysisRevision
    from app.domains.geo.rainfall.repository import baseline_cumulatives, intervals_in_window
    from app.domains.geo.rainfall.scope import AnalysisScope
    from app.domains.geo.rainfall.service import RAINFALL_HISTORICAL_SOURCE, fallback_used_for

    scope = AnalysisScope(kind="zone", id=scope_id, version="v1", regional_estimate=False)
    year_start = datetime(_GAP_YEAR, 1, 1, tzinfo=UTC)
    resolved = [
        (interval.interval_start, interval.interval_end, interval.value)
        for interval in intervals_in_window(
            db,
            source_id="chirps-v3-sat",
            scope_kind="zone",
            scope_id=scope_id,
            scope_version="v1",
            start=year_start - timedelta(days=90),
            end=datetime(_GAP_YEAR + 1, 1, 1, tzinfo=UTC),
        )
    ]
    baseline = baseline_cumulatives(
        db,
        source_id=RAINFALL_HISTORICAL_SOURCE,
        asset=asset_name_for("zone", scope_id),
        dates=temporal.baseline_dates(
            baseline_cutoff_for(year=_GAP_YEAR, now=_GAP_NOW, intervals=resolved)
        ),
    )
    snapshot = _as_pre_ops6_envelope(
        build_snapshot(
            scope=scope,
            year=_GAP_YEAR,
            role="daily",
            source_id="chirps-v3-sat",
            intervals=resolved,
            batch=batch,
            now=_GAP_NOW,
            fallback_used=fallback_used_for("daily", "chirps-v3-sat"),
            baseline=baseline,
        )
    )
    data_revision = data_revision_for(
        "chirps-v3-sat",
        revision_family(batch["provider_revision"]),
        scope,
        _GAP_YEAR,
        temporal.comparison_end(_GAP_YEAR, temporal.buenos_aires_date(_GAP_NOW)),
        [(interval_start, value) for interval_start, _end, value in resolved],
    )

    db.add(
        RainfallAnalysisRevision(
            request_fingerprint=fingerprint,
            policy_revision=_PRE_OPS6_POLICY_REVISION,
            data_revision=data_revision,
            snapshot=snapshot,
            created_at=_GAP_NOW - timedelta(days=1),
        )
    )
    db.flush()
    return data_revision, snapshot


def test_policy_bump_lands_the_corrected_envelope_over_a_pre_fix_incumbent(db):
    """PEG-001: the corrected envelope LANDS on an already-materialized key
    whose evidence has not moved, and is the one served afterwards."""
    from sqlalchemy import select

    from app.domains.geo.rainfall import tasks
    from app.domains.geo.rainfall.models import RainfallAnalysisRevision
    from app.domains.geo.rainfall.policy import RAINFALL_METRIC_POLICY_REVISION
    from app.domains.geo.rainfall.service import normalize_snapshot

    # The bump itself. Without it every assertion below collides by
    # construction: one policy revision, one data revision, one row.
    assert RAINFALL_METRIC_POLICY_REVISION != _PRE_OPS6_POLICY_REVISION

    scope_id = "zone-peg1-bump-lands"
    outbox, batch, fingerprint = _seed_gap_evidence(db, scope_id=scope_id, missing_days=5)

    # The incumbent the pre-fix code left behind: SAME key and SAME
    # data_revision (the evidence has not moved -- that is the whole premise),
    # the superseded policy revision, and the biased rank served as available.
    unmoved_data_revision, incumbent_snapshot = _pre_ops6_incumbent(
        db, scope_id=scope_id, fingerprint=fingerprint, batch=batch
    )

    # It is a usable answer, and that is the trap: it serves the biased rank
    # to every reader, with no policy edit able to take it back.
    stale_served = normalize_snapshot(
        incumbent_snapshot, expected_policy_revision=_PRE_OPS6_POLICY_REVISION
    )
    assert stale_served["annual"]["percentile"]["state"] == "available"
    assert stale_served["annual"]["percentile"]["value"] == pytest.approx(_GAP_BIASED_PERCENTILE)

    # The rebuild the stale-policy requeue triggers (workbook §2.1,
    # `rainfall.analysis.policy_revision_stale`).
    rebuilt = tasks._persist_analysis_revision(
        db, outbox_id=str(outbox.id), batch=batch, now=_GAP_NOW
    )
    assert rebuilt["decision"] == "write"
    assert rebuilt["data_revision"] == unmoved_data_revision

    stored = db.scalars(
        select(RainfallAnalysisRevision).where(
            RainfallAnalysisRevision.request_fingerprint == fingerprint
        )
    ).all()
    assert len(stored) == 2, [(row.policy_revision, row.data_revision) for row in stored]
    # Identical evidence -- the policy revision is provably the only
    # difference, which is precisely what the unique constraint would have
    # collapsed into a discarded duplicate without the bump.
    assert {row.data_revision for row in stored} == {unmoved_data_revision}
    assert {row.policy_revision for row in stored} == {
        _PRE_OPS6_POLICY_REVISION,
        RAINFALL_METRIC_POLICY_REVISION,
    }
    landed = next(row for row in stored if row.policy_revision == RAINFALL_METRIC_POLICY_REVISION)

    # ... and it is the row a reader now gets, carrying the refusal.
    served_row = RainfallRepository().get_snapshot(db, fingerprint)
    assert served_row is not None
    assert served_row.id == landed.id
    served = normalize_snapshot(
        served_row.snapshot, expected_policy_revision=RAINFALL_METRIC_POLICY_REVISION
    )
    percentile = served["annual"]["percentile"]
    assert percentile["state"] == "suppressed"
    assert percentile["value"] is None
    assert percentile["reason"] == "selected_evidence_below_threshold"
    # The total is untouched by the correction: it cleared its own gate before
    # the bump and still does, so the bump costs the reader nothing it had.
    assert served["annual"]["selected"]["state"] == "available"
    assert served["annual"]["selected"]["value"] == pytest.approx(46 * _GAP_SELECTED_DAILY)
