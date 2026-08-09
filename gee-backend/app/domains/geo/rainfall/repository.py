"""Rainfall snapshot reads/writes and PostGIS-only parcel scope resolution."""

import json
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domains.geo.models import GeoApprovedZoning
from app.domains.geo.rainfall.compute import correction_revision, revision_family
from app.domains.geo.rainfall.models import (
    RainfallAnalysisRevision,
    RainfallIntervalLifecycle,
    RainfallIntervalValue,
)
from app.domains.geo.rainfall.ports import SourceInterval
from app.domains.geo.rainfall.scope import AnalysisScope, NoScopeMatch


class ScopeConfigurationError(ValueError):
    """Approved zoning geometry cannot safely serve a rainfall scope."""


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


def record_supersession(db: Session, *, interval_value_id: UUID, superseded_by_id: UUID) -> None:
    """Append-only lifecycle link. ``event_type='superseded'`` — deliberately
    not ``'expired'``: only an expired row with a due ``expires_at`` is ever
    deletable by ``purge_expired_rainfall_intervals``, so a supersession can
    never turn into a delete."""
    db.add(
        RainfallIntervalLifecycle(
            interval_value_id=interval_value_id,
            superseded_by_id=superseded_by_id,
            event_type="superseded",
            expires_at=None,
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
    superseded = 0
    for row, revision, superseded_id in candidates:
        landed_id = landed_ids.get((row.interval_start, row.interval_end, revision))
        if landed_id is None:
            continue
        inserted += 1
        if superseded_id is not None:
            record_supersession(db, interval_value_id=superseded_id, superseded_by_id=landed_id)
            superseded += 1

    return {"inserted": inserted, "unchanged": unchanged, "superseded": superseded}
