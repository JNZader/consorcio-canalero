"""Pure calendar rules: UTC normalization, the Buenos Aires policy calendar,
and explicit event windows."""

from datetime import UTC, date, datetime, timedelta


# design.md D2 (lluvia-antecedente-referencia): the bounds of the persisted
# baseline `repository.baseline_daily_values` reads, half-open --
# `[1991-01-01, 2021-01-01)`, the period every served envelope names
# "1991-2020".
#
# LOAD-BEARING, not hygiene. The 2021-2025 backfill has landed under the SAME
# `(scope_kind="provider_asset", scope_id=<asset>, scope_version=
# BASELINE_ASSET_VERSION)` key as the baseline -- measured on the box, not
# assumed: one key, 12,784 rows, 35 unbroken years 1991-2025, every year at
# exactly its calendar day count. So an unbounded read would silently widen
# the ranked distribution past the period the disclosure keeps naming: a
# reference that says one period and ranks against another, with nothing on
# any surface to reveal it. Named constants rather than inline literals
# because the upper bound and its exclusivity are both mutation-gated.
#
# They live HERE, not in `repository.py`, for one reason (BL-BASELINE-STRING-
# SOURCE): `compute.py` must derive the period STRING it serves from the same
# bounds the read applies, and `repository` already imports `compute`, so
# `compute` importing `repository` would close a cycle. `temporal` is the
# module both already depend on and the one that owns calendar facts, so the
# span has exactly one definition and both directions reach it. `repository`
# re-exports the two names, which is where every existing caller imports them
# from.
BASELINE_SPAN_START = datetime(1991, 1, 1, tzinfo=UTC)
BASELINE_SPAN_END = datetime(2021, 1, 1, tzinfo=UTC)  # exclusive


def baseline_period_label(span_start: datetime, span_end: datetime) -> str:
    """The human period name for a half-open baseline span: ``"1991-2020"``.

    The end year is ``span_end.year - 1`` because the bound is EXCLUSIVE --
    the same exclusivity `baseline_daily_values` applies. Deriving the string
    is the whole point: it was a literal in `compute.build_snapshot`, so
    moving the span left fourteen surfaces (four label cells, six sheet rows,
    four badges) naming a period the reference no longer ranks against.

    Rejects a span that does not end on a January 1 rather than inventing a
    name for it: "1991-2020" is only true of a whole-calendar-year span, and a
    silently wrong period name is exactly the defect this replaces.
    """
    if span_end <= span_start:
        raise ValueError(f"baseline span is empty: [{span_start}, {span_end})")
    if (span_end.month, span_end.day) != (1, 1) or (span_start.month, span_start.day) != (1, 1):
        raise ValueError(
            "baseline period label is only defined for a whole-calendar-year span, "
            f"got [{span_start.date()}, {span_end.date()})"
        )
    return f"{span_start.year}-{span_end.year - 1}"


class EventSuppressed(ValueError):
    """The requested event metric cannot be qualified under the policy."""


def as_utc(moment: datetime) -> datetime:
    """*moment* in UTC, treating a naive value as UTC.

    THE one normalization every module that turns a stored ``timestamptz``
    into a calendar day must go through (LI3A-005). ``psycopg2`` renders a
    ``timestamptz`` in the database session's ``TimeZone`` setting, and
    nothing in this codebase pins that setting, so ``.date()`` taken straight
    off a returned value is silently session-TZ-dependent: a UTC-midnight
    boundary read under UTC-3 lands on the previous day. That is the LI1-002
    defect class, and it has now appeared on three separate paths
    (``date_part`` grouping, series day bucketing, and the baseline cutoff).

    It lives HERE, next to :func:`buenos_aires_date`, rather than as a
    private helper in each module, precisely because two private copies is
    how the pattern drifts back apart.
    """
    return moment.astimezone(UTC) if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def utc_day(moment: datetime) -> date:
    """The UTC calendar day *moment* falls on (see :func:`as_utc`)."""
    return as_utc(moment).date()


def comparison_end(year: int, today: date) -> date:
    return today if year == today.year else date(year, 12, 31)


def antecedent_dates(end: date, days: int) -> tuple[date, date]:
    if days < 1:
        raise ValueError("antecedent days must be positive")
    return end - timedelta(days=days - 1), end


def baseline_years_for(day: date) -> tuple[int, ...]:
    years = range(1991, 2021)
    if day.month == 2 and day.day == 29:
        return tuple(
            year for year in years if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        )
    return tuple(years)


def event_peak_and_duration(
    *,
    start: datetime,
    end: datetime,
    cadence: timedelta,
    intervals: tuple[tuple[datetime, float], ...],
    duration_threshold: float | None,
    rolling_window: timedelta,
) -> tuple[float, timedelta]:
    """Compute a qualified peak and one wet run, otherwise suppress both metrics."""
    if duration_threshold is None:
        raise EventSuppressed("duration threshold is unset")
    if (
        end <= start
        or cadence <= timedelta()
        or rolling_window < cadence
        or rolling_window % cadence
    ):
        raise EventSuppressed("event window or cadence is invalid")
    expected = tuple(start + cadence * index for index in range(int((end - start) / cadence)))
    if end != start + cadence * len(expected) or tuple(item[0] for item in intervals) != expected:
        raise EventSuppressed("expected interval coverage is not complete")
    wet_runs, current = [], []
    for _, value in intervals:
        if value >= duration_threshold:
            current.append(value)
        elif current:
            wet_runs.append(current)
            current = []
    if current:
        wet_runs.append(current)
    if len(wet_runs) != 1:
        raise EventSuppressed("event window must contain exactly one wet run")
    width, values = int(rolling_window / cadence), tuple(value for _, value in intervals)
    if width < 1 or len(values) < width:
        raise EventSuppressed("rolling window is unsupported")
    return max(
        sum(values[index : index + width]) for index in range(len(values) - width + 1)
    ), cadence * len(wet_runs[0])


def rolling_total(
    *,
    end: datetime,
    window: timedelta,
    cadence: timedelta,
    intervals: tuple[tuple[datetime, float], ...],
) -> float:
    """Sum a cadence-aligned window only when every expected interval is present."""
    if window <= timedelta() or cadence <= timedelta() or window % cadence:
        raise EventSuppressed("rolling window is unsupported by source cadence")
    start = end - window
    expected = tuple(start + cadence * index for index in range(int(window / cadence)))
    starts = tuple(interval_start for interval_start, _ in intervals)
    if len(set(starts)) != len(starts):
        raise EventSuppressed("expected interval coverage is not complete")
    values = {interval_start: value for interval_start, value in intervals}
    if tuple(values) != expected:
        raise EventSuppressed("expected interval coverage is not complete")
    return sum(values[item] for item in expected)


def buenos_aires_date(timestamp: datetime) -> date:
    """Convert a provider UTC boundary once into the policy's local calendar date."""
    from zoneinfo import ZoneInfo

    return timestamp.astimezone(ZoneInfo("America/Argentina/Buenos_Aires")).date()


def baseline_dates(comparison_end: date) -> tuple[date, ...]:
    """Build fixed 1991–2020 same-month/day normal dates without leap-day imputation."""
    return tuple(
        date(year, comparison_end.month, comparison_end.day)
        for year in baseline_years_for(comparison_end)
    )
