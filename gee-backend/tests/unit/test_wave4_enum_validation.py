"""Focused unit tests verifying HTTP 422 enum validation across query & body filters."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("UPLOADS_ROOT", "/tmp/consorcio-unit-uploads")
os.environ.setdefault("DOCUMENTOS_ROOT", "/tmp/consorcio-unit-documentos")

from app.auth import require_admin_or_operator  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def operator_client():
    fake_user = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        email="op@example.com",
        role="operador",
        is_active=True,
    )
    app.dependency_overrides[require_admin_or_operator] = lambda: fake_user
    app.dependency_overrides[get_db] = lambda: MagicMock()
    client = TestClient(app)
    client.headers.update({"Host": "localhost"})
    yield client
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "url",
    [
        "/api/v2/padron?estado=bogus",
        "/api/v2/geo/jobs?estado=bogus",
        "/api/v2/geo/jobs?tipo=bogus",
        "/api/v2/geo/layers?tipo=bogus",
        "/api/v2/geo/layers?fuente=bogus",
        "/api/v2/geo/gee/analysis?tipo=bogus",
        "/api/v2/geo/gee/analysis?estado=bogus",
    ],
)
def test_enum_query_filters_reject_invalid_values_with_422(
    operator_client: TestClient,
    url: str,
) -> None:
    response = operator_client.get(url)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("layer_tipo", ["bogus", "   ", ""])
def test_zonal_stats_rejects_invalid_layer_tipo_with_422(
    operator_client: TestClient,
    layer_tipo: str,
) -> None:
    response = operator_client.post(
        "/api/v2/geo/zonal-stats",
        json={"layer_tipo": layer_tipo},
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422, response.text
