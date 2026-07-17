"""HTTP happy-path test for the login → refresh-cookie → rotation flow.

``test_auth_gates.py`` pins the REJECTION side (401 without cookie);
this spec pins the ACCEPTANCE side end-to-end through the real ASGI
stack (middlewares included):

  1. ``POST /api/v2/auth/jwt/login`` (fastapi-users, form body) with
     valid credentials → 200 + access token.
  2. ``POST /api/v2/auth/jwt/login-with-refresh`` with the Bearer
     header → 200 + ``refresh_token`` HttpOnly cookie stamped.
  3. ``POST /api/v2/auth/jwt/refresh`` with that cookie → 200, a NEW
     access token, and a ROTATED cookie (value must change).

Style follows ``test_auth_gates.py`` (TestClient + Host header) and
seeds its user directly against the session-scoped ``test_engine``.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete
from sqlalchemy.orm import Session

from app.auth.models import User, UserRole

PASSWORD = "e2e-refresh-flow-Passw0rd!"


def _discard_async_pool() -> None:
    """Drop the app's pooled asyncpg connections WITHOUT closing them.

    Starlette's TestClient (outside a ``with`` block) runs every
    request in a fresh event loop, but the app's async engine uses a
    QueuePool in tests (NullPool only under pgbouncer) — a connection
    created during request N is bound to request N's (now dead) loop
    and explodes with "attached to a different loop" when request N+1
    checks it out. Discarding the pool before each request forces a
    fresh connection on the current loop. ``close=False`` because the
    old connections' loop is gone — they can't be awaited anymore;
    letting them be GC'd is the only safe option in-process.
    """
    import asyncio

    from app.db.session import async_engine

    asyncio.run(async_engine.dispose(close=False))


@pytest.fixture(autouse=True)
def _isolated_async_pool():
    """Keep the shared pool clean before AND after each test so other
    TestClient-based modules never inherit dead-loop connections."""
    _discard_async_pool()
    yield
    _discard_async_pool()


@pytest.fixture(scope="module")
def client() -> TestClient:
    """TestClient against the real app — same setup as test_auth_gates."""
    import os

    os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-auth-refresh")
    os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
    from app.main import app

    tc = TestClient(app)
    tc.headers.update({"Host": "localhost"})
    return tc


@pytest.fixture()
def seeded_user(test_engine):
    """Committed user with a real password hash, cleaned up after.

    Must be COMMITTED (not the rolled-back ``db`` fixture) because the
    app serves requests over its own async connections — the row has
    to be visible cross-connection. refresh_tokens cascade on delete.
    """
    from fastapi_users.password import PasswordHelper

    user = User(
        id=uuid.uuid4(),
        email=f"refresh-flow-{uuid.uuid4().hex[:8]}@playwright.com",
        hashed_password=PasswordHelper().hash(PASSWORD),
        is_active=True,
        is_verified=True,
        is_superuser=False,
        role=UserRole.OPERADOR,
    )
    with Session(bind=test_engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)

    yield user

    with Session(bind=test_engine) as session:
        session.execute(sa_delete(User).where(User.id == user.id))
        session.commit()


def test_login_sets_refresh_cookie_and_refresh_rotates_it(client: TestClient, seeded_user: User):
    # ── 1. Password login (fastapi-users form body; /auth/ paths are
    #       CSRF-exempt so x-www-form-urlencoded is accepted). ──
    login = client.post(
        "/api/v2/auth/jwt/login",
        data={"username": seeded_user.email, "password": PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200, f"login failed: {login.text}"
    access_token = login.json()["access_token"]
    assert access_token

    # ── 2. Stamp the refresh cookie (SPA does this right after login). ──
    _discard_async_pool()
    with_refresh = client.post(
        "/api/v2/auth/jwt/login-with-refresh",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )
    assert with_refresh.status_code == 200, with_refresh.text
    assert with_refresh.json()["access_token"], "must return an access token too"

    cookie_before = client.cookies.get("refresh_token")
    assert cookie_before, "login-with-refresh MUST set the refresh_token cookie"
    # HttpOnly so document.cookie can never read it.
    set_cookie_header = with_refresh.headers.get("set-cookie", "")
    assert "httponly" in set_cookie_header.lower()

    # ── 3. Refresh: cookie in, new access token + ROTATED cookie out. ──
    _discard_async_pool()
    refreshed = client.post(
        "/api/v2/auth/jwt/refresh",
        headers={"Content-Type": "application/json"},
    )
    assert refreshed.status_code == 200, f"refresh failed: {refreshed.text}"
    body = refreshed.json()
    assert body["token_type"] == "bearer"
    new_access = body["access_token"]
    assert new_access, "refresh must mint a new access token"

    cookie_after = client.cookies.get("refresh_token")
    assert cookie_after, "refresh MUST re-stamp the refresh cookie"
    assert cookie_after != cookie_before, (
        "refresh cookie must ROTATE — same value back means the old token was never revoked"
    )

    # The new access token actually authenticates.
    _discard_async_pool()
    me = client.get("/api/v2/users/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200, me.text
    assert me.json()["email"] == seeded_user.email


def test_refresh_works_again_with_rotated_cookie(client: TestClient, seeded_user: User):
    """The rotated cookie is itself refreshable — the chain doesn't
    dead-end after one rotation (family chaining works over HTTP)."""
    login = client.post(
        "/api/v2/auth/jwt/login",
        data={"username": seeded_user.email, "password": PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    _discard_async_pool()
    stamped = client.post(
        "/api/v2/auth/jwt/login-with-refresh",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    assert stamped.status_code == 200, stamped.text

    seen = set()
    for i in range(2):
        _discard_async_pool()
        resp = client.post(
            "/api/v2/auth/jwt/refresh",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200, f"rotation #{i + 1} failed: {resp.text}"
        cookie = client.cookies.get("refresh_token")
        assert cookie and cookie not in seen, "every rotation must mint a new value"
        seen.add(cookie)
