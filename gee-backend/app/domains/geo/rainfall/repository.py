"""Rainfall snapshot reads/writes and PostGIS-only parcel scope resolution."""

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, distinct, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from app.domains.geo.models import GeoApprovedZoning
from app.domains.geo.rainfall import temporal
from app.domains.geo.rainfall.adapters.gee_client import BASELINE_ASSET_VERSION
from app.domains.geo.rainfall.compute import correction_revision, revision_family
from app.domains.geo.rainfall.models import (
    RainfallAnalysisRevision,
    RainfallExtremeEvent,
    RainfallIntervalLifecycle,
    RainfallIntervalValue,
    RainfallOutbox,
)
from app.domains.geo.rainfall.ports import SourceInterval
from app.domains.geo.rainfall.scope import AnalysisScope, NoScopeMatch

# R1-001 (review-ledger.md "Pre-PR review — PR3"): mirrors
# app/auth/refresh_tokens.py's `_LOCK_TIMEOUT_MS` convention (defense-in-
# depth bound on an advisory-lock wait, applied via `SET LOCAL` so it never
# leaks into the global config or any other query). Without it, two
# siblings sharing a fingerprint (design.md "Serializing siblings") could
# block each other indefinitely if one worker died holding the lock's
# transaction open; a bounded wait turns that into a loud SQLSTATE 55P03
# a caller can retry, rather than a silent hang. 5s is far beyond a
# legitimate sibling's own per-row work; anything longer is pathological.
_FINGERPRINT_LOCK_TIMEOUT_MS = 5000

# design.md D2 (lluvia-antecedente-referencia): the bounds of the persisted
# baseline `baseline_daily_values` reads, half-open -- `[1991-01-01,
# 2021-01-01)`, the period every served envelope names "1991-2020".
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
BASELINE_SPAN_START = datetime(1991, 1, 1, tzinfo=UTC)
BASELINE_SPAN_END = datetime(2021, 1, 1, tzinfo=UTC)  # exclusive


class ScopeConfigurationError(ValueError):
    """Approved zoning geometry cannot safely serve a rainfall scope."""


class DuplicateBaselineSlotError(ValueError):
    """One baseline year holds two non-superseded rows for one interval slot.

    LI2B-004 (review-ledger.md "Slice 2b -- resilience lens + general
    refuter"): :func:`baseline_cumulatives` has raised on this broken
    invariant since LI2A-005, but as a BARE ``ValueError`` -- which
    ``tasks._persist_analysis_revision`` could not catch selectively without
    also swallowing every unrelated ``ValueError`` from the same block. A
    dedicated subclass lets the task degrade exactly the two metrics that
    read the baseline (``annual.normal``/``annual.percentile``) instead of
    losing the whole build to data it cannot repair by retrying. Still a
    ``ValueError``, so every existing caller and contract test that expects
    one keeps working.

    Carries the numbers the guard measured so the caller's event payload does
    not have to re-parse the message.
    """

    def __init__(
        self,
        message: str,
        *,
        source_id: str,
        asset: str,
        year: int,
        matched: int,
        distinct_slots: int,
    ) -> None:
        super().__init__(message)
        self.source_id = source_id
        self.asset = asset
        self.year = year
        self.matched = matched
        self.distinct_slots = distinct_slots


class RainfallRepository:
    def get_revision(self, db: Session, revision_id: UUID) -> RainfallAnalysisRevision | None:
        return db.get(RainfallAnalysisRevision, revision_id)

    def get_snapshot(
        self, db: Session, request_fingerprint: str
    ) -> RainfallAnalysisRevision | None:
        query = (
            select(RainfallAnalysisRevision)
            .where(RainfallAnalysisRevision.request_fingerprint == request_fingerprint)
            .order_by(
                RainfallAnalysisRevision.created_at.desc(), RainfallAnalysisRevision.id.desc()
            )
        )
        return db.scalar(query)

    @staticmethod
    def _validate_active_zoning(db: Session) -> None:
        """Reject invalid active zoning instead of silently omitting it from scope choices."""
        zonings = db.execute(
            select(GeoApprovedZoning.version, GeoApprovedZoning.feature_collection).where(
                GeoApprovedZoning.is_active.is_(True)
            )
        )
        identities: set[tuple[str, str]] = set()
        for version, feature_collection in zonings:
            if not isinstance(feature_collection, dict):
                raise ScopeConfigurationError("approved zoning features are invalid")
            features = feature_collection.get("features")
            if feature_collection.get("type") != "FeatureCollection":
                raise ScopeConfigurationError("approved zoning features are invalid")
            if not isinstance(features, list):
                raise ScopeConfigurationError("approved zoning features are invalid")
            for feature in features:
                if not isinstance(feature, dict) or feature.get("type") != "Feature":
                    raise ScopeConfigurationError("approved zoning feature is invalid")
                properties = feature.get("properties")
                if properties is not None and not isinstance(properties, dict):
                    raise ScopeConfigurationError("properties must be an object")
                raw_zone_id = properties.get("zone_id") if properties else None
                zone_id = feature.get("id") if raw_zone_id is None else raw_zone_id
                if not isinstance(zone_id, str) or not zone_id:
                    raise ScopeConfigurationError("approved zoning feature has no stable id")
                if (identity := (zone_id, str(version))) in identities:
                    raise ScopeConfigurationError("approved zoning has duplicate stable ids")
                identities.add(identity)
                geometry = feature.get("geometry")
                geometry_type = geometry.get("type") if isinstance(geometry, dict) else None
                if geometry_type not in {"Polygon", "MultiPolygon"}:
                    raise ScopeConfigurationError("approved zoning geometry is invalid")
                try:
                    valid = db.scalar(
                        text(
                            "SELECT COALESCE(ST_IsValid(geometry), false) "
                            "AND NOT COALESCE(ST_IsEmpty(geometry), true) AND ST_Envelope(geometry) @ ST_MakeEnvelope(-180, -90, 180, 90, 4326) "
                            "FROM (SELECT ST_SetSRID(ST_GeomFromGeoJSON("
                            "CAST(:geometry AS text)), 4326) AS geometry) AS parsed"
                        ),
                        {"geometry": json.dumps(geometry)},
                    )
                except SQLAlchemyError as exc:
                    raise ScopeConfigurationError("approved zoning geometry is invalid") from exc
                if not valid:
                    raise ScopeConfigurationError("approved zoning geometry is invalid")

    def resolve_parcel_scopes(self, db: Session, nomenclature: str) -> tuple[AnalysisScope, ...]:
        if (
            db.scalar(
                text("SELECT 1 FROM parcelas_catastro WHERE nomenclatura = :name"),
                {"name": nomenclature},
            )
            is None
        ):
            raise NoScopeMatch("parcel was not found")
        try:
            self._validate_active_zoning(db)
            zones = db.execute(
                text("""
                WITH parcel AS (SELECT geometria FROM parcelas_catastro WHERE nomenclatura = :name)
                SELECT COALESCE(feature->'properties'->>'zone_id', feature->>'id'), zoning.version::text
                FROM geo_approved_zonings AS zoning CROSS JOIN parcel
                CROSS JOIN LATERAL jsonb_array_elements(CAST(zoning.feature_collection AS jsonb)->'features') AS feature
                WHERE zoning.is_active AND ST_IsValid(ST_SetSRID(ST_GeomFromGeoJSON((feature->'geometry')::text), 4326))
                  AND ST_Area(ST_Intersection(parcel.geometria, ST_SetSRID(ST_GeomFromGeoJSON((feature->'geometry')::text), 4326))) > 0
                ORDER BY 1, 2
            """),
                {"name": nomenclature},
            ).all()
            if any(row[0] is None or not row[0] for row in zones):
                raise ScopeConfigurationError("intersecting approved zone has no stable id")
            basins = db.execute(
                text("""
                SELECT id::text, md5(encode(ST_AsEWKB(ST_Normalize(zonas_operativas.geometria)), 'hex'))
                FROM zonas_operativas CROSS JOIN (SELECT geometria FROM parcelas_catastro WHERE nomenclatura = :name) AS parcel
                WHERE ST_Area(ST_Intersection(parcel.geometria, zonas_operativas.geometria)) > 0 ORDER BY 1, 2
            """),
                {"name": nomenclature},
            ).all()
        except SQLAlchemyError as exc:
            raise ScopeConfigurationError("approved zoning geometry is invalid") from exc
        choices = [AnalysisScope("zone", row[0], row[1], True) for row in zones]
        choices.extend(AnalysisScope("basin", row[0], row[1], True) for row in basins)
        if not choices:
            raise NoScopeMatch("parcel has no matching regional scope")
        return tuple(choices)


