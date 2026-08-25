"""Unit tests for ``rainfall/detector.py`` — the pure extreme-event detector.

Pure by contract, exactly like ``test_rainfall_climatology.py``: no ``Session``,
no network, no ``repository`` import is exercised anywhere in this file. Every
case is a hand-built daily series. The real persisted baseline arrives in B1c
(gold anchors + calibration); nothing here reads a database.

The governing rule under test is **D0**:

    Catalog identity is a function of evidence, never of when the detector ran.

and its boundary corollary **D1**: an end-day *fires* ``(L, T)`` iff its
``L``-window is COMPLETE and its absolute percentile is ``>=`` the tier
threshold; the tier's day-set is the UNION of every firing window's coverage
set ``[E-L+1, E]``; an event is a maximal run in that union bridging gaps of at
most ``GAP_DAYS``.

Why the union and not "runs of over-threshold days": seven moderate days whose
d7 total ranks p99.9 contain no single day near the d1 threshold, so the literal
reading produces an EMPTY run and the accumulation event the spec explicitly
wants recorded as ``d7`` never exists. ``TestAccumulationEvent`` is that case,
and if it can be made to pass by a run-of-hot-days implementation, the test is
wrong.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from pathlib import Path

import pytest

import app
from app.domains.geo.rainfall.climatology import (
    absolute_window_percentile,
    absolute_window_samples,
)
from app.domains.geo.rainfall.compute import MIN_WINDOW_BASELINE_YEARS
from app.domains.geo.rainfall.detector import (
    DETECTION_CONSTANTS,
    DETECTOR_CLIMATOLOGY_END,
    DETECTOR_CLIMATOLOGY_START,
    DETECTOR_CONSTANTS_DIGEST,
    DETECTOR_REVISION,
    GAP_DAYS,
    MIN_WINDOW_SAMPLES,
    TIER_PERCENTILES,
    WINDOW_LENGTHS,
    DetectedEvent,
    FiredWindow,
    InsufficientClimatologyError,
    constants_digest,
    detect_events,
    synthesize_description,
    synthesize_name,
)

# ---------------------------------------------------------------------------
# Hand-built series helpers.
#
# Every series here is DENSE unless a test means to punch a hole, and a hole is
# an ABSENT day rather than a zero: ``climatology`` counts a stored 0.0 as a
# measured dry day, so conflating the two would quietly turn an evidence gap
# into evidence.
# ---------------------------------------------------------------------------

ORIGIN = date(1991, 1, 1)


def day(offset: int) -> date:
    """The day *offset* days after :data:`ORIGIN` — series positions read as ints."""
    return ORIGIN + timedelta(days=offset)


def daily_series(
    values: Sequence[float], *, holes: frozenset[int] = frozenset()
) -> tuple[tuple[date, float], ...]:
    """``(day, mm)`` pairs for *values*, minus the day offsets in *holes*."""
    return tuple(
        (day(offset), float(value)) for offset, value in enumerate(values) if offset not in holes
    )


def covered_days(events: Iterable[object]) -> frozenset[date]:
    """Every day inside every event span.

    Spans, not coverage sets: a bridged gap day IS inside the span it bridges,
    so tests that mean to pin WHICH end-days fired pass ``gap_days=0`` rather
    than reading this set and hoping.
    """
    days: set[date] = set()
    for event in events:
        current = event.start_date  # type: ignore[attr-defined]
        while current <= event.end_date:  # type: ignore[attr-defined]
            days.add(current)
            current += timedelta(days=1)
    return frozenset(days)


def fired_lengths(event: object) -> tuple[int, ...]:
    return tuple(window.days for window in event.fired_windows)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Task 1.1 — the firing rule, asserted at the boundary in BOTH directions
# ---------------------------------------------------------------------------


class TestFiringRuleBoundary:
    """D1: ``percentile >= threshold`` fires, one float below does not.

    The threshold is injected rather than taken from the frozen block because a
    30-sample hand-built series cannot reach p99.75 at all (``100 * mean_rank /
    (N + 1)`` caps below 100 for any finite N). The frozen constants are pinned
    separately by the digest test; what is pinned HERE is the comparison
    operator, which ``>`` instead of ``>=`` silently changes.
    """

    def _population(self) -> tuple[tuple[tuple[date, float], ...], float]:
        daily = daily_series([float(value) for value in range(1, 31)])
        samples = absolute_window_samples(daily=daily, days=1)
        percentile = absolute_window_percentile(samples, 25.0, min_samples=1)
        assert percentile is not None
        return daily, percentile

    def test_a_window_exactly_at_the_threshold_fires(self) -> None:
        daily, percentile = self._population()

        events = detect_events(
            daily=daily,
            tier="extrema",
            window_lengths=(1,),
            gap_days=0,
            min_samples=1,
            tier_percentiles={"extrema": percentile},
        )

        assert day(24) in covered_days(events)  # the 25.0 mm day

    def test_a_window_one_float_below_the_threshold_does_not_fire(self) -> None:
        daily, percentile = self._population()

        events = detect_events(
            daily=daily,
            tier="extrema",
            window_lengths=(1,),
            gap_days=0,
            min_samples=1,
            tier_percentiles={"extrema": math.nextafter(percentile, math.inf)},
        )

        assert day(24) not in covered_days(events)


# ---------------------------------------------------------------------------
# Task 1.2 — the accumulation event: D1's whole reason for existing
# ---------------------------------------------------------------------------


class TestAccumulationEvent:
    """Seven moderate days that rank at the top on d7 and nowhere on d1.

    The background carries 30 mm spikes in ADJACENT PAIRS so that a 20 mm day
    is unremarkable on d1 and the block's 60 mm three-day total is unremarkable
    on d3 as well; only the block's 140 mm d7 total stands out, and it is the
    largest 7-day total in the record. A "run of over-threshold days"
    implementation finds NO over-threshold day here and produces nothing.
    """

    BLOCK_START = 200
    BLOCK_END = 206

    def _series(self) -> tuple[tuple[date, float], ...]:
        values = [0.0] * 400
        for offset in range(5, 399, 10):
            values[offset] = 30.0
            values[offset + 1] = 30.0
        for offset in range(self.BLOCK_START, self.BLOCK_END + 1):
            values[offset] = 20.0
        return daily_series(values)

    def _events(self) -> tuple[object, ...]:
        return detect_events(
            daily=self._series(),
            tier="extrema",
            min_samples=1,
            tier_percentiles={"extrema": 99.0},
        )

    def test_the_accumulation_block_yields_exactly_one_event(self) -> None:
        events = self._events()

        assert len(events) == 1
        span = covered_days(events)
        for offset in range(self.BLOCK_START, self.BLOCK_END + 1):
            assert day(offset) in span

    def test_the_event_records_d7_and_does_not_record_d1(self) -> None:
        (event,) = self._events()

        assert fired_lengths(event) == (7,)

    def test_no_single_day_comes_near_the_d1_threshold(self) -> None:
        samples = absolute_window_samples(daily=self._series(), days=1)
        percentile = absolute_window_percentile(samples, 20.0, min_samples=1)

        assert percentile is not None
        assert percentile < 99.0


# ---------------------------------------------------------------------------
# Task 1.3 — coverage sets and the one-dry-day gap tolerance
# ---------------------------------------------------------------------------


class TestGapTolerance:
    """``GAP_DAYS = 1``: a gap of 0 or 1 merges, a gap of 2 splits.

    Run at the FROZEN ``gap_days`` default, so widening or narrowing the
    constant is visible here and not only in the digest.
    """

    HOT = 100.0

    def _events(self, *, second_offset: int) -> tuple[object, ...]:
        values = [0.0] * 300
        values[100] = self.HOT
        values[second_offset] = self.HOT
        return detect_events(
            daily=daily_series(values),
            tier="extrema",
            window_lengths=(1,),
            min_samples=1,
            tier_percentiles={"extrema": 99.0},
        )

    @pytest.mark.parametrize(
        "second_offset, expected_events, expected_span",
        [
            pytest.param(101, 1, (100, 101), id="gap-of-0-merges"),
            pytest.param(102, 1, (100, 102), id="gap-of-exactly-1-merges"),
            pytest.param(103, 2, None, id="gap-of-2-splits"),
        ],
    )
    def test_the_gap_tolerance_is_exactly_one_day(
        self,
        second_offset: int,
        expected_events: int,
        expected_span: tuple[int, int] | None,
    ) -> None:
        events = self._events(second_offset=second_offset)

        assert len(events) == expected_events
        if expected_span is not None:
            (event,) = events
            assert event.start_date == day(expected_span[0])  # type: ignore[attr-defined]
            assert event.end_date == day(expected_span[1])  # type: ignore[attr-defined]
        else:
            assert [event.start_date for event in events] == [  # type: ignore[attr-defined]
                day(100),
                day(103),
            ]

    def test_a_d7_firing_covers_its_whole_window_not_only_its_end_day(self) -> None:
        values = [0.0] * 300
        for offset in range(150, 157):
            values[offset] = 20.0

        events = detect_events(
            daily=daily_series(values),
            tier="extrema",
            window_lengths=(7,),
            gap_days=0,
            min_samples=1,
            tier_percentiles={"extrema": 99.0},
        )

        span = covered_days(events)
        assert day(150) in span, "the coverage set is [E-L+1, E], not [E, E]"
        assert day(156) in span


# ---------------------------------------------------------------------------
# Task 1.4 — tier interaction: the alta span bridges two extrema peaks
# ---------------------------------------------------------------------------


class TestTierInteraction:
    """Detection runs once per tier and the tiers never consult each other.

    Two 100 mm peaks 20 days apart, with a 40 mm plateau between them. The
    plateau reaches ``alta`` and not ``extrema``, so ``extrema`` yields TWO
    rows and ``alta`` yields ONE row spanning both — an ``alta`` span that is a
    superset of two ``extrema`` spans is the ratified behaviour, and it is the
    reason ``tier`` joins the identity key (D2).
    """

    PEAK_A = 100
    PEAK_B = 120
    TIERS = {"extrema": 99.0, "alta": 95.0}

    def _series(self) -> tuple[tuple[date, float], ...]:
        values = [0.0] * 300
        for offset in range(self.PEAK_A, self.PEAK_B + 1):
            values[offset] = 40.0
        values[self.PEAK_A] = 100.0
        values[self.PEAK_B] = 100.0
        return daily_series(values)

    def _events(self, tier: str) -> tuple[object, ...]:
        return detect_events(
            daily=self._series(),
            tier=tier,
            window_lengths=(1,),
            min_samples=1,
            tier_percentiles=self.TIERS,
        )

    def test_extrema_yields_two_rows_one_per_peak(self) -> None:
        events = self._events("extrema")

        assert len(events) == 2
        assert [(event.start_date, event.end_date) for event in events] == [  # type: ignore[attr-defined]
            (day(self.PEAK_A), day(self.PEAK_A)),
            (day(self.PEAK_B), day(self.PEAK_B)),
        ]

    def test_alta_yields_one_row_spanning_both_peaks(self) -> None:
        (event,) = self._events("alta")

        assert event.start_date == day(self.PEAK_A)  # type: ignore[attr-defined]
        assert event.end_date == day(self.PEAK_B)  # type: ignore[attr-defined]

    def test_the_tier_travels_on_the_event(self) -> None:
        assert {event.tier for event in self._events("alta")} == {"alta"}  # type: ignore[attr-defined]
        assert {event.tier for event in self._events("extrema")} == {"extrema"}  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Task 1.5 — an incomplete window is a false negative, never a fabricated event
# ---------------------------------------------------------------------------


class TestIncompleteWindowsNeverQualify:
    """R1 S3, and the two DIFFERENT failure modes a reader would otherwise fuse.

    An INTERIOR hole leaves the window present and incomplete, so the window is
    skipped and never partially summed. A LEADING or TRAILING hole moves the
    span ``absolute_window_samples`` infers from ``min``/``max``
    (``climatology.py``), so the edge window VANISHES instead of reporting
    itself incomplete. Same outcome for the catalog, different mechanism, and a
    reader who assumes they are the same will eventually add a completeness
    check to a window that does not exist.
    """

    def test_an_interior_hole_never_produces_a_partial_sum(self) -> None:
        values = [0.0] * 300
        values[150] = 200.0
        values[152] = 200.0

        events = detect_events(
            daily=daily_series(values, holes=frozenset({151})),
            tier="extrema",
            window_lengths=(3,),
            gap_days=0,
            min_samples=1,
            tier_percentiles={"extrema": 99.0},
        )

        fired = [window for event in events for window in event.fired_windows]  # type: ignore[attr-defined]
        assert all(window.peak_total_mm != 400.0 for window in fired), (
            "the 150+152 pair was summed across the missing day 151"
        )
        assert all(window.peak_end not in {day(151), day(152), day(153)} for window in fired), (
            "a window spanning the hole fired"
        )

    def test_a_trailing_hole_deletes_the_edge_window_rather_than_reporting_it_incomplete(
        self,
    ) -> None:
        values = [0.0] * 200
        values[199] = 1000.0
        daily = daily_series(values, holes=frozenset({199}))

        samples = absolute_window_samples(daily=daily, days=1)

        assert all(sample.complete for sample in samples)
        assert all(sample.end != day(199) for sample in samples)
        assert (
            detect_events(
                daily=daily,
                tier="extrema",
                window_lengths=(1,),
                min_samples=1,
                tier_percentiles={"extrema": 99.0},
            )
            == ()
        )


# ---------------------------------------------------------------------------
# Tasks 1.7 / 1.9 — the D5 lockstep, and a floor that is derived, not borrowed
# ---------------------------------------------------------------------------


DETECTOR_SOURCE = (
    Path(app.__file__).resolve().parent / "domains" / "geo" / "rainfall" / "detector.py"
)


class TestDetectionConstantsAreLockedToTheRevision:
    """D5: EVERY constant that can move a span or a tier is in the pin.

    An earlier revision pinned only the span end. That is not enough: changing
    ``GAP_DAYS`` alone merges two historic events under a new ``start_date``,
    and since the catalog is append-only the old rows cannot be deleted — so
    one revision string would permanently serve two contradictory tellings of
    the same weather. The digest is a hand-written literal precisely so that
    moving any constant FAILS until somebody edits the pin, which is the line
    the newest-first history comment lives on.
    """

    def test_the_pinned_digest_matches_the_frozen_constants(self) -> None:
        assert constants_digest(DETECTION_CONSTANTS) == DETECTOR_CONSTANTS_DIGEST

    def test_the_digest_is_a_literal_and_not_recomputed_at_import(self) -> None:
        source = DETECTOR_SOURCE.read_text(encoding="utf-8")

        assert f'DETECTOR_CONSTANTS_DIGEST = "{DETECTOR_CONSTANTS_DIGEST}"' in source, (
            "a digest computed at import time can never fail, and pins nothing"
        )

    @pytest.mark.parametrize(
        "key, mutated",
        [
            pytest.param("climatology_span_start", "1992-01-01", id="span-start"),
            pytest.param("climatology_span_end", "2027-01-01", id="span-end"),
            pytest.param("window_lengths", [1, 3, 5], id="window-lengths"),
            pytest.param("gap_days", 2, id="gap-days"),
            pytest.param("min_window_samples", 3000, id="min-window-samples"),
            pytest.param("tier_percentiles", {"extrema": 99.0, "alta": 98.8}, id="tier-extrema"),
            pytest.param("tier_percentiles", {"extrema": 99.75, "alta": 95.0}, id="tier-alta"),
        ],
    )
    def test_moving_any_single_constant_moves_the_digest(self, key: str, mutated: object) -> None:
        changed = dict(DETECTION_CONSTANTS)
        changed[key] = mutated

        assert constants_digest(changed) != DETECTOR_CONSTANTS_DIGEST

    def test_the_constants_block_covers_every_frozen_value(self) -> None:
        assert DETECTION_CONSTANTS == {
            "climatology_span_start": DETECTOR_CLIMATOLOGY_START.date().isoformat(),
            "climatology_span_end": DETECTOR_CLIMATOLOGY_END.date().isoformat(),
            "window_lengths": list(WINDOW_LENGTHS),
            "gap_days": GAP_DAYS,
            "min_window_samples": MIN_WINDOW_SAMPLES,
            "tier_percentiles": dict(TIER_PERCENTILES),
        }

    def test_the_history_comment_names_the_current_revision(self) -> None:
        source = DETECTOR_SOURCE.read_text(encoding="utf-8")

        assert f"# - `{DETECTOR_REVISION}`" in source, (
            "the newest-first history convention (policy.py) is what turns a "
            "digest edit into an audited revision bump"
        )

    def test_extrema_is_strictly_stricter_than_alta(self) -> None:
        assert TIER_PERCENTILES["extrema"] > TIER_PERCENTILES["alta"]

    def test_the_climatology_span_is_whole_calendar_years(self) -> None:
        assert (DETECTOR_CLIMATOLOGY_START.month, DETECTOR_CLIMATOLOGY_START.day) == (1, 1)
        assert (DETECTOR_CLIMATOLOGY_END.month, DETECTOR_CLIMATOLOGY_END.day) == (1, 1)


class TestTheSampleFloorIsDerivedNotBorrowed:
    """1.9 — a characterization pin (it passes on arrival by construction).

    Its RED is the executed mutant, not a red-to-green cycle:
    ``MIN_WINDOW_SAMPLES -> MIN_WINDOW_BASELINE_YEARS`` is run in the mutant
    sweep. ``MIN_WINDOW_BASELINE_YEARS = 20`` is a floor over ~30 YEARLY
    samples; applying it to ~12.7k ROLLING windows is a floor carried across
    populations, which is the error class that got a predecessor design
    rejected twice.
    """

    def test_the_two_floors_are_neither_the_same_object_nor_the_same_value(self) -> None:
        assert MIN_WINDOW_SAMPLES is not MIN_WINDOW_BASELINE_YEARS
        assert MIN_WINDOW_SAMPLES != MIN_WINDOW_BASELINE_YEARS

    def test_the_detector_does_not_import_the_snapshot_compute_module(self) -> None:
        tree = ast.parse(DETECTOR_SOURCE.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }

        assert not any(module.endswith("rainfall.compute") for module in imported)


# ---------------------------------------------------------------------------
# Task 1.10 — D10: the name and the description are SYNTHESIZED, never stored
# ---------------------------------------------------------------------------


def an_event(
    *,
    tier: str = "extrema",
    start: date,
    end: date,
    peak: date | None = None,
    max_percentile: float = 99.4,
    fired: tuple[FiredWindow, ...] = (),
) -> DetectedEvent:
    return DetectedEvent(
        tier=tier,
        start_date=start,
        end_date=end,
        peak_date=peak or start,
        max_percentile=max_percentile,
        fired_windows=fired
        or (
            FiredWindow(days=3, peak_end=start, peak_total_mm=120.0, percentile=99.4),
            FiredWindow(days=7, peak_end=end, peak_total_mm=180.0, percentile=99.1),
        ),
        climatology_span_start=date(1991, 1, 1),
        climatology_span_end=date(2026, 1, 1),
    )


class TestSynthesizedName:
    """The three shapes, verbatim, plus the tier word mapping.

    Nothing here is stored: both strings run at READ time (D10), so this test
    is the only place the wording is pinned. ``isHistoricFlood`` silently
    filters out any record without a ``name``, with no error anywhere, which is
    why the name is a function and not a nullable column.

    Spanish in the picker's existing UNACCENTED register — the surrounding
    literals carry no accents, and a lone accented month would read as a
    different voice on the same card.
    """

    @pytest.mark.parametrize(
        "tier, start, end, expected",
        [
            pytest.param(
                "extrema",
                date(2025, 9, 5),
                date(2025, 9, 5),
                "Lluvia extrema 5 de septiembre 2025",
                id="one-day",
            ),
            pytest.param(
                "extrema",
                date(2015, 3, 12),
                date(2015, 3, 15),
                "Lluvia extrema 12-15 de marzo 2015",
                id="same-month-range",
            ),
            pytest.param(
                "alta",
                date(2003, 2, 28),
                date(2003, 3, 3),
                "Lluvia intensa 28 de febrero - 3 de marzo 2003",
                id="cross-month-range",
            ),
            pytest.param(
                "alta",
                date(2002, 12, 30),
                date(2003, 1, 2),
                "Lluvia intensa 30 de diciembre 2002 - 2 de enero 2003",
                id="cross-year-range",
            ),
        ],
    )
    def test_the_name_shape(self, tier: str, start: date, end: date, expected: str) -> None:
        assert synthesize_name(an_event(tier=tier, start=start, end=end)) == expected

    def test_the_tier_word_mapping_is_exhaustive(self) -> None:
        words = {
            tier: synthesize_name(
                an_event(tier=tier, start=date(2020, 1, 1), end=date(2020, 1, 1))
            ).split(" 1 de")[0]
            for tier in TIER_PERCENTILES
        }

        assert words == {"extrema": "Lluvia extrema", "alta": "Lluvia intensa"}

    def test_an_unknown_tier_is_refused_rather_than_rendered_blank(self) -> None:
        with pytest.raises(ValueError, match="tier"):
            synthesize_name(
                an_event(tier="catastrofica", start=date(2020, 1, 1), end=date(2020, 1, 1))
            )


class TestSynthesizedDescription:
    """The firing windows, the max percentile with its span, and the CHIRPS line.

    The span comes from the EVENT, not from the module constants: a row ranked
    against 1991-2025 must keep saying 1991-2025 after a later revision widens
    the span, or every already-persisted generation gets silently relabelled.
    """

    def test_it_carries_the_firing_windows_the_max_and_the_disclosure(self) -> None:
        event = an_event(start=date(2015, 3, 12), end=date(2015, 3, 15))

        description = synthesize_description(event)

        assert description == (
            "Ventanas que superaron el umbral: d3 (p99.4), d7 (p99.1). "
            "Percentil maximo 99.4 sobre 1991-2025. "
            "CHIRPS ordena de forma relativa: no es una medicion en milimetros."
        )

    def test_the_span_is_read_from_the_row_not_from_the_module_constants(self) -> None:
        event = DetectedEvent(
            tier="extrema",
            start_date=date(1995, 4, 1),
            end_date=date(1995, 4, 1),
            peak_date=date(1995, 4, 1),
            max_percentile=99.8,
            fired_windows=(
                FiredWindow(days=1, peak_end=date(1995, 4, 1), peak_total_mm=90.0, percentile=99.8),
            ),
            climatology_span_start=date(1991, 1, 1),
            climatology_span_end=date(2021, 1, 1),
        )

        assert "sobre 1991-2020." in synthesize_description(event)

    def test_only_the_windows_that_fired_are_listed(self) -> None:
        event = an_event(
            start=date(2015, 3, 12),
            end=date(2015, 3, 15),
            fired=(
                FiredWindow(
                    days=7, peak_end=date(2015, 3, 15), peak_total_mm=180.0, percentile=99.1
                ),
            ),
        )

        description = synthesize_description(event)

        assert "d7 (p99.1)" in description
        assert "d1" not in description
        assert "d3" not in description


class TestInsufficientClimatologyIsLoud:
    """The ``None`` from ``absolute_window_percentile`` never becomes silence.

    ``detector.py`` is the raise SITE, so the guard lives here; B1c wires it to
    the CLI's labelled stop and its exit code. Below the floor the function
    answers ``None`` (``climatology.py``), and the only two things that can
    happen without this guard are a ``TypeError`` comparing ``None`` to a float
    or -- far worse -- a silent non-fire, which is a FABRICATED ABSENCE:
    indistinguishable in a permanent catalog from a genuinely quiet record.
    """

    def test_a_population_below_the_floor_aborts_with_a_named_reason(self) -> None:
        daily = daily_series([1.0] * 100)

        with pytest.raises(InsufficientClimatologyError, match="insufficient climatology"):
            detect_events(
                daily=daily,
                tier="extrema",
                window_lengths=(1,),
                min_samples=3650,
                tier_percentiles={"extrema": 99.0},
            )

    def test_it_is_neither_an_empty_result_nor_a_type_error(self) -> None:
        daily = daily_series([1.0] * 100)

        try:
            detect_events(
                daily=daily,
                tier="extrema",
                window_lengths=(1,),
                min_samples=3650,
                tier_percentiles={"extrema": 99.0},
            )
        except InsufficientClimatologyError:
            pass
        except TypeError as unhandled:  # pragma: no cover - the guard above wins
            pytest.fail(f"the None reached a comparison: {unhandled}")
        else:  # pragma: no cover - the guard above wins
            pytest.fail("a population below the floor was served as an empty catalog")

    def test_the_real_frozen_floor_is_what_the_defaults_use(self) -> None:
        assert MIN_WINDOW_SAMPLES == 3650
