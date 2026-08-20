"""PostGIS and ASGI contracts for protected basin-to-catastro membership."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from geoalchemy2 import WKTElement

from app.auth import require_admin_or_operator
from app.db.session import get_db
from app.domains.geo.intelligence.models import ParcelaCatastro, ZonaOperativa
from app.domains.geo.intelligence.repository import IntelligenceRepository
from app.domains.geo.router_basins_bundle import router

ENDPOINT = "/api/v2/geo/basins"


def _polygon(x1, y1, x2, y2):
    return WKTElement(
        f"POLYGON(({x1} {y1},{x2} {y1},{x2} {y2},{x1} {y2},{x1} {y1}))",
        srid=4326,
    )


def _seed_basin(db, *, parcels=()):
    basin = ZonaOperativa(
        nombre="membership-basin",
        cuenca="test",
        superficie_ha=1,
        geometria=_polygon(0, 0, 2, 2),
    )
    db.add(basin)
    for nomenclatura, bounds in parcels:
        db.add(ParcelaCatastro(nomenclatura=nomenclatura, geometria=_polygon(*bounds)))
    db.flush()
    return basin


def _client(db=None):
    app = FastAPI()
    if db is not None:
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[require_admin_or_operator] = lambda: None
    app.include_router(router, prefix="/api/v2/geo")
    return TestClient(app)


def test_repository_returns_sorted_overlaps_and_excludes_boundary_only_contact(db):
    basin = _seed_basin(
        db,
        parcels=(
            ("parcel-b", (1, 1, 3, 3)),
            ("parcel-a", (0.5, 0.5, 1.5, 1.5)),
            ("boundary-only", (2, 0, 3, 1)),
            ("outside", (3, 3, 4, 4)),
        ),
    )

    result = IntelligenceRepository().get_catastro_membership_by_basin(db, basin.id)

    assert result == ["parcel-a", "parcel-b"]


def test_repository_returns_none_for_unknown_basin(db):
    assert IntelligenceRepository().get_catastro_membership_by_basin(db, uuid4()) is None


def test_membership_endpoint_rejects_anonymous_requests():
    response = _client().get(f"{ENDPOINT}/{uuid4()}/catastro-membership")

    assert response.status_code == 401


def test_membership_endpoint_returns_minimal_wire_contract(db):
    basin = _seed_basin(
        db,
        parcels=(("parcel-b", (1, 1, 3, 3)), ("parcel-a", (0.5, 0.5, 1.5, 1.5))),
    )

    response = _client(db).get(f"{ENDPOINT}/{basin.id}/catastro-membership")

    assert response.status_code == 200
    assert response.json() == {
        "basin_id": str(basin.id),
        "feature_id_property": "nomenclatura",
        "intersecting_feature_ids": ["parcel-a", "parcel-b"],
    }


def test_membership_endpoint_distinguishes_empty_and_unknown_basins(db):
    basin = _seed_basin(db)
    client = _client(db)

    empty_response = client.get(f"{ENDPOINT}/{basin.id}/catastro-membership")
    unknown_response = client.get(f"{ENDPOINT}/{uuid4()}/catastro-membership")

    assert empty_response.status_code == 200
    assert empty_response.json() == {
        "basin_id": str(basin.id),
        "feature_id_property": "nomenclatura",
        "intersecting_feature_ids": [],
    }
    assert unknown_response.status_code == 404
