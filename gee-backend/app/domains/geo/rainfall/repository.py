"""Rainfall snapshot reads and PostGIS-only parcel scope resolution."""

import json
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domains.geo.models import GeoApprovedZoning
from app.domains.geo.rainfall.models import RainfallAnalysisRevision
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
