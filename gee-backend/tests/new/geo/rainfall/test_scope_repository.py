"""PostGIS integration coverage for the evidence-safe parcel scope resolver."""

import pytest
from geoalchemy2 import WKTElement

from app.domains.geo.intelligence.models import ParcelaCatastro, ZonaOperativa
from app.domains.geo.models import GeoApprovedZoning
from app.domains.geo.rainfall.repository import RainfallRepository, ScopeConfigurationError
from app.domains.geo.rainfall.scope import NoScopeMatch


def _polygon(x1, y1, x2, y2):
    return WKTElement(f"POLYGON(({x1} {y1},{x2} {y1},{x2} {y2},{x1} {y2},{x1} {y1}))", srid=4326)


def _feature(zone_id, coordinates):
    return {
        "type": "Feature",
        "properties": {"zone_id": zone_id},
        "geometry": {"type": "Polygon", "coordinates": [coordinates]},
    }


def _seed(db, *, features, active=True, basin=True):
    db.add(ParcelaCatastro(nomenclatura="parcel-1", geometria=_polygon(0, 0, 2, 2)))
    db.add(
        GeoApprovedZoning(
            version=7,
            is_active=active,
            feature_collection={"type": "FeatureCollection", "features": features},
        )
    )
    if basin:
        db.add(
            ZonaOperativa(
                nombre="basin", cuenca="c", superficie_ha=1, geometria=_polygon(1, 1, 3, 3)
            )
        )
    db.flush()


def test_resolve_parcel_returns_ordered_zone_and_basin_with_positive_area(db):
    _seed(db, features=[_feature("zone-b", [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]])])
    choices = RainfallRepository().resolve_parcel_scopes(db, "parcel-1")
    assert [(item.kind, item.id, item.regional_estimate) for item in choices] == [
        ("zone", "zone-b", True),
        ("basin", choices[1].id, True),
    ]
    assert choices[0].version == "7"


def test_resolve_parcel_excludes_boundary_contact_and_inactive_zonings(db):
    _seed(db, active=False, features=[_feature("touch", [[2, 0], [3, 0], [3, 2], [2, 2], [2, 0]])])
    choices = RainfallRepository().resolve_parcel_scopes(db, "parcel-1")
    assert [item.kind for item in choices] == ["basin"]


def test_resolve_parcel_distinguishes_missing_parcel_no_match_and_invalid_zone_id(db):
    with pytest.raises(NoScopeMatch, match="not found"):
        RainfallRepository().resolve_parcel_scopes(db, "missing")
    _seed(db, features=[], basin=False)
    with pytest.raises(NoScopeMatch, match="no matching"):
        RainfallRepository().resolve_parcel_scopes(db, "parcel-1")
    db.add(
        GeoApprovedZoning(
            version=8,
            is_active=True,
            feature_collection={
                "type": "FeatureCollection",
                "features": [_feature(None, [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]])],
            },
        )
    )
    db.flush()
    with pytest.raises(ScopeConfigurationError, match="stable id"):
        RainfallRepository().resolve_parcel_scopes(db, "parcel-1")


@pytest.mark.parametrize(
    "feature",
    [
        {"type": "Feature", "properties": {"zone_id": "bad"}},
        {"type": "Feature", "properties": {"zone_id": "bad"}, "geometry": None},
        {"type": "Feature", "properties": {"zone_id": "bad"}, "geometry": {}},
        {
            "type": "Feature",
            "properties": {"zone_id": "bad"},
            "geometry": {"type": "Polygon", "coordinates": []},
        },
        _feature(None, [[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]),
    ],
)
def test_resolve_parcel_rejects_malformed_active_zoning_even_with_intersecting_basin(db, feature):
    _seed(db, features=[feature])

    with pytest.raises(ScopeConfigurationError):
        RainfallRepository().resolve_parcel_scopes(db, "parcel-1")


@pytest.mark.parametrize(
    "properties",
    [
        pytest.param("invalid-properties", id="string"),
        pytest.param(["invalid-properties"], id="non-empty-list"),
        pytest.param([], id="empty-list"),
        pytest.param("", id="empty-string"),
        pytest.param(0, id="zero"),
        pytest.param(False, id="false"),
    ],
)
def test_resolve_parcel_rejects_non_object_properties_even_with_intersecting_basin(db, properties):
    feature = _feature("zone-a", [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]])
    feature["id"] = "feature-id-fallback-must-not-apply"
    feature["properties"] = properties
    _seed(db, features=[feature])

    with pytest.raises(ScopeConfigurationError, match="properties must be an object"):
        RainfallRepository().resolve_parcel_scopes(db, "parcel-1")


@pytest.mark.parametrize("properties", [None, {}, pytest.param("missing", id="missing")])
def test_resolve_parcel_uses_feature_id_when_properties_are_missing_or_empty(db, properties):
    feature = _feature("ignored-zone-id", [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]])
    feature["id"] = "zone-id-1"
    if properties == "missing":
        feature.pop("properties")
    else:
        feature["properties"] = properties
    _seed(db, features=[feature])

    choices = RainfallRepository().resolve_parcel_scopes(db, "parcel-1")

    assert [(item.kind, item.id) for item in choices] == [
        ("zone", "zone-id-1"),
        ("basin", choices[1].id),
    ]


def test_resolve_parcel_rejects_non_array_features_and_duplicate_active_identity(db):
    _seed(db, features=[_feature("zone-a", [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]])])
    db.add(GeoApprovedZoning(version=8, is_active=True, feature_collection={"features": {}}))
    db.flush()
    with pytest.raises(ScopeConfigurationError, match="features"):
        RainfallRepository().resolve_parcel_scopes(db, "parcel-1")

    db.query(GeoApprovedZoning).filter(GeoApprovedZoning.version == 8).delete()
    db.add(
        GeoApprovedZoning(
            version=7,
            is_active=True,
            feature_collection={
                "features": [_feature("zone-a", [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]])]
            },
        )
    )
    db.flush()
    with pytest.raises(ScopeConfigurationError, match="duplicate"):
        RainfallRepository().resolve_parcel_scopes(db, "parcel-1")
