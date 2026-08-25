"""Unit tests for ``rainfall/climatology.py`` — the pure window-climatology module.

Pure by contract: no ``Session``, no network, no ``policy`` import is exercised
anywhere in this file. Every case here is a hand-built daily series.

The governing rule under test is **D0 carried to the baseline side**: a baseline
year contributes iff its window is derivable AND complete
(``matched_days == expected_days`` exactly). There is no 0.95 floor here; the
0.94-exclusion case below asserts the resulting value NUMERICALLY, because the
bias a floor reintroduces is a bias in the number, not in a reason string.
"""

from __future__ import annotations

import ast
import dataclasses
import sys
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pytest

import app
from app.domains.geo.rainfall import temporal
from app.domains.geo.rainfall.climatology import (
    ABSOLUTE_WEIBULL_RANK,
    SEASONAL_WEIBULL_RANK,
    WINDOW_MEAN,
    SeasonalClimatology,
    WindowSample,
    absolute_window_percentile,
    absolute_window_samples,
    seasonal_climatology,
    seasonal_window_percentile,
    weibull_percentile,
    window_normal,
)

# ---------------------------------------------------------------------------
# Shared span: the persisted baseline envelope D2 bounds the read to.
# ---------------------------------------------------------------------------

SPAN_START = date(1991, 1, 1)
SPAN_END = date(2021, 1, 1)  # exclusive
BASELINE_YEARS = tuple(range(1991, 2021))


def daily_series(
    *,
    start: date,
    end: date,
    value: float = 1.0,
    value_for: Callable[[date], float] | None = None,
    holes: frozenset[date] = frozenset(),
) -> tuple[tuple[date, float], ...]:
    """A dense ``(day, mm)`` series over ``[start, end]`` minus *holes*.

    A hole is an ABSENT day, never a zero: a zero is a measured dry day and
    completeness must not confuse the two.

    *value_for* makes the series POSITION-DEPENDENT. A flat 1.0 mm/day series
    cannot see a window-start off-by-one at all — any ``days`` consecutive days
    sum to the same number — so every test that means to pin WHICH days a
    window covers passes *value_for* and asserts the total exactly.
    """
    span = (end - start).days + 1
    days = (start + timedelta(days=offset) for offset in range(span))
    return tuple(
        (day, value if value_for is None else value_for(day)) for day in days if day not in holes
    )


def ordinal_mod_7(day: date) -> float:
    """A position-dependent daily value with period 7 and per-week sum 21."""
    return float(day.toordinal() % 7)


class TestWindowSample:
    """Task 1.1 — the sample is immutable and ``complete`` is exact equality."""

    def test_is_frozen(self) -> None:
        sample = WindowSample(
            end=date(2020, 1, 30), total_mm=30.0, matched_days=30, expected_days=30
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            sample.total_mm = 99.0  # type: ignore[misc]

    def test_is_slotted(self) -> None:
        sample = WindowSample(
            end=date(2020, 1, 30), total_mm=30.0, matched_days=30, expected_days=30
        )
        assert not hasattr(sample, "__dict__")
        # The invariant is "assignment of an unknown attribute is refused".
        # WHICH exception carries the refusal is interpreter-dependent: 3.12+
        # raises AttributeError; 3.11's generated frozen __setattr__ hits the
        # known stale-super() path on frozen+slots dataclasses and raises
        # TypeError instead. Pin the refusal, not the interpreter's choice.
        with pytest.raises((AttributeError, TypeError)):
            sample.unexpected = 1  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        ("matched", "expected", "complete"),
        [
            (30, 30, True),
            (29, 30, False),  # 0.9667 — admitted by a 0.95 floor, refused here
            (0, 30, False),
            (90, 90, True),
            (86, 90, False),  # 0.9556 — likewise
        ],
    )
    def test_complete_is_exact_equality_not_a_ratio(
        self, matched: int, expected: int, complete: bool
    ) -> None:
        sample = WindowSample(
            end=date(2020, 1, 30),
            total_mm=float(matched),
            matched_days=matched,
            expected_days=expected,
        )
        assert sample.complete is complete


class TestSeasonalClimatologyEligible:
    """Task 1.2 — ``eligible`` is the ONE definition of a contributing year."""

    def test_eligible_returns_complete_samples_only(self) -> None:
        whole = WindowSample(
            end=date(2019, 1, 30), total_mm=30.0, matched_days=30, expected_days=30
        )
        short = WindowSample(
            end=date(2020, 1, 30), total_mm=29.0, matched_days=29, expected_days=30
        )
        clim = SeasonalClimatology(
            days=30,
            anchor=date(2020, 1, 30),
            derivable_years=(2019, 2020),
            samples=(whole, short),
        )
        assert clim.eligible == (whole,)

    def test_is_frozen_and_slotted(self) -> None:
        clim = SeasonalClimatology(
            days=30, anchor=date(2020, 1, 30), derivable_years=(), samples=()
        )
        assert not hasattr(clim, "__dict__")
        with pytest.raises(dataclasses.FrozenInstanceError):
            clim.days = 7  # type: ignore[misc]


