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


@pytest.mark.parametrize("zone_id", [0, False, [], {}, ""])
def test_resolve_parcel_rejects_falsey_zone_ids_without_feature_id_fallback(db, zone_id):
    coordinates = [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]
    features = [_feature(zone_id, coordinates), _feature(zone_id, coordinates)]
    features[0]["id"], features[1]["id"] = "feature-a", "feature-b"
    _seed(db, features=features)

    with pytest.raises(ScopeConfigurationError, match="stable id"):
        RainfallRepository().resolve_parcel_scopes(db, "parcel-1")


@pytest.mark.parametrize("properties", [{}, {"zone_id": None}])
def test_resolve_parcel_uses_feature_id_when_zone_id_is_missing_or_null(db, properties):
    feature = _feature("ignored-zone-id", [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]])
    feature["id"], feature["properties"] = "zone-id-2", properties
    _seed(db, features=[feature])

    assert RainfallRepository().resolve_parcel_scopes(db, "parcel-1")[0].id == "zone-id-2"


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
                "type": "FeatureCollection",
                "features": [_feature("zone-a", [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]])],
            },
        )
    )
    db.flush()
    with pytest.raises(ScopeConfigurationError, match="duplicate"):
        RainfallRepository().resolve_parcel_scopes(db, "parcel-1")


@pytest.mark.parametrize(
    "feature_collection",
    [
        pytest.param({"features": []}, id="missing-type"),
        pytest.param({"type": "Collection", "features": []}, id="wrong-type"),
    ],
)
def test_resolve_parcel_rejects_non_feature_collection_active_zoning(db, feature_collection):
    _seed(db, active=False, basin=False, features=[])
    db.add(GeoApprovedZoning(version=7, is_active=True, feature_collection=feature_collection))
    db.flush()

    with pytest.raises(ScopeConfigurationError):
        RainfallRepository().resolve_parcel_scopes(db, "parcel-1")


@pytest.mark.parametrize(
    "feature",
    [
        pytest.param(
            {
                "properties": {"zone_id": "zone-a"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
                },
            },
            id="missing-type",
        ),
        pytest.param(
            {
                "type": "Geometry",
                "properties": {"zone_id": "zone-a"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
                },
            },
            id="wrong-type",
        ),
    ],
)
def test_resolve_parcel_rejects_non_feature_active_zoning_member(db, feature):
    _seed(db, features=[feature])

    with pytest.raises(ScopeConfigurationError):
        RainfallRepository().resolve_parcel_scopes(db, "parcel-1")


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [0, 0]},
        {"type": "LineString", "coordinates": [[0, 0], [2, 2]]},
    ],
)
def test_resolve_parcel_rejects_non_area_active_zoning_geometry(db, geometry):
    _seed(
        db,
        features=[
            {
                "type": "Feature",
                "properties": {"zone_id": "zone-a"},
                "geometry": geometry,
            }
        ],
    )

    with pytest.raises(ScopeConfigurationError):
        RainfallRepository().resolve_parcel_scopes(db, "parcel-1")


@pytest.mark.parametrize(
    "geometry",
    [
        {
            "type": "Polygon",
            "coordinates": [[[179, 89], [180, 89], [180, 90], [179, 90], [179, 89]]],
        },
        {
            "type": "MultiPolygon",
            "coordinates": [[[[179, 89], [180, 89], [180, 90], [179, 90], [179, 89]]]],
        },
    ],
)
def test_resolve_parcel_accepts_wgs84_boundary_geometry(db, geometry):
    _seed(
        db,
        basin=False,
        features=[{"type": "Feature", "properties": {"zone_id": "edge"}, "geometry": geometry}],
    )

    with pytest.raises(NoScopeMatch, match="no matching"):
        RainfallRepository().resolve_parcel_scopes(db, "parcel-1")


@pytest.mark.parametrize(
    "coordinates",
    [
        [[180, 0], [181, 0], [181, 1], [180, 1], [180, 0]],
        [[0, 90], [1, 90], [1, 91], [0, 91], [0, 90]],
    ],
)
def test_resolve_parcel_rejects_out_of_range_wgs84_geometry(db, coordinates):
    _seed(db, features=[_feature("out-of-range", coordinates)])

    with pytest.raises(ScopeConfigurationError, match="geometry is invalid"):
        RainfallRepository().resolve_parcel_scopes(db, "parcel-1")


def test_resolve_parcel_accepts_polygon_and_multi_polygon_active_zoning(db):
    _seed(
        db,
        features=[
            _feature("polygon", [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]),
            {
                "type": "Feature",
                "properties": {"zone_id": "multi-polygon"},
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [[[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]],
                },
            },
        ],
        basin=False,
    )

    choices = RainfallRepository().resolve_parcel_scopes(db, "parcel-1")

    assert [(item.kind, item.id) for item in choices] == [
        ("zone", "multi-polygon"),
        ("zone", "polygon"),
    ]