# ---------------------------------------------------------------------------
# Write paths (design.md "NRT Correction Supersession" + decisions 2/3/3c)
# ---------------------------------------------------------------------------


def _values_equal_at_6dp(new: float, current: float) -> bool:
    """A restated value is a no-op iff it rounds to the same 6-dp value.

    The *same* rounding ``data_revision_for`` will hash over resolved
    intervals (decision 3b), so a difference too small to move the content
    address never creates an interval row — and never creates a lifecycle
    row claiming a correction the disclosure cannot show.
    """
    return round(new, 6) == round(current, 6)


def _next_correction_ordinal(current_provider_revision: str, family: str) -> int:
    """Ordinal for a slot's next correction: 1 for the first, chained off the
    current row's own ordinal for later ones (design.md "NRT Correction
    Supersession" step 2, "changed" branch)."""
    if current_provider_revision == family:
        return 1
    suffix = current_provider_revision[len(family) :]
    if not suffix.startswith("+r"):
        raise ValueError(f"unrecognized provider revision shape: {current_provider_revision!r}")
    return int(suffix[2:]) + 1


def record_supersession(db: Session, *, pairs: Sequence[tuple[UUID, UUID]]) -> None:
    """Append-only lifecycle link(s), one multi-row Core ``INSERT`` per call
    (R4-001/R4-104 — the single implementation ``persist_intervals`` calls;
    no inlined duplicate of this INSERT shape exists elsewhere).
    ``event_type='superseded'`` — deliberately not ``'expired'``: only an
    expired row with a due ``expires_at`` is ever deletable by
    ``purge_expired_rainfall_intervals``, so a supersession can never turn
    into a delete.

    Core ``INSERT``, not an ORM ``db.add`` — matching
    ``persist_intervals``/``persist_revision``. An ORM add stays pending in
    ``session.new`` until the session flushes, and production's
    ``SessionLocal`` is ``autoflush=False`` (``app/db/session.py``): the very
    next read in the same transaction — ``intervals_in_window``'s anti-join
    against this table, called from the chained ``build_analysis`` right
    after ``persist_intervals`` — would miss an unflushed row and see the
    slot's old and new revisions as two "current" rows at once. A Core
    ``INSERT`` lands at execute time, independent of any flush.

    A no-op on an empty *pairs* — callers do not need to guard.
    """
    if not pairs:
        return
    db.execute(
        pg_insert(RainfallIntervalLifecycle).values(
            [
                {
                    "interval_value_id": interval_value_id,
                    "superseded_by_id": superseded_by_id,
                    "event_type": "superseded",
                    "expires_at": None,
                }
                for interval_value_id, superseded_by_id in pairs
            ]
        )
    )


def intervals_in_window(
    db: Session,
    *,
    source_id: str,
    scope_kind: str,
    scope_id: str,
    scope_version: str,
    start: datetime,
    end: datetime,
) -> list[RainfallIntervalValue]:
    """Non-superseded rows for this source/scope with ``interval_start`` in ``[start, end)``.

    Anti-joins ``rainfall_interval_lifecycle`` (``event_type='superseded'``).
    Supersession is per slot and append-only (design.md "NRT Correction
    Supersession"), so the result holds at most one row per slot. No
    ``provider_revision`` filter, by design (decision 7): one ``source_id``
    can own several revision *families* plus their corrections.
    """
    superseded = select(RainfallIntervalLifecycle.interval_value_id).where(
        RainfallIntervalLifecycle.event_type == "superseded",
        RainfallIntervalLifecycle.interval_value_id == RainfallIntervalValue.id,
    )
    query = (
        select(RainfallIntervalValue)
        .where(RainfallIntervalValue.source_id == source_id)
        .where(RainfallIntervalValue.scope_kind == scope_kind)
        .where(RainfallIntervalValue.scope_id == scope_id)
        .where(RainfallIntervalValue.scope_version == scope_version)
        .where(RainfallIntervalValue.interval_start >= start)
        .where(RainfallIntervalValue.interval_start < end)
        .where(~superseded.exists())
        .order_by(RainfallIntervalValue.interval_start)
    )
    return list(db.scalars(query).all())