class TestDerivability:
    """Tasks 1.3 + 1.4 — the denominator states the sample honestly."""

    def test_first_baseline_year_is_underivable_and_leaves_the_denominator_at_29(
        self,
    ) -> None:
        """A d90 anchored mid-February needs 44 days of 1990 that were never
        persisted. 1991 is therefore NOT derivable — it is excluded from the
        denominator rather than counted as a 29/30 loss (0.967), which is what
        a fixed denominator of 30 would have reported.
        """
        clim = seasonal_climatology(
            daily=daily_series(start=SPAN_START, end=date(2020, 12, 31)),
            days=90,
            anchor=date(2020, 2, 15),
            years=BASELINE_YEARS,
            span_start=SPAN_START,
            span_end=SPAN_END,
        )

        assert len(clim.derivable_years) == 29
        assert len(clim.derivable_years) != 30
        assert 1991 not in clim.derivable_years
        assert clim.derivable_years[0] == 1992
        assert clim.derivable_years[-1] == 2020
        # And the derivable years all produced a sample, in the same order.
        assert len(clim.samples) == 29

    def test_window_crossing_the_calendar_year_is_derivable_and_contributes(
        self,
    ) -> None:
        """A d90 window ending 15 February starts on 18 November of the
        PRECEDING calendar year. There is no year-start ``GROUP BY`` here to
        split it, so ``expected_days == days`` always and the sample spans that
        baseline year's own preceding-year days.

        The series is POSITION-DEPENDENT on purpose. Under a flat 1.0 mm/day
        fixture this whole path is blind to a window-start off-by-one -- any 90
        consecutive days total 90.0 -- and re-deriving the start from
        ``first.end`` would only restate the line already asserted above it.
        So the total is pinned to a number computed here, independently:

            start 1991-11-18 has ordinal 727154, and 727154 % 7 == 1, so the
            window's daily residues run 1,2,3,4,5,6,0 repeating.
            90 days == 12 whole weeks + 6 days.
            12 weeks x (0+1+2+3+4+5+6 == 21) == 252
            trailing 6 days resume at residue 1: 1+2+3+4+5+6 == 21
            total == 252 + 21 == 273.0 mm

        A start one day earlier totals 267.0, so the assertion below sees the
        off-by-one that the flat fixture could not.
        """
        clim = seasonal_climatology(
            daily=daily_series(start=SPAN_START, end=date(2020, 12, 31), value_for=ordinal_mod_7),
            days=90,
            anchor=date(2020, 2, 15),
            years=BASELINE_YEARS,
            span_start=SPAN_START,
            span_end=SPAN_END,
        )

        assert all(sample.expected_days == 90 for sample in clim.samples)
        assert all(sample.complete for sample in clim.samples)
        first = clim.samples[0]
        assert first.end == date(1992, 2, 15)
        assert first.matched_days == 90
        assert first.total_mm == pytest.approx(273.0)

    def test_the_window_start_is_the_inclusive_day_days_minus_one_back(self) -> None:
        """The window is [end - (days - 1), end] INCLUSIVE, pinned on a series
        whose values differ day by day.

        d3 ending 1991-01-03 must cover 1 to 3 January. Residues: 1991-01-01 has
        ordinal 726833, 726833 % 7 == 2, so the three days are 2, 3, 4 and the
        total is 2+3+4 == 9.0. A start one day back would cover 31 December to
        2 January (residues 1, 2, 3) and total 6.0.
        """
        samples = absolute_window_samples(
            daily=daily_series(
                start=date(1990, 12, 25), end=date(1991, 1, 10), value_for=ordinal_mod_7
            ),
            days=3,
        )

        third = next(sample for sample in samples if sample.end == date(1991, 1, 3))
        assert third.matched_days == 3
        assert third.total_mm == pytest.approx(9.0)

    def test_short_window_keeps_every_baseline_year_derivable(self) -> None:
        """A d7 anchored mid-February fits inside 1991, so nothing truncates:
        the denominator is the full 30, proving the 29 above is the window
        reaching backwards, not a blanket off-by-one.
        """
        clim = seasonal_climatology(
            daily=daily_series(start=SPAN_START, end=date(2020, 12, 31)),
            days=7,
            anchor=date(2020, 2, 15),
            years=BASELINE_YEARS,
            span_start=SPAN_START,
            span_end=SPAN_END,
        )

        assert len(clim.derivable_years) == 30
        assert clim.derivable_years[0] == 1991

    def test_window_reaching_past_the_span_end_is_underivable(self) -> None:
        """``span_end`` is exclusive: a window whose last day IS 2021-01-01 --
        the exclusive bound itself, not merely beyond it -- reaches evidence the
        bounded read never returned.

        The anchor is 1 January precisely so that the 2021 window ends ON
        ``span_end``. An earlier revision of this test anchored on 31 December,
        whose 2021 window ends a whole year past the bound: it read as a
        boundary case but exercised none, and ``end > span_end`` would have
        passed it unharmed.
        """
        clim = seasonal_climatology(
            daily=daily_series(start=SPAN_START, end=date(2020, 12, 31)),
            days=7,
            anchor=date(2020, 1, 1),
            years=(*BASELINE_YEARS, 2021),
            span_start=SPAN_START,
            span_end=SPAN_END,
        )

        assert date(2021, 1, 1) == SPAN_END  # the 2021 window ends exactly here
        assert 2021 not in clim.derivable_years
        assert clim.derivable_years[-1] == 2020

    def test_a_window_starting_exactly_on_the_span_start_is_derivable(self) -> None:
        """``span_start`` is INCLUSIVE. A d30 window ending 1991-01-30 starts on
        1991-01-01, the first persisted day, so every day it needs exists and
        the year contributes.

        This is the tight edge of ``end - timedelta(days=days - 1) <
        span_start``: ``days`` instead of ``days - 1`` would reach one day
        before the span, and ``<=`` instead of ``<`` would reject a window that
        starts precisely on the bound. Both discard a year of real evidence.
        """
        clim = seasonal_climatology(
            daily=daily_series(start=SPAN_START, end=date(2020, 12, 31)),
            days=30,
            anchor=date(2020, 1, 30),
            years=(1991,),
            span_start=SPAN_START,
            span_end=SPAN_END,
        )

        assert clim.derivable_years == (1991,)
        sample = clim.samples[0]
        assert sample.end == date(1991, 1, 30)
        assert sample.end - timedelta(days=29) == SPAN_START
        assert sample.complete

    def test_the_same_window_one_day_earlier_is_underivable(self) -> None:
        """Shift that window a single day back and its first day is 1990-12-31,
        which the bounded read never returned: structurally underivable, not a
        completeness loss.
        """
        clim = seasonal_climatology(
            daily=daily_series(start=SPAN_START, end=date(2020, 12, 31)),
            days=30,
            anchor=date(2020, 1, 29),
            years=(1991,),
            span_start=SPAN_START,
            span_end=SPAN_END,
        )

        assert clim.derivable_years == ()
        assert clim.samples == ()


