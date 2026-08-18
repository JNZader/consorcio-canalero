"""Public-edge validation of the anonymous tile rescale params (hardening H1).

Exercises ``router_core.proxy_tile`` — the unauthenticated, rate-limiter-exempt
tile endpoint — to prove it rejects malformed/unsupported rescale input with an
explicit 4xx and only forwards canonical, bounded values to the internal
geo-worker. The worker itself is stubbed so the proxy can be tested in isolation
(no real raster, no DB beyond a monkeypatched tipo lookup).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domains.geo import router_core

LAYER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
BASE = f"/api/v2/geo/layers/{LAYER_ID}/tiles/10/0/0.png"


class _FakeTileResponse:
    status_code = 200
    content = b"FAKE_PNG_BYTES"


class _FakeTileClient:
    def __init__(self):
        self.last_params: dict | None = None

    async def get(self, url, params=None):
        self.last_params = params
        return _FakeTileResponse()

    async def aclose(self):
        return None


@pytest.fixture
def client(monkeypatch) -> tuple[TestClient, _FakeTileClient]:
    fake = _FakeTileClient()
    monkeypatch.setattr(router_core, "_get_tile_client", lambda: fake)
    # Default: the requested layer is the only one that may carry rescale.
    monkeypatch.setattr(router_core, "_layer_tipo", lambda lid: "precip_normal")

    app = FastAPI()
    app.include_router(router_core.router, prefix="/api/v2/geo")
    return TestClient(app), fake


def test_valid_monthly_pair_is_200_and_forwards_canonical(client):
    test_client, fake = client
    response = test_client.get(BASE, params={"rescale_min": 0, "rescale_max": 200})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"FAKE_PNG_BYTES"
    assert fake.last_params == {"rescale_min": 0.0, "rescale_max": 200.0}


def test_valid_annual_pair_is_200_and_forwards_canonical(client):
    test_client, fake = client
    response = test_client.get(BASE, params={"rescale_min": 0, "rescale_max": 1800})

    assert response.status_code == 200
    assert fake.last_params == {"rescale_min": 0.0, "rescale_max": 1800.0}


def test_one_member_missing_returns_400(client):
    test_client, _ = client
    response = test_client.get(BASE, params={"rescale_min": 0})

    assert response.status_code == 400
    assert "juntos" in response.json()["detail"]


def test_equal_range_returns_400(client):
    test_client, _ = client
    response = test_client.get(BASE, params={"rescale_min": 200, "rescale_max": 200})

    assert response.status_code == 400
    assert "estrictamente menor" in response.json()["detail"]


def test_inverted_range_returns_400(client):
    test_client, _ = client
    response = test_client.get(BASE, params={"rescale_min": 200, "rescale_max": 0})

    assert response.status_code == 400


def test_non_finite_nan_returns_400(client):
    test_client, _ = client
    response = test_client.get(BASE, params={"rescale_min": "nan", "rescale_max": 200})

    assert response.status_code == 400
    assert "finitos" in response.json()["detail"]


def test_non_finite_infinity_returns_400(client):
    test_client, _ = client
    response = test_client.get(BASE, params={"rescale_min": 0, "rescale_max": "inf"})

    assert response.status_code == 400


def test_unsupported_pair_returns_400(client):
    test_client, _ = client
    response = test_client.get(BASE, params={"rescale_min": 0, "rescale_max": 100})

    assert response.status_code == 400
    assert "no soportado" in response.json()["detail"]


def test_rescale_on_non_whitelisted_layer_returns_400(client, monkeypatch):
    monkeypatch.setattr(router_core, "_layer_tipo", lambda lid: "dem_raw")
    test_client, _ = client
    response = test_client.get(BASE, params={"rescale_min": 0, "rescale_max": 200})

    assert response.status_code == 400
    assert "no soportado" in response.json()["detail"]


def test_no_override_forwards_no_rescale_and_is_200(client):
    test_client, fake = client
    response = test_client.get(BASE)

    assert response.status_code == 200
    assert fake.last_params is None or "rescale_min" not in fake.last_params
