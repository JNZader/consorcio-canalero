"""One daily-series contract for a stored Rainfall v2 analysis revision.

Two consumers, one builder (design.md D3): ``GET /rainfall/analyses/{id}/series``
for the chart, and the xlsx "Serie diaria" sheet (D7). Curve points are NOT
embedded in the snapshot -- that would inflate an immutable audit row ~15x with
display data the interval store already holds verbatim -- so they are read live
here instead.

Reading live is exactly what creates the problem this module also solves. The
revision row is immutable and forever servable, while an NRT correction can
supersede a slot inside its window at any time, so the same revision id could
otherwise serve a card whose total disagrees with its own chart. Every response
therefore carries a **server-side pin**: the ``data_revision`` digest is
recomputed over exactly the keys and the window the build read and compared
with the one stored on the row. Errors are one-directional by construction --
an ambiguous family or an unequal digest reports INCONSISTENT, and nothing
reports consistent unless the two digests are equal.

Boundary rule (design.md "Technical Approach"): ``repository.py`` owns SQL,
``compute.py`` stays pure, and this module owns the Session for one read-only
request. It is READ-ONLY on purpose: it writes nothing, enqueues nothing and
has no side effect a caller could drive by polling.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, NamedTuple

from sqlalchemy.orm import Session

from app.domains.geo.rainfall.adapters.gee_client import UnknownProviderScope, asset_name_for
from app.domains.geo.rainfall.compute import data_revision_for, revision_family, served_state
from app.domains.geo.rainfall.models import RainfallAnalysisRevision
from app.domains.geo.rainfall.repository import baseline_curve_rows, daily_series_rows
from app.domains.geo.rainfall.scope import AnalysisScope
from app.domains.geo.rainfall.service import RAINFALL_HISTORICAL_SOURCE, SnapshotContractError

# The two reasons a series can fail to match the revision it illustrates
# (design.md D3). `consistency_reason` is null in every other case, and a
# `false` flag ALWAYS carries one of these -- the pair is the contract the
# chart and the xlsx Resumen stamp both read.
CONSISTENCY_DATA_REVISION_MOVED = "data_revision_moved"
CONSISTENCY_INTERVAL_FAMILY_AMBIGUOUS = "interval_family_ambiguous"

# design.md D6: `tasks._persist_analysis_revision` reads
# [year_start - 90d, year_end) so antecedents.d90 can reach into the prior
# year, and `data_revision_for` hashes THAT set. The pin must recompute over
# the same window: a display-window recompute would hash a different interval
# set and mismatch every time.
_BUILD_READ_LOOKBACK = timedelta(days=90)

# February 29 carries no curve point: only 8 of the 30 baseline years have
# that day (temporal.baseline_years_for), so a "normal" for it would be an
# average over a different, much smaller sample than every neighbouring day.
# Its rain still accumulates inside the leap years' own running totals -- the
# curve is keyed by (month, day), not filtered by it.
_LEAP_DAY = (2, 29)

POINT_AVAILABLE = "available"
POINT_UNAVAILABLE = "unavailable"


class _Analysis(NamedTuple):
    """Everything the series needs, taken from the served revision ALONE --
    no provider call, and nothing re-derived from the live interval store,
    which is the thing being checked."""

    scope: AnalysisScope
    year: int
    source_id: str
    unit: str
    comparison_end: date
    available_through: str
    window_end: datetime


def _as_utc(moment: datetime) -> datetime:
    """*moment* in UTC, treating a naive value as UTC.

    Day bucketing below MUST NOT depend on the database session's ``TimeZone``
    setting: ``psycopg2`` renders a ``timestamptz`` in the session's zone, so
    a UTC midnight boundary read under UTC-3 would bucket into the previous
    day (the same class of defect as LI1-002's ``date_part`` grouping).
    """
    return moment.astimezone(UTC) if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _utc_day(moment: datetime) -> date:
    return _as_utc(moment).date()


def _analysis(snapshot: Any) -> _Analysis:
    """Read the series' inputs off the stored envelope, or refuse.

    Raises :class:`SnapshotContractError`, which both routes that serve a
    stored snapshot already map to a 503 -- a snapshot too broken to describe
    itself must not be illustrated with a chart built from guesses.
    """
    state = served_state(snapshot) if isinstance(snapshot, dict) else None
    if state is None:
        raise SnapshotContractError("snapshot has no readable annual.selected provenance")
    source_id, _temporal_state = state

    scope = snapshot.get("scope")
    year = snapshot.get("year")
    comparison_end = snapshot.get("comparison_end")
    selected = snapshot["annual"]["selected"]
    provenance = selected["provenance"]
    available_through = provenance.get("available_through")
    if (
        not isinstance(scope, dict)
        or not all(isinstance(scope.get(field), str) for field in ("kind", "id", "version"))
        or not isinstance(year, int)
        or isinstance(year, bool)
        or not isinstance(comparison_end, str)
        or not isinstance(available_through, str)
    ):
        raise SnapshotContractError("snapshot envelope cannot back a daily series")
    try:
        parsed_comparison_end = date.fromisoformat(comparison_end)
        window_end = _as_utc(datetime.fromisoformat(available_through))
    except ValueError as exc:
        raise SnapshotContractError("snapshot carries an unparseable disclosure window") from exc

    unit = selected.get("unit")
    return _Analysis(
        scope=AnalysisScope(
            kind=scope["kind"],
            id=scope["id"],
            version=scope["version"],
            # Not hashed by `data_revision_for` and not a property of the
            # computation (it records how the ORIGINAL request reached this
            # scope), so it cannot affect the pin.
            regional_estimate=False,
        ),
        year=year,
        source_id=source_id,
        unit=unit if isinstance(unit, str) else "mm",
        comparison_end=parsed_comparison_end,
        available_through=available_through,
        window_end=window_end,
    )


def _pin(
    rows: list[tuple[datetime, datetime, float, str]],
    *,
    analysis: _Analysis,
    stored_data_revision: str,
) -> tuple[bool, str | None]:
    """Recompute the build's own content address over *rows* and compare
    (design.md D3).

    The family is derived per-row from the persisted ``provider_revision``,
    while the build took it from the adapter batch's single reported value
    (``tasks.py``). ``intervals_in_window`` deliberately does not filter by
    family, so the rule here is that the read rows MUST map to exactly one --
    zero families (nothing left to read) and two or more (a second family
    landed) are both "not exactly one", and both report inconsistent without
    ever attempting a comparison. The asymmetry is bounded to that direction:
    it can produce a false INCONSISTENT, never a false consistent.

    *rows* are fed to ``data_revision_for`` exactly as the read returned them,
    with no normalization, because parity with the build is the whole point:
    any transformation applied here and not there would flip a healthy pin.
    """
    families = {revision_family(provider_revision) for _s, _e, _v, provider_revision in rows}
    if len(families) != 1:
        return False, CONSISTENCY_INTERVAL_FAMILY_AMBIGUOUS

    recomputed = data_revision_for(
        analysis.source_id,
        next(iter(families)),
        analysis.scope,
        analysis.year,
        analysis.comparison_end,
        [(interval_start, value) for interval_start, _end, value, _revision in rows],
    )
    if recomputed != stored_data_revision:
        return False, CONSISTENCY_DATA_REVISION_MOVED
    return True, None


def _normal_curve(
    db: Session, *, snapshot: dict[str, Any], scope: AnalysisScope, cutoff: date
) -> dict[tuple[int, int], float]:
    """Cumulative baseline normal keyed by ``(month, day)``, averaged over
    EXACTLY ``annual.normal``'s own eligible-year set (design.md D3).

    Reads the same rows, same key and same per-year windows
    ``repository.baseline_cumulatives`` aggregated for that metric, so the
    curve's last point is that metric's value read at daily resolution rather
    than a second, independently-derived number. When ``annual.normal`` is not
    served -- an unmapped scope, a thin baseline, invalid evidence -- there is
    no curve: an empty mapping, never a mean over an empty sample, which would
    draw a flat zero line beside a real year.
    """
    annual = snapshot.get("annual")
    normal = annual.get("normal") if isinstance(annual, dict) else None
    if not isinstance(normal, dict) or normal.get("state") != "available":
        return {}
    quality = normal.get("quality")
    eligible = quality.get("eligible_years") if isinstance(quality, dict) else None
    if not isinstance(eligible, list) or not eligible:
        return {}
    years = [int(year) for year in eligible]

    try:
        asset = asset_name_for(scope.kind, scope.id)
        cutoffs = [date(year, cutoff.month, cutoff.day) for year in years]
    except (UnknownProviderScope, ValueError):
        # A served `annual.normal` implies both resolved at build time; if
        # either stopped resolving, the honest answer is no curve.
        return {}

    rows = baseline_curve_rows(db, source_id=RAINFALL_HISTORICAL_SOURCE, asset=asset, dates=cutoffs)
    by_year: dict[int, dict[date, float]] = {year: {} for year in years}
    for interval_start, value in rows:
        day = _utc_day(interval_start)
        bucket = by_year.get(day.year)
        if bucket is not None:
            bucket[day] = bucket.get(day, 0.0) + value

    cumulative_by_key: dict[tuple[int, int], list[float]] = {}
    for year in years:
        running = 0.0
        day = date(year, 1, 1)
        last_day = date(year, cutoff.month, cutoff.day)
        while day <= last_day:
            # The leap day contributes to the running total of the years that
            # HAVE it (that is what `baseline_cumulatives` sums), it just
            # carries no key of its own.
            running += by_year[year].get(day, 0.0)
            if (day.month, day.day) != _LEAP_DAY:
                cumulative_by_key.setdefault((day.month, day.day), []).append(running)
            day += timedelta(days=1)

    # Every eligible year walks its own full calendar above, so each key holds
    # one value per year; the guard exists so a future change cannot silently
    # start averaging a key over a subset of the sample.
    return {
        key: sum(values) / len(values)
        for key, values in cumulative_by_key.items()
        if len(values) == len(years)
    }


def _points(
    rows: list[tuple[datetime, datetime, float, str]],
    *,
    year_start: datetime,
    window_end: datetime,
    curve: dict[tuple[int, int], float],
) -> list[dict[str, Any]]:
    """One point per calendar day of the analysis' own disclosure window.

    The window ends at the CLIPPED ``window_end`` the snapshot discloses
    (design.md D5/D6 amendments), not at the calendar ``comparison_end``:
    provider lag is the documented steady state, and emitting empty points for
    days the provider has not published would read as a dry spell on a chart.
    A day inside the window with no evidence is ``mm: null`` and
    ``state: "unavailable"`` -- never a zero -- and the cumulative carries
    across it unchanged rather than inventing a value; before the first
    published day there is no cumulative at all.
    """
    daily: dict[date, float] = {}
    for interval_start, _interval_end, value, _revision in rows:
        if year_start <= interval_start < window_end:
            day = _utc_day(interval_start)
            daily[day] = daily.get(day, 0.0) + value

    points: list[dict[str, Any]] = []
    running: float | None = None
    day = year_start.date()
    while datetime(day.year, day.month, day.day, tzinfo=UTC) < window_end:
        millimetres = daily.get(day)
        if millimetres is not None:
            running = millimetres if running is None else running + millimetres
        points.append(
            {
                "date": day.isoformat(),
                "mm": millimetres,
                "accumulated": running,
                "normal_accumulated": curve.get((day.month, day.day)),
                "state": POINT_AVAILABLE if millimetres is not None else POINT_UNAVAILABLE,
            }
        )
        day += timedelta(days=1)
    return points


def build_series(db: Session, revision: RainfallAnalysisRevision) -> dict[str, Any]:
    """The daily series for one stored revision, pinned to it.

    ONE read backs both halves: the displayed points and the consistency pin
    are two projections of the same resolved interval set, so an interval that
    landed after the build cannot be visible to the chart and invisible to the
    pin (or the reverse). The read is the build's own D6-widened window; the
    display is the narrower disclosure window filtered out of it.
    """
    analysis = _analysis(revision.snapshot)
    year_start = datetime(analysis.year, 1, 1, tzinfo=UTC)
    year_end = datetime(analysis.year + 1, 1, 1, tzinfo=UTC)

    rows = daily_series_rows(
        db,
        source_id=analysis.source_id,
        scope_kind=analysis.scope.kind,
        scope_id=analysis.scope.id,
        scope_version=analysis.scope.version,
        start=year_start - _BUILD_READ_LOOKBACK,
        end=year_end,
    )
    consistent, reason = _pin(rows, analysis=analysis, stored_data_revision=revision.data_revision)

    # A disclosure window can never legitimately outrun the analysis year; the
    # clamp keeps a corrupt `available_through` from turning the day loop into
    # an unbounded one.
    window_end = min(analysis.window_end, year_end)
    curve = _normal_curve(
        db,
        snapshot=revision.snapshot,
        scope=analysis.scope,
        cutoff=_utc_day(window_end - timedelta(days=1)),
    )
    return {
        "analysis_revision_id": str(revision.id),
        "data_revision": revision.data_revision,
        "scope": {
            "kind": analysis.scope.kind,
            "id": analysis.scope.id,
            "version": analysis.scope.version,
        },
        "year": analysis.year,
        "unit": analysis.unit,
        "comparison_end": analysis.comparison_end.isoformat(),
        "available_through": analysis.available_through,
        "consistent_with_snapshot": consistent,
        "consistency_reason": reason,
        "points": _points(rows, year_start=year_start, window_end=window_end, curve=curve),
    }
