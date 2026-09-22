"""Canal publication: public GET is anonymous; catalog is staff-only."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-canal-pub")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long")

PUBLIC = "/api/v2/geo/canales/publico"
STAFF = "/api/v2/geo/canales/publicacion"
STAFF_PATCH = "/api/v2/geo/canales/publicacion/canal-1"
APRHI = "/api/v2/geo/canales/aprhi-referencia"
APRHI_PATCH = "/api/v2/geo/canales/publicacion/aprhi/aprhi-canal-viejo"

_KMZ_RELEVADO = {
    "type": "Feature",
    "id": "canal-10-de-mayo",
    "geometry": None,
    "properties": {
        "id": "canal-10-de-mayo",
        "nombre": "Canal 10 de Mayo",
        "estado": "relevado",
    },
}


class _FakeCatalog:
    def list_staff(self, _db):
        from app.domains.geo.canales_publicacion.schemas import CanalPublicacionList

        return CanalPublicacionList(
            items=[],
            geojson={"type": "FeatureCollection", "features": []},
            aprhi_items=[],
            geojson_aprhi={"type": "FeatureCollection", "features": []},
        )

    def public_collections(self, _db):
        return {
            "relevados": {"type": "FeatureCollection", "features": [_KMZ_RELEVADO]},
            "propuestas": {"type": "FeatureCollection", "features": []},
        }

    def aprhi_referencia(self, _db):
        return {"type": "FeatureCollection", "features": []}

    def patch(self, _db, canal_id, payload):
        from app.domains.geo.canales_publicacion.schemas import CanalPublicacionRow

        publicado = True if payload.publicado is None else payload.publicado
        return CanalPublicacionRow(
            id=canal_id,
            estado="relevado",
            nombre_interno="Canal 10 de Mayo",
            nombre_publico=payload.nombre_publico or "Canal 10 de Mayo",
            publicado=publicado,
            origen="kmz",
        )

    def patch_aprhi(self, _db, canal_id, payload):
        from app.domains.geo.canales_publicacion.schemas import CanalPublicacionRow

        publicado = True if payload.publicado is None else payload.publicado
        return CanalPublicacionRow(
            id=canal_id,
            estado="relevado",
            nombre_interno="Canal Viejo",
            nombre_publico=payload.nombre_publico or "Canal Viejo",
            publicado=publicado,
            origen="aprhi",
        )


@pytest.fixture
def app_client(db_session_factory):
    from app.db.session import get_db
    from app.domains.geo.canales_publicacion.router import _service
    from app.main import app

    def _get_db():
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[_service] = lambda: _FakeCatalog()
    client = TestClient(app)
    client.headers.update({"Host": "localhost"})
    yield app, client
    app.dependency_overrides.clear()


def _as_role(app, role: str) -> None:
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole

    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(role=UserRole(role))


class TestPublicCatalog:
    def test_anonymous_can_read_public_collections(self, app_client):
        _app, client = app_client
        response = client.get(PUBLIC)
        assert response.status_code == 200
        body = response.json()
        assert body["relevados"]["type"] == "FeatureCollection"
        assert body["propuestas"]["type"] == "FeatureCollection"
        ids = [feature.get("id") for feature in body["relevados"]["features"]]
        assert ids == ["canal-10-de-mayo"]
        assert all(not str(feature_id).startswith("aprhi-") for feature_id in ids)


class TestStaffCatalogAuth:
    def test_unauthenticated_staff_list_is_401(self, app_client):
        _app, client = app_client
        assert client.get(STAFF).status_code == 401

    def test_citizen_staff_list_is_403(self, app_client):
        app, client = app_client
        _as_role(app, "ciudadano")
        response = client.get(STAFF)
        assert response.status_code == 403
        assert "FeatureCollection" not in response.text
        assert "nombre_publico" not in response.text

    @pytest.mark.parametrize("role", ["operador", "admin"])
    def test_operator_can_list_staff_catalog(self, app_client, role: str):
        app, client = app_client
        _as_role(app, role)
        response = client.get(STAFF)
        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert body["geojson"]["type"] == "FeatureCollection"
        assert body["aprhi_items"] == []
        assert body["geojson_aprhi"]["type"] == "FeatureCollection"


class TestStaffPatchAuth:
    def test_unauthenticated_kmz_patch_is_401(self, app_client):
        _app, client = app_client
        assert client.patch(STAFF_PATCH, json={"publicado": False}).status_code == 401

    def test_citizen_kmz_patch_is_403(self, app_client):
        app, client = app_client
        _as_role(app, "ciudadano")
        response = client.patch(STAFF_PATCH, json={"publicado": False})
        assert response.status_code == 403

    @pytest.mark.parametrize("role", ["operador", "admin"])
    def test_operator_can_patch_kmz(self, app_client, role: str):
        app, client = app_client
        _as_role(app, role)
        response = client.patch(STAFF_PATCH, json={"publicado": False})
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "canal-1"
        assert body["publicado"] is False
        assert body["origen"] == "kmz"

    def test_unauthenticated_aprhi_patch_is_401(self, app_client):
        _app, client = app_client
        assert client.patch(APRHI_PATCH, json={"publicado": True}).status_code == 401

    def test_citizen_aprhi_patch_is_403(self, app_client):
        app, client = app_client
        _as_role(app, "ciudadano")
        response = client.patch(APRHI_PATCH, json={"publicado": True})
        assert response.status_code == 403

    @pytest.mark.parametrize("role", ["operador", "admin"])
    def test_operator_can_patch_aprhi(self, app_client, role: str):
        app, client = app_client
        _as_role(app, role)
        response = client.patch(APRHI_PATCH, json={"publicado": True})
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "aprhi-canal-viejo"
        assert body["publicado"] is True
        assert body["origen"] == "aprhi"


class TestAprhiReferenciaAuth:
    def test_unauthenticated_aprhi_overlay_is_401(self, app_client):
        _app, client = app_client
        assert client.get(APRHI).status_code == 401

    def test_citizen_aprhi_overlay_is_403(self, app_client):
        app, client = app_client
        _as_role(app, "ciudadano")
        response = client.get(APRHI)
        assert response.status_code == 403
        assert "FeatureCollection" not in response.text

    @pytest.mark.parametrize("role", ["operador", "admin"])
    def test_operator_can_read_aprhi_overlay(self, app_client, role: str):
        app, client = app_client
        _as_role(app, role)
        response = client.get(APRHI)
        assert response.status_code == 200
        assert response.json()["type"] == "FeatureCollection"


class TestAprhiPublicMerge:
    def test_aprhi_canal_id_slugs_grouped_name(self):
        from app.domains.geo.canales_publicacion.service import (
            aprhi_canal_id,
            aprhi_group_key,
        )

        assert aprhi_group_key("  Canal Viejo ") == "Canal Viejo"
        assert aprhi_group_key("   ") == "(sin nombre APRHI)"
        assert aprhi_canal_id("Canal Viejo") == "aprhi-canal-viejo"
        assert aprhi_canal_id("(sin nombre APRHI)") == "aprhi-sin-nombre-aprhi"

    def test_unpublished_aprhi_does_not_enter_relevados(self):
        from app.domains.geo.canales_publicacion.service import append_published_aprhi

        relevados = [_KMZ_RELEVADO]
        aprhi = [
            {
                "type": "Feature",
                "id": "aprhi-canal-viejo",
                "geometry": None,
                "properties": {
                    "id": "aprhi-canal-viejo",
                    "nombre_publico": "Canal Viejo",
                    "publicado": False,
                },
            }
        ]
        merged = append_published_aprhi(relevados, aprhi)
        ids = [feature["id"] for feature in merged]
        assert ids == ["canal-10-de-mayo"]
        assert relevados == [_KMZ_RELEVADO]

    def test_published_aprhi_appends_as_relevado_sin_obra(self):
        from app.domains.geo.canales_publicacion.service import append_published_aprhi

        merged = append_published_aprhi(
            [_KMZ_RELEVADO],
            [
                {
                    "type": "Feature",
                    "id": "aprhi-canal-viejo",
                    "geometry": {"type": "LineString", "coordinates": []},
                    "properties": {
                        "id": "aprhi-canal-viejo",
                        "nombre_publico": "Canal Viejo",
                        "publicado": True,
                        "longitud_m": 1200,
                    },
                }
            ],
        )
        assert [feature["id"] for feature in merged] == [
            "canal-10-de-mayo",
            "aprhi-canal-viejo",
        ]
        props = merged[1]["properties"]
        assert props["estado"] == "relevado"
        assert props["source_style"] == "sin_obra"
        assert props["nombre"] == "Canal Viejo"
        assert props["id"] == "aprhi-canal-viejo"