def baseline_cumulatives(
    db: Session,
    *,
    source_id: str,
    asset: str,
    dates: Sequence[date],
) -> dict[int, tuple[float, int, int]]:
    """Per-baseline-year cumulative totals through each given calendar date
    (design.md D1).

    Reads under the fixed provider-asset key -- ``scope_kind="provider_asset"``,
    ``scope_id=asset``, ``scope_version=BASELINE_ASSET_VERSION`` (never a
    zoning version, so a zone republication can never orphan this read) --
    anti-joined on supersession exactly like :func:`intervals_in_window`.

    For each *date* in *dates* (one per baseline year, typically
    :func:`temporal.baseline_dates`), sums the matching year's
    ``[<year>-01-01, date + 1 day)`` window in one SQL ``GROUP BY``
    aggregate ("window SUM" in design.md D1). Returns ``{year: (total_mm,
    matched_days, expected_days)}``; a year with zero matched rows is
    simply absent from the result -- never a fabricated zero total.

    Raises :class:`DuplicateBaselineSlotError` (a ``ValueError``) when a
    year's read holds two non-superseded rows for one ``interval_start``
    (LI2A-005): that is the same broken invariant
    :func:`compute.build_snapshot` refuses to sum, and here it would inflate
    the total AND the matched-day count together, hiding itself.
    """
    if not dates:
        return {}

    superseded = select(RainfallIntervalLifecycle.interval_value_id).where(
        RainfallIntervalLifecycle.event_type == "superseded",
        RainfallIntervalLifecycle.interval_value_id == RainfallIntervalValue.id,
    )

    expected_days_by_year: dict[int, int] = {}
    windows = []
    for cutoff in dates:
        window_start = datetime(cutoff.year, 1, 1, tzinfo=UTC)
        window_end = datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=UTC) + timedelta(days=1)
        expected_days_by_year[cutoff.year] = (window_end - window_start).days
        windows.append(
            and_(
                RainfallIntervalValue.interval_start >= window_start,
                RainfallIntervalValue.interval_start < window_end,
            )
        )

    # LI1-002 (review-ledger.md): `date_part('year', timestamptz)` converts
    # to the session's `TimeZone` setting BEFORE extracting the field, so
    # grouping is silently session-TZ-dependent (nothing in this codebase
    # pins the connection's TZ). Pinning `AT TIME ZONE 'UTC'` first makes
    # the extraction deterministic regardless of session TZ -- verified
    # emitted SQL: "date_part('year', ... AT TIME ZONE 'UTC')".
    year_expr = func.date_part(
        "year", RainfallIntervalValue.interval_start.op("AT TIME ZONE")("UTC")
    )
    query = (
        select(
            year_expr.label("year"),
            func.sum(RainfallIntervalValue.value),
            func.count(),
            func.count(distinct(RainfallIntervalValue.interval_start)),
        )
        .where(RainfallIntervalValue.source_id == source_id)
        .where(RainfallIntervalValue.scope_kind == "provider_asset")
        .where(RainfallIntervalValue.scope_id == asset)
        .where(RainfallIntervalValue.scope_version == BASELINE_ASSET_VERSION)
        .where(or_(*windows))
        .where(~superseded.exists())
        .group_by(year_expr)
    )

    totals: dict[int, tuple[float, int, int]] = {}
    for year, total, matched, distinct_slots in db.execute(query).all():
        if matched != distinct_slots:
            # LI2A-005: the same broken invariant `build_snapshot` already
            # refuses to sum (compute.py's duplicated-slot guard). Both read
            # through the same supersession anti-join, so both inherit "at
            # most one non-superseded row per slot" -- but here a duplicate
            # would inflate BOTH the total AND matched_days, leaving the year
            # looking complete while quietly biasing annual.normal and every
            # percentile ranked against it. Loud, not quietly wrong.
            raise DuplicateBaselineSlotError(
                "baseline_cumulatives received duplicated interval_start slots "
                f"(source_id={source_id!r}, asset={asset!r}, year={int(year)}: "
                f"{int(matched)} rows over {int(distinct_slots)} slots)",
                source_id=source_id,
                asset=asset,
                year=int(year),
                matched=int(matched),
                distinct_slots=int(distinct_slots),
            )
        totals[int(year)] = (float(total), int(matched), expected_days_by_year[int(year)])
    return totals


