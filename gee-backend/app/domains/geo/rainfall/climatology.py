"""Window climatology: the ONE definition of a rolling-window baseline sample.

Pure by contract -- no ``Session``, no network, no ``policy`` import. Both
consumers derive from here: the antecedent card (seasonal mode) and the future
detector (absolute mode). Days arrive ALREADY bucketed by the caller with
:func:`temporal.utc_day`; nothing in this module calls ``.date()`` on a
``timestamptz`` (LI3A-005).

The governing symmetry (D0)
---------------------------

``temporal.rolling_total`` demands the EXACT expected slot tuple, and
``compute._antecedent_metric`` measures completeness over that same slot set.
Therefore, on the SELECTED side::

    total is not None  <=>  matched_slots == expected_slots  <=>  completeness == 1.0

The selected side is already complete-or-nothing. Ranking a whole selected
window against baseline windows admitted at 0.95 would bias the ``normal`` LOW
and the percentile HIGH -- the Ops.6 bias with its sign flipped. So the
BASELINE side is complete-or-nothing too: :attr:`WindowSample.complete` is
``matched_days == expected_days``, exact equality, and there is deliberately no
0.95 floor anywhere in this module. A 29/30 window is 0.9667 and a 90-day
window short four days is 0.9556; both would have passed such a floor, and the
damage they do is to the NUMBER, with nothing suppressed and no caveat shown.

Two denominators, not one
-------------------------

``derivable_years`` (windows that fit entirely inside the persisted span) is
the denominator; ``eligible`` (derivable AND complete) is the numerator. A
baseline year whose window reaches before the span begins never had the
evidence persisted at all -- a d90 anchored mid-February needs 44 days of the
preceding year -- so it is structurally underivable rather than dropped, and a
fixed denominator of 30 would have hidden that loss behind 29/30 = 0.967. A
smaller denominator only ever makes the eligible fraction LARGER, so the
sample-size floor above this module keeps binding.

Why the absolute mode is a separate function
--------------------------------------------

An earlier revision materialized the absolute distribution alongside the
seasonal one, building ~32.6k windows per snapshot build across three window
lengths for a consumer that does not exist yet. :func:`absolute_window_samples`
is therefore a function the snapshot path never calls, kept here so the
detector inherits the same evidence rules, and guarded by a test asserting it
has no consumer. Its percentile takes an explicit ``min_samples``: more samples
is not an exemption from stating a floor.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Mode names (D8) — three independent literals.
#
# None is defined in terms of another: deriving one from another (an f-string,
# a shared prefix constant) is what would let a rename quietly carry a value
# from one mode onto the other's name on the wire, which is precisely what the
# spec forbids. ``ABSOLUTE_WEIBULL_RANK`` must never reach a served metric.
# ---------------------------------------------------------------------------

WINDOW_MEAN = "window_mean"
SEASONAL_WEIBULL_RANK = "seasonal_weibull_rank"
ABSOLUTE_WEIBULL_RANK = "absolute_weibull_rank"


@dataclass(frozen=True, slots=True)
class WindowSample:
    """One rolling window's total and the evidence behind it.

    ``complete`` is EXACT equality, not a ratio and not ``>=``: a 29/30 window
    is 0.9667 and a 90-day window missing four days is 0.9556, both of which a
    0.95 floor would admit. Admitting them biases a baseline mean LOW and the
    rank of a whole selected window HIGH.
    """

    end: date  # inclusive last day of the window
    total_mm: float
    matched_days: int
    expected_days: int

    @property
    def complete(self) -> bool:
        return self.matched_days == self.expected_days


@dataclass(frozen=True, slots=True)
class SeasonalClimatology:
    """The per-baseline-year sample set for one window length and one anchor.

    ``derivable_years`` is the DENOMINATOR: the baseline years whose window
    fits entirely inside the persisted span. A year whose window reaches before
    the span begins is not "dropped", it is structurally underivable, and
    counting it would hide the loss behind a fraction like 29/30 = 0.967.
    """

    days: int
    anchor: date  # the month/day every sample ends on
    derivable_years: tuple[int, ...]
    samples: tuple[WindowSample, ...]  # one per derivable year, same order

    @property
    def eligible(self) -> tuple[WindowSample, ...]:
        """The complete samples — the ONLY years that contribute.

        Exposed so no caller re-implements the rule; ``compute.py`` reads this
        and never its own copy.
        """
        return tuple(sample for sample in self.samples if sample.complete)


# ---------------------------------------------------------------------------
# Window assembly
# ---------------------------------------------------------------------------


def _day_map(daily: Iterable[tuple[date, float]]) -> dict[date, float]:
    """``(day, mm)`` pairs as a lookup, refusing a repeated day.

    The caller hands days ALREADY bucketed with :func:`temporal.utc_day`; this
    module never calls ``.date()`` on a ``timestamptz`` itself (LI3A-005 —
    ``psycopg2`` renders in the session TZ and nothing pins it, so a bare
    ``.date()`` moves a UTC-midnight boundary a day under UTC-3).

    A repeated day is refused rather than collapsed: a ranked statistic cannot
    take a tolerance that silently inflates a total, and ``dict()`` over pairs
    would keep the last value with no signal at all.
    """
    values: dict[date, float] = {}
    for day, value in daily:
        if day in values:
            raise ValueError(f"duplicate baseline day in climatology input: {day.isoformat()}")
        values[day] = value
    return values


def _window_sample(values: dict[date, float], *, end: date, days: int) -> WindowSample:
    """The ``days``-long window ending inclusively on *end*.

    ``expected_days == days``, always: a fixed-length rolling window has no
    year anchor, so there is no year-start grouping for a January-crossing
    window to be split across. An ABSENT day is simply not matched; a stored
    ``0.0`` is a measured dry day and counts as evidence.
    """
    start = end - timedelta(days=days - 1)
    matched = 0
    total = 0.0
    for offset in range(days):
        value = values.get(start + timedelta(days=offset))
        if value is None:
            continue
        matched += 1
        total += value
    return WindowSample(end=end, total_mm=total, matched_days=matched, expected_days=days)


def seasonal_climatology(
    *,
    daily: Iterable[tuple[date, float]],
    days: int,
    anchor: date,
    years: Iterable[int],
    span_start: date,
    span_end: date,
) -> SeasonalClimatology:
    """One ``days``-long window per baseline year, all ending on *anchor*'s
    month and day — the seasonal sample the card ranks against.

    *span_start* / *span_end* (exclusive) are the bounds of the persisted
    baseline read and are passed in rather than inferred from *daily*, because
    inferring them would conflate two different things: a day that was never
    persisted (structural, excluded from the denominator) and a HOLE inside the
    persisted span (evidence loss, which must count against completeness and be
    disclosed). Inferring the span from ``min(daily)`` would silently promote
    the second into the first — exactly the loss D4 refuses to hide.

    *years* is the caller's already-filtered year set. For a 29 February anchor
    ``temporal.baseline_years_for`` yields the 8 leap years, and the resulting
    thin sample is suppressed downstream by the sample-size floor. There is no
    leap-day branch here, and adding one would be the special case that quietly
    ranks a 29 February window against 28 February windows.

    That filtering is a PRECONDITION, not a convenience: a 29 February anchor
    handed an unfiltered year set raises ``ValueError`` out of the ``date()``
    construction on the first non-leap year, by design, so callers pass
    ``temporal.baseline_years_for(anchor)`` rather than let this module invent
    a substitute day.
    """
    if days < 1:
        raise ValueError(f"window length must be positive, got {days}")
    values = _day_map(daily)
    derivable: list[int] = []
    samples: list[WindowSample] = []
    for year in sorted(years):
        end = date(year, anchor.month, anchor.day)
        if end - timedelta(days=days - 1) < span_start or end >= span_end:
            continue
        derivable.append(year)
        samples.append(_window_sample(values, end=end, days=days))
    return SeasonalClimatology(
        days=days,
        anchor=anchor,
        derivable_years=tuple(derivable),
        samples=tuple(samples),
    )


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def weibull_percentile(baseline_values: Sequence[float], selected_value: float) -> float:
    """Empirical Weibull plotting-position rank -- pure, no suppression logic;
    the caller applies its floors before ever calling this.

    Sample = *baseline_values* plus *selected_value* (``N = n + 1``);
    returns ``p = 100 * i / (N + 1)`` where ``i`` is the 1-based ascending
    rank of *selected_value* within the combined sample, ties taking the
    MEAN of their tied positions. Including the selected value in its own
    sample avoids a degenerate 0/100 rank and keeps the range 3.1-96.9 at
    n=30 baseline years (the lowest/highest possible ranks, i=1 and i=N).

    Relocated here from ``compute.py`` so the annual pair and the window pair
    rank by the SAME definition; ``compute.py`` re-exports the name. The move
    was safe because the symbol had zero ``mock.patch`` call sites, so every
    existing import is genuinely covered by the re-export.
    """
    combined = sorted([*baseline_values, selected_value])
    n = len(combined)
    tied_positions = [
        position + 1 for position, value in enumerate(combined) if value == selected_value
    ]
    mean_rank = sum(tied_positions) / len(tied_positions)
    return 100 * mean_rank / (n + 1)


def window_normal(clim: SeasonalClimatology, *, min_years: int) -> float | None:
    """The baseline mean for this window and anchor, or ``None`` below the
    sample-size floor.

    Exposed rather than left inline so ``compute.py`` never re-implements the
    eligibility rule ``seasonal_window_percentile`` applies: one definition of
    "eligible year", the same argument that moved ``weibull_percentile`` here.
    """
    eligible = clim.eligible
    if len(eligible) < min_years:
        return None
    return sum(sample.total_mm for sample in eligible) / len(eligible)


def seasonal_window_percentile(
    clim: SeasonalClimatology, selected_total: float, *, min_years: int
) -> float | None:
    """Rank *selected_total* against the windows ending on the SAME month and
    day (~one sample per baseline year), or ``None`` below the floor.

    This is the only mode the antecedent card may serve. A ``None`` here is
    never backfilled from :func:`absolute_window_percentile`: the two rank
    against different populations, so substituting one for the other would
    serve a value under the other's name.
    """
    eligible = clim.eligible
    if len(eligible) < min_years:
        return None
    return weibull_percentile([sample.total_mm for sample in eligible], selected_total)


# ---------------------------------------------------------------------------
# Absolute mode — the detector's entry point, NEVER on the snapshot path
# ---------------------------------------------------------------------------


def absolute_window_samples(
    *, daily: Iterable[tuple[date, float]], days: int
) -> tuple[WindowSample, ...]:
    """Every rolling ``days``-long window inside the span *daily* covers.

    A SEPARATE function rather than a field of :class:`SeasonalClimatology`,
    deliberately. Materializing this eagerly beside the seasonal sample built
    ~32.6k windows per snapshot build for three window lengths with no consumer
    at all -- "for free" was simply false. Nothing on the snapshot path calls
    this, and a test asserts that no consumer exists.

    The span is INFERRED from the ``min`` and ``max`` of the surviving days, so
    the "a hole never shortens the record" guarantee holds for INTERIOR holes
    only: an interior hole leaves its windows present and incomplete, while a
    LEADING or TRAILING hole moves the inferred bound and deletes the edge
    windows outright. A caller that needs fixed-span semantics passes a series
    dense at both ends, or filters the result itself; this function cannot tell
    an edge hole from a shorter record because nothing here carries the span.
    """
    if days < 1:
        raise ValueError(f"window length must be positive, got {days}")
    values = _day_map(daily)
    if not values:
        return ()
    first, last = min(values), max(values)
    ends = (last - first).days + 2 - days
    if ends < 1:
        return ()
    return tuple(
        _window_sample(values, end=first + timedelta(days=days - 1 + offset), days=days)
        for offset in range(ends)
    )


def absolute_window_percentile(
    samples: Sequence[WindowSample], selected_total: float, *, min_samples: int
) -> float | None:
    """Rank *selected_total* against ALL rolling windows of that length.

    *min_samples* is explicit and has no default: having thousands of windows
    instead of thirty does not exempt the detector from stating the floor it
    ranks above. Only complete windows are ranked, by the same
    complete-or-nothing rule the seasonal mode applies -- the two modes differ
    in their POPULATION, never in what counts as evidence.

    Never call this to backfill a suppressed seasonal percentile: it ranks
    against a different population, so its value under the seasonal name would
    be a different statistic wearing the wrong label.
    """
    eligible = [sample.total_mm for sample in samples if sample.complete]
    if len(eligible) < min_samples:
        return None
    return weibull_percentile(eligible, selected_total)
