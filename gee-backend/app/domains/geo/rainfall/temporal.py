"""Pure calendar rules: UTC normalization, the Buenos Aires policy calendar,
and explicit event windows."""

from datetime import UTC, date, datetime, timedelta


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