def baseline_daily_values(
    db: Session,
    *,
    source_id: str,
    asset: str,
    span_start: datetime = BASELINE_SPAN_START,
    span_end: datetime = BASELINE_SPAN_END,
) -> tuple[tuple[date, float], ...]:
    """The baseline as a RAW DAILY SERIES over ``[span_start, span_end)``,
    ordered, one entry per persisted UTC day (design.md D2,
    lluvia-antecedente-referencia).

    The span is a PARAMETER whose defaults are the card's own constants
    (lluvia-eventos-extremos D14), so every pre-existing caller is
    byte-unchanged and the card keeps ranking against the period its envelope
    names. The extreme-event detector is the one caller that passes a wider
    span explicitly -- and it seals the span it used into every row it writes,
    so a widened read can never silently relabel a persisted statistic.

    Deliberately NOT a sibling ``detector_daily_values``: that would duplicate
    the supersession anti-join and the duplicate-slot guard below, which is the
    exact shape this module argues (:437-443) can quietly make a validity claim
    false while each copy looks correct on its own.

    Same fixed provider-asset key and same supersession anti-join as
    :func:`baseline_cumulatives`; what differs is the SHAPE, and the reason
    is structural. A rolling window of fixed length has no year anchor, so
    that function's year-start ``GROUP BY`` (:322-333) is not reusable here
    -- there is no group a January-crossing window could be split across.
    Every window is rolled in Python from this one bounded read
    (``climatology.seasonal_climatology``), so ``expected_days == days``
    always, including for a window reaching back into the prior year.

    Days are bucketed through :func:`temporal.utc_day`, never a bare
    ``.date()`` (LI3A-005): ``interval_start`` comes back from ``psycopg2``
    rendered in the SESSION's zone, so under any zone west of UTC a bare
    ``.date()`` files ``1991-01-01T00:00Z`` under 1990-12-31 -- the very day
    the span starts on, and one the ``>=`` bound above admitted. Rows that
    share a bucketed day are summed, which is what makes the entry a DAILY
    total rather than one arbitrary row of that day.

    Raises :class:`DuplicateBaselineSlotError` on two non-superseded rows for
    one ``interval_start``, exactly like :func:`baseline_cumulatives` and
    deliberately UNLIKE :func:`baseline_curve_rows`, which tolerates the same
    residue and dedups downstream (series.py:289). That trade is right for a
    workbook curve -- one day drawn slightly wrong beats no curve -- and
    wrong for a ranked statistic: a duplicated slot inflates the window total
    while leaving the window looking complete, so the rank moves and nothing
    discloses it.

    Note that this read sees duplicates ``baseline_cumulatives``
    STRUCTURALLY cannot: its windows stop at each year's cutoff, so a
    duplicate later in a year is invisible there and visible here. The two
    reads may therefore disagree about baseline validity within one build.
    That is intended (design.md D2) -- each degrades only its own metrics --
    and it is the reason ``tasks._persist_analysis_revision`` contains this
    read in a handler of its OWN rather than widening the existing one.
    """
    superseded = select(RainfallIntervalLifecycle.interval_value_id).where(
        RainfallIntervalLifecycle.event_type == "superseded",
        RainfallIntervalLifecycle.interval_value_id == RainfallIntervalValue.id,
    )
    query = (
        select(RainfallIntervalValue.interval_start, RainfallIntervalValue.value)
        .where(RainfallIntervalValue.source_id == source_id)
        .where(RainfallIntervalValue.scope_kind == "provider_asset")
        .where(RainfallIntervalValue.scope_id == asset)
        .where(RainfallIntervalValue.scope_version == BASELINE_ASSET_VERSION)
        .where(RainfallIntervalValue.interval_start >= span_start)
        .where(RainfallIntervalValue.interval_start < span_end)
        .where(~superseded.exists())
        .order_by(RainfallIntervalValue.interval_start)
    )

    rows = db.execute(query).all()

    # Counted per YEAR, over the WHOLE read, before anything is summed: the
    # payload `tasks` puts on its event has to mean the same thing
    # `baseline_cumulatives`' does (that year's rows over that year's distinct
    # slots), so it cannot be a partial count taken at the first repeat.
    matched_by_year: dict[int, int] = {}
    slots_by_year: dict[int, set[datetime]] = {}
    for interval_start, _value in rows:
        year = temporal.utc_day(interval_start).year
        matched_by_year[year] = matched_by_year.get(year, 0) + 1
        slots_by_year.setdefault(year, set()).add(interval_start)
    for year in sorted(matched_by_year):
        matched, distinct_slots = matched_by_year[year], len(slots_by_year[year])
        if matched != distinct_slots:
            raise DuplicateBaselineSlotError(
                "baseline_daily_values received duplicated interval_start slots "
                f"(source_id={source_id!r}, asset={asset!r}, year={year}: "
                f"{matched} rows over {distinct_slots} slots)",
                source_id=source_id,
                asset=asset,
                year=year,
                matched=matched,
                distinct_slots=distinct_slots,
            )

    daily: dict[date, float] = {}
    for interval_start, value in rows:
        day = temporal.utc_day(interval_start)
        daily[day] = daily.get(day, 0.0) + float(value)
    return tuple(sorted(daily.items()))


#: The `event_key` prefix per tier (D2). The key is the SERVED id, so it has to
#: distinguish the two tiers: both are persisted and an `alta` span is a
#: superset of the `extrema` spans inside it, so a single prefix would collide
#: on `uq_rainfall_extreme_event_key` the first time that happened.
EVENT_KEY_PREFIXES = {"extrema": "ext", "alta": "alt"}


def event_key(event) -> str:
    """The served id for a detected event -- one definition, one caller shape.

    Public because the runbook CLI needs the same string to talk about a row it
    has not written yet (an aborted batch names the identity it stopped on), and
    a second rendering of the same key in another module is how the served id
    and the persisted id start to disagree.
    """
    prefix = EVENT_KEY_PREFIXES.get(event.tier)
    if prefix is None:
        raise ValueError(
            f"no event_key prefix for tier {event.tier!r}: the tier domain "
            f"({sorted(EVENT_KEY_PREFIXES)}) and the detector's tiers disagree"
        )
    return f"{prefix}_{event.start_date.strftime('%Y%m%d')}"


#: Everything compared before a re-run is called a no-op. The identity columns
#: are excluded because they are what selected the row; every OTHER persisted
#: column is here, so "identical" means field-for-field and not "close enough
#: on the number somebody remembered to check".
_COMPARED_FIELDS = (
    "event_key",
    "end_date",
    "peak_date",
    "max_percentile",
    "fired_windows",
    "sealed_detection_params",
    "climatology_span_start",
    "climatology_span_end",
)


class CatalogDivergenceError(ValueError):
    """A second computation disagrees with a persisted catalog row (D7).

    The alternative -- ``ON CONFLICT DO NOTHING`` -- is only safe given a proof
    that no second computation of one identity can ever differ. D5's constants
    pin makes divergence UNLIKELY; it does not make it impossible (a code
    defect, moved evidence, a superseded interval). DO NOTHING would convert
    every such disagreement into silence and seal the first computation
    forever, and in an append-only catalog "forever" is not a figure of speech.

    So the run stops, naming the identity and the fields that disagree.
    """

    def __init__(
        self,
        message: str,
        *,
        event_key: str,
        differing_fields: Sequence[str],
    ) -> None:
        super().__init__(message)
        self.event_key = event_key
        self.differing_fields = tuple(differing_fields)


def _jsonable(value: object) -> object:
    """The value as Postgres will hand it back: plain dicts, lists, floats.

    The comparison in :func:`persist_events` is between a freshly computed
    payload and one that has ROUND-TRIPPED through a JSON column, so the two
    must be normalized to the same shape first. Without this a tuple-vs-list
    difference makes every second run look divergent -- and a writer that cries
    wolf on every run gets its guard deleted, which is how the silence the
    guard exists to prevent comes back through the front door.
    """
    return json.loads(json.dumps(value, default=dict))


def seal_detection_params(constants: Mapping[str, object] | None = None) -> dict:
    """The full frozen constants block plus its digest, ready to store (D5).

    Sealed PER ROW so each row is self-describing: a reader can tell what
    produced the statistic without finding the code that wrote it, and a later
    constants bump cannot retroactively relabel an already-persisted
    generation.
    """
    from app.domains.geo.rainfall import detector

    block = detector.DETECTION_CONSTANTS if constants is None else constants
    sealed = _jsonable(block)
    sealed["constants_digest"] = detector.constants_digest(block)
    return sealed