class TestInputGuards:
    """The refusals — each one is a defence with no other line of retreat."""

    def test_a_duplicate_day_is_refused_by_the_seasonal_path(self) -> None:
        """D2: the ONLY defence against silent duplicate inflation.

        ``dict()`` over pairs would keep the last value and say nothing; summing
        them would inflate a ranked total. Neither failure is visible in the
        served number, so the guard raises and this test is what keeps it there.
        """
        day = date(1991, 1, 10)
        with pytest.raises(ValueError, match="duplicate baseline day"):
            seasonal_climatology(
                daily=((day, 1.0), (date(1991, 1, 11), 1.0), (day, 5.0)),
                days=7,
                anchor=date(2020, 1, 15),
                years=BASELINE_YEARS,
                span_start=SPAN_START,
                span_end=SPAN_END,
            )

    def test_a_duplicate_day_is_refused_by_the_absolute_path(self) -> None:
        day = date(1991, 1, 10)
        with pytest.raises(ValueError, match="duplicate baseline day"):
            absolute_window_samples(daily=((day, 1.0), (day, 5.0)), days=3)

    @pytest.mark.parametrize("days", [0, -1])
    def test_seasonal_climatology_refuses_a_non_positive_window(self, days: int) -> None:
        """A zero-length window is complete-by-vacuity: ``matched == expected ==
        0``, so without this guard it would rank a 0.0 mm total as evidence."""
        with pytest.raises(ValueError, match="window length must be positive"):
            seasonal_climatology(
                daily=daily_series(start=SPAN_START, end=date(1991, 12, 31)),
                days=days,
                anchor=date(2020, 1, 30),
                years=BASELINE_YEARS,
                span_start=SPAN_START,
                span_end=SPAN_END,
            )

    @pytest.mark.parametrize("days", [0, -1])
    def test_absolute_window_samples_refuses_a_non_positive_window(self, days: int) -> None:
        with pytest.raises(ValueError, match="window length must be positive"):
            absolute_window_samples(
                daily=daily_series(start=date(1991, 1, 1), end=date(1991, 1, 10)), days=days
            )

    def test_absolute_window_samples_on_an_empty_series_yields_nothing(self) -> None:
        """No days means no span to infer: an empty result, not a crash inside
        ``min()`` and not a fabricated window."""
        assert absolute_window_samples(daily=(), days=3) == ()


