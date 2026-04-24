import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.middleware import SecurityHeadersMiddleware


async def call_next(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def make_request(path: str, headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": raw_headers,
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
        }
    )


@pytest.mark.asyncio
async def test_security_headers_are_added_to_api_responses():
    middleware = SecurityHeadersMiddleware(app=None)

    response = await middleware.dispatch(make_request("/api/v2/public"), call_next)

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert (
        response.headers["Permissions-Policy"]
        == "camera=(), microphone=(), geolocation=()"
    )
    assert "Strict-Transport-Security" not in response.headers


@pytest.mark.asyncio
async def test_hsts_is_added_for_forwarded_https_requests():
    middleware = SecurityHeadersMiddleware(app=None)

    response = await middleware.dispatch(
        make_request("/api/v2/public", {"X-Forwarded-Proto": "https"}), call_next
    )

    assert (
        response.headers["Strict-Transport-Security"]
        == "max-age=31536000; includeSubDomains"
    )


@pytest.mark.asyncio
async def test_auth_responses_are_not_cached():
    middleware = SecurityHeadersMiddleware(app=None)

    response = await middleware.dispatch(
        make_request("/api/v2/auth/session"), call_next
    )

    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