def persist_events(
    db: Session,
    *,
    source_id: str,
    scope_kind: str,
    scope_id: str,
    scope_version: str,
    events: Sequence[object],
    detector_revision: str | None = None,
    detection_constants: Mapping[str, object] | None = None,
) -> dict[str, int]:
    """Write detected events: INSERT, skip-if-identical, or RAISE (D7).

    Explicitly NOT ``ON CONFLICT DO NOTHING``; see
    :class:`CatalogDivergenceError` for why that shape is the failure this
    function replaces rather than the shortcut it declines.

    ``detector_revision`` and ``detection_constants`` default TOGETHER to the
    detector module's frozen pair, and a caller that overrides one overrides
    both -- which is exactly what a revision bump is (D5's lockstep). Sealing
    the block that was actually used, rather than whatever the module currently
    holds, is what keeps a row's own account of itself true.
    """
    from app.domains.geo.rainfall import detector

    revision = detector.DETECTOR_REVISION if detector_revision is None else detector_revision
    sealed = seal_detection_params(detection_constants)

    inserted = 0
    skipped = 0
    for event in events:
        candidate = {
            "event_key": event_key(event),
            "end_date": event.end_date,
            "peak_date": event.peak_date,
            "max_percentile": event.max_percentile,
            "fired_windows": _jsonable(event.fired_windows_payload),
            "sealed_detection_params": sealed,
            "climatology_span_start": event.climatology_span_start,
            "climatology_span_end": event.climatology_span_end,
        }
        existing = db.execute(
            select(RainfallExtremeEvent)
            .where(RainfallExtremeEvent.source_id == source_id)
            .where(RainfallExtremeEvent.scope_kind == scope_kind)
            .where(RainfallExtremeEvent.scope_id == scope_id)
            .where(RainfallExtremeEvent.scope_version == scope_version)
            .where(RainfallExtremeEvent.detector_revision == revision)
            .where(RainfallExtremeEvent.provenance == "detected")
            .where(RainfallExtremeEvent.tier == event.tier)
            .where(RainfallExtremeEvent.start_date == event.start_date)
        ).scalar_one_or_none()

        if existing is None:
            db.add(
                RainfallExtremeEvent(
                    source_id=source_id,
                    scope_kind=scope_kind,
                    scope_id=scope_id,
                    scope_version=scope_version,
                    detector_revision=revision,
                    provenance="detected",
                    tier=event.tier,
                    start_date=event.start_date,
                    **candidate,
                )
            )
            inserted += 1
            continue

        differing = [
            field for field in _COMPARED_FIELDS if getattr(existing, field) != candidate[field]
        ]
        if differing:
            raise CatalogDivergenceError(
                "the catalog already holds a different row at this identity "
                f"(event_key={existing.event_key!r}, revision={revision!r}, "
                f"tier={event.tier!r}, start_date={event.start_date.isoformat()}): "
                f"differing fields {differing}",
                event_key=existing.event_key,
                differing_fields=differing,
            )
        skipped += 1

    return {"inserted": inserted, "skipped": skipped}


def daily_series_rows(
    db: Session,
    *,
    source_id: str,
    scope_kind: str,
    scope_id: str,
    scope_version: str,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, datetime, float, str]]:
    """The resolved rows a series is drawn from, as ORM-free tuples
    ``(interval_start, interval_end, value, provider_revision)`` (design.md
    D3, slice 3a).

    DELEGATES to :func:`intervals_in_window` rather than re-expressing its
    supersession anti-join: the series and its consistency pin exist to prove
    that what a chart draws is the same evidence a stored revision was built
    from, so a second, independently-maintained read of the same thing is the
    one shape that could quietly make that claim false. The projection is the
    only difference -- ``provider_revision`` comes along because the pin
    derives the revision FAMILY from the rows themselves
    (``compute.revision_family``), which is the input ``build_snapshot``'s
    caller took from the adapter batch instead.
    """
    return [
        (row.interval_start, row.interval_end, row.value, row.provider_revision)
        for row in intervals_in_window(
            db,
            source_id=source_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
            scope_version=scope_version,
            start=start,
            end=end,
        )
    ]


def baseline_curve_rows(
    db: Session,
    *,
    source_id: str,
    asset: str,
    dates: Sequence[date],
) -> list[tuple[datetime, float]]:
    """The DAILY baseline rows behind :func:`baseline_cumulatives`, ordered by
    ``interval_start`` (design.md D3, slice 3a).

    Same fixed provider-asset key and same supersession anti-join as
    :func:`baseline_cumulatives`, over exactly the same per-year windows
    ``[<year>-01-01, date + 1 day)`` -- this is that function's aggregate,
    unrolled day by day, so a curve built here and the ``annual.normal`` value
    built there are the same sum read at two resolutions. That is what makes
    the acceptance rule ("the normal curve's last point equals
    ``annual.normal.value``") a property of the code rather than a
    coincidence of the fixtures.
    """
    if not dates:
        return []

    superseded = select(RainfallIntervalLifecycle.interval_value_id).where(
        RainfallIntervalLifecycle.event_type == "superseded",
        RainfallIntervalLifecycle.interval_value_id == RainfallIntervalValue.id,
    )
    windows = [
        and_(
            RainfallIntervalValue.interval_start >= datetime(cutoff.year, 1, 1, tzinfo=UTC),
            RainfallIntervalValue.interval_start
            < datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=UTC) + timedelta(days=1),
        )
        for cutoff in dates
    ]
    query = (
        select(RainfallIntervalValue.interval_start, RainfallIntervalValue.value)
        .where(RainfallIntervalValue.source_id == source_id)
        .where(RainfallIntervalValue.scope_kind == "provider_asset")
        .where(RainfallIntervalValue.scope_id == asset)
        .where(RainfallIntervalValue.scope_version == BASELINE_ASSET_VERSION)
        .where(or_(*windows))
        .where(~superseded.exists())
        .order_by(RainfallIntervalValue.interval_start)
    )
    return [(interval_start, float(value)) for interval_start, value in db.execute(query).all()]


