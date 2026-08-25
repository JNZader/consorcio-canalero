"""Extreme-event detection: the ONE definition of a catalog event span.

Pure by contract -- no ``Session``, no network, no ``repository`` import, no
``policy`` import. It turns a persisted daily series into event spans and
nothing else; the reading, the writing and the runbook live elsewhere
(``repository.persist_events``, ``detector_cli``). Days arrive ALREADY bucketed
by the caller with :func:`temporal.utc_day`, exactly as ``climatology`` requires.

The governing rule (D0)
-----------------------

    **Catalog identity is a function of evidence, never of when the detector
    ran.**

Spec R2 S1 demands that a re-run at the same revision over the same persisted
rows insert, update and delete nothing. Everything below follows from that:

* the ranking population is a FROZEN, whole-calendar-year span
  (:data:`DETECTOR_CLIMATOLOGY_START` .. :data:`DETECTOR_CLIMATOLOGY_END`),
  never "everything persisted so far" -- a rolling population makes R2 S1
  unsatisfiable, because yesterday's rank moves when today's day lands;
* every parameter that can move a span or a tier is frozen TOGETHER with
  :data:`DETECTOR_REVISION` (D5, see the digest below);
* a row is written only once its extent is settled, which under a full-span
  run it always is.

The boundary rule (D1) -- union of coverage, not a run of hot days
------------------------------------------------------------------

For window length ``L`` and tier ``T``, an end-day ``E`` *fires* iff its
``L``-window is COMPLETE (``WindowSample.complete``, exact equality -- there is
deliberately no 0.95 floor anywhere in the climatology module and none here)
and its absolute percentile is ``>=`` ``threshold(T)``. Its *coverage set* is
the ``L`` days ``[E-L+1, E]``. The tier's day-set is the UNION of every firing
window's coverage set, and an event is a maximal run in that union bridging
gaps of at most :data:`GAP_DAYS`.

The proposal's literal wording -- "consecutive over-threshold days" -- was
ambiguous and, read literally, **provably drops accumulation events**: seven
moderate days whose d7 total ranks p99.9 contain no single day anywhere near
the d1 threshold, so the run of over-threshold days is EMPTY and the event the
spec explicitly wants recorded as ``d7`` never exists. A d7 window's
constituent days are not individually over any threshold; that is the whole
point of ranking a window instead of a day.

Detection runs once per tier and the tiers never consult each other. Severity
is uniform within a row because the tier IS the severity, so there is no
precedence table and no decision row with an empty domain. An ``alta`` span
that is a superset of two separate ``extrema`` spans is the ratified behaviour,
and it is exactly why ``tier`` joins the identity key (D2).

Why there is no incremental mode (D6)
-------------------------------------

An earlier revision of this design carried one, and it is **cut deliberately**;
this paragraph exists so a future reader does not "restore the missing
incremental mode". The climatology span is frozen to whole calendar years, so
every run ranks against the same distribution and reads the same rows;
advancing the span requires a revision bump, which regenerates the whole
generation anyway. The incremental path existed only to bound a read of ~12.7k
rows -- roughly one indexed range scan -- and it cost two of the hardest
findings in review: sealing a truncated event's extent, and deferrals that were
permanently lost. Both dissolve with it. The detector runs FULL-SPAN, always.

Ranking cost, and why the threshold is found by bisection
---------------------------------------------------------

``absolute_window_percentile`` sorts its whole population on every call, so
ranking each of ~12.8k windows individually is ~38k sorts of ~12.8k floats per
tier -- minutes to hours, not seconds. The percentile is MONOTONE
non-decreasing in the selected total (a larger value can only take a larger
mean rank in the combined sample), so ``p(total) >= threshold`` holds exactly
for ``total >= critical``, and the critical total is found with ~log2(n) calls
to the real function. The ranking definition is never re-implemented here: the
bisection's oracle IS ``climatology.absolute_window_percentile``, and the
percentile recorded on each firing window is a real call to it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType

from app.domains.geo.rainfall.climatology import (
    WindowSample,
    absolute_window_percentile,
    absolute_window_samples,
)

# ---------------------------------------------------------------------------
# The frozen detection constants (D4) -- all of them pinned together (D5).
# ---------------------------------------------------------------------------

DETECTOR_CLIMATOLOGY_START = datetime(1991, 1, 1, tzinfo=UTC)
DETECTOR_CLIMATOLOGY_END = datetime(2026, 1, 1, tzinfo=UTC)  # exclusive, whole years
WINDOW_LENGTHS = (1, 3, 7)
GAP_DAYS = 1
MIN_WINDOW_SAMPLES = 3650
# READ-ONLY, not merely "by convention". D5 seals these to the revision, but a
# plain dict is sealed only to the SOURCE: any module in the process could run
# `TIER_PERCENTILES["extrema"] = 99.0` at import time, change what fires for the
# whole run, and leave the digest test green -- the digest is computed FROM the
# mapping the mutation just edited, so it agrees with the mutation instead of
# catching it. `MappingProxyType` makes that write raise rather than land.
TIER_PERCENTILES: Mapping[str, float] = MappingProxyType(
    {"extrema": 99.75, "alta": 98.8}  # owner-ratified 2026-08-26
)

# Whole calendar years ONLY, so the ranking distribution cannot shift mid-year
# as new days land (D0). A partial trailing year would make the same window
# rank differently on two runs of the same revision, which is precisely what
# R2 S1 forbids.
#
# MIN_WINDOW_SAMPLES is DERIVED, not borrowed. `compute.MIN_WINDOW_BASELINE_YEARS
# = 20` is a floor over ~30 YEARLY samples; reusing it over ~12.7k ROLLING
# windows is a floor carried across populations -- the exact scale-blind reuse
# that got a predecessor design rejected twice. 3650 is ten years of rolling
# windows, below which a p99 has fewer than ~36 windows above it and the tail
# rank is noise.
#
# The ratified rationale for the two tier percentiles is the MEASURED
# percentile -> firing-day table over the all-window population (N ~ 12,780),
# reproduced here because the spec requires the rationale to be pinned in the
# code and not only in a design document:
#
#     percentile | firing end-days per window length
#     -----------+----------------------------------
#     p95.0      | ~639
#     p98.0      | ~256
#     p99.0      | ~128
#     p99.5      |  ~64
#     p99.75     |  ~32   <- `extrema`
#     p99.9      |  ~13
#     p98.8      | ~153   <- `alta`
#
# `weibull_percentile` is `p = 100 * mean_rank / (n + 1)` with `n = N + 1`, so
# `p >= T` selects the top `(100 - T)%` of the population. The earlier p99/p95
# wording was carried from an estimate taken over the ~2,400 WET-DAY
# population, while this detector ranks over ALL rolling windows: p99 there is
# ~130 events and p95 ~600, roughly 4x the ~30/~150 volumes the proposal
# described. Ratified 2026-08-26: the LIST SIZES were the intent, so the
# constants are p99.75 / p98.8. The ~470 events between p98.8 and p99.75 stay
# out of the catalog, recoverable later by a constants change plus a revision
# bump -- which the lockstep below makes a single audited move.

# Read-only all the way down, for the same reason: a frozen outer mapping
# holding a mutable inner one seals nothing. `window_lengths` is a TUPLE rather
# than the list it used to be; `json` renders both as the same array, so the
# pinned digest below did not move when the types did.
DETECTION_CONSTANTS: Mapping[str, object] = MappingProxyType(
    {
        "climatology_span_start": DETECTOR_CLIMATOLOGY_START.date().isoformat(),
        "climatology_span_end": DETECTOR_CLIMATOLOGY_END.date().isoformat(),
        "window_lengths": WINDOW_LENGTHS,
        "gap_days": GAP_DAYS,
        "min_window_samples": MIN_WINDOW_SAMPLES,
        "tier_percentiles": TIER_PERCENTILES,
    }
)


def constants_digest(constants: Mapping[str, object]) -> str:
    """A stable hash of a detection-constants mapping.

    Canonical JSON (sorted keys, no incidental whitespace) so the digest is a
    function of the VALUES and never of dict insertion order or of how the
    literal happened to be formatted.

    ``default=dict`` is what lets the READ-ONLY constants above be hashed:
    ``json`` refuses a ``mappingproxy`` outright (it is not a ``dict``
    subclass), at any nesting depth. It normalizes the CONTAINER only, never a
    value, so the digest stays a function of the values -- a proxy and the dict
    it wraps hash identically, which is why sealing the constants did not move
    the pinned literal.
    """
    payload = json.dumps(constants, sort_keys=True, separators=(",", ":"), default=dict)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# The lockstep (D5). `DETECTOR_CONSTANTS_DIGEST` is a hand-written LITERAL, not
# `constants_digest(DETECTION_CONSTANTS)`: a digest computed at import time can
# never disagree with itself and therefore pins nothing. Moving any constant
# above fails the digest test until somebody edits this block, and this block
# is where the newest-first history comment lives -- so a constants change and
# a revision bump become one audited edit instead of two independent ones.
#
# Why every constant and not just the span end: changing `GAP_DAYS` alone
# merges two historic events under a new `start_date`. The catalog is
# append-only, so the old rows cannot be deleted, and one revision string would
# permanently serve two contradictory tellings of the same weather.
#
# Naming and the newest-first convention follow `RAINFALL_METRIC_POLICY_REVISION`
# (`policy.py`). History of this constant, newest first:
#
# - `rainfall-extreme-v1-2026-08` (lluvia-eventos-extremos B1a, design.md D4/D5):
#   the first generation. Span [1991-01-01, 2026-01-01), windows d1/d3/d7,
#   `GAP_DAYS = 1`, `MIN_WINDOW_SAMPLES = 3650`, tiers p99.75 / p98.8 as
#   ratified 2026-08-26 against the measured percentile->count table above.
DETECTOR_REVISION = "rainfall-extreme-v1-2026-08"
DETECTOR_CONSTANTS_DIGEST = "97584d309ae4fc648bf683890ccabe467d78c8645cf1b9578aa11cf790c65331"

SPAN_START_DAY = DETECTOR_CLIMATOLOGY_START.date()
SPAN_END_DAY = DETECTOR_CLIMATOLOGY_END.date()  # exclusive


class InsufficientClimatologyError(ValueError):
    """The ranked population is below :data:`MIN_WINDOW_SAMPLES`.

    ``absolute_window_percentile`` answers ``None`` below its floor
    (``climatology.py``), and the detector must never let that ``None`` become
    either a silent non-fire -- a FABRICATED ABSENCE, indistinguishable in the
    catalog from a genuinely quiet record -- or a ``TypeError`` comparing
    ``None`` to a float. A catalog row is permanent, so unlike a snapshot
    metric the detector never degrades: it stops with a named reason, mirroring
    ``repository.DuplicateBaselineSlotError``'s discipline.

    Unreachable for the zone asset at ~12.7k samples; reachable for any future
    asset with a short record, which is exactly when a silent non-fire would be
    most misleading.

    Two shapes, distinguishable by message and both loud:

    * MARGINAL -- the population exists but sits below *min_samples*
      (``_critical_total``);
    * GROSS -- the record is shorter than the requested window, so
      ``absolute_window_samples`` answers ``()`` and there is no population at
      all (``_firings``). Stopping less loudly for the WORSE evidence would be
      backwards, so this case raises too rather than skipping the length.
    """


@dataclass(frozen=True, slots=True)
class FiredWindow:
    """One window length that fired inside an event, at its strongest end-day.

    Only windows that FIRED are recorded (D3). ``peak_end`` is the end-day of
    the strongest firing of this length inside the event, not the event's own
    end: a d7 window ending on the event's last day and a d1 window firing on
    its first are both true statements about different days.
    """

    days: int
    peak_end: date
    peak_total_mm: float
    percentile: float

    @property
    def label(self) -> str:
        """``d1`` / ``d3`` / ``d7`` -- the key the persisted JSON uses."""
        return f"d{self.days}"


@dataclass(frozen=True, slots=True)
class DetectedEvent:
    """One event span at one tier, with the evidence that produced it.

    ``climatology_span_start`` / ``_end`` travel ON THE EVENT rather than being
    read back from the module constants at render time. The row must be
    self-describing (D5): a description that says "sobre 1991-2025" has to mean
    the span THIS row was ranked against, not whatever span the code happens to
    carry when somebody reads it, or a constants bump would silently relabel
    every already-persisted generation.
    """

    tier: str
    start_date: date
    end_date: date
    peak_date: date
    max_percentile: float
    fired_windows: tuple[FiredWindow, ...]
    climatology_span_start: date
    climatology_span_end: date  # exclusive

    @property
    def fired_windows_payload(self) -> dict[str, dict[str, object]]:
        """The persisted JSON shape (D3) -- one entry per window that fired."""
        return {
            window.label: {
                "peak_end": window.peak_end.isoformat(),
                "peak_total_mm": window.peak_total_mm,
                "percentile": window.percentile,
            }
            for window in self.fired_windows
        }

    @property
    def clipped_at_span_end(self) -> bool:
        """The event reaches the frozen span's last day, so it may be cut.

        DERIVED, never stored: the same row under a wider span in a later
        revision is a different row, and a stored flag would go stale the
        moment the span moved.
        """
        return self.end_date == self.climatology_span_end - timedelta(days=1)


@dataclass(frozen=True, slots=True)
class _Firing:
    """One (length, end-day) that cleared the tier threshold."""

    days: int
    end: date
    total_mm: float
    percentile: float


def _critical_total(
    samples: Sequence[WindowSample], *, threshold: float, min_samples: int
) -> float | None:
    """The smallest complete-window total whose percentile reaches *threshold*.

    ``None`` when no window in the population reaches it. Raises
    :class:`InsufficientClimatologyError` below the sample floor rather than
    letting ``absolute_window_percentile``'s ``None`` propagate.
    """
    complete = [sample.total_mm for sample in samples if sample.complete]
    if len(complete) < min_samples:
        raise InsufficientClimatologyError(
            "insufficient climatology for the ranked population: "
            f"{len(complete)} complete windows, floor is {min_samples}"
        )
    totals = sorted(set(complete))
    highest = absolute_window_percentile(samples, totals[-1], min_samples=min_samples)
    if highest is None:  # pragma: no cover - the floor above already guarantees a value
        raise InsufficientClimatologyError(
            "absolute_window_percentile declined to rank above its own floor"
        )
    if highest < threshold:
        return None
    low, high = 0, len(totals) - 1
    while low < high:
        middle = (low + high) // 2
        percentile = absolute_window_percentile(samples, totals[middle], min_samples=min_samples)
        assert percentile is not None  # noqa: S101 - the floor is checked above
        if percentile >= threshold:
            high = middle
        else:
            low = middle + 1
    return totals[low]


def _firings(
    *,
    daily: Sequence[tuple[date, float]],
    window_lengths: Sequence[int],
    threshold: float,
    min_samples: int,
) -> list[_Firing]:
    fired: list[_Firing] = []
    for days in window_lengths:
        samples = absolute_window_samples(daily=daily, days=days)
        if not samples:
            # GROSS insufficiency, and it must be LOUDER than the marginal kind
            # `_critical_total` raises below. `absolute_window_samples` answers
            # `()` when the record is shorter than the window, so a `continue`
            # here would drop the whole length silently -- the catalog would
            # then be a true statement about the lengths that fit and a false
            # one about the length that did not, in the same rows, with nothing
            # marking which. That is the fabricated absence
            # `InsufficientClimatologyError` exists to prevent, reached through
            # the one branch the floor check below never sees.
            raise InsufficientClimatologyError(
                f"the persisted record is shorter than the {days}-day window: "
                "the ranked population is empty"
            )
        critical = _critical_total(samples, threshold=threshold, min_samples=min_samples)
        if critical is None:
            continue
        for sample in samples:
            if not sample.complete or sample.total_mm < critical:
                continue
            percentile = absolute_window_percentile(
                samples, sample.total_mm, min_samples=min_samples
            )
            assert percentile is not None  # noqa: S101 - the floor is checked above
            fired.append(
                _Firing(
                    days=days,
                    end=sample.end,
                    total_mm=sample.total_mm,
                    percentile=percentile,
                )
            )
    return fired


def _coverage(firing: _Firing) -> tuple[date, ...]:
    """The ``[E-L+1, E]`` days a firing window vouches for.

    NOT ``[E, E]``. Collapsing the coverage set to the end-day is the mutation
    that makes the accumulation event disappear: a d7 firing would then vouch
    for one day out of the seven whose total earned it.
    """
    start = firing.end - timedelta(days=firing.days - 1)
    return tuple(start + timedelta(days=offset) for offset in range(firing.days))


def _spans(days: Sequence[date], *, gap_days: int) -> list[tuple[date, date]]:
    """Maximal runs in *days*, bridging gaps of at most *gap_days*."""
    spans: list[tuple[date, date]] = []
    start = previous = days[0]
    for current in days[1:]:
        if (current - previous).days - 1 > gap_days:
            spans.append((start, previous))
            start = current
        previous = current
    spans.append((start, previous))
    return spans


def _strongest_per_length(firings: Sequence[_Firing]) -> tuple[FiredWindow, ...]:
    """One :class:`FiredWindow` per length, at its strongest end-day.

    Ties break on the EARLIEST end-day so the output is a function of the
    evidence alone (D0) and not of iteration order.
    """
    best: dict[int, _Firing] = {}
    for firing in firings:
        current = best.get(firing.days)
        if (
            current is None
            or firing.percentile > current.percentile
            or (firing.percentile == current.percentile and firing.end < current.end)
        ):
            best[firing.days] = firing
    return tuple(
        FiredWindow(
            days=firing.days,
            peak_end=firing.end,
            peak_total_mm=firing.total_mm,
            percentile=firing.percentile,
        )
        for firing in (best[days] for days in sorted(best))
    )


def detect_events(
    *,
    daily: Sequence[tuple[date, float]],
    tier: str,
    window_lengths: Sequence[int] = WINDOW_LENGTHS,
    gap_days: int = GAP_DAYS,
    min_samples: int = MIN_WINDOW_SAMPLES,
    tier_percentiles: Mapping[str, float] = TIER_PERCENTILES,
    climatology_span: tuple[date, date] = (SPAN_START_DAY, SPAN_END_DAY),
) -> tuple[DetectedEvent, ...]:
    """Every event of *tier* in *daily*, per D1.

    Every parameter after *tier* defaults to the frozen block above and exists
    so a test can rank a hand-built 300-day series -- which cannot reach p99.75
    at all, since ``100 * mean_rank / (N + 1)`` caps below 100 for finite N --
    and so a future revision can move a constant in ONE audited place. The
    defaults are the sealed values; :data:`DETECTOR_CONSTANTS_DIGEST` pins them.

    Raises :class:`InsufficientClimatologyError` rather than returning an empty
    tuple when the population is below *min_samples*, and likewise when the
    record is shorter than a requested window and there is no population at
    all: an empty catalog and a catalog that could not be computed are
    different facts.
    """
    if tier not in tier_percentiles:
        raise ValueError(f"unknown tier {tier!r}; known tiers are {sorted(tier_percentiles)}")
    threshold = tier_percentiles[tier]
    firings = _firings(
        daily=daily,
        window_lengths=window_lengths,
        threshold=threshold,
        min_samples=min_samples,
    )
    if not firings:
        return ()

    covered: set[date] = set()
    for firing in firings:
        covered.update(_coverage(firing))

    span_start, span_end = climatology_span
    events: list[DetectedEvent] = []
    for start, end in _spans(sorted(covered), gap_days=gap_days):
        inside = [firing for firing in firings if start <= firing.end <= end]
        # BY DECISION, `max_percentile` compares percentiles taken over
        # DIFFERENT populations: each firing's percentile is a rank within its
        # own window-length distribution, so a d1 p99.8 and a d7 p99.6 are not
        # measurements of the same quantity. Ranking them against each other is
        # the intended reading -- "the strongest single statement this event
        # supports" -- and not an oversight to be normalized away later.
        # Ties break on the EARLIEST end-day, hence the negated ordinal.
        peak = max(inside, key=lambda firing: (firing.percentile, -firing.end.toordinal()))
        events.append(
            DetectedEvent(
                tier=tier,
                start_date=start,
                end_date=end,
                peak_date=peak.end,
                max_percentile=peak.percentile,
                fired_windows=_strongest_per_length(inside),
                climatology_span_start=span_start,
                climatology_span_end=span_end,
            )
        )
    return tuple(events)


# ---------------------------------------------------------------------------
# D10 -- the name and the description are SYNTHESIZED at read, never stored
# ---------------------------------------------------------------------------
#
# `isHistoricFlood` (useImageExplorerController.tsx) REQUIRES `name: string`
# and silently filters out any record without one -- no error, no log, the
# card simply never appears -- and ImageExplorerInfoPanels renders
# `description` unconditionally. Storing them would put a copy of the wording
# beside the statistics it describes, free to drift from them, and would make a
# wording fix a data migration over an APPEND-ONLY table. Deriving them costs
# one function call per served row.
#
# Spanish, in the picker's existing UNACCENTED register: every surrounding
# literal on that surface is unaccented, and a lone accented month would read
# as a different voice on the same card.

_TIER_WORDS = {"extrema": "Lluvia extrema", "alta": "Lluvia intensa"}

_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

CHIRPS_DISCLOSURE = "CHIRPS ordena de forma relativa: no es una medicion en milimetros."


def _month(value: date) -> str:
    return _MONTHS[value.month - 1]


def synthesize_name(event: DetectedEvent) -> str:
    """The card title for *event*, in one of three shapes.

    One day        ``Lluvia extrema 5 de septiembre 2025``
    Same month     ``Lluvia extrema 12-15 de marzo 2015``
    Across months  ``Lluvia intensa 28 de febrero - 3 de marzo 2003``

    A span crossing a YEAR boundary repeats the year on both sides, because
    "30 de diciembre - 2 de enero 2003" names one year for two different ones.
    """
    try:
        word = _TIER_WORDS[event.tier]
    except KeyError:
        raise ValueError(
            f"unknown tier {event.tier!r}; known tiers are {sorted(_TIER_WORDS)}"
        ) from None
    start, end = event.start_date, event.end_date
    if start == end:
        return f"{word} {start.day} de {_month(start)} {start.year}"
    if start.year != end.year:
        return (
            f"{word} {start.day} de {_month(start)} {start.year}"
            f" - {end.day} de {_month(end)} {end.year}"
        )
    if start.month == end.month:
        return f"{word} {start.day}-{end.day} de {_month(start)} {start.year}"
    return f"{word} {start.day} de {_month(start)} - {end.day} de {_month(end)} {end.year}"


def synthesize_description(event: DetectedEvent) -> str:
    """The card body: which windows fired, the maximum, and the disclosure.

    The climatology span is read from the EVENT, never from the module
    constants: a row ranked against 1991-2025 has to keep saying 1991-2025
    after a later revision widens the span, or the bump silently relabels every
    already-persisted generation with a span it was never ranked against.

    The CHIRPS sentence is part of this prose AND a separate machine-readable
    field on the served record (D11) -- the spec requires a machine-readable
    disclosure, and the picker renders prose only.
    """
    windows = ", ".join(
        f"{window.label} (p{window.percentile:.1f})" for window in event.fired_windows
    )
    last_year = event.climatology_span_end.year - 1
    return (
        f"Ventanas que superaron el umbral: {windows}. "
        f"Percentil maximo {event.max_percentile:.1f} sobre "
        f"{event.climatology_span_start.year}-{last_year}. "
        f"{CHIRPS_DISCLOSURE}"
    )