def complete_climatology(
    count: int, *, totals: tuple[float, ...] | None = None
) -> SeasonalClimatology:
    """*count* complete d30 samples, one per derivable year — the sample-size
    boundary is about how MANY years cleared, so the values are incidental."""
    years = tuple(range(1991, 1991 + count))
    values = totals if totals is not None else tuple(float(10 + index) for index in range(count))
    samples = tuple(
        WindowSample(end=date(year, 1, 30), total_mm=value, matched_days=30, expected_days=30)
        for year, value in zip(years, values, strict=True)
    )
    return SeasonalClimatology(
        days=30, anchor=date(2020, 1, 30), derivable_years=years, samples=samples
    )


class TestBaselineYearCompletenessExclusion:
    """Task 1.6 — the CRITICAL-2 bias, asserted as a NUMBER.

    A reason-string test cannot see this defect: with a 0.95 floor the metric
    is still served, still unsuppressed, and still carries no caveat. Only the
    value moves.
    """

    ANCHOR = date(2020, 1, 30)
    HOLE = date(2020, 1, 15)  # inside 2020's own d30 window

    def _clim(self) -> SeasonalClimatology:
        return seasonal_climatology(
            daily=daily_series(
                start=SPAN_START, end=date(2020, 12, 31), holes=frozenset({self.HOLE})
            ),
            days=30,
            anchor=self.ANCHOR,
            years=BASELINE_YEARS,
            span_start=SPAN_START,
            span_end=SPAN_END,
        )

    def test_a_29_of_30_baseline_year_is_excluded(self) -> None:
        clim = self._clim()

        assert len(clim.derivable_years) == 30  # the hole is a LOSS, not underivability
        holed = next(sample for sample in clim.samples if sample.end == self.ANCHOR)
        assert (holed.matched_days, holed.expected_days) == (29, 30)
        assert holed.matched_days / holed.expected_days == pytest.approx(0.9667, abs=1e-4)
        assert holed not in clim.eligible
        assert len(clim.eligible) == 29

    def test_the_excluded_year_changes_the_normal_numerically(self) -> None:
        clim = self._clim()
        served = window_normal(clim, min_years=20)

        under_a_095_floor = sum(sample.total_mm for sample in clim.samples) / len(clim.samples)

        assert served == pytest.approx(30.0)
        assert under_a_095_floor == pytest.approx(899 / 30)  # 29.9667 — biased LOW
        assert served != pytest.approx(under_a_095_floor)


class TestSampleSizeBoundary:
    """Task 1.7 — 20 serves, 19 suppresses, on BOTH functions at once."""

    @pytest.mark.parametrize(("eligible_years", "served"), [(20, True), (19, False)])
    def test_window_normal_boundary(self, eligible_years: int, served: bool) -> None:
        clim = complete_climatology(eligible_years)
        assert (window_normal(clim, min_years=20) is not None) is served

    @pytest.mark.parametrize(("eligible_years", "served"), [(20, True), (19, False)])
    def test_seasonal_window_percentile_boundary(self, eligible_years: int, served: bool) -> None:
        clim = complete_climatology(eligible_years)
        assert (seasonal_window_percentile(clim, 25.0, min_years=20) is not None) is served

    def test_incomplete_years_do_not_count_towards_the_floor(self) -> None:
        """20 derivable years of which one is holed is NINETEEN eligible —
        the floor counts eligibility, never derivability."""
        clim = complete_climatology(20)
        holed = dataclasses.replace(clim.samples[0], matched_days=29)
        thinned = dataclasses.replace(clim, samples=(holed, *clim.samples[1:]))

        assert len(thinned.derivable_years) == 20
        assert len(thinned.eligible) == 19
        assert window_normal(thinned, min_years=20) is None
        assert seasonal_window_percentile(thinned, 25.0, min_years=20) is None


class TestSeasonalRanking:
    """The seasonal mode ranks the selected total INSIDE its own sample."""

    def test_ranks_against_eligible_years_only(self) -> None:
        clim = complete_climatology(20, totals=tuple(float(value) for value in range(1, 21)))

        lowest = seasonal_window_percentile(clim, 0.0, min_years=20)
        highest = seasonal_window_percentile(clim, 999.0, min_years=20)

        assert lowest is not None and highest is not None
        assert 0.0 < lowest < highest < 100.0

    def test_normal_is_the_mean_of_eligible_totals(self) -> None:
        clim = complete_climatology(20, totals=tuple(float(value) for value in range(1, 21)))
        assert window_normal(clim, min_years=20) == pytest.approx(10.5)