def persist_intervals(
    db: Session,
    *,
    source_id: str,
    scope_kind: str,
    scope_id: str,
    scope_version: str,
    rows: Sequence[SourceInterval],
) -> dict[str, int]:
    """Classify-then-append write path (design.md "NRT Correction Supersession").

    1. Read the slots already current for this window via
       :func:`intervals_in_window` (a classification read, not a
       get-before-insert — a lost race just degrades to a skipped write).
    2. Classify each fetched interval: **absent** -> INSERT with the row's
       own (family) revision; **equal** at 6 decimal places
       (:func:`_values_equal_at_6dp`) -> no-op; **changed** -> INSERT a
       ``family+rN`` correction row.
    3. ``ON CONFLICT DO NOTHING`` keyed on ``uq_rainfall_interval_revision``
       (decision 3), so a re-ingest of an unchanged slot never raises. Only
       for the ids ``RETURNING`` reports as actually landed, record the
       supersession link — a lost race degrades to a skipped write, never a
       lifecycle row claiming a correction that never landed.
    """
    if not rows:
        return {"inserted": 0, "unchanged": 0, "superseded": 0}

    window_start = min(row.interval_start for row in rows)
    window_end = max(row.interval_end for row in rows)
    current = intervals_in_window(
        db,
        source_id=source_id,
        scope_kind=scope_kind,
        scope_id=scope_id,
        scope_version=scope_version,
        start=window_start,
        end=window_end,
    )
    current_by_slot = {(row.interval_start, row.interval_end): row for row in current}

    # (row, provider_revision to write, id of the row it supersedes or None)
    candidates: list[tuple[SourceInterval, str, UUID | None]] = []
    unchanged = 0
    for row in rows:
        existing = current_by_slot.get((row.interval_start, row.interval_end))
        if existing is None:
            candidates.append((row, row.provider_revision, None))
        elif _values_equal_at_6dp(row.value, existing.value):
            unchanged += 1
        else:
            family = revision_family(existing.provider_revision)
            incoming_family = revision_family(row.provider_revision)
            if incoming_family != family:
                # Decision 7's invariant is source_id <-> provider-revision
                # *family*, 1:1. A caller handing back a different family
                # for an already-current slot violates that invariant; do
                # not silently re-stamp the value with the incumbent's
                # family (that would discard the incoming provider_revision
                # and hide the bug).
                raise ValueError(
                    f"provider_revision family mismatch for source_id={source_id!r} "
                    f"slot {row.interval_start!r}: existing family {family!r} vs "
                    f"incoming {row.provider_revision!r} (family {incoming_family!r})"
                )
            ordinal = _next_correction_ordinal(existing.provider_revision, family)
            candidates.append((row, correction_revision(family, ordinal), existing.id))

    if not candidates:
        return {"inserted": 0, "unchanged": unchanged, "superseded": 0}

    stmt = (
        pg_insert(RainfallIntervalValue)
        .values(
            [
                {
                    "source_id": source_id,
                    "scope_kind": scope_kind,
                    "scope_id": scope_id,
                    "scope_version": scope_version,
                    "interval_start": row.interval_start,
                    "interval_end": row.interval_end,
                    "provider_revision": revision,
                    "value": row.value,
                    "unit": row.unit,
                }
                for row, revision, _superseded_id in candidates
            ]
        )
        .on_conflict_do_nothing(constraint="uq_rainfall_interval_revision")
        .returning(
            RainfallIntervalValue.id,
            RainfallIntervalValue.interval_start,
            RainfallIntervalValue.interval_end,
            RainfallIntervalValue.provider_revision,
        )
    )
    landed_ids = {
        (landed_start, landed_end, landed_revision): landed_id
        for landed_id, landed_start, landed_end, landed_revision in db.execute(stmt).all()
    }

    inserted = 0
    superseded_pairs: list[tuple[UUID, UUID]] = []
    for row, revision, superseded_id in candidates:
        landed_id = landed_ids.get((row.interval_start, row.interval_end, revision))
        if landed_id is None:
            continue
        inserted += 1
        if superseded_id is not None:
            superseded_pairs.append((superseded_id, landed_id))

    # R4-104: the single implementation — record_supersession itself does
    # the batched multi-row Core INSERT (R4-001), no duplicate inlined here.
    record_supersession(db, pairs=superseded_pairs)

    return {
        "inserted": inserted,
        "unchanged": unchanged,
        "superseded": len(superseded_pairs),
    }


def persist_revision(
    db: Session,
    *,
    request_fingerprint: str,
    policy_revision: str,
    data_revision: str,
    snapshot: dict,
) -> UUID:
    """Idempotent revision write (decision 3): ``ON CONFLICT DO NOTHING``
    keyed on ``uq_rainfall_analysis_snapshot`` (``request_fingerprint``,
    ``policy_revision``, ``data_revision``), then ``SELECT`` — an identical
    ``data_revision`` is a no-op that returns the existing id rather than
    raising or writing a duplicate row.
    """
    stmt = (
        pg_insert(RainfallAnalysisRevision)
        .values(
            request_fingerprint=request_fingerprint,
            policy_revision=policy_revision,
            data_revision=data_revision,
            snapshot=snapshot,
        )
        .on_conflict_do_nothing(constraint="uq_rainfall_analysis_snapshot")
        .returning(RainfallAnalysisRevision.id)
    )
    landed_id = db.execute(stmt).scalar()
    if landed_id is not None:
        return landed_id

    existing_id = db.scalar(
        select(RainfallAnalysisRevision.id).where(
            RainfallAnalysisRevision.request_fingerprint == request_fingerprint,
            RainfallAnalysisRevision.policy_revision == policy_revision,
            RainfallAnalysisRevision.data_revision == data_revision,
        )
    )
    if existing_id is None:
        # The conflict target guarantees a matching row exists; a lost
        # race that skipped it would mean the constraint itself is wrong.
        raise RuntimeError(
            "persist_revision hit ON CONFLICT DO NOTHING but found no matching row "
            f"(fingerprint={request_fingerprint!r}, policy_revision={policy_revision!r}, "
            f"data_revision={data_revision!r})"
        )
    return existing_id


def recent_done(
    db: Session,
    *,
    source_id: str,
    role: str,
    scope_kind: str,
    scope_id: str,
    scope_version: str,
    year: int,
    since: datetime,
) -> RainfallOutbox | None:
    """Newest ``done`` row for this key with ``completed_at >= since``
    (decision 6 request-path cooldown). Seeks
    ``ix_rainfall_outbox_done_lookup`` (migration ``lluvia_v2_005``) --
    the existing unique index is ``pending``-only and cannot serve this.
    """
    query = (
        select(RainfallOutbox)
        .where(RainfallOutbox.source_id == source_id)
        .where(RainfallOutbox.role == role)
        .where(RainfallOutbox.scope_kind == scope_kind)
        .where(RainfallOutbox.scope_id == scope_id)
        .where(RainfallOutbox.scope_version == scope_version)
        .where(RainfallOutbox.year == year)
        .where(RainfallOutbox.status == "done")
        .where(RainfallOutbox.completed_at.is_not(None))
        .where(RainfallOutbox.completed_at >= since)
        .order_by(RainfallOutbox.completed_at.desc())
        .limit(1)
    )
    return db.scalar(query)


