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

import hashlib
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete, update as sa_update
from sqlalchemy.orm import Session

from app.auth.models import RefreshToken, User, UserRole
from app.auth.refresh_tokens import RACE_WINDOW

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
        headers={
            "Content-Type": "application/json",
            "Origin": "http://localhost:3000",
        },
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
            headers={
                "Content-Type": "application/json",
                "Origin": "http://localhost:3000",
            },
        )
        assert resp.status_code == 200, f"rotation #{i + 1} failed: {resp.text}"
        cookie = client.cookies.get("refresh_token")
        assert cookie and cookie not in seen, "every rotation must mint a new value"
        seen.add(cookie)


# ---------------------------------------------------------------------------
# Two-tab refresh race (RES2-002) + the genuine-failure cookie-clear pins
# ---------------------------------------------------------------------------


def _login_and_stamp_refresh_cookie(client: TestClient, seeded_user: User) -> str:
    """Password login + cookie stamp; returns the raw refresh-cookie value
    now sitting in the shared TestClient (browser) jar."""
    login = client.post(
        "/api/v2/auth/jwt/login",
        data={"username": seeded_user.email, "password": PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200, f"login failed: {login.text}"
    access_token = login.json()["access_token"]

    _discard_async_pool()
    stamped = client.post(
        "/api/v2/auth/jwt/login-with-refresh",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )
    assert stamped.status_code == 200, stamped.text
    cookie = client.cookies.get("refresh_token")
    assert cookie, "login-with-refresh MUST set the refresh_token cookie"
    return cookie


_REFRESH_HEADERS = {
    "Content-Type": "application/json",
    "Origin": "http://localhost:3000",
}


def test_refresh_race_loser_keeps_shared_cookie(client: TestClient, seeded_user: User, monkeypatch):
    """RES2-002 (two-tab race, HTTP level).

    Tab A and tab B hit ``/auth/jwt/refresh`` with the same cookie. Tab A
    wins the CAS and stamps the rotated cookie into the SHARED browser jar;
    tab B — serialized behind tab A by the per-family advisory xact lock,
    so it responds AFTER the winner — loses and gets a 401.

    The 401 stands (a loser may not mint an access token), but the response
    MUST NOT carry ``delete_cookie``: the valid rotated token lives in the
    same jar, and the delete empties it — killing the session up to an hour
    later, in a DIFFERENT tab than the race (with 60-min access tokens,
    ~10%/user-day for two-tab users at ~8 refresh boundaries/day).

    This test pins the HEADER DISCRIMINATION, not the window value: the
    window is widened via monkeypatch so the loser's classification cannot
    flake on a stalled CI runner between the two adjacent requests (a real
    5 s stall would flip it to REPLAY, burn the family, and false-fail —
    review RELC-003). The 5 s boundary itself is pinned with an epsilon
    pair in test_refresh_token_rotation.py (RELC-001).

    Assertions on the response HEADER (not the httpx jar — httpx does not
    honour Max-Age=0 deletes, but every real browser does). Red-checked:
    on the pre-fix code the loser's response carries the delete and this
    test FAILS.
    """
    from app.auth import refresh_tokens as refresh_tokens_mod

    monkeypatch.setattr(refresh_tokens_mod, "RACE_WINDOW", timedelta(seconds=300))
    stale_cookie = _login_and_stamp_refresh_cookie(client, seeded_user)

    # Tab A wins the rotation; the shared jar now holds the rotated value.
    _discard_async_pool()
    winner = client.post("/api/v2/auth/jwt/refresh", headers=dict(_REFRESH_HEADERS))
    assert winner.status_code == 200, winner.text
    rotated_cookie = client.cookies.get("refresh_token")
    assert rotated_cookie and rotated_cookie != stale_cookie, "winner must rotate the cookie"

    # Tab B: its request context captured the OLD value before the winner's
    # Set-Cookie landed in the shared jar, so it presents the stale copy
    # explicitly (an explicit Cookie header replaces the jar — verified).
    # revoked_at is milliseconds old, well inside the MONKEYPATCHED 300 s
    # window (this test deliberately does not pin the production 5 s — see
    # the docstring), so rotate() must classify this as a race LOSS.
    _discard_async_pool()
    loser = client.post(
        "/api/v2/auth/jwt/refresh",
        headers={**_REFRESH_HEADERS, "Cookie": f"refresh_token={stale_cookie}"},
    )
    assert loser.status_code == 401, "race loser may not mint an access token"

    # THE fix: no delete_cookie directive on the loser's response.
    set_cookie = loser.headers.get("set-cookie", "")
    assert "refresh_token" not in set_cookie.lower(), (
        "race-loss 401 must NOT delete the refresh cookie — the winner tab's "
        "rotated token is alive in the shared browser jar; deleting it empties "
        "the jar and forces a delayed logout in a tab that never lost anything "
        "(RES2-002)"
    )

    # The family was NOT burned by the race loss: the jar's rotated token
    # still refreshes, so the session survives the two-tab race.
    _discard_async_pool()
    survivor = client.post("/api/v2/auth/jwt/refresh", headers=dict(_REFRESH_HEADERS))
    assert survivor.status_code == 200, (
        f"the winner's rotated token must still refresh after the race loss — "
        f"got {survivor.status_code}: {survivor.text}"
    )
    assert survivor.json()["access_token"], "surviving refresh must mint an access token"


def test_refresh_garbage_cookie_still_cleared(client: TestClient, seeded_user: User):
    """Genuine invalid cookie (pin): an unknown value → 401 AND the
    destructive delete_cookie stays — the RES2-002 fix spares ONLY the
    race-loss branch."""
    _login_and_stamp_refresh_cookie(client, seeded_user)

    _discard_async_pool()
    resp = client.post(
        "/api/v2/auth/jwt/refresh",
        headers={**_REFRESH_HEADERS, "Cookie": "refresh_token=totally-bogus-value"},
    )
    assert resp.status_code == 401
    set_cookie = resp.headers.get("set-cookie", "")
    assert "refresh_token" in set_cookie.lower(), (
        "genuine invalid refresh cookie must still be cleared client-side"
    )


def test_refresh_replay_past_window_burned_and_cleared(
    client: TestClient, seeded_user: User, test_engine
):
    """Genuine replay (pin): the same revoked cookie presented PAST the
    RACE_WINDOW burns the family, the 401 still clears the cookie, and the
    WINNER's rotated token dies with the family — unchanged by the
    RES2-002 fix."""
    stale_cookie = _login_and_stamp_refresh_cookie(client, seeded_user)

    _discard_async_pool()
    winner = client.post("/api/v2/auth/jwt/refresh", headers=dict(_REFRESH_HEADERS))
    assert winner.status_code == 200, winner.text
    rotated_cookie = client.cookies.get("refresh_token")
    assert rotated_cookie and rotated_cookie != stale_cookie

    # Age the revoked row past RACE_WINDOW (mirrors the unit tests'
    # ``_backdate``) so the stale presentation reads as REPLAY, not race.
    digest = hashlib.sha256(stale_cookie.encode()).hexdigest()
    with Session(bind=test_engine) as session:
        session.execute(
            sa_update(RefreshToken)
            .where(RefreshToken.token_hash == digest)
            .values(revoked_at=RefreshToken.revoked_at - (RACE_WINDOW + timedelta(seconds=60)))
        )
        session.commit()

    _discard_async_pool()
    replay = client.post(
        "/api/v2/auth/jwt/refresh",
        headers={**_REFRESH_HEADERS, "Cookie": f"refresh_token={stale_cookie}"},
    )
    assert replay.status_code == 401, "replayed token must never refresh"
    set_cookie = replay.headers.get("set-cookie", "")
    assert "refresh_token" in set_cookie.lower(), (
        "replay 401 must still clear the cookie (genuine-failure path)"
    )

    # Family burned: even the WINNER's rotated token is dead now.
    _discard_async_pool()
    burned = client.post(
        "/api/v2/auth/jwt/refresh",
        headers={**_REFRESH_HEADERS, "Cookie": f"refresh_token={rotated_cookie}"},
    )
    assert burned.status_code == 401, (
        "confirmed replay must burn the whole family — the winner's rotated "
        "token cannot survive the sweep"
    )
