"""Tests for single-use OAuth exchange cookie nonce & narrow cookie Path."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.models import UserRole
from app.config import settings
from app.core.cache import JSONCache


def _load_oauth_router_module(monkeypatch: pytest.MonkeyPatch, fake_cache: JSONCache):
    """Load an isolated copy of ``app.auth.router`` with OAuth enabled."""
    monkeypatch.setattr(settings, "google_oauth_client_id", "test-oauth-client-id")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "test-oauth-client-secret")

    router_path = Path(__file__).resolve().parents[2] / "app" / "auth" / "router.py"
    module_name = f"_oauth_router_isolated_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, router_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise

    monkeypatch.setattr(module, "get_cache", lambda: fake_cache)
    return module, module_name


def test_oauth_exchange_cookie_is_narrow_path_and_strictly_single_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_cache = JSONCache(redis_url=None)
    module, module_name = _load_oauth_router_module(monkeypatch, fake_cache)
    try:
        user = SimpleNamespace(
            id=uuid.uuid4(),
            email="oauth@example.com",
            role=UserRole.OPERADOR,
            is_active=True,
            revocation_epoch=0,
        )

        class _Result:
            def __init__(self, row):
                self._row = row

            def scalar_one_or_none(self):
                return self._row

        class _FakeSession:
            def __init__(self) -> None:
                self._calls = 0

            async def execute(self, _stmt):
                self._calls += 1
                return _Result(user if self._calls == 1 else None)

        fake_session = _FakeSession()

        @asynccontextmanager
        async def _unused_lifespan(_app: FastAPI):
            yield

        isolated_app = FastAPI(lifespan=_unused_lifespan)
        isolated_app.include_router(module.router, prefix="/api/v2")
        isolated_app.dependency_overrides[module.get_async_db] = lambda: fake_session

        monkeypatch.setattr(
            module.google_oauth_client,
            "get_access_token",
            AsyncMock(return_value={"id_token": "fake-id-token"}),
        )
        monkeypatch.setattr(
            module,
            "_verify_google_id_token",
            lambda _raw: {
                "iss": "https://accounts.google.com",
                "email": "oauth@example.com",
                "email_verified": True,
            },
        )
        monkeypatch.setattr(
            module,
            "issue_token",
            AsyncMock(return_value=("raw-refresh-token", SimpleNamespace())),
        )
        monkeypatch.setattr(
            module,
            "get_jwt_strategy",
            lambda: SimpleNamespace(write_token=AsyncMock(return_value="minted-jwt-token")),
        )

        client = TestClient(isolated_app, follow_redirects=False)

        auth_resp = client.get("/api/v2/auth/google/authorize")
        assert auth_resp.status_code == 200
        state_cookie = auth_resp.cookies.get("oauth_state")
        assert state_cookie

        cb_resp = client.get(
            f"/api/v2/auth/google/callback?code=authcode&state={state_cookie}",
            cookies={"oauth_state": state_cookie},
        )
        assert cb_resp.status_code in (302, 307)

        set_cookies = cb_resp.headers.get_list("set-cookie")
        exchange_headers = [h for h in set_cookies if "oauth_access_token=" in h]
        assert len(exchange_headers) == 1
        exchange_header = exchange_headers[0]
        assert "path=/api/v2/auth/jwt/exchange-cookie" in exchange_header.lower()
        assert "httponly" in exchange_header.lower()
        assert "minted-jwt-token" not in exchange_header

        nonce = exchange_header.split("oauth_access_token=", 1)[1].split(";", 1)[0]
        assert nonce and nonce != "minted-jwt-token"

        first = client.post(
            "/api/v2/auth/jwt/exchange-cookie",
            cookies={"oauth_access_token": nonce},
        )
        assert first.status_code == 200, first.text
        assert first.json() == {"access_token": "minted-jwt-token", "token_type": "bearer"}
        delete_headers = first.headers.get_list("set-cookie")
        assert any(
            "oauth_access_token=" in h and "path=/api/v2/auth/jwt/exchange-cookie" in h.lower()
            for h in delete_headers
        )

        # Replay of the exact same cookie nonce MUST fail with 401.
        replay = client.post(
            "/api/v2/auth/jwt/exchange-cookie",
            cookies={"oauth_access_token": nonce},
        )
        assert replay.status_code == 401
        assert replay.json()["error"] == "missing_exchange_cookie"
    finally:
        sys.modules.pop(module_name, None)