def latest_terminal_attempt(
    db: Session,
    *,
    source_id: str,
    role: str,
    scope_kind: str,
    scope_id: str,
    scope_version: str,
    year: int,
) -> RainfallOutbox | None:
    """The key's newest TERMINAL row -- ``done`` or ``failed`` -- whatever its
    age. Sibling of :func:`recent_done`, not a replacement: that one answers
    "did this key finish inside the recompute window", this one answers "what
    was this key's last outcome", which is the question LI2B-001 (terminal
    ``failed``) and LI2B-003 (a ``done`` row whose build refused to write)
    both need and neither of the two pre-existing reads could answer.

    Ordered by ``COALESCE(completed_at, updated_at) DESC`` because the two
    terminal states are dated by different columns:

    - ``done`` stamps ``completed_at`` (``tasks._process_outbox_row``);
    - ``failed`` never does -- the failure path
      (``tasks._process_outbox_batch``) writes ``status``/``retry_count``/
      ``last_error``/``next_attempt_at``, and ``TimestampMixin``'s
      ``onupdate=func.now()`` (``db/base.py``) advances ``updated_at`` on
      EVERY attempt including the final one. That is the column that dates a
      terminal failure. ``next_attempt_at`` is deliberately NOT used: it is
      the failure instant PLUS ``_backoff_seconds`` (up to an hour), so it
      would date the failure into the future and shorten every cooldown
      measured from it.

    Returning the newest row rather than filtering by a window is what keeps
    the cooldowns honest: a key that FAILED and was later healed reports its
    ``done`` row, so a stale failure can never suppress a healthy key.

    Seeks the same six-column prefix of ``ix_rainfall_outbox_done_lookup``
    (``models.py``) ``recent_done`` uses; only the trailing ``completed_at``
    cannot serve the ``COALESCE`` ordering, which sorts one key's own rows,
    never a scan.
    """
    attempted_at = func.coalesce(RainfallOutbox.completed_at, RainfallOutbox.updated_at)
    query = (
        select(RainfallOutbox)
        .where(RainfallOutbox.source_id == source_id)
        .where(RainfallOutbox.role == role)
        .where(RainfallOutbox.scope_kind == scope_kind)
        .where(RainfallOutbox.scope_id == scope_id)
        .where(RainfallOutbox.scope_version == scope_version)
        .where(RainfallOutbox.year == year)
        .where(RainfallOutbox.status.in_(("done", "failed")))
        .order_by(attempted_at.desc())
        .limit(1)
    )
    return db.scalar(query)


def pending_row_for_key(
    db: Session,
    *,
    source_id: str,
    role: str,
    scope_kind: str,
    scope_id: str,
    scope_version: str,
    year: int,
) -> RainfallOutbox | None:
    """The single ``pending``-row-for-this-key query shape (R2-003 --
    review-ledger.md "Pre-PR review — PR3"): was duplicated three times
    (``tasks.py``'s own sweep pre-check, plus ``queue_missing_analysis``'s
    pre-check and its post-``IntegrityError`` re-read, decision 8) against
    the same predicate ``ix_rainfall_outbox_pending_unique`` mirrors.
    """
    query = (
        select(RainfallOutbox)
        .where(RainfallOutbox.source_id == source_id)
        .where(RainfallOutbox.role == role)
        .where(RainfallOutbox.scope_kind == scope_kind)
        .where(RainfallOutbox.scope_id == scope_id)
        .where(RainfallOutbox.scope_version == scope_version)
        .where(RainfallOutbox.year == year)
        .where(RainfallOutbox.status == "pending")
    )
    return db.scalar(query)


def current_year_done_keys(db: Session, *, year: int, limit: int) -> list[RainfallOutbox]:
    """``DISTINCT ON`` the outbox key, newest ``done`` row per key, for
    sweep stage 1 (Current-Year Revisit Cycle).

    Rotated (C2 -- review-ledger.md "Pre-PR review — PR3"): the DISTINCT
    ON'd candidate set is wrapped in a subquery and the OUTER query orders
    it by ``completed_at`` ASC (least-recently-attempted first), instead of
    serving the same lexicographic prefix of ``(source_id, role,
    scope_kind, scope_id, scope_version, year)`` every sweep. Without
    rotation, a key sorted past position `limit` in that ascending key
    order never gets selected again once >= `limit` OTHER keys exist --
    its ``comparison_end`` freezes for the rest of the year, silently
    (JDA-001 at scale). A key's own refresh gives its NEXT `done` row a
    fresh ``completed_at`` (task 3.10's cycle), which is what sends it to
    the back of the rotation on its own -- no separate bookkeeping needed.
    """
    inner = (
        select(RainfallOutbox)
        .distinct(
            RainfallOutbox.source_id,
            RainfallOutbox.role,
            RainfallOutbox.scope_kind,
            RainfallOutbox.scope_id,
            RainfallOutbox.scope_version,
            RainfallOutbox.year,
        )
        .where(RainfallOutbox.status == "done")
        .where(RainfallOutbox.year == year)
        .order_by(
            RainfallOutbox.source_id,
            RainfallOutbox.role,
            RainfallOutbox.scope_kind,
            RainfallOutbox.scope_id,
            RainfallOutbox.scope_version,
            RainfallOutbox.year,
            RainfallOutbox.completed_at.desc(),
        )
        .subquery()
    )
    rotated = aliased(RainfallOutbox, inner)
    query = select(rotated).order_by(rotated.completed_at.asc()).limit(limit)
    return list(db.scalars(query).all())