class TestFebruary29SuppressesStructurally:
    """D5 — no leap-day branch anywhere; 8 < 20 is the WHOLE mechanism.

    The completeness here is 8/8 = 1.0, so a coverage/quality threshold pinned
    at 20/30 PASSES on this path. Only the sample-size floor gates 29 February,
    and stating that plainly is what stops the next reader "simplifying" the
    floor away as redundant.
    """

    def test_only_the_eight_leap_years_are_derivable_and_all_are_eligible(self) -> None:
        anchor = date(2020, 2, 29)
        clim = seasonal_climatology(
            daily=daily_series(start=SPAN_START, end=date(2020, 12, 31)),
            days=7,
            anchor=anchor,
            years=temporal.baseline_years_for(anchor),
            span_start=SPAN_START,
            span_end=SPAN_END,
        )

        assert clim.derivable_years == (1992, 1996, 2000, 2004, 2008, 2012, 2016, 2020)
        assert len(clim.eligible) == len(clim.samples) == 8
        assert len(clim.eligible) / len(clim.derivable_years) == 1.0  # the policy pin passes

    def test_both_reference_values_suppress_on_sample_size(self) -> None:
        anchor = date(2020, 2, 29)
        clim = seasonal_climatology(
            daily=daily_series(start=SPAN_START, end=date(2020, 12, 31)),
            days=7,
            anchor=anchor,
            years=temporal.baseline_years_for(anchor),
            span_start=SPAN_START,
            span_end=SPAN_END,
        )

        assert window_normal(clim, min_years=20) is None
        assert seasonal_window_percentile(clim, 7.0, min_years=20) is None

    def test_an_unfiltered_year_set_raises_rather_than_substituting_a_day(self) -> None:
        """The filtering contract is a PRECONDITION and the failure is LOUD.

        Handing the full 1991-2020 range to a 29 February anchor hits
        ``date(1991, 2, 29)`` and raises. That is the designed behaviour: the
        alternative -- a leap-day branch quietly falling back to 28 February --
        is exactly the special case D5 refuses, because it would rank a
        29 February window against 28 February windows under the same name.
        Callers filter with ``temporal.baseline_years_for(anchor)``.

        The message regex accepts both interpreter eras: Python <= 3.12 says
        "day is out of range for month", newer versions name the day and range.
        Pinning one exact message is a version pin in disguise (bug-class:
        local 3.14 vs CI 3.11 drift, second occurrence in this repo).
        """
        with pytest.raises(
            ValueError,
            match=r"day is out of range for month|day 29 must be in range 1\.\.28 for month 2",
        ):
            seasonal_climatology(
                daily=daily_series(start=SPAN_START, end=date(2020, 12, 31)),
                days=7,
                anchor=date(2020, 2, 29),
                years=BASELINE_YEARS,  # unfiltered: 1991 is not a leap year
                span_start=SPAN_START,
                span_end=SPAN_END,
            )


# ---------------------------------------------------------------------------
# Absolute mode (the detector's entry point) — tasks 1.10 to 1.12
# ---------------------------------------------------------------------------

APP_ROOT = Path(app.__file__).resolve().parent
CLIMATOLOGY_SOURCE = APP_ROOT / "domains" / "geo" / "rainfall" / "climatology.py"


