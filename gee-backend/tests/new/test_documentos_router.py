"""HTTP contracts for /api/v2/documentos."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-documentos-router")
os.environ.setdefault("DOCUMENTOS_ROOT", "/tmp/documentos-test-router")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long")

LIST_PATH = "/api/v2/documentos"


@pytest.fixture
def app_client(db_session_factory, tmp_path: Path):
    from app.config import settings
    from app.db.session import get_db
    from app.domains.documentos.catalog import get_documento
    from app.main import app

    doc = get_documento("codist-p-ach")
    assert doc is not None and doc.files
    archivo = doc.files[0]
    dest = tmp_path.joinpath(*Path(archivo.relative_path).parts)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"%PDF-1.4 documentos-test")

    previous_root = settings.documentos_root
    settings.documentos_root = str(tmp_path)

    def _get_db():
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    client = TestClient(app)
    client.headers.update({"Host": "localhost"})
    yield app, client, archivo
    settings.documentos_root = previous_root
    app.dependency_overrides.clear()


def _as_role(app, role: str) -> None:
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole

    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(role=UserRole(role))


class TestDocumentosRouter:
    def test_operator_lists_25_items(self, app_client) -> None:
        app, client, _archivo = app_client
        _as_role(app, "operador")

        resp = client.get(LIST_PATH)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert len(body["items"]) == 25
        assert all(item["clasificacion"] == "privado" for item in body["items"])
        assert all("files" not in item for item in body["items"])
        assert all("relative_path" not in item for item in body["items"])

    def test_filter_codist(self, app_client) -> None:
        app, client, _archivo = app_client
        _as_role(app, "operador")

        resp = client.get(LIST_PATH, params={"group": "codist"})
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 5

    def test_detail_includes_files(self, app_client) -> None:
        app, client, archivo = app_client
        _as_role(app, "operador")

        resp = client.get(f"{LIST_PATH}/codist-p-ach")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "codist-p-ach"
        assert body["file_count"] >= 1
        assert any(f["id"] == archivo.id for f in body["files"])
        assert all("relative_path" not in f for f in body["files"])

    def test_unknown_detail_404(self, app_client) -> None:
        app, client, _archivo = app_client
        _as_role(app, "operador")

        resp = client.get(f"{LIST_PATH}/does-not-exist")
        assert resp.status_code == 404

    def test_download_attachment(self, app_client) -> None:
        app, client, archivo = app_client
        _as_role(app, "operador")

        resp = client.get(f"{LIST_PATH}/codist-p-ach/archivo/{archivo.id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/pdf")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert resp.content.startswith(b"%PDF")

    def test_ciudadano_forbidden(self, app_client) -> None:
        app, client, archivo = app_client
        _as_role(app, "ciudadano")

        assert client.get(LIST_PATH).status_code == 403
        assert client.get(f"{LIST_PATH}/codist-p-ach").status_code == 403
        assert client.get(f"{LIST_PATH}/codist-p-ach/archivo/{archivo.id}").status_code == 403

    def test_unauthenticated_401(self, app_client) -> None:
        _app, client, archivo = app_client

        assert client.get(LIST_PATH).status_code == 401
        assert client.get(f"{LIST_PATH}/codist-p-ach/archivo/{archivo.id}").status_code == 401
