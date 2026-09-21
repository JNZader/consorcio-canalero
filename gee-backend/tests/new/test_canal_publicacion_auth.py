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


class _FakeCatalog:
    def list_staff(self, _db):
        from app.domains.geo.canales_publicacion.schemas import CanalPublicacionList

        return CanalPublicacionList(items=[])

    def public_collections(self, _db):
        return {
            "relevados": {"type": "FeatureCollection", "features": []},
            "propuestas": {"type": "FeatureCollection", "features": []},
        }


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
        assert "items" in response.json()
