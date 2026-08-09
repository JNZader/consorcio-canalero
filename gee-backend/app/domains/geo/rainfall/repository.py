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
    RainfallOutbox,
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


def current_year_done_keys(db: Session, *, year: int, limit: int) -> list[RainfallOutbox]:
    """``DISTINCT ON`` the outbox key, newest ``done`` row per key, for
    sweep stage 1 (Current-Year Revisit Cycle)."""
    query = (
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
        .limit(limit)
    )
    return list(db.scalars(query).all())


def completed_year_daily_done_keys(
    db: Session, *, before_year: int, limit: int
) -> list[RainfallOutbox]:
    """Sweep stage 2's SQL pre-filter (Year-Rollover Finalization step 2): a
    SUPERSET of candidates, never the termination condition -- the served
    snapshot's own provenance (``served_state``) decides that.
    """
    query = (
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
        .order_by(
            RainfallOutbox.scope_kind,
            RainfallOutbox.scope_id,
            RainfallOutbox.scope_version,
            RainfallOutbox.year,
            RainfallOutbox.completed_at.desc(),
        )
        .limit(limit)
    )
    return list(db.scalars(query).all())


def acquire_fingerprint_lock(db: Session, *, lock_key: int) -> None:
    """Transaction-scoped advisory lock keyed on the fingerprint (design.md
    "Serializing siblings — the per-fingerprint advisory lock"). Blocking
    wait -- never ``SKIP LOCKED`` -- because blocking is the point: it makes
    read -> decide -> INSERT atomic per fingerprint across two sibling
    builds. Released automatically at the per-row COMMIT/ROLLBACK
    (``pg_advisory_xact_lock``, not the session-level variant), so a dead
    worker leaks nothing.
    """
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
