from __future__ import annotations

import asyncio
import socket
from typing import Any

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.config import settings
from app.core.middleware import DistributedRateLimitMiddleware

from app.server import (
    ProxyTrustConfigurationError,
    main,
    resolve_forwarded_allow_ips,
)


async def _run_proxy_middleware(
    *,
    peer: str,
    trusted_hosts: list[str],
) -> tuple[str, str]:
    captured: dict[str, Any] = {}

    async def app(scope, receive, send):
        captured["client"] = scope["client"][0]
        captured["scheme"] = scope["scheme"]
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = ProxyHeadersMiddleware(app, trusted_hosts=trusted_hosts)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"x-forwarded-for", b"203.0.113.9"),
            (b"x-forwarded-proto", b"https"),
        ],
        "client": (peer, 12345),
        "server": ("testserver", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        return None

    await middleware(scope, receive, send)
    return captured["client"], captured["scheme"]


def test_resolved_caddy_peer_applies_forwarded_headers_only_for_that_peer() -> None:
    trusted = resolve_forwarded_allow_ips(
        "127.0.0.1,caddy",
        hostname_resolver=lambda hostname: ("172.22.0.7",),
    )

    assert asyncio.run(_run_proxy_middleware(peer="172.22.0.7", trusted_hosts=trusted)) == (
        "203.0.113.9",
        "https",
    )
    assert asyncio.run(_run_proxy_middleware(peer="172.22.0.8", trusted_hosts=trusted)) == (
        "172.22.0.8",
        "http",
    )


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("127.0.0.1", ["127.0.0.1"]),
        ("10.20.0.0/24", ["10.20.0.0/24"]),
        ("::1", ["::1"]),
        ("2001:db8::/64", ["2001:db8::/64"]),
    ],
)
def test_ip_and_cidr_entries_do_not_use_dns(configured: str, expected: list[str]) -> None:
    def fail_resolver(hostname: str):
        raise AssertionError(f"DNS must not resolve {hostname}")

    assert (
        resolve_forwarded_allow_ips(
            configured,
            hostname_resolver=fail_resolver,
        )
        == expected
    )


@pytest.mark.parametrize("configured", ["*", "", "0.0.0.0/0", "::/0"])
def test_broad_or_empty_proxy_trust_is_rejected(configured: str) -> None:
    with pytest.raises(ProxyTrustConfigurationError):
        resolve_forwarded_allow_ips(configured)


def test_unresolvable_proxy_hostname_is_rejected() -> None:
    def unavailable(hostname: str):
        raise socket.gaierror(hostname)

    with pytest.raises(ProxyTrustConfigurationError):
        resolve_forwarded_allow_ips("caddy", hostname_resolver=unavailable)


def test_main_does_not_start_uvicorn_when_resolution_fails(monkeypatch) -> None:
    started = False

    def fake_run(*args, **kwargs):
        nonlocal started
        started = True

    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")
    monkeypatch.setattr("app.server.uvicorn.run", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 78
    assert started is False


class _RecordingLimiter:
    max_requests = 10

    def __init__(self) -> None:
        self.keys: list[str] = []

    async def check(self, key: str) -> tuple[bool, int, int]:
        self.keys.append(key)
        return True, 9, 60


async def _run_forwarded_auth_request(
    *,
    peer: str,
    trusted_hosts: list[str],
) -> tuple[dict[str, str], list[str]]:
    generic_limiter = _RecordingLimiter()
    auth_limiter = _RecordingLimiter()

    async def endpoint(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "client": request.client.host if request.client else "unknown",
                "scheme": request.url.scheme,
            }
        )

    app = Starlette(routes=[Route("/api/v2/auth/jwt/login", endpoint, methods=["POST"])])
    app.add_middleware(
        DistributedRateLimitMiddleware,
        rate_limiter=generic_limiter,
        auth_rate_limiter=auth_limiter,
    )
    wrapped = ProxyHeadersMiddleware(app, trusted_hosts=trusted_hosts)
    transport = httpx.ASGITransport(app=wrapped, client=(peer, 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://backend") as client:
        response = await client.post(
            "/api/v2/auth/jwt/login",
            headers={
                "X-Forwarded-For": "203.0.113.9",
                "X-Forwarded-Proto": "https",
            },
        )

    assert response.status_code == 200
    return response.json(), auth_limiter.keys


def test_caddy_forwarded_identity_reaches_auth_rate_limiter(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_disabled", False)
    trusted = resolve_forwarded_allow_ips(
        "127.0.0.1,caddy",
        hostname_resolver=lambda hostname: ("172.22.0.7",),
    )

    response, keys = asyncio.run(
        _run_forwarded_auth_request(peer="172.22.0.7", trusted_hosts=trusted)
    )

    assert response == {"client": "203.0.113.9", "scheme": "https"}
    assert keys == ["ip:203.0.113.9"]