def completed_year_daily_done_keys(
    db: Session, *, before_year: int, limit: int
) -> list[RainfallOutbox]:
    """Sweep stage 2's candidate selection (Year-Rollover Finalization step
    2), now WITH the served-state termination pushed into SQL (C1 --
    review-ledger.md "Pre-PR review — PR3"): a lateral read of each
    candidate key's own newest revision (``created_at DESC, id DESC`` --
    the same order ``get_snapshot`` uses) excludes a key whose served state
    already discloses ``("chirps-v3-final", "final")``. Relies on the latch
    (design.md "The latch") guaranteeing a provisional revision is never
    written over a final incumbent, so "newest revision is final" and "a
    final revision exists" stay equivalent for as long as that guarantee
    holds -- documented here because that reliance is exactly what makes
    the equivalence safe rather than incidental.

    The JSON comparison uses ``IS NOT TRUE`` (not a plain boolean negation)
    so SQL's three-valued logic KEEPS a key whose fingerprint has no
    revision yet (the JDA-002 healing case) or whose newest revision cannot
    be read: both read as `NULL`, and `NULL IS NOT TRUE` is true, so the
    row stays in the candidate set instead of silently vanishing. The
    caller's own ``served_state`` check (tasks.py) stays the authoritative,
    Python-side gate -- this exclusion is a superset filter that closes
    the starvation, not a replacement for that check.

    NOT rotated the way stage 1 is (R4-301 — review-ledger.md "PR3 scoped
    re-review (fix round 1)"): a candidate row here IS the original
    ``role='daily'`` ``done`` row for that scope+year, and nothing ever
    re-stamps its ``completed_at`` — a finalization attempt always INSERTs
    a SEPARATE ``role='historical'`` row (design.md "Year-Rollover
    Finalization" step 6) and never touches this one. So a stalled
    candidate's position in the ``completed_at`` ASC order is FIXED for as
    long as it stays a candidate at all — unlike stage 1, where a key's own
    refresh gives its NEXT `done` row a fresh `completed_at` and genuinely
    rotates it. What actually frees a slot for a key parked past the
    `limit` cursor is the ``already_final`` exclusion above: once an
    ahead-of-cursor key's served state genuinely turns final, it drops OUT
    of this query's candidate set entirely (not merely re-sorted),
    shrinking the population the cursor has to clear. The outer
    ``completed_at`` ASC re-sort is a one-time tie-break over whatever set
    the exclusion leaves, not a rotation mechanism — it exists so a freed
    slot is backfilled by the next-oldest stalled key rather than an
    arbitrary one.

    Bound: with up to `limit` (`MAX_OUTBOX_BATCH`) genuinely-stalled keys
    sorted ahead of a given key, draining the head takes at most
    ``ceil(N / limit)`` daily sweeps, where N is the count of ahead-of-
    cursor keys that eventually clear the write gate — a key stuck behind
    a head that never clears (inadequate final data that never improves)
    is not bounded by this arithmetic and stays starved until that data
    improves. Observable via ``rainfall.finalization.completed``'s
    ``truncated`` flag (true when ``scanned == limit``, tasks.py
    ``_revisit_stale``); a persistently ``true`` value is the signal the
    head has not drained.
    """
    newest_snapshot = (
        select(RainfallAnalysisRevision.snapshot)
        .where(RainfallAnalysisRevision.request_fingerprint == RainfallOutbox.request_fingerprint)
        .order_by(RainfallAnalysisRevision.created_at.desc(), RainfallAnalysisRevision.id.desc())
        .limit(1)
        .correlate(RainfallOutbox)
        .scalar_subquery()
    )
    already_final = and_(
        newest_snapshot["annual"]["selected"]["provenance"]["source_id"].astext
        == "chirps-v3-final",  # service.RAINFALL_HISTORICAL_SOURCE (decision 7)
        newest_snapshot["annual"]["selected"]["temporal_state"].astext == "final",
    )

    inner = (
        select(RainfallOutbox)
        .distinct(
            RainfallOutbox.scope_kind,
            RainfallOutbox.scope_id,
            RainfallOutbox.scope_version,
            RainfallOutbox.year,
        )
        .where(RainfallOutbox.status == "done")
        .where(RainfallOutbox.role == "daily")
        .where(RainfallOutbox.year < before_year)
        .where(RainfallOutbox.request_fingerprint.is_not(None))
        .where(already_final.isnot(True))
        .order_by(
            RainfallOutbox.scope_kind,
            RainfallOutbox.scope_id,
            RainfallOutbox.scope_version,
            RainfallOutbox.year,
            RainfallOutbox.completed_at.desc(),
        )
        .subquery()
    )
    rotated = aliased(RainfallOutbox, inner)
    query = select(rotated).order_by(rotated.completed_at.asc()).limit(limit)
    return list(db.scalars(query).all())


def acquire_fingerprint_lock(db: Session, *, lock_key: int) -> None:
    """Transaction-scoped advisory lock keyed on the fingerprint (design.md
    "Serializing siblings — the per-fingerprint advisory lock"). Blocking
    wait -- never ``SKIP LOCKED`` -- because blocking is the point: it makes
    read -> decide -> INSERT atomic per fingerprint across two sibling
    builds. Released automatically at the per-row COMMIT/ROLLBACK
    (``pg_advisory_xact_lock``, not the session-level variant), so a dead
    worker leaks nothing.

    R1-001: ``SET LOCAL lock_timeout`` is issued in the SAME transaction
    immediately before the lock wait, so a wait longer than
    ``_FINGERPRINT_LOCK_TIMEOUT_MS`` raises (SQLSTATE 55P03) instead of
    blocking forever. The caller (``tasks._persist_analysis_revision``,
    inside decision 2c's per-row ``SAVEPOINT``) does not need its own
    SQLSTATE-specific handling: that error falls into the EXISTING generic
    retry/backoff bookkeeping in ``tasks._process_outbox_batch`` the same
    way any other row failure does.
    """
    db.execute(text(f"SET LOCAL lock_timeout = '{_FINGERPRINT_LOCK_TIMEOUT_MS}'"))
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})


def claim_outbox_row(db: Session, *, outbox_id: UUID, now: datetime) -> RainfallOutbox | None:
    """Re-claim a candidate row for exclusive per-row processing (decision
    2c). ``None`` means another worker already owns it (still ``pending``
    but locked by a concurrent claim, filtered out by ``SKIP LOCKED``) or
    it already finished (no longer ``pending``) or is not yet due. Blocking
    is never appropriate here — a worker that cannot claim a row this cycle
    simply leaves it for the next one.

    ``now`` is a Python-side timestamp, not SQL's ``now()``: within one
    transaction, PostgreSQL's ``now()`` is frozen to *transaction start*
    (``transaction_timestamp()``), not statement time. A row whose
    ``next_attempt_at`` is stamped with Python's wall clock AFTER this
    session's transaction already began would then read as "in the
    future" relative to a frozen SQL ``now()`` and never be claimable in
    that same transaction — reproduced empirically against this exact
    query shape.
    """
    query = (
        select(RainfallOutbox)
        .where(RainfallOutbox.id == outbox_id)
        .where(RainfallOutbox.status == "pending")
        .where(RainfallOutbox.next_attempt_at <= now)
        .with_for_update(skip_locked=True)
    )
    return db.scalar(query)