class TestAbsoluteWindowSamples:
    """Task 1.10 — every rolling window in the span, and a sample-size floor.

    The detector is not exempt from sample-size discipline just because it has
    ~32.6k samples where the seasonal mode has ~30.
    """

    def test_yields_one_sample_per_rolling_window_in_the_span(self) -> None:
        samples = absolute_window_samples(
            daily=daily_series(start=date(1991, 1, 1), end=date(1991, 1, 10)), days=3
        )

        assert len(samples) == 8  # ends 3 Jan through 10 Jan
        assert samples[0].end == date(1991, 1, 3)
        assert samples[-1].end == date(1991, 1, 10)
        assert all(sample.expected_days == 3 for sample in samples)
        assert all(sample.complete for sample in samples)
        assert samples[0].total_mm == pytest.approx(3.0)

    def test_a_hole_leaves_the_window_present_but_incomplete(self) -> None:
        """A hole must not silently delete windows: the count is a property of
        the span, and only ``complete`` records the loss."""
        samples = absolute_window_samples(
            daily=daily_series(
                start=date(1991, 1, 1), end=date(1991, 1, 10), holes=frozenset({date(1991, 1, 5)})
            ),
            days=3,
        )

        assert len(samples) == 8
        touched = [sample for sample in samples if not sample.complete]
        assert [sample.end for sample in touched] == [
            date(1991, 1, 5),
            date(1991, 1, 6),
            date(1991, 1, 7),
        ]
        assert all(sample.matched_days == 2 for sample in touched)

    def test_a_leading_edge_hole_shrinks_the_inferred_span_and_deletes_windows(
        self,
    ) -> None:
        """The interior-hole guarantee does NOT extend to the edges, and the
        contract now says so.

        The span is inferred from ``min``/``max`` of the surviving days, so a
        missing FIRST day is indistinguishable here from a record that simply
        started a day later: the window count drops from 8 to 7 and the loss is
        recorded nowhere. Pinned rather than merely documented, because a caller
        needing fixed-span semantics has to know it must pass a dense series.
        """
        dense = absolute_window_samples(
            daily=daily_series(start=date(1991, 1, 1), end=date(1991, 1, 10)), days=3
        )
        leading_hole = absolute_window_samples(
            daily=daily_series(
                start=date(1991, 1, 1), end=date(1991, 1, 10), holes=frozenset({date(1991, 1, 1)})
            ),
            days=3,
        )

        assert len(dense) == 8
        assert len(leading_hole) == 7  # not 8-with-an-incomplete-window
        assert leading_hole[0].end == date(1991, 1, 4)
        assert all(sample.complete for sample in leading_hole)  # the loss is invisible

    def test_a_trailing_edge_hole_shrinks_the_inferred_span_too(self) -> None:
        trailing_hole = absolute_window_samples(
            daily=daily_series(
                start=date(1991, 1, 1), end=date(1991, 1, 10), holes=frozenset({date(1991, 1, 10)})
            ),
            days=3,
        )

        assert len(trailing_hole) == 7
        assert trailing_hole[-1].end == date(1991, 1, 9)
        assert all(sample.complete for sample in trailing_hole)

    def test_a_span_shorter_than_the_window_yields_nothing(self) -> None:
        samples = absolute_window_samples(
            daily=daily_series(start=date(1991, 1, 1), end=date(1991, 1, 2)), days=3
        )
        assert samples == ()

    @pytest.mark.parametrize(("min_samples", "served"), [(8, True), (9, False)])
    def test_percentile_honours_its_own_min_samples_floor(
        self, min_samples: int, served: bool
    ) -> None:
        samples = absolute_window_samples(
            daily=daily_series(start=date(1991, 1, 1), end=date(1991, 1, 10)), days=3
        )
        result = absolute_window_percentile(samples, 5.0, min_samples=min_samples)
        assert (result is not None) is served

    def test_percentile_ranks_only_complete_samples(self) -> None:
        samples = absolute_window_samples(
            daily=daily_series(
                start=date(1991, 1, 1), end=date(1991, 1, 10), holes=frozenset({date(1991, 1, 5)})
            ),
            days=3,
        )
        # 8 windows, 3 of them holed -> 5 eligible, below a floor of 6.
        assert absolute_window_percentile(samples, 3.0, min_samples=6) is None
        assert absolute_window_percentile(samples, 3.0, min_samples=5) is not None


class TestModeNamesAreDistinct:
    """Task 1.12 (D8) — three independent literals, none derived from another."""

    def test_the_three_names_are_distinct(self) -> None:
        names = (WINDOW_MEAN, SEASONAL_WEIBULL_RANK, ABSOLUTE_WEIBULL_RANK)
        assert names == ("window_mean", "seasonal_weibull_rank", "absolute_weibull_rank")
        assert len(set(names)) == 3

    @pytest.mark.parametrize(
        "assignment",
        [
            'WINDOW_MEAN = "window_mean"',
            'SEASONAL_WEIBULL_RANK = "seasonal_weibull_rank"',
            'ABSOLUTE_WEIBULL_RANK = "absolute_weibull_rank"',
        ],
    )
    def test_each_name_is_a_bare_literal(self, assignment: str) -> None:
        """Not an f-string, not a shared prefix, not one spelled in terms of
        another: a derivation is how a rename carries one mode's value onto the
        other's name on the wire."""
        assert assignment in CLIMATOLOGY_SOURCE.read_text(encoding="utf-8")


REPO_ROOT = APP_ROOT.parent.parent  # .../<repo>/gee-backend/app -> .../<repo>
FRONTEND_SOURCE_ROOT = REPO_ROOT / "consorcio-web" / "src"

# The absolute mode is no longer consumerless: the extreme-event detector is
# its ONE legitimate consumer (rainfall-analysis MODIFIED, S4). Retiring the
# old "referenced nowhere" guard by DELETION would read as the regression the
# proposal's own risk row names, so it is REPLACED, in the same slice that
# introduces the consumer, by a narrower snapshot-path isolation guard.
ABSOLUTE_MODE_ALLOWLIST = frozenset(
    {
        "domains/geo/rainfall/climatology.py",
        "domains/geo/rainfall/detector.py",
    }
)
# The two rank NAMES stay tighter still: the detector ranks, but it never
# reaches for the wire label, and `ABSOLUTE_WEIBULL_RANK` must never reach a
# served metric.
RANK_NAME_ALLOWLIST = frozenset({"domains/geo/rainfall/climatology.py"})

