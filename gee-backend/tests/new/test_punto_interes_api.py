"""Happy-path API for staff map pins: POST then GET, invalid tipo, DELETE."""

from __future__ import annotations

import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-punto-interes-api")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long")

ENDPOINT = "/api/v2/geo/puntos-interes"


def _app_client(db_session_factory):
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
    return app, client


def _as_operador(app) -> None:
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole

    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(role=UserRole.OPERADOR)


def test_operador_post_then_get_contains_the_point(db_session_factory):
    app, client = _app_client(db_session_factory)
    try:
        _as_operador(app)
        created = client.post(
            ENDPOINT,
            json={
                "lng": -62.81,
                "lat": -32.51,
                "titulo": "Alteo sobre el 8",
                "nota": "bordo de 40 cm",
                "tipo": "alteo",
            },
        )
        assert created.status_code == 201, created.text
        feature = created.json()
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        assert feature["geometry"]["coordinates"] == [-62.81, -32.51]
        assert feature["properties"]["titulo"] == "Alteo sobre el 8"
        assert feature["properties"]["tipo"] == "alteo"
        punto_id = feature["id"]

        listed = client.get(ENDPOINT)
        assert listed.status_code == 200
        body = listed.json()
        assert body["type"] == "FeatureCollection"
        ids = [item["id"] for item in body["features"]]
        assert punto_id in ids
        match = next(item for item in body["features"] if item["id"] == punto_id)
        assert match["properties"]["titulo"] == "Alteo sobre el 8"
        assert match["geometry"]["coordinates"] == [-62.81, -32.51]
    finally:
        app.dependency_overrides.clear()


def test_invalid_tipo_is_422(db_session_factory):
    app, client = _app_client(db_session_factory)
    try:
        _as_operador(app)
        response = client.post(
            ENDPOINT,
            json={
                "lng": -62.8,
                "lat": -32.5,
                "titulo": "algo",
                "tipo": "cuneta",
            },
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_delete_returns_204_then_gone(db_session_factory):
    app, client = _app_client(db_session_factory)
    try:
        _as_operador(app)
        created = client.post(
            ENDPOINT,
            json={
                "lng": -62.7,
                "lat": -32.4,
                "titulo": "Taponamiento",
                "tipo": "taponamiento",
            },
        )
        assert created.status_code == 201, created.text
        punto_id = created.json()["id"]

        deleted = client.delete(
            f"{ENDPOINT}/{punto_id}",
            headers={"Content-Type": "application/json"},
        )
        assert deleted.status_code == 204

        listed = client.get(ENDPOINT)
        assert listed.status_code == 200
        ids = [item["id"] for item in listed.json()["features"]]
        assert punto_id not in ids
    finally:
        app.dependency_overrides.clear()
