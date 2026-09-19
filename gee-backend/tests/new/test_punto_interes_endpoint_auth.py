"""``/api/v2/geo/puntos-interes`` is operator-and-admin only.

A denial must disclose no FeatureCollection, coordinates, titulo, geometria or
tipo token. The dependency rejects before the service runs, so there is no
partial payload to leak — but that claim is checked against the raw body.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-punto-interes-auth")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long")

ENDPOINT = "/api/v2/geo/puntos-interes"
SAMPLE_ID = "11111111-1111-4111-8111-111111111111"
JSON_HEADERS = {"Content-Type": "application/json"}
CREATE_BODY = {
    "lng": -62.8,
    "lat": -32.5,
    "titulo": "Alcantarilla norte",
    "nota": "tapa hundida",
    "tipo": "alcantarilla",
}

FORBIDDEN_IN_A_DENIAL = (
    "FeatureCollection",
    "coordinates",
    "titulo",
    "geometria",
    "alcantarilla",
)


@pytest.fixture
def app_client(db_session_factory):
    from app.db.session import get_db
    from app.main import app

    def _get_db():
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    client = TestClient(app)
    client.headers.update({"Host": "localhost"})
    yield app, client
    app.dependency_overrides.clear()


def _as_role(app, role: str) -> None:
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole

    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(role=UserRole(role))


def _assert_denial_leaks_nothing(raw: str) -> None:
    for token in FORBIDDEN_IN_A_DENIAL:
        assert token not in raw, f"a denial must not disclose {token!r}"


class TestGetAuthorization:
    @pytest.mark.parametrize("role", ["operador", "admin"])
    def test_an_operator_or_admin_gets_a_feature_collection(self, app_client, role: str):
        app, client = app_client
        _as_role(app, role)

        response = client.get(ENDPOINT)

        assert response.status_code == 200
        body = response.json()
        assert body["type"] == "FeatureCollection"
        assert body["features"] == []

    def test_a_citizen_is_denied_and_the_body_discloses_nothing(self, app_client):
        app, client = app_client
        _as_role(app, "ciudadano")

        response = client.get(ENDPOINT)

        assert response.status_code == 403
        _assert_denial_leaks_nothing(response.text)

    def test_an_unauthenticated_visitor_is_denied(self, app_client):
        _app, client = app_client

        response = client.get(ENDPOINT)

        assert response.status_code == 401
        _assert_denial_leaks_nothing(response.text)


class TestPostAuthorization:
    def test_a_citizen_cannot_create_and_the_body_discloses_nothing(self, app_client):
        app, client = app_client
        _as_role(app, "ciudadano")

        response = client.post(ENDPOINT, json=CREATE_BODY)

        assert response.status_code == 403
        _assert_denial_leaks_nothing(response.text)

    def test_an_unauthenticated_visitor_cannot_create(self, app_client):
        _app, client = app_client

        response = client.post(ENDPOINT, json=CREATE_BODY)

        assert response.status_code == 401
        _assert_denial_leaks_nothing(response.text)


class TestDeleteAuthorization:
    def test_a_citizen_cannot_delete_and_the_body_discloses_nothing(self, app_client):
        app, client = app_client
        _as_role(app, "ciudadano")

        response = client.delete(f"{ENDPOINT}/{SAMPLE_ID}", headers=JSON_HEADERS)

        assert response.status_code == 403
        _assert_denial_leaks_nothing(response.text)

    def test_an_unauthenticated_visitor_cannot_delete(self, app_client):
        _app, client = app_client

        response = client.delete(f"{ENDPOINT}/{SAMPLE_ID}", headers=JSON_HEADERS)

        assert response.status_code == 401
        _assert_denial_leaks_nothing(response.text)
