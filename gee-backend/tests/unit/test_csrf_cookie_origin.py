"""Cookie session mutations require an allowed Origin. Login does not."""

import asyncio

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.core.middleware import CSRFProtectionMiddleware

ALLOWED = "http://localhost:3000"


async def _ok(request: Request) -> JSONResponse:  # noqa: ARG001
    return JSONResponse({"ok": True})


def _app() -> Starlette:
    app = Starlette(
        routes=[
            Route("/api/v2/auth/jwt/login", _ok, methods=["POST"]),
            Route("/api/v2/auth/jwt/refresh", _ok, methods=["POST"]),
            Route("/api/v2/auth/jwt/logout", _ok, methods=["POST"]),
            Route("/api/v2/auth/jwt/logout-all", _ok, methods=["POST"]),
        ]
    )
    app.add_middleware(CSRFProtectionMiddleware)
    return app


def _post(path: str, origin: str | None) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://backend") as client:
            headers = {}
            if origin is not None:
                headers["Origin"] = origin
            return await client.post(path, headers=headers)

    return asyncio.run(run())


@pytest.mark.parametrize(
    "path",
    [
        "/api/v2/auth/jwt/refresh",
        "/api/v2/auth/jwt/logout",
        "/api/v2/auth/jwt/logout-all",
    ],
)
def test_cookie_session_mutations_reject_a_missing_or_foreign_origin(path: str):
    missing = _post(path, None)
    foreign = _post(path, "https://evil.example")
    allowed = _post(path, ALLOWED)
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "CSRF_INVALID_ORIGIN"
    assert foreign.status_code == 403
    assert allowed.status_code == 200


def test_login_stays_exempt_when_origin_is_absent():
    assert _post("/api/v2/auth/jwt/login", None).status_code == 200
