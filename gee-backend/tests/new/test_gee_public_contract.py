"""Service-free HTTP contracts for protected and public GEE surfaces."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-gee-public-contract")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long")


@pytest.fixture
def app_client():
    from app.main import app

    client = TestClient(app)
    client.headers.update({"Host": "localhost"})
    yield app, client
    app.dependency_overrides.clear()


def _feature_collection(name: str) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-62.7, -32.6]},
                "properties": {"name": name},
            }
        ],
    }


def test_protected_gee_is_401_unauthenticated(app_client) -> None:
    _app, client = app_client

    response = client.get("/api/v2/geo/gee/images/historic-floods")

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        ("ciudadano", 403),
        ("operador", 200),
        ("admin", 200),
    ],
)
def test_protected_gee_enforces_role_matrix(app_client, role: str, expected_status: int) -> None:
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole

    app, client = app_client
    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(role=UserRole(role))

    response = client.get("/api/v2/geo/gee/images/historic-floods")

    assert response.status_code == expected_status
    if expected_status == 200:
        assert response.json()["total"] > 0


def test_legacy_map_parameter_route_is_authenticated_backward_compatibility(app_client) -> None:
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole
    from app.db.session import get_db
    from app.domains.settings.router import get_service

    class FakeSettingsService:
        def get_setting(self, _db, _key: str):
            return None

    app, client = app_client
    assert client.get("/api/v2/public/settings/mapa/imagen").status_code == 401

    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(
        role=UserRole.OPERADOR
    )
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_service] = FakeSettingsService

    response = client.get("/api/v2/public/settings/mapa/imagen")

    assert response.status_code == 200
    assert response.json() == {"imagen_principal": None, "imagen_comparacion": None}


def test_complete_gee_route_family_keeps_operator_guard() -> None:
    from app.auth.dependencies import require_operator
    from app.domains.geo.router import router

    def has_operator_guard(route: APIRoute) -> bool:
        pending = list(route.dependant.dependencies)
        while pending:
            dependency = pending.pop()
            if dependency.call is require_operator:
                return True
            pending.extend(dependency.dependencies)
        return False

    gee_routes = [
        route
        for route in router.routes
        if isinstance(route, APIRoute) and route.path.startswith("/gee/")
    ]

    assert gee_routes
    assert all(has_operator_guard(route) for route in gee_routes)


def test_public_gee_surface_contains_only_fixed_routes() -> None:
    from app.domains.geo.public_map import router

    paths = {route.path for route in router.routes if isinstance(route, APIRoute)}

    assert paths == {
        "/map/gee/zona",
        "/map/gee/caminos",
        "/map/gee/current-image",
    }
    assert all("{" not in path for path in paths)


@pytest.mark.parametrize(
    "query",
    [
        "asset_id=users/private/asset",
        "expression=ndvi%28private%29",
        "collection=PRIVATE/COLLECTION",
        "target_date=2026-01-01",
        "start_date=2025-01-01&end_date=2026-01-01",
        "analysis=classification",
    ],
)
def test_public_gee_routes_reject_all_query_parameters(app_client, query: str) -> None:
    _app, client = app_client

    response = client.get(f"/api/v2/public/map/gee/zona?{query}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Public map projections do not accept query parameters"


def test_public_gee_routes_do_not_accept_arbitrary_path_identifiers(app_client) -> None:
    _app, client = app_client

    response = client.get("/api/v2/public/map/gee/layers/users/private/asset")

    assert response.status_code == 404


def test_public_zona_and_caminos_are_fixed_cached_projections(app_client, monkeypatch) -> None:
    from app.domains.geo import public_map

    async def fake_layer(*, layer_name: str, ensure_gee):
        assert layer_name == "zona"
        assert callable(ensure_gee)
        return JSONResponse(content=_feature_collection("zona"))

    async def fake_caminos(*, ensure_gee):
        assert callable(ensure_gee)
        return JSONResponse(content=_feature_collection("caminos"))

    monkeypatch.setattr(public_map, "get_gee_layer_impl", fake_layer)
    monkeypatch.setattr(public_map, "get_caminos_coloreados_impl", fake_caminos)
    _app, client = app_client

    zona = client.get("/api/v2/public/map/gee/zona")
    caminos = client.get("/api/v2/public/map/gee/caminos")

    assert zona.status_code == caminos.status_code == 200
    assert zona.json() == {
        "status": "available",
        "projection": "zona",
        "data": _feature_collection("zona"),
        "reason": None,
    }
    assert caminos.json()["data"] == _feature_collection("caminos")
    assert "max-age=3600" in zona.headers["cache-control"]
    assert "stale-while-revalidate=86400" in caminos.headers["cache-control"]


def test_public_projection_returns_explicit_unavailable_contract(app_client, monkeypatch) -> None:
    from app.domains.geo import public_map

    async def unavailable(**_kwargs):
        raise RuntimeError("private service detail")

    monkeypatch.setattr(public_map, "get_gee_layer_impl", unavailable)
    _app, client = app_client

    response = client.get("/api/v2/public/map/gee/zona")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "projection": "zona",
        "data": None,
        "reason": "temporarily_unavailable",
    }
    assert "private service detail" not in response.text
    assert response.headers["cache-control"] == "public, max-age=60"


def _override_current_image_dependencies(app, raw_setting: object) -> None:
    from app.db.session import get_db
    from app.domains.geo import public_map

    class FakeSettingsService:
        def get_setting(self, _db, key: str):
            assert key == "mapa/imagen_principal"
            return raw_setting

    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[public_map._get_settings_service] = FakeSettingsService


def test_public_current_image_uses_only_server_approved_bounded_params(
    app_client, monkeypatch
) -> None:
    from app.domains.geo import public_map

    raw_setting = {
        "sensor": "Sentinel-2",
        "target_date": "2026-03-05",
        "visualization": "ndvi",
        "max_cloud": 0,
        "days_buffer": 10,
        "mode": "composite",
    }
    captured: dict[str, Any] = {}

    async def fake_image(**kwargs):
        captured.update(kwargs)
        return {
            "tile_url": "https://earthengine.googleapis.com/v1/projects/test/maps/approved/tiles/{z}/{x}/{y}",
            "target_date": "attacker-controlled-value-is-ignored",
            "sensor": "attacker-controlled-value-is-ignored",
            "visualization": "attacker-controlled-value-is-ignored",
            "visualization_description": "Indice de vegetacion NDVI",
            "images_count": 2,
            "collection": "PRIVATE/COLLECTION/IS/NOT/PROJECTED",
        }

    monkeypatch.setattr(public_map, "get_satellite_image_impl", fake_image)
    app, client = app_client
    _override_current_image_dependencies(app, raw_setting)

    response = client.get("/api/v2/public/map/gee/current-image")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available"
    assert body["image"] == {
        "tile_url": "https://earthengine.googleapis.com/v1/projects/test/maps/approved/tiles/{z}/{x}/{y}",
        "target_date": "2026-03-05",
        "sensor": "Sentinel-2",
        "visualization": "ndvi",
        "visualization_description": "Indice de vegetacion NDVI",
        "images_count": 2,
        "days_buffer": 10,
        "max_cloud": 0,
        "mode": "composite",
    }
    assert captured["sensor"] == "sentinel2"
    assert captured["max_cloud"] == 0
    assert captured["visualization"] == "ndvi"
    assert captured["mode"] == "composite"
    assert "collection" not in body["image"]
    assert "max-age=300" in response.headers["cache-control"]


def test_public_current_image_rejects_extra_asset_fields_without_calling_gee(
    app_client, monkeypatch
) -> None:
    from app.domains.geo import public_map

    raw_setting = {
        "sensor": "Sentinel-2",
        "target_date": "2026-03-05",
        "visualization": "rgb",
        "max_cloud": 20,
        "days_buffer": 10,
        "mode": "scene",
        "asset_id": "users/private/asset",
    }

    async def must_not_run(**_kwargs):
        raise AssertionError("unsafe configuration reached GEE")

    monkeypatch.setattr(public_map, "get_satellite_image_impl", must_not_run)
    app, client = app_client
    _override_current_image_dependencies(app, raw_setting)

    response = client.get("/api/v2/public/map/gee/current-image")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "image": None,
        "reason": "configuration_not_approved",
    }


def test_public_current_image_rejects_unapproved_tile_host(app_client, monkeypatch) -> None:
    from app.domains.geo import public_map

    raw_setting = {
        "sensor": "Sentinel-1",
        "target_date": "2026-03-05",
        "visualization": "vv",
        "days_buffer": 10,
        "mode": "scene",
    }

    async def fake_image(**_kwargs):
        return {
            "tile_url": "https://attacker.example/tiles/{z}/{x}/{y}",
            "visualization_description": "Radar SAR banda VV",
            "images_count": 1,
        }

    monkeypatch.setattr(public_map, "get_satellite_image_impl", fake_image)
    app, client = app_client
    _override_current_image_dependencies(app, raw_setting)

    response = client.get("/api/v2/public/map/gee/current-image")

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["reason"] == "temporarily_unavailable"