# Every rainfall module that participates in building, computing or rendering
# the antecedent card's snapshot. Named explicitly rather than derived as "the
# rest of the package", so adding a module to the snapshot path is a decision
# somebody makes here rather than a default it inherits.
SNAPSHOT_PATH_MODULES = (
    "compute.py",
    "policy.py",
    "metrics.py",
    "service.py",
    "router.py",
    "schemas.py",
    "series.py",
    "export.py",
    "repository.py",
    "models.py",
    "tasks.py",
    "scope.py",
    "temporal.py",
    "feature_flags.py",
)

ABSOLUTE_MODE_SYMBOLS = ("absolute_window_samples", "absolute_window_percentile")
ABSOLUTE_RANK_NAMES = ("absolute_weibull_rank", "ABSOLUTE_WEIBULL_RANK")


def _readable_sources(root: Path, suffixes: tuple[str, ...]) -> tuple[Path, ...]:
    """Every source file under *root*, minus vendored trees.

    ``venv`` / ``.venv`` / ``node_modules`` are excluded by PATH PART, not by a
    prefix match on the whole path: an unbounded ``rglob`` walks whatever the
    developer happens to have installed beside the code and tests THAT instead
    of the repository (BL-RGLOB-VENV-BLIND-EXCLUSION). Decode errors are
    tolerated for the same reason — one stray binary must not decide whether an
    isolation guard runs at all.
    """
    excluded = {"venv", ".venv", "node_modules", "__pycache__", "dist", "build"}
    return tuple(
        path
        for path in sorted(root.rglob("*"))
        if path.suffix in suffixes and path.is_file() and not excluded.intersection(path.parts)
    )


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def referencing_app_modules(symbol: str) -> frozenset[str]:
    """Every module under ``app/`` whose source mentions *symbol*."""
    return frozenset(
        str(module.relative_to(APP_ROOT))
        for module in _readable_sources(APP_ROOT, (".py",))
        if symbol in _text(module)
    )


def allowlist_violations(consumers: frozenset[str], allowlist: frozenset[str]) -> tuple[str, ...]:
    """The referencing modules the allowlist does not admit."""
    return tuple(sorted(consumers - allowlist))


class TestAbsoluteModeStaysOffTheSnapshotPath:
    """The guard that REPLACES ``TestAbsoluteModeHasNoConsumer``.

    Spec ``rainfall-analysis`` MODIFIED: the absolute mode now has exactly one
    consumer, so the "no consumer at all" guard is retired IN THE SAME SLICE
    that introduces that consumer and is replaced — not merely deleted — by a
    narrower isolation guard. What still must hold is the substantive rule: a
    suppressed seasonal percentile is never backfilled by the absolute one, and
    the cheapest structural proof of that is that no snapshot, compute or
    rendering module can even reach the absolute-mode symbols.
    """

    @pytest.mark.parametrize("symbol", ABSOLUTE_MODE_SYMBOLS)
    def test_the_referencing_module_set_is_exactly_climatology_and_detector(
        self, symbol: str
    ) -> None:
        assert symbol in CLIMATOLOGY_SOURCE.read_text(encoding="utf-8")

        assert referencing_app_modules(symbol) == ABSOLUTE_MODE_ALLOWLIST

    @pytest.mark.parametrize("symbol", ABSOLUTE_RANK_NAMES)
    def test_the_rank_name_never_leaves_the_climatology_module(self, symbol: str) -> None:
        assert referencing_app_modules(symbol) == RANK_NAME_ALLOWLIST

    @pytest.mark.parametrize("module", SNAPSHOT_PATH_MODULES)
    @pytest.mark.parametrize("symbol", ABSOLUTE_MODE_SYMBOLS + ABSOLUTE_RANK_NAMES)
    def test_no_snapshot_compute_or_rendering_module_references_the_absolute_mode(
        self, symbol: str, module: str
    ) -> None:
        source = APP_ROOT / "domains" / "geo" / "rainfall" / module
        assert source.exists(), f"{module} moved; the guard is scanning nothing"

        assert symbol not in _text(source)

    @pytest.mark.parametrize("symbol", ABSOLUTE_RANK_NAMES)
    def test_the_rank_name_never_reaches_the_frontend(self, symbol: str) -> None:
        assert FRONTEND_SOURCE_ROOT.is_dir(), (
            f"{FRONTEND_SOURCE_ROOT} is missing; a wire-leak scan over a tree "
            "that does not exist is a guard that tests nothing"
        )

        leaks = [
            str(path.relative_to(FRONTEND_SOURCE_ROOT))
            for path in _readable_sources(FRONTEND_SOURCE_ROOT, (".ts", ".tsx", ".js", ".jsx"))
            if symbol in _text(path)
        ]

        assert leaks == [], f"{symbol} reached the wire: {leaks}"


