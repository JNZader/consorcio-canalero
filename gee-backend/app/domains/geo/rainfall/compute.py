"""Pure Rainfall v2 materialization logic: no Session, no network.

Boundary rule (design.md "Technical Approach"): adapters own providers,
``compute.py`` is pure, ``repository.py`` owns SQL, ``tasks.py`` only
orchestrates and owns the Session. Every function in this module is a plain
transformation over its inputs and is safe to unit-test without a database.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, NamedTuple

from app.domains.geo.rainfall import temporal
from app.domains.geo.rainfall.adapters.manifests import CANDIDATE_MANIFESTS

# ``weibull_percentile`` now lives in ``climatology.py`` so the annual pair and
# the antecedent-window pair rank by ONE definition. It is re-exported here --
# one direction, no cycle -- because every existing caller imports it from
# ``compute``. The move was verified safe by grep: the symbol has zero
# ``mock.patch`` call sites, which is what makes a re-export a genuine cover
# rather than a name that patches the wrong module object.
from app.domains.geo.rainfall import climatology
from app.domains.geo.rainfall.climatology import weibull_percentile
from app.domains.geo.rainfall.policy import (
    RAINFALL_METRIC_POLICY,
    RAINFALL_METRIC_POLICY_REVISION,
    MetricThresholdPolicy,
    apply_metric_policy,
)
from app.domains.geo.rainfall.scope import AnalysisScope

_CORRECTION_SEPARATOR = "+r"


def revision_family(provider_revision: str) -> str:
    """Strip a correction suffix, returning the provider-revision family.

    ``"v3-nrt+r2"`` -> ``"v3-nrt"``; a bare family revision (no adapter has
    ever emitted a correction for it) maps to itself. ``"+r"`` is reserved as
    the correction separator (design.md "NRT Correction Supersession");
    adapters MUST NOT emit ``+`` in a ``provider_revision``.
    """
    return provider_revision.split(_CORRECTION_SEPARATOR, 1)[0]


def correction_revision(family: str, ordinal: int) -> str:
    """Build the n-th correction's ``provider_revision`` string for *family*.

    ``("v3-nrt", 2)`` -> ``"v3-nrt+r2"``. The ordinal is 1 for a slot's first
    correction, chained off the current row's own ordinal for later ones
    (design.md "NRT Correction Supersession" step 2, "changed" branch).
    """
    if ordinal < 1:
        raise ValueError(f"correction ordinal must be >= 1, got {ordinal}")
    return f"{family}{_CORRECTION_SEPARATOR}{ordinal}"


# ---------------------------------------------------------------------------
# Snapshot materialization (design.md decisions 5/5b/5c and Interfaces)
# ---------------------------------------------------------------------------

_SOURCE_CLASS_BY_ID: dict[str, str] = {
    manifest.source_id: manifest.source_class for manifest in CANDIDATE_MANIFESTS
}


def _source_class_for(source_id: str) -> str:
    try:
        return _SOURCE_CLASS_BY_ID[source_id]
    except KeyError as exc:
        raise ValueError(
            f"no candidate manifest registers a source_class for source_id={source_id!r}"
        ) from exc


# ---------------------------------------------------------------------------
# The disclosure window: ONE derivation of the end everything is measured to
# (design.md D5 amendment / D6 amendment, slice 2b)
# ---------------------------------------------------------------------------


class _DisclosureWindow(NamedTuple):
    """The single derivation of "how far this analysis actually reaches"."""

    comparison_end_date: date
    year_start: datetime
    in_window: list[tuple[datetime, datetime, float]]
    window_end: datetime


def _disclosure_window(
    *,
    year: int,
    now: datetime,
    intervals: Sequence[tuple[datetime, datetime, float]],
) -> _DisclosureWindow:
    """Resolve the disclosure window from the calendar and the evidence.

    ``comparison_end_date`` is the CALENDAR end the snapshot discloses (the
    owner's accepted "calendar ``comparison_end`` + ``available_through``"
    decision); ``window_end`` is the EXCLUSIVE end everything is actually
    measured to, clipped to the last published interval because provider lag
    is the documented steady state (design.md D6 amendment). One derivation,
    two call sites -- :func:`build_snapshot` and :func:`baseline_cutoff_for`
    -- so the baseline can never be cut somewhere the selected year is not.
    """
    year_start = datetime(year, 1, 1, tzinfo=UTC)
    comparison_end_date = temporal.comparison_end(year, temporal.buenos_aires_date(now))
    comparison_end_exclusive = datetime(
        comparison_end_date.year, comparison_end_date.month, comparison_end_date.day, tzinfo=UTC
    ) + timedelta(days=1)

    in_window = [
        (interval_start, interval_end, value)
        for interval_start, interval_end, value in intervals
        if year_start <= interval_start < comparison_end_exclusive
    ]
    window_end = (
        min(comparison_end_exclusive, max(interval_end for _s, interval_end, _v in in_window))
        if in_window
        else comparison_end_exclusive
    )
    return _DisclosureWindow(comparison_end_date, year_start, in_window, window_end)


def baseline_cutoff_for(
    *,
    year: int,
    now: datetime,
    intervals: Sequence[tuple[datetime, datetime, float]],
) -> date:
    """The calendar date the 1991-2020 baseline MUST be cut at, for a build
    over *intervals* (design.md D5 amendment, LI2A-101).

    Same-date comparison is D5's whole premise, so the baseline is cut at the
    end the selected year actually reaches -- ``window_end``'s last covered
    day -- not at the raw calendar ``comparison_end``. With no provider lag
    the two are provably the same date (``window_end ==
    comparison_end_exclusive == comparison_end + 1 day``); under lag, cutting
    at the calendar date would rank a selected year that is short by the lag
    against baselines totalled through today, biasing the percentile low.

    ``tasks._persist_analysis_revision`` calls this to pick
    ``temporal.baseline_dates(...)`` BEFORE :func:`build_snapshot`, which
    then re-derives the identical window from the identical inputs -- the
    same "computed once ahead, recomputed identically inside" shape the
    caller already uses for ``comparison_end``.
    """
    return _cutoff_date(_disclosure_window(year=year, now=now, intervals=intervals).window_end)


def _cutoff_date(window_end: datetime) -> date:
    """The last day *window_end* (exclusive) actually covers.

    ``window_end`` is daily-cadence-aligned for every source that reaches
    the annual metrics (``repository.baseline_cumulatives`` counts DAYS), so
    the last covered day is the day before it.

    Normalized through ``temporal.utc_day`` rather than a bare ``.date()``
    (LI3A-005). Under provider lag -- the documented steady state -- this
    ``window_end`` is ``max(interval_end)``, a value ``psycopg2`` rendered in
    the database session's zone, so a bare ``.date()`` cut the baseline a day
    early under any non-UTC session. With no lag the two agreed by accident:
    ``window_end`` was then ``comparison_end_exclusive``, built in UTC by
    Python and therefore immune. Same helper ``series.py`` buckets its days
    with, so the two paths cannot drift.
    """
    return temporal.utc_day(window_end - timedelta(days=1))


# ---------------------------------------------------------------------------
# annual.normal / annual.percentile (design.md D4/D5, slice 2a)
# ---------------------------------------------------------------------------

# design.md D5: eligible baseline years must clear this SAMPLE-SIZE floor
# before normal/percentile are disclosed at all -- a floor, not a
# policy.RAINFALL_METRIC_POLICY threshold entry, since apply_metric_policy
# only speaks fractions (coverage/quality) and cannot see absolute n.
# February 29 has only 8 leap years in 1991-2020
# (temporal.baseline_years_for), well below this floor -- so a Feb 29
# comparison suppresses structurally, with no special-case code below.
MIN_BASELINE_YEARS = 20

# design.md D5: a baseline year's OWN day-completeness must clear this
# floor to count toward MIN_BASELINE_YEARS -- a year with a data gap must
# not silently participate as if it were whole.
_BASELINE_YEAR_COMPLETENESS_THRESHOLD = 0.95

# design.md D5: normal/percentile always carry the HISTORICAL baseline's
# own source_id, regardless of what sourced the selected year (role
# assignment, not blending) -- a bare literal (not service.py's
# RAINFALL_HISTORICAL_SOURCE) to keep compute.py's import graph pointed
# only at policy.py/scope.py/temporal.py/adapters.manifests, never at the
# orchestration layer above it.
_BASELINE_SOURCE_ID = "chirps-v3-final"

# The two reasons a baseline can be absent at disclosure time (LI2B-004).
# Named constants rather than inline literals because the caller
# (`tasks._persist_analysis_revision`) has to pick between them and a typo
# there would silently ship an undocumented reason string.
BASELINE_SCOPE_UNMAPPED = "baseline_scope_unmapped"
BASELINE_EVIDENCE_INVALID = "baseline_evidence_invalid"

# Ops.6 (archive-report.md 2026-08-11 section 10): the percentile ranks the
# SELECTED year's total, so it inherits that total's evidence problems. Its
# own reason string, distinct from `coverage_below_threshold` (which speaks
# for `annual.selected` itself) and from the two baseline reasons above,
# because the shortfall is in neither the baseline nor the policy: the
# selected year is missing days INSIDE the window it is ranked over.
SELECTED_EVIDENCE_BELOW_THRESHOLD = "selected_evidence_below_threshold"

# The sample-size reason both the annual pair and the window reference
# disclose. ONE definition on purpose: the two FLOORS are deliberately
# separate constants (MIN_BASELINE_YEARS vs MIN_WINDOW_BASELINE_YEARS, D5), so
# they can never be moved as one -- but the sentence a reader is shown when
# either floor binds says the same thing, and two literals of it is how a
# rename reaches one surface and not the other.
BASELINE_YEARS_BELOW_MINIMUM = "baseline_years_below_minimum"


def _selected_metric_disclosable(
    policy: MetricThresholdPolicy, annual_selected: dict[str, Any]
) -> bool:
    """Does ``annual.selected`` clear its OWN policy gate?

    One derivation, two callers -- :func:`build_snapshot`, which refuses to
    RANK a total the reader will never be shown, and
    :func:`revision_write_decision`, which refuses to overwrite a final
    incumbent with one -- so "good enough to disclose" cannot come to mean
    two different things inside one module.

    Reads the built metric's own ``value``/``coverage``/``completeness``/
    ``quality["score"]`` instead of re-deriving them from the intervals, so
    it measures exactly the four numbers the disclosure path
    (``service._normalize_metric``) will measure, through exactly the same
    function. A threshold moved in ``RAINFALL_METRIC_POLICY`` therefore moves
    both gates together, which is the whole point: a percentile that outlives
    the total it ranks is the defect this closes.
    """
    applied = apply_metric_policy(
        policy,
        annual_selected["metric"],
        value=annual_selected["value"],
        coverage=annual_selected["coverage"],
        quality_score=annual_selected["quality"]["score"],
        completeness=annual_selected["completeness"],
    )
    return applied.state == "available"


def _selected_metric_rankable(
    policy: MetricThresholdPolicy, annual_selected: dict[str, Any]
) -> bool:
    """May ``annual.selected``'s total be RANKED against the baseline (Ops.6)?

    Two conditions, both about the selected year's OWN evidence inside the
    clipped disclosure window:

    1. it clears its own disclosure gate
       (:func:`_selected_metric_disclosable`). A total too incomplete to SHOW
       is certainly too incomplete to RANK, and coupling the two gates is
       what stops the rank outliving the number it ranks. Before Ops.6 they
       were decoupled -- ``annual`` thresholded on its own coverage while
       ``annual_percentile`` thresholded on the BASELINE's eligible-year
       fraction, a different quantity entirely -- so a suppressed
       accumulation still shipped a percentile beside it.
    2. its day-completeness clears
       :data:`_BASELINE_YEAR_COMPLETENESS_THRESHOLD` -- deliberately the SAME
       floor every baseline year had to clear to enter the sample, not a
       second number that could drift from it. This is the condition (1)
       alone cannot express: ``weibull_percentile`` does not merely compare
       the selected year to the sample, it ranks the year INSIDE it
       (``[*baseline_values, selected_value]``), so the year being ranked is
       a member on the same terms as every other member. Holding the
       members to 0.95 and the ranked year to nothing is what let a year
       short by 10% of its days -- comfortably above ``annual``'s own 0.8
       gate -- rank ~19 points low with nothing suppressed and no caveat.

    Only the trailing edge is already handled: ``_disclosure_window`` clips
    to the last published interval, so a lagging provider leaves nothing
    missing INSIDE the window and its completeness is a flat 1.0. A hole in
    the middle is what this refuses, and refusing is the only honest answer
    -- the missing days' rain is exactly the quantity that is unknown, so
    there is no correction to apply.
    """
    return _selected_metric_disclosable(policy, annual_selected) and (
        annual_selected["completeness"] >= _BASELINE_YEAR_COMPLETENESS_THRESHOLD
    )


def _normal_and_percentile_metrics(
    *,
    baseline: dict[int, tuple[float, int, int]] | None,
    baseline_cutoff: date,
    selected_value: float | None,
    selected_evidence_rankable: bool,
    selected_temporal_state: str,
    selected_source_id: str,
    nominal_resolution: str,
    scope: AnalysisScope,
    now: datetime,
    baseline_unavailable_reason: str = BASELINE_SCOPE_UNMAPPED,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """``annual.normal``/``annual.percentile`` (design.md D4/D5): ALWAYS
    present in the envelope -- an unmapped or thin baseline suppresses
    these two metrics rather than dropping them, so a served analysis has
    a stable metric shape regardless of baseline coverage.

    *baseline_unavailable_reason* is the reason disclosed when *baseline* is
    ``None``. It defaults to the original ``"baseline_scope_unmapped"`` and
    exists because ``None`` now reaches here for TWO distinct causes
    (LI2B-004): a scope with no provider asset, and a baseline read the
    repository refused to return because the evidence is duplicated. Naming
    the second one "scope unmapped" would be the same wrong-explanation
    defect LI2A-003 fixed on the sample-size side -- a suppressed metric's
    reason is the only thing the reader gets, so it has to be true.

    *baseline_cutoff* is the EFFECTIVE end (:func:`baseline_cutoff_for`),
    not the calendar ``comparison_end`` -- the same date the caller used to
    build the *baseline* dict itself, so the year set, the disclosed
    envelope and the summed evidence all agree (design.md D5 amendment).

    *selected_evidence_rankable* is :func:`_selected_metric_rankable`'s
    verdict on ``annual.selected`` (Ops.6). It gates the PERCENTILE only, and
    only in the ``else`` branch below, AFTER the ``selected_value is None``
    case: an absent total keeps its own ``annual_selected_value_unavailable``
    reason rather than being relabelled as an evidence shortfall, since
    "there is no total" and "the total is built on too few days" are
    different things to tell a reader.
    The ``normal`` never consults it -- a baseline average ranks nothing, so
    the selected year's holes cannot bias it (the same asymmetry the
    ``selected_value is None`` branch already encodes).

    Both are built from the historical baseline alone
    (``repository.baseline_cumulatives``, D1), never from an adapter
    ``batch`` -- there is no adapter batch behind a SQL aggregate to
    inherit ``quality``/``discrepancies`` from (task 2a.8, LIB-102 fold).
    ``Provenance`` and ``MetricResult`` both set ``extra="forbid"``
    (schemas.py:11,25), so every field below is built explicitly from
    scratch rather than assumed from a partial source.
    """
    possible_years = temporal.baseline_years_for(baseline_cutoff)
    eligible_years = sorted(
        year
        for year, (_total, matched, expected) in (baseline or {}).items()
        if year in possible_years
        and expected > 0
        and (matched / expected) >= _BASELINE_YEAR_COMPLETENESS_THRESHOLD
    )
    completeness = (len(eligible_years) / len(possible_years)) if possible_years else 0.0
    coverage = (
        min((baseline[year][1] / baseline[year][2]) for year in eligible_years)
        if eligible_years
        else 0.0
    )

    last_baseline_year = max(possible_years)
    envelope_start = datetime(1991, 1, 1, tzinfo=UTC)
    envelope_end = datetime(
        last_baseline_year, baseline_cutoff.month, baseline_cutoff.day, tzinfo=UTC
    ) + timedelta(days=1)

    if baseline is None:
        normal_state, normal_reason = "suppressed", baseline_unavailable_reason
        percentile_state, percentile_reason = "suppressed", baseline_unavailable_reason
        normal_value = percentile_value = None
    elif len(eligible_years) < MIN_BASELINE_YEARS:
        # design.md D5: the per-year completeness floor already trimmed
        # `eligible_years` above; Feb 29 (only 8 leap years in 1991-2020)
        # suppresses HERE, unconditionally -- 8 < MIN_BASELINE_YEARS.
        normal_state, normal_reason = "suppressed", BASELINE_YEARS_BELOW_MINIMUM
        percentile_state, percentile_reason = "suppressed", BASELINE_YEARS_BELOW_MINIMUM
        normal_value = percentile_value = None
    else:
        normal_value = sum(baseline[year][0] for year in eligible_years) / len(eligible_years)
        normal_state, normal_reason = "available", None
        if selected_value is None:
            # The rank needs a selected-year total to rank AGAINST; the
            # normal (a pure baseline average) does not.
            percentile_value = None
            percentile_state, percentile_reason = (
                "suppressed",
                "annual_selected_value_unavailable",
            )
        elif not selected_evidence_rankable:
            # Ops.6: `total_value` sums only the slots that are PRESENT, so a
            # selected year holed inside its window is short by exactly those
            # days' rain -- and `weibull_percentile` ranks that short total
            # against baselines that each had to be ~whole to participate.
            # The NORMAL above is deliberately still served: it is a pure
            # baseline average, so it ranks nothing and the selected year's
            # holes cannot bias it (the same asymmetry the `selected_value is
            # None` branch encodes).
            percentile_value = None
            percentile_state, percentile_reason = (
                "suppressed",
                SELECTED_EVIDENCE_BELOW_THRESHOLD,
            )
        else:
            eligible_totals = [baseline[year][0] for year in eligible_years]
            percentile_value = weibull_percentile(eligible_totals, selected_value)
            percentile_state, percentile_reason = "available", None

    quality = {
        "score": completeness,
        "eligible_years": eligible_years,
        "baseline_years_possible": len(possible_years),
    }

    # design.md D5 (LIB-003, slice 2b): a current-year comparison ranks an
    # NRT-sourced total against a Final-sourced baseline -- a methodological
    # caveat the reader cannot infer from the numbers. The baseline has no
    # disclosure channel of its own (it is a SQL aggregate, so there is no
    # adapter batch whose `discrepancies` it could inherit), so the caveat
    # goes into these two metrics' OWN `discrepancies` -- the same channel,
    # carried through `_normalize_metric`'s passthrough into JSON, the audit
    # CSV rows and the xlsx sheet. Flat `key=value`, no spaces
    # (adapters/zonal.py's convention). Emitted only where it is true: a
    # completed year sourced from Final emits nothing.
    discrepancies = (
        []
        if selected_source_id == _BASELINE_SOURCE_ID
        else [f"cross_source_baseline={_BASELINE_SOURCE_ID}_vs_{selected_source_id}"]
    )

    def _provenance(method: str) -> dict[str, Any]:
        return {
            "source_id": _BASELINE_SOURCE_ID,
            "source_class": _source_class_for(_BASELINE_SOURCE_ID),
            "method": method,
            "nominal_resolution": nominal_resolution,
            "aggregation": "daily",
            "spatial_scope": scope.kind,
            "freshness": now.isoformat(),
            "available_through": envelope_end.isoformat(),
        }

    normal_metric = {
        "metric": "annual_normal",
        "value": normal_value,
        "unit": "mm",
        "state": normal_state,
        "reason": normal_reason,
        "interval_start": envelope_start.isoformat(),
        "interval_end": envelope_end.isoformat(),
        "coverage": coverage,
        "completeness": completeness,
        "quality": quality,
        "discrepancies": list(discrepancies),
        "temporal_state": "final",
        "revision": RAINFALL_METRIC_POLICY_REVISION,
        "provenance": _provenance("mean"),
        "fallback_used": False,
    }
    percentile_metric = {
        "metric": "annual_percentile",
        "value": percentile_value,
        "unit": "percentil",
        "state": percentile_state,
        "reason": percentile_reason,
        "interval_start": envelope_start.isoformat(),
        "interval_end": envelope_end.isoformat(),
        "coverage": coverage,
        "completeness": completeness,
        "quality": dict(quality),
        "discrepancies": list(discrepancies),
        "temporal_state": "provisional" if selected_temporal_state == "provisional" else "final",
        "revision": RAINFALL_METRIC_POLICY_REVISION,
        "provenance": _provenance("weibull_rank"),
        "fallback_used": False,
    }
    return normal_metric, percentile_metric


# ---------------------------------------------------------------------------
# antecedents.{d7,d30,d90} (design.md D6, slice 2a)
# ---------------------------------------------------------------------------

_ANTECEDENT_WINDOWS: tuple[tuple[str, int], ...] = (("d7", 7), ("d30", 30), ("d90", 90))


def _antecedent_metric(
    *,
    name: str,
    days: int,
    intervals: Sequence[tuple[datetime, datetime, float]],
    end: datetime,
    cadence: timedelta,
    source_id: str,
    scope: AnalysisScope,
    now: datetime,
    aggregation: str,
    nominal_resolution: str,
    batch: dict[str, Any],
    temporal_state: str,
    fallback_used: bool,
) -> dict[str, Any]:
    """One ``antecedents.{d7,d30,d90}`` entry (design.md D6): a
    cadence-exact rolling total ending at *end*, never at the calendar-year
    boundary, read from *intervals* -- the D6-widened
    ``[year_start - 90d, year_end)`` set the caller
    (``tasks._persist_analysis_revision``) reads, so a window that dips
    into the prior year still finds its rows here. Same *source_id* as
    ``annual.selected`` -- never mixing revision families (design.md D6).

    *end* is the CLIPPED disclosure end
    ``min(comparison_end_exclusive, last_interval_end)`` that
    ``annual.selected`` already uses (design.md D6 amendment), NOT the raw
    calendar ``comparison_end``: provider lag is the documented steady
    state, so anchoring the window at a slot nobody has published yet
    would fail the exact-slot-set check below and suppress all three
    antecedents on every current-year build. ``provenance.available_through``
    therefore discloses that same clipped end -- the honest value -- exactly
    as ``annual.selected`` reports its own clipped ``window_end``.

    ``temporal.rolling_total`` requires an EXACT cadence-aligned match
    (design.md: "never a short sum"), so *intervals* is filtered down to
    precisely ``[end - days, end)`` before the call; a gap anywhere in
    that window raises ``EventSuppressed``, suppressed here with its own
    reason rather than a partial sum.
    """
    window = timedelta(days=days)
    window_start = end - window
    window_pairs = tuple(
        (interval_start, value)
        for interval_start, _interval_end, value in intervals
        if window_start <= interval_start < end
    )
    expected_slots = int(window / cadence) if cadence > timedelta() else 0
    matched_slots = len(window_pairs)
    completeness = (matched_slots / expected_slots) if expected_slots > 0 else 0.0

    try:
        total = temporal.rolling_total(
            end=end, window=window, cadence=cadence, intervals=window_pairs
        )
    except temporal.EventSuppressed:
        value, state, reason = None, "suppressed", "antecedent_window_incomplete"
    else:
        value, state, reason = total, "available", None

    quality = {**batch["quality"], "score": completeness, "checksum": batch["checksum"]}
    provenance = {
        "source_id": source_id,
        "source_class": _source_class_for(source_id),
        "method": "sum",
        "nominal_resolution": nominal_resolution,
        "aggregation": aggregation,
        "spatial_scope": scope.kind,
        "freshness": now.isoformat(),
        "available_through": end.isoformat(),
    }
    return {
        "metric": name,
        "value": value,
        "unit": "mm",
        "state": state,
        "reason": reason,
        "interval_start": window_start.isoformat(),
        "interval_end": end.isoformat(),
        "coverage": completeness,
        "completeness": completeness,
        "quality": quality,
        "discrepancies": list(batch["discrepancies"]),
        "temporal_state": temporal_state,
        "revision": RAINFALL_METRIC_POLICY_REVISION,
        "provenance": provenance,
        "fallback_used": fallback_used,
    }


# ---------------------------------------------------------------------------
# antecedents.{d7,d30,d90}_{normal,percentile} — the rolling-window
# climatological reference (lluvia-antecedente-referencia, D0/D4-D9)
# ---------------------------------------------------------------------------

# D4: eligible baseline YEARS below this floor suppress both reference metrics
# with `BASELINE_YEARS_BELOW_MINIMUM`. Deliberately a SECOND constant beside
# `MIN_BASELINE_YEARS` even though both read 20 today (D5): the annual floor
# counts years of a whole-year accumulation and this one counts years of a
# `days`-long window, so a future move of one must not silently carry the
# other. February 29 is the standing proof that this floor is load-bearing on
# its own -- `temporal.baseline_years_for` yields 8 leap years there, 8 < 20,
# and the 20/30 policy entry PASSES on that path (completeness is 8/8 = 1.0),
# so this constant is the SOLE gate, not a belt beside a policy brace.
MIN_WINDOW_BASELINE_YEARS = 20

# D7 (owner-ratified 2026-08-25): the reference is available for `zone` scope
# only, and that limit is declared PER METRIC -- `quality["reference_scope"]`
# plus this suppression reason off-zone -- never as a root flag.
# `export.py:339` projects root flags as ANALYSIS-level workbook rows, so a
# root "reference scope: zone" row would state a limit about an analysis whose
# antecedent TOTALS are not zone-limited.
REFERENCE_SCOPE_UNSUPPORTED = "reference_scope_unsupported"
_REFERENCE_SCOPE_KIND = "zone"


def _antecedent_reference_metrics(
    *,
    window: str,
    days: int,
    total_metric: dict[str, Any],
    daily_baseline: Sequence[tuple[date, float]] | None,
    baseline_unavailable_reason: str,
    span: tuple[date, date] | None,
    anchor: date,
    selected_source_id: str,
    nominal_resolution: str,
    scope: AnalysisScope,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """``antecedents.{window}_normal`` and ``..._percentile`` (D6/D8/D9).

    *daily_baseline* is the value ``tasks._persist_analysis_revision`` read
    through ``repository.baseline_daily_values`` -- span-bounded and contained
    by that caller's own ``DuplicateBaselineSlotError`` handler -- or ``None``
    when it could not be resolved. It is HANDED IN rather than read here on
    purpose: a second read inside this pure module would carry neither the
    ``[1991-01-01, 2021-01-01)`` bound nor the containment, and every existing
    test would have stayed green while the six metrics silently ranked against
    a distribution the envelope keeps calling "1991-2020".

    *anchor* is the last day the SELECTED window actually covers
    (:func:`_cutoff_date` of the clipped ``window_end``). Every baseline sample
    is the ``days``-long window ending on that same month and day -- the
    seasonal mode, and the only mode the card may serve (D8).

    Reason precedence (D6), applied in this order, earlier rows winning:

    ==  =========================  ============================  ==================================
    #   condition                  ``normal``                    ``percentile``
    ==  =========================  ============================  ==================================
    1   scope is not ``zone``      ``reference_scope_unsupported``  same
    2   baseline unresolvable      *baseline_unavailable_reason*    same
    3   eligible years < 20        ``baseline_years_below_minimum`` same
    4   antecedent total is None   **served**                       ``selected_evidence_below_threshold``
    5   otherwise                  ``window_mean``                  seasonal Weibull rank
    ==  =========================  ============================  ==================================

    Row 4 is the whole of the selected-evidence floor and it is REACHABLE: by
    D0 an antecedent total is absent exactly when its window is not whole
    (``temporal.rolling_total`` demands the exact slot tuple), which is
    precisely the evidence shortfall Ops.6 named. The ``normal`` is still
    served there because a baseline average ranks nothing -- the same asymmetry
    :func:`_normal_and_percentile_metrics` encodes for the annual pair. r1's
    extra row, "total present AND completeness < 0.95", is deleted: D0 proves
    its domain empty. So is the second reason string r1 proposed for an absent
    total -- ``_antecedent_metric`` emits exactly ONE
    (``antecedent_window_incomplete``, covering both the holed window and the
    unsupported-cadence path), so a second name would have an empty domain too,
    and a dead branch against a hypothetical future reason is how r1's defect
    was born. A test asserts that name appears nowhere in the tree.
    """
    possible_years = temporal.baseline_years_for(anchor)
    on_scope = scope.kind == _REFERENCE_SCOPE_KIND

    clim = (
        climatology.seasonal_climatology(
            daily=daily_baseline,
            days=days,
            anchor=anchor,
            years=possible_years,
            span_start=span[0],
            span_end=span[1],
        )
        if daily_baseline is not None and span is not None and on_scope
        else None
    )
    eligible = clim.eligible if clim is not None else ()
    derivable = clim.derivable_years if clim is not None else ()

    # D4: the eligible/derivable YEAR fraction, NOT matched_days/expected_days
    # -- which is a constant 1.0 for every eligible year under
    # complete-or-nothing and would say nothing at all. `coverage` is the same
    # number deliberately: `apply_metric_policy` compares the threshold against
    # BOTH, so giving coverage the annual path's per-year day completeness
    # would leave half the policy gate permanently satisfied.
    completeness = (len(eligible) / len(derivable)) if derivable else 0.0
    coverage = completeness

    total_value = total_metric["value"]
    normal_value: float | None
    percentile_value: float | None

    if not on_scope:
        normal_value = percentile_value = None
        normal_state = percentile_state = "suppressed"
        normal_reason = percentile_reason = REFERENCE_SCOPE_UNSUPPORTED
    elif daily_baseline is None:
        normal_value = percentile_value = None
        normal_state = percentile_state = "suppressed"
        normal_reason = percentile_reason = baseline_unavailable_reason
    elif len(eligible) < MIN_WINDOW_BASELINE_YEARS:
        normal_value = percentile_value = None
        normal_state = percentile_state = "suppressed"
        normal_reason = percentile_reason = BASELINE_YEARS_BELOW_MINIMUM
    else:
        normal_value = climatology.window_normal(clim, min_years=MIN_WINDOW_BASELINE_YEARS)
        normal_state, normal_reason = "available", None
        if total_value is None:
            percentile_value = None
            percentile_state, percentile_reason = (
                "suppressed",
                SELECTED_EVIDENCE_BELOW_THRESHOLD,
            )
        else:
            percentile_value = climatology.seasonal_window_percentile(
                clim, total_value, min_years=MIN_WINDOW_BASELINE_YEARS
            )
            percentile_state, percentile_reason = "available", None

    # D9: the interval is the BASELINE envelope, not the selected window --
    # 1991-01-01 through the last derivable year's anchor + one day, mirroring
    # `annual_normal` (compute.py:452-453). The interval must describe the
    # sample the value speaks FOR; the selected window's own bounds would tell
    # a reader that a thirty-year climatology was measured over seven days.
    last_year = max(derivable) if derivable else max(possible_years)
    envelope_start = datetime(1991, 1, 1, tzinfo=UTC)
    envelope_end = datetime(last_year, anchor.month, anchor.day, tzinfo=UTC) + timedelta(days=1)

    quality = {
        "score": completeness,
        "eligible_years": [sample.end.year for sample in eligible],
        "baseline_years_derivable": len(derivable),
        # D7: the zone limit, declared on the metric that carries it.
        "reference_scope": _REFERENCE_SCOPE_KIND,
    }

    # Carried verbatim from the annual pair (compute.py:428-432): silence here
    # would rank an NRT-sourced window against a Final-sourced baseline with no
    # disclosure at all, and the baseline has no channel of its own.
    discrepancies = (
        []
        if selected_source_id == _BASELINE_SOURCE_ID
        else [f"cross_source_baseline={_BASELINE_SOURCE_ID}_vs_{selected_source_id}"]
    )

    def _provenance(method: str) -> dict[str, Any]:
        return {
            "source_id": _BASELINE_SOURCE_ID,
            "source_class": _source_class_for(_BASELINE_SOURCE_ID),
            # D8: the MODE reaches the wire through the field that already
            # renders as `Método` and already exports, so the two modes become
            # non-interchangeable in the served contract at zero new fields.
            # Only the seasonal mode's two names reach here; the absolute
            # mode's name is not written anywhere in this module, and task
            # 1.11's standing guard in `test_rainfall_climatology.py` fails the
            # day it is -- naming it even in prose is how a consumer starts.
            "method": method,
            "nominal_resolution": nominal_resolution,
            "aggregation": "daily",
            "spatial_scope": scope.kind,
            "freshness": now.isoformat(),
            "available_through": envelope_end.isoformat(),
        }

    normal_metric = {
        "metric": f"{window}_normal",
        "value": normal_value,
        "unit": "mm",
        "state": normal_state,
        "reason": normal_reason,
        "interval_start": envelope_start.isoformat(),
        "interval_end": envelope_end.isoformat(),
        "coverage": coverage,
        "completeness": completeness,
        "quality": dict(quality),
        "discrepancies": list(discrepancies),
        # A completed 1991-2020 climatology is final whatever the selected
        # window is; only the RANK inherits the selected total's state.
        "temporal_state": "final",
        "revision": RAINFALL_METRIC_POLICY_REVISION,
        "provenance": _provenance(climatology.WINDOW_MEAN),
        "fallback_used": False,
    }
    percentile_metric = {
        "metric": f"{window}_percentile",
        "value": percentile_value,
        "unit": "percentil",
        "state": percentile_state,
        "reason": percentile_reason,
        "interval_start": envelope_start.isoformat(),
        "interval_end": envelope_end.isoformat(),
        "coverage": coverage,
        "completeness": completeness,
        "quality": dict(quality),
        "discrepancies": list(discrepancies),
        "temporal_state": (
            "provisional" if total_metric["temporal_state"] == "provisional" else "final"
        ),
        "revision": RAINFALL_METRIC_POLICY_REVISION,
        "provenance": _provenance(climatology.SEASONAL_WEIBULL_RANK),
        "fallback_used": False,
    }
    return normal_metric, percentile_metric


def build_snapshot(
    *,
    scope: AnalysisScope,
    year: int,
    role: str,
    source_id: str,
    intervals: Sequence[tuple[datetime, datetime, float]],
    batch: dict[str, Any],
    now: datetime,
    fallback_used: bool = False,
    baseline: dict[int, tuple[float, int, int]] | None = None,
    baseline_unavailable_reason: str = BASELINE_SCOPE_UNMAPPED,
    window_baseline: Sequence[tuple[date, float]] | None = None,
    window_baseline_unavailable_reason: str = BASELINE_SCOPE_UNMAPPED,
    window_baseline_span: tuple[date, date] | None = None,
) -> dict[str, Any]:
    """Build the snapshot envelope: root keys are a subset of
    ``SNAPSHOT_ROOT_KEYS``. v1 shipped only ``annual.selected`` (decision
    5); slice 2a (design.md D3/D4/D5/D6) grows it with
    ``annual.{normal,percentile}`` and ``antecedents.{d7,d30,d90}`` --
    ALWAYS present, suppressed (never omitted) when their evidence is
    insufficient, so a served analysis has a stable metric shape
    regardless of baseline coverage.

    ``baseline`` is the caller's resolved historical baseline
    (``repository.baseline_cumulatives``, design.md D1): ``{year: (total_mm,
    matched_days, expected_days)}``, or ``None`` when the caller could not
    resolve one -- in which case ``annual.normal``/``annual.percentile`` both
    suppress with ``baseline_unavailable_reason`` (design.md D5), which
    defaults to ``"baseline_scope_unmapped"`` (no provider asset for the
    scope) and is ``"baseline_evidence_invalid"`` when the baseline read
    itself refused to answer (LI2B-004).

    Coverage/completeness/quality are recomputed here, at build time, over
    ``[year_start, min(comparison_end, last_interval_end))`` — the
    *disclosure* window — rather than reused from the fetch-time batch
    (decision 5c): the adapter measures coverage over the whole requested
    year, which would report a current year in progress as near-zero
    forever. ``quality``/``discrepancies``/``checksum`` evidence is carried
    from the batch as-is; only ``score`` (decision 5b) is added, set to the
    measured completeness — there is no independent QC signal for a
    satellite zonal mean.

    ``intervals`` is a plain, ORM-free sequence of
    ``(interval_start, interval_end, value)`` — the resolved, non-superseded
    rows for the whole requested year (repository.intervals_in_window's
    result, stripped of its ORM identity by the caller).

    ``window_baseline`` is the caller's raw baseline DAILY SERIES
    (``repository.baseline_daily_values``, D2) — ``((day, mm), ...)`` bounded
    to ``[BASELINE_SPAN_START, BASELINE_SPAN_END)``, or ``None`` when the
    caller could not resolve one, in which case the six reference metrics
    suppress with ``window_baseline_unavailable_reason``. ``window_baseline_span``
    carries that read's own bounds: it is REQUIRED alongside the values and is
    not defaulted here, because the span is the only thing that separates a day
    that was never persisted (structural, out of the denominator) from a HOLE
    inside the record (evidence loss, which must count against completeness).
    A default here would be a second copy of ``repository``'s constants living
    where no test of the read would ever reach it — and ``repository.py``
    imports this module (repository.py:16), so importing them is a cycle.
    """
    if window_baseline is not None and window_baseline_span is None:
        raise ValueError("window_baseline requires its window_baseline_span bounds")

    starts = [interval_start for interval_start, _interval_end, _value in intervals]
    if len(starts) != len(set(starts)):
        # intervals_in_window's anti-join is supposed to guarantee at most
        # one non-superseded row per slot; a duplicate here is a broken
        # invariant that must be loud, not a quietly inflated total.
        raise ValueError("build_snapshot received a duplicated interval_start slot")

    comparison_end_date, year_start, in_window, window_end = _disclosure_window(
        year=year, now=now, intervals=intervals
    )
    total_value: float | None = sum(value for _s, _e, value in in_window) if in_window else None

    cadence_seconds = batch["cadence_seconds"]
    expected_slots = (
        int((window_end - year_start) / timedelta(seconds=cadence_seconds))
        if cadence_seconds > 0
        else 0
    )
    matched_slots = len(in_window)
    completeness = (matched_slots / expected_slots) if expected_slots > 0 else 0.0
    coverage = completeness

    quality = {**batch["quality"], "score": completeness, "checksum": batch["checksum"]}

    if total_value is None:
        metric_state, metric_reason = "unavailable", "no_data_in_disclosure_window"
    else:
        metric_state, metric_reason = "available", None

    aggregation = "daily" if cadence_seconds == 86400 else f"{int(cadence_seconds)}s"
    scale_m = batch["quality"].get("scale_m", "unknown")
    nominal_resolution = f"{scale_m}m"

    provenance = {
        "source_id": source_id,
        "source_class": _source_class_for(source_id),
        "method": "sum",
        "nominal_resolution": nominal_resolution,
        "aggregation": aggregation,
        "spatial_scope": scope.kind,
        "freshness": now.isoformat(),
        "available_through": window_end.isoformat(),
    }

    annual_metric = {
        "metric": "annual",
        "value": total_value,
        "unit": batch.get("unit") or "mm",
        "state": metric_state,
        "reason": metric_reason,
        "interval_start": year_start.isoformat(),
        "interval_end": window_end.isoformat(),
        "coverage": coverage,
        "completeness": completeness,
        "quality": quality,
        "discrepancies": list(batch["discrepancies"]),
        "temporal_state": "final" if role == "historical" else "provisional",
        "revision": RAINFALL_METRIC_POLICY_REVISION,
        "provenance": provenance,
        "fallback_used": fallback_used,
    }

    # design.md D4/D5 (slice 2a) + D5 amendment (slice 2b, LI2A-101): cut at
    # the SAME EFFECTIVE end annual.selected just totalled through -- the
    # last covered day of `window_end`, not the raw calendar comparison_end
    # -- so a lagging provider cannot rank a short selected year against
    # baselines totalled through today. Identical to the calendar date when
    # there is no lag. The caller resolved the `baseline` dict itself at this
    # same cutoff (tasks._persist_analysis_revision via baseline_cutoff_for).
    #
    # Ops.6: clipping fixed only the TRAILING edge. A hole in the MIDDLE of
    # the window biases the rank low by exactly the missing days' rain, so
    # the percentile is additionally coupled to the selected year's own
    # evidence (:func:`_selected_metric_rankable`). `annual_metric` is
    # finished just above, so that verdict reads the metric's own numbers
    # instead of re-deriving coverage/completeness a second time here.
    normal_metric, percentile_metric = _normal_and_percentile_metrics(
        baseline=baseline,
        baseline_cutoff=_cutoff_date(window_end),
        selected_value=total_value,
        selected_evidence_rankable=_selected_metric_rankable(RAINFALL_METRIC_POLICY, annual_metric),
        selected_temporal_state=annual_metric["temporal_state"],
        selected_source_id=source_id,
        nominal_resolution=nominal_resolution,
        scope=scope,
        now=now,
        baseline_unavailable_reason=baseline_unavailable_reason,
    )

    # design.md D6 (slice 2a): *intervals* is the D6-widened
    # [year_start - 90d, year_end) set the caller now reads -- a window
    # that dips into the prior year still finds its rows here, while
    # annual.selected above stayed scoped to the unwidened `in_window`.
    #
    # The windows END at `window_end` -- the SAME
    # min(comparison_end_exclusive, last_interval_end) clip annual.selected
    # applies above -- not at the calendar comparison_end (design.md D6
    # amendment). Provider lag is the documented steady state, and
    # temporal.rolling_total demands an exact slot set, so a rigid calendar
    # anchor would demand a slot for TODAY and suppress all three
    # antecedents on every current-year build. With no in-window intervals
    # at all, `window_end` falls back to comparison_end_exclusive and the
    # windows suppress anyway: their last expected slot (end - cadence) is
    # never earlier than year_start, so it would have been in `in_window`
    # had it existed.
    #
    # lluvia-antecedente-referencia D1: each window's baseline `normal` and
    # `percentile` are emitted as FLAT SIBLINGS beside the total, in
    # total -> normal -> percentile order. The `snapshot` column is
    # `postgresql.JSON`, not JSONB, so that insertion order genuinely survives
    # the round trip and is the order the fold renders. Nesting them inside
    # `d30` was rejected: `MetricResult` is `extra="forbid"`, so a nested key
    # would make the TOTAL itself `metric_contract_invalid`.
    #
    # `ANTECEDENT_ORDER` (RainfallDetailPanel.tsx) is deliberately NOT
    # extended, which is what keeps the always-visible collapsed header at
    # exactly three entries and the answer-surface requirement true by
    # construction.
    cadence = timedelta(seconds=cadence_seconds) if cadence_seconds > 0 else timedelta()
    reference_anchor = _cutoff_date(window_end)
    antecedents: dict[str, Any] = {}
    for name, days in _ANTECEDENT_WINDOWS:
        total_metric = _antecedent_metric(
            name=name,
            days=days,
            intervals=intervals,
            end=window_end,
            cadence=cadence,
            source_id=source_id,
            scope=scope,
            now=now,
            aggregation=aggregation,
            nominal_resolution=nominal_resolution,
            batch=batch,
            temporal_state=annual_metric["temporal_state"],
            fallback_used=fallback_used,
        )
        normal_reference, percentile_reference = _antecedent_reference_metrics(
            window=name,
            days=days,
            total_metric=total_metric,
            daily_baseline=window_baseline,
            baseline_unavailable_reason=window_baseline_unavailable_reason,
            span=window_baseline_span,
            anchor=reference_anchor,
            selected_source_id=source_id,
            nominal_resolution=nominal_resolution,
            scope=scope,
            now=now,
        )
        antecedents[name] = total_metric
        antecedents[f"{name}_normal"] = normal_reference
        antecedents[f"{name}_percentile"] = percentile_reference

    return {
        "scope": {"kind": scope.kind, "id": scope.id, "version": scope.version},
        "regional_estimate": scope.regional_estimate,
        "year": year,
        "comparison_end": comparison_end_date.isoformat(),
        "baseline": "1991-2020",
        "metric_policy": {
            "revision": RAINFALL_METRIC_POLICY_REVISION,
            "minimum_coverage_by_metric": dict(RAINFALL_METRIC_POLICY.minimum_coverage_by_metric),
            "minimum_quality_by_metric": dict(RAINFALL_METRIC_POLICY.minimum_quality_by_metric),
            "duration_threshold": RAINFALL_METRIC_POLICY.duration_threshold,
        },
        "annual": {
            "selected": annual_metric,
            "normal": normal_metric,
            "percentile": percentile_metric,
        },
        "antecedents": antecedents,
    }


def data_revision_for(
    source_id: str,
    provider_revision_family: str,
    scope: AnalysisScope,
    year: int,
    comparison_end: date,
    intervals: Sequence[tuple[datetime, float]],
) -> str:
    """Content address (decision 3b): stable when neither the resolved
    interval values nor the disclosed ``comparison_end`` move; changes when
    either does. ``comparison_end`` MUST be in the hash — while the provider
    lags, the interval set is byte-identical day over day, and a
    content-only address would collide on ``uq_rainfall_analysis_snapshot``
    and freeze the served comparison end on the day of first compute.
    """
    canonical_intervals = sorted(
        ((interval_start.isoformat(), round(value, 6)) for interval_start, value in intervals),
        key=lambda item: item[0],
    )
    canonical = json.dumps(
        [
            source_id,
            provider_revision_family,
            [scope.kind, scope.id, scope.version],
            year,
            comparison_end.isoformat(),
            canonical_intervals,
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Year-rollover finalization: served_state, revision_write_decision, the
# per-fingerprint advisory lock key (design.md "Year-Rollover Finalization",
# "Serializing siblings — the per-fingerprint advisory lock")
# ---------------------------------------------------------------------------


def fingerprint_lock_key(request_fingerprint: str) -> int:
    """Deterministic signed 64-bit advisory-lock key derived from a request
    fingerprint (a lowercase sha256 hex digest, service.py:102-107). No new
    column: take the first 16 hex chars (the first 8 bytes) as an unsigned
    big-endian integer and reinterpret that as PostgreSQL's signed
    ``bigint`` -- process-stable (no ``hash()`` randomization). A collision
    between two unrelated fingerprints costs one shared queue slot, never a
    wrong answer.
    """
    unsigned = int(request_fingerprint[:16], 16)
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


def served_state(snapshot: dict[str, Any]) -> tuple[str, str] | None:
    """``(annual.selected.provenance.source_id, annual.selected.temporal_state)``
    from a complete envelope, or ``None`` when either is missing (a corrupt
    or pre-contract row) -- treated as *unknown*, never as *finalized*. The
    single Python function that reads it (R2-002 -- review-ledger.md
    "Pre-PR review — PR3"): called from stage 2's own defense-in-depth
    check (``tasks._revisit_stage2``), :func:`revision_write_decision`, and
    the latch branch's own event payload (``tasks._persist_analysis_revision``)
    -- so there is one place to be wrong, not three raw dict subscripts
    that could each drift from it independently.
    ``repository.completed_year_daily_done_keys`` mirrors these same two
    JSON fields in raw SQL for its own exclusion filter (a SUPERSET, not
    the authority -- see that function's docstring); it cannot call this
    function, since it runs inside the database, so it is a deliberate,
    documented second implementation, not a fourth Python reader.
    """
    annual = snapshot.get("annual")
    if not isinstance(annual, dict):
        return None
    selected = annual.get("selected")
    if not isinstance(selected, dict):
        return None
    provenance = selected.get("provenance")
    if not isinstance(provenance, dict):
        return None
    source_id = provenance.get("source_id")
    temporal_state = selected.get("temporal_state")
    if not isinstance(source_id, str) or not isinstance(temporal_state, str):
        return None
    return source_id, temporal_state


def revision_write_decision(
    incumbent: dict[str, Any] | None,
    candidate: dict[str, Any],
    policy: MetricThresholdPolicy,
) -> Literal["write", "latched", "gate_refused"]:
    """``"write"`` | ``"latched"`` | ``"gate_refused"`` (design.md
    "Write gate — no-regression semantics"). R2-005: typed as a
    ``Literal`` rather than a bare ``str`` so the consumer
    (``tasks._persist_analysis_revision``) can branch on it exhaustively
    with an explicit fail-loud ``else`` instead of a silent fall-through.

    - No incumbent, or the incumbent's ``served_state`` is ``None`` (an
      envelope the router would 503 on anyway), or incumbent and candidate
      name the same ``source_id`` -> ``"write"``. Stage 1's daily rebuild
      and the first-materialization case; decision 3b's content address
      already makes a no-information rebuild a silent no-op.
    - Cross-source, candidate ``provisional``, incumbent ``final`` ->
      ``"latched"``. Never write -- see "The latch" in design.md.
    - Cross-source otherwise (the finalization case) -> ``"write"`` iff
      :func:`_selected_metric_disclosable` -- which runs
      ``apply_metric_policy``, the SAME function the disclosure path already
      runs, over the candidate's own ``annual.selected`` -- says yes;
      otherwise ``"gate_refused"``.
    """
    incumbent_state = served_state(incumbent) if incumbent is not None else None
    if incumbent_state is None:
        return "write"

    incumbent_source_id, incumbent_temporal_state = incumbent_state
    candidate_state = served_state(candidate)
    if candidate_state is None:
        # A candidate this module built itself is always well-formed; an
        # unreadable candidate would be a compute bug, not a policy branch.
        raise ValueError("revision_write_decision received a candidate with no served_state")
    candidate_source_id, candidate_temporal_state = candidate_state

    if incumbent_source_id == candidate_source_id:
        return "write"

    if candidate_temporal_state == "provisional" and incumbent_temporal_state == "final":
        return "latched"

    disclosable = _selected_metric_disclosable(policy, candidate["annual"]["selected"])
    return "write" if disclosable else "gate_refused"
