"""proxy_tile degrades gracefully when the layer-tipo DB lookup fails (HARD-R4-001).

This is the staged-hardening CRITICAL finding: ``proxy_tile`` calls the cached
``_layer_tipo`` DB lookup outside any error handling whenever rescale params are
provided, so a transient SQLAlchemy/DB failure propagated as a 500 even though the
proxy can safely forward without a rescale override.

These tests pin the contract after the fix in ``router_core.proxy_tile``:

  * a DB lookup ``OperationalError`` / ``SQLAlchemyError`` yields a successful
    (200) upstream forward with DEFAULT rendering, not a 500;
  * the forwarded params OMIT the rescale override on lookup failure;
  * the failure is NOT cached — the next request re-attempts the lookup;
  * a successful lookup still validates the canonical monthly/annual pair;
  * unrelated (programmer) exceptions are not swallowed.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.domains.geo import router_core

LAYER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
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
    app = FastAPI()
    app.include_router(router_core.router, prefix="/api/v2/geo")
    return TestClient(app), fake


@pytest.fixture(autouse=True)
def _clear_tipo_cache():
    # The cached lookup is process-global; isolate tests from each other.
    router_core._layer_tipo_cached.cache_clear()
    yield
    router_core._layer_tipo_cached.cache_clear()


# ─────────────────────────────────────────────────────────────────────────────
# 1. DB failure → 200 with default (no rescale) upstream forwarding, not 500
# ─────────────────────────────────────────────────────────────────────────────


def test_db_lookup_operational_error_forwards_default_200(client, monkeypatch):
    monkeypatch.setattr(
        router_core,
        "_layer_tipo",
        lambda lid: (_ for _ in ()).throw(OperationalError("connection refused", None, None)),
    )
    test_client, fake = client
    response = test_client.get(BASE, params={"rescale_min": 0, "rescale_max": 200})

    # No 500: the proxy degrades to default rendering and forwards the tile.
    assert response.status_code == 200
    assert response.content == b"FAKE_PNG_BYTES"
    # Rescale override must be omitted because the lookup failed.
    assert "rescale_min" not in (fake.last_params or {})
    assert "rescale_max" not in (fake.last_params or {})


def test_db_lookup_sqlalchemy_error_forwards_default_200(client, monkeypatch):
    class _Boom(SQLAlchemyError):
        pass

    monkeypatch.setattr(
        router_core,
        "_layer_tipo",
        lambda lid: (_ for _ in ()).throw(_Boom("db down")),
    )
    test_client, fake = client
    response = test_client.get(BASE, params={"rescale_min": 0, "rescale_max": 1800})

    assert response.status_code == 200
    assert "rescale_min" not in (fake.last_params or {})


# ─────────────────────────────────────────────────────────────────────────────
# 2. Failure is not cached — the next request re-attempts the lookup
# ─────────────────────────────────────────────────────────────────────────────


def test_db_failure_then_retry_forwards_rescale(client, monkeypatch):
    calls = {"n": 0}

    def _flaky_lookup(lid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OperationalError("transient db blip", None, None)
        return "precip_normal"

    monkeypatch.setattr(router_core, "_layer_tipo", _flaky_lookup)
    test_client, fake = client

    # First request: lookup fails → default forward, no rescale override.
    r1 = test_client.get(BASE, params={"rescale_min": 0, "rescale_max": 200})
    assert r1.status_code == 200
    assert "rescale_min" not in (fake.last_params or {})

    # Second request: lookup now succeeds → canonical rescale is forwarded,
    # proving the prior failure was not cached as a permanent None.
    r2 = test_client.get(BASE, params={"rescale_min": 0, "rescale_max": 200})
    assert r2.status_code == 200
    assert fake.last_params == {"rescale_min": 0.0, "rescale_max": 200.0}


# ─────────────────────────────────────────────────────────────────────────────
# 2b. Lower-level: lru_cache never stores a raised exception (contract proof)
# ─────────────────────────────────────────────────────────────────────────────


class _CountingSession:
    def __init__(self):
        self.execute_calls = 0
        self._raise_first = True

    def execute(self, stmt):
        self.execute_calls += 1
        if self._raise_first and self.execute_calls == 1:
            raise OperationalError("connection refused", None, None)

        class _Result:
            def scalar_one_or_none(self):
                return "precip_normal"

        return _Result()

    def close(self):
        return None


def test_cached_lookup_does_not_cache_exception(monkeypatch):
    session = _CountingSession()
    monkeypatch.setattr(router_core, "SessionLocal", lambda: session)
    key = str(LAYER_ID)

    # First call raises — must NOT be memoised by lru_cache.
    with pytest.raises(SQLAlchemyError):
        router_core._layer_tipo_cached(key)

    # Second call with the SAME key re-runs the DB lookup (execute called again).
    assert router_core._layer_tipo_cached(key) == "precip_normal"
    assert session.execute_calls == 2


# ─────────────────────────────────────────────────────────────────────────────
# 3. Successful lookup still validates the canonical monthly/annual pair
# ─────────────────────────────────────────────────────────────────────────────


def test_successful_lookup_forwards_monthly_canonical(client, monkeypatch):
    monkeypatch.setattr(router_core, "_layer_tipo", lambda lid: "precip_normal")
    test_client, fake = client
    response = test_client.get(BASE, params={"rescale_min": 0, "rescale_max": 200})

    assert response.status_code == 200
    assert fake.last_params == {"rescale_min": 0.0, "rescale_max": 200.0}


def test_successful_lookup_forwards_annual_canonical(client, monkeypatch):
    monkeypatch.setattr(router_core, "_layer_tipo", lambda lid: "precip_normal")
    test_client, fake = client
    response = test_client.get(BASE, params={"rescale_min": 0, "rescale_max": 1800})

    assert response.status_code == 200
    assert fake.last_params == {"rescale_min": 0.0, "rescale_max": 1800.0}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Unrelated (programmer) exceptions are NOT swallowed
# ─────────────────────────────────────────────────────────────────────────────


def test_unrelated_exception_propagates(client, monkeypatch):
    class _NotADbError(Exception):
        pass

    monkeypatch.setattr(
        router_core,
        "_layer_tipo",
        lambda lid: (_ for _ in ()).throw(_NotADbError("logic bug")),
    )
    test_client, _ = client
    # A non-SQLAlchemy exception must escape untouched, not be degraded to 200.
    with pytest.raises(_NotADbError):
        test_client.get(BASE, params={"rescale_min": 0, "rescale_max": 200})