# ---------------------------------------------------------------------------
# BL-BASIN-SCOPE-BROKEN — the resolver's basin identity must be the provider's
# ---------------------------------------------------------------------------


def _seed_basins(db, *rows):
    """A parcel plus one ``ZonaOperativa`` per ``(nombre, cuenca)``, all
    overlapping the parcel. No approved zoning, so the choices are basins only.
    """
    db.add(ParcelaCatastro(nomenclatura="parcel-1", geometria=_polygon(0, 0, 2, 2)))
    for index, (nombre, cuenca) in enumerate(rows):
        db.add(
            ZonaOperativa(
                nombre=nombre,
                cuenca=cuenca,
                superficie_ha=1,
                geometria=_polygon(1, 1, 3 + index, 3 + index),
            )
        )
    db.flush()


def test_a_resolved_basin_scope_maps_to_a_gee_asset(db):
    """BL-BASIN-SCOPE-BROKEN, end to end and in ONE test, because the defect
    lived in neither half.

    The resolver emitted ``zonas_operativas.id::text`` -- a per-ROW UUID --
    while ``asset_name_for`` accepts only the four operational WATERSHED asset
    names, so every basin scope this resolver ever produced raised
    ``UnknownProviderScope``: basin coverage was broken end to end, not
    partially served. Each half was internally consistent and separately
    tested, which is exactly why nothing caught it; the composition is the
    contract, so the composition is what is asserted here.

    A sub-basin ROW was never the right identity either. The GEE asset covers
    the whole parent watershed, so resolving a row id to it would reduce over
    a geometry the scope does not name -- the failure ``gee_client``'s docstring
    refuses by raising. Grouping by ``cuenca`` makes the emitted identity the
    one the provider actually has imagery for.
    """
    from app.domains.geo.rainfall.adapters.gee_client import asset_name_for

    _seed_basins(db, ("sub-basin-a", "norte"), ("sub-basin-b", "norte"))

    choices = RainfallRepository().resolve_parcel_scopes(db, "parcel-1")

    # Two intersecting sub-basins of ONE watershed are ONE scope, not two.
    assert [(item.kind, item.id) for item in choices] == [("basin", "norte")]
    assert asset_name_for("basin", choices[0].id) == "norte"


def test_two_watersheds_stay_two_basin_scopes_ordered(db):
    """The grouping collapses rows, never watersheds: a parcel straddling two
    watersheds still gets one choice per watershed, ordered."""
    _seed_basins(db, ("b", "norte"), ("a", "candil"), ("c", "norte"))

    choices = RainfallRepository().resolve_parcel_scopes(db, "parcel-1")

    assert [item.id for item in choices] == ["candil", "norte"]


def test_a_basin_scope_version_is_stable_and_moves_with_its_members(db):
    """``scope_version`` is a GEOMETRY identity, so it must survive a re-read
    unchanged and must move when any member sub-basin's geometry does.

    Stability is the half that matters for storage: the version is part of the
    persisted key, so a version that reshuffles per query would orphan every
    row written under the previous read.
    """
    _seed_basins(db, ("sub-a", "norte"), ("sub-b", "norte"))
    repo = RainfallRepository()

    first = repo.resolve_parcel_scopes(db, "parcel-1")[0].version
    assert repo.resolve_parcel_scopes(db, "parcel-1")[0].version == first

    moved = db.query(ZonaOperativa).filter_by(nombre="sub-b").one()
    moved.geometria = _polygon(1, 1, 9, 9)
    db.flush()

    assert repo.resolve_parcel_scopes(db, "parcel-1")[0].version != first


def test_a_watershed_with_no_gee_asset_still_fails_closed(db):
    """The fix must not become "resolve anything". A watershed the deployment
    owns no asset for still raises rather than reducing over the wrong
    geometry -- the property the UUID mismatch was accidentally providing and
    which must now be provided on purpose.
    """
    from app.domains.geo.rainfall.adapters.gee_client import UnknownProviderScope, asset_name_for

    _seed_basins(db, ("sub", "auto_delineated"))

    choices = RainfallRepository().resolve_parcel_scopes(db, "parcel-1")

    assert [item.id for item in choices] == ["auto_delineated"]
    with pytest.raises(UnknownProviderScope, match="no GEE asset mapped"):
        asset_name_for("basin", choices[0].id)


@pytest.mark.parametrize("stored", ["Norte", " norte ", "NORTE", "Noroeste"])
def test_the_asset_seam_normalises_the_stored_watershed_name(stored):
    """``cuenca`` is free text a human typed into a table, so the seam matches
    on a normalised form rather than requiring the database to have been
    lowercase all along. Unmapped is still unmapped -- normalisation widens the
    spelling, never the set.
    """
    from app.domains.geo.rainfall.adapters.gee_client import BASIN_ASSET_NAMES, asset_name_for

    resolved = asset_name_for("basin", stored)
    assert resolved == stored.strip().lower()
    assert resolved in BASIN_ASSET_NAMES