class TestTheIsolationGuardActuallyRejects:
    """The allowlist comparison itself, exercised on synthetic inputs.

    An allowlist that is never shown rejecting anything is indistinguishable
    from an allowlist that admits everything. These two cases are what the
    "allowlist widened" mutant has to get past, and they are pure set logic, so
    they need no third module to actually exist.
    """

    def test_a_third_module_is_rejected(self) -> None:
        consumers = ABSOLUTE_MODE_ALLOWLIST | {"domains/geo/router_gee_support.py"}

        assert allowlist_violations(consumers, ABSOLUTE_MODE_ALLOWLIST) == (
            "domains/geo/router_gee_support.py",
        )

    def test_compute_is_rejected_specifically(self) -> None:
        consumers = ABSOLUTE_MODE_ALLOWLIST | {"domains/geo/rainfall/compute.py"}

        assert allowlist_violations(consumers, ABSOLUTE_MODE_ALLOWLIST) == (
            "domains/geo/rainfall/compute.py",
        )

    def test_the_detector_alone_does_not_satisfy_the_rank_name_allowlist(self) -> None:
        consumers = frozenset({"domains/geo/rainfall/detector.py"})

        assert allowlist_violations(consumers, RANK_NAME_ALLOWLIST) == (
            "domains/geo/rainfall/detector.py",
        )


class TestModuleIsPureByImport:
    """The purity claim in the module docstring, enforced instead of asserted.

    "No ``Session``, no network, no ``policy`` import" is only true for as long
    as nobody adds one, and the day somebody does, the import graph is the first
    place it shows. This parses the source rather than importing it, so it also
    holds if a future import is guarded or lazy at call time.
    """

    def _import_roots(self) -> set[str]:
        tree = ast.parse(CLIMATOLOGY_SOURCE.read_text(encoding="utf-8"))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, "a relative import would reach back into the app package"
                assert node.module is not None
                roots.add(node.module.split(".")[0])
        return roots

    def test_every_import_is_stdlib(self) -> None:
        roots = self._import_roots()
        non_stdlib = sorted(root for root in roots if root not in sys.stdlib_module_names)
        assert non_stdlib == [], f"climatology.py grew a non-stdlib import: {non_stdlib}"

    def test_the_current_import_set_is_the_expected_one(self) -> None:
        """Named explicitly so an addition is a deliberate edit here, not a
        silent widening under a rule that only checks "stdlib"."""
        assert self._import_roots() == {"__future__", "collections", "dataclasses", "datetime"}


class TestWeibullPercentileIsPinnedNumerically:
    """Task 1.8 — one exact rank, hand-computed, through the seasonal wiring.

    The other ranking tests assert ORDER (lowest < highest). Order survives a
    wrong denominator, a 0-based rank or a dropped ``+ 1``; only an exact value
    sees them.
    """

    def test_the_seasonal_percentile_is_the_exact_weibull_position(self) -> None:
        """Baseline totals 10, 20, 30, 40; selected 25.0.

        combined ascending == [10, 20, 25, 30, 40]  ->  N == 5
        the 1-based rank of 25.0 is i == 3
        p == 100 * i / (N + 1) == 100 * 3 / 6 == 50.0
        """
        clim = complete_climatology(4, totals=(10.0, 20.0, 30.0, 40.0))

        assert seasonal_window_percentile(clim, 25.0, min_years=4) == pytest.approx(50.0)
        # ... and the same arithmetic straight through the primitive.
        assert weibull_percentile([10.0, 20.0, 30.0, 40.0], 25.0) == pytest.approx(50.0)

    def test_a_tie_takes_the_mean_of_the_tied_positions(self) -> None:
        """Baseline totals 10, 20, 20, 40; selected 20.0.

        combined ascending == [10, 20, 20, 20, 40]  ->  N == 5
        20.0 sits at 1-based positions 2, 3, 4  ->  mean rank == 3
        p == 100 * 3 / 6 == 50.0
        """
        assert weibull_percentile([10.0, 20.0, 20.0, 40.0], 20.0) == pytest.approx(50.0)


class TestWeibullPercentileRelocation:
    """Task 1.9 — the move, and the re-export that covers every caller."""

    def test_compute_re_exports_the_relocated_symbol(self) -> None:
        from app.domains.geo.rainfall import compute

        assert compute.weibull_percentile is weibull_percentile

    def test_the_definition_no_longer_lives_in_compute(self) -> None:
        source = (APP_ROOT / "domains" / "geo" / "rainfall" / "compute.py").read_text(
            encoding="utf-8"
        )
        assert "def weibull_percentile(" not in source
