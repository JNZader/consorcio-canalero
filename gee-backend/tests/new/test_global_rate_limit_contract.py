"""The generic rate-limit tier still answers 429 — asserted, not assumed.

``tests/new/conftest.py`` disables the process-wide limiter for the whole
suite (BL-RATE-LIMIT-SUITE-CASCADE: one in-memory bucket keyed ``ip:testclient``
was throttling the run itself). A blanket suppression that leaves the throttle
with NO coverage would trade a noisy false red for a silent hole, so this module
opts back in via ``@pytest.mark.rate_limited`` and drives the real limiter past
its own budget.

Marked tests do not get a disabled limiter, they get FLUSHED buckets — so the
window here starts empty regardless of what ran before.
"""

import asyncio

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.core.middleware import DistributedRateLimitMiddleware
from app.core.rate_limit import get_rate_limiter

# A non-exempt, non-auth path: the generic tier, not the strict auth tier and
# not one of the ``/health`` / ``/tiles/`` bypasses.
PROBE_PATH = "/api/v2/probe"


async def _drive(request_count: int) -> list[httpx.Response]:
    async def endpoint(request: Request) -> JSONResponse:  # noqa: ARG001 — Starlette signature
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route(PROBE_PATH, endpoint, methods=["GET"])])
    app.add_middleware(DistributedRateLimitMiddleware, rate_limiter=get_rate_limiter())

    transport = httpx.ASGITransport(app=app, client=("198.51.100.7", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://backend") as client:
        return [await client.get(PROBE_PATH) for _ in range(request_count)]


@pytest.mark.rate_limited
def test_the_generic_tier_answers_429_once_its_budget_is_spent(monkeypatch) -> None:
    """The (limit + 1)-th request is refused, and the refusal is self-describing.

    ``rate_limit_disabled`` is pinned False explicitly rather than trusted to
    still hold its default: the suite-wide fixture is what normally flips it,
    and a test asserting the limiter must not depend on fixture ordering to
    know which way that flag points.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_disabled", False)
    limiter = get_rate_limiter()

    responses = asyncio.run(_drive(limiter.max_requests + 1))

    assert all(response.status_code == 200 for response in responses[:-1]), (
        "requests inside the budget must pass"
    )

    refused = responses[-1]
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert int(refused.headers["Retry-After"]) >= 1
    assert refused.headers["X-RateLimit-Limit"] == str(limiter.max_requests)
    assert refused.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.rate_limited
def test_options_preflight_does_not_spend_the_generic_budget(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_disabled", False)
    limiter = get_rate_limiter()

    async def endpoint(request: Request) -> JSONResponse:  # noqa: ARG001
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route(PROBE_PATH, endpoint, methods=["GET", "OPTIONS"])])
    app.add_middleware(DistributedRateLimitMiddleware, rate_limiter=limiter)

    async def run() -> list[int]:
        transport = httpx.ASGITransport(app=app, client=("198.51.100.9", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://backend") as client:
            options_codes = [
                (await client.options(PROBE_PATH)).status_code
                for _ in range(limiter.max_requests + 5)
            ]
            get_codes = [(await client.get(PROBE_PATH)).status_code for _ in range(3)]
            return options_codes + get_codes

    codes = asyncio.run(run())
    assert all(code == 200 for code in codes)


@pytest.mark.rate_limited
def test_public_map_gets_do_not_spend_the_generic_budget(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_disabled", False)
    limiter = get_rate_limiter()

    async def endpoint(request: Request) -> JSONResponse:  # noqa: ARG001
        return JSONResponse({"ok": True})

    public_path = "/api/v2/geo/layers/public"
    app = Starlette(
        routes=[
            Route(public_path, endpoint, methods=["GET"]),
            Route(PROBE_PATH, endpoint, methods=["GET"]),
        ]
    )
    app.add_middleware(DistributedRateLimitMiddleware, rate_limiter=limiter)

    async def run() -> tuple[list[int], int, str | None]:
        transport = httpx.ASGITransport(app=app, client=("198.51.100.11", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://backend") as client:
            layer_responses = [
                await client.get(public_path) for _ in range(limiter.max_requests + 5)
            ]
            probe = (await client.get(PROBE_PATH)).status_code
            return (
                [response.status_code for response in layer_responses],
                probe,
                layer_responses[0].headers.get("Cache-Control"),
            )

    layer_codes, probe, cache_control = asyncio.run(run())
    assert all(code == 200 for code in layer_codes)
    assert probe == 200
    assert cache_control == "public, max-age=300, stale-while-revalidate=60"


@pytest.mark.rate_limited
def test_admin_gee_layers_get_spends_the_generic_budget(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_disabled", False)
    limiter = get_rate_limiter()

    async def endpoint(request: Request) -> JSONResponse:  # noqa: ARG001
        return JSONResponse({"ok": True})

    admin_path = "/api/v2/geo/gee/layers/zona"
    app = Starlette(routes=[Route(admin_path, endpoint, methods=["GET"])])
    app.add_middleware(DistributedRateLimitMiddleware, rate_limiter=limiter)

    async def run() -> int:
        transport = httpx.ASGITransport(app=app, client=("198.51.100.13", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://backend") as client:
            last = 200
            for _ in range(limiter.max_requests + 1):
                last = (await client.get(admin_path)).status_code
            return last

    assert asyncio.run(run()) == 429


@pytest.mark.rate_limited
def test_the_disabled_switch_is_what_the_suite_fixture_uses(monkeypatch) -> None:
    """With ``rate_limit_disabled`` on, the same overrun is never refused.

    This is the seam ``conftest._disable_global_rate_limiter`` flips for the
    rest of the suite; asserting it here is what makes that fixture a
    documented behavior rather than an undocumented side effect.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_disabled", True)
    limiter = get_rate_limiter()

    responses = asyncio.run(_drive(limiter.max_requests + 1))

    assert {response.status_code for response in responses} == {200}


@pytest.mark.rate_limited
def test_public_map_get_sends_etag_and_honors_if_none_match(monkeypatch) -> None:
    from app.config import settings
    from app.core.middleware import _etag_for_body

    monkeypatch.setattr(settings, "rate_limit_disabled", False)
    public_path = "/api/v2/public/settings/branding"

    async def endpoint(request: Request) -> JSONResponse:  # noqa: ARG001
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route(public_path, endpoint, methods=["GET"])])
    app.add_middleware(DistributedRateLimitMiddleware, rate_limiter=get_rate_limiter())

    async def run() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app, client=("198.51.100.21", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://backend") as client:
            first = await client.get(public_path)
            second = await client.get(public_path, headers={"If-None-Match": first.headers["etag"]})
            return first, second

    first, second = asyncio.run(run())
    assert first.status_code == 200
    assert first.headers["etag"] == _etag_for_body(first.content)
    assert second.status_code == 304
    assert second.headers["etag"] == first.headers["etag"]
    assert second.content == b""
    assert second.headers["cache-control"] == first.headers["cache-control"]


@pytest.mark.rate_limited
def test_only_exact_tile_urls_skip_the_generic_budget(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_disabled", False)
    limiter = get_rate_limiter()
    fake_tile = "/api/v2/geo/layers/tiles/sentinel2"
    real_tile = "/api/v2/geo/layers/11111111-1111-1111-1111-111111111111/tiles/1/0/0.png"
    worker_tile = "/tiles/dem-1/2/1/0.png"

    async def endpoint(request: Request) -> JSONResponse:  # noqa: ARG001
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[
            Route(fake_tile, endpoint, methods=["GET"]),
            Route(
                "/api/v2/geo/layers/{layer_id}/tiles/{z}/{x}/{y}.png",
                endpoint,
                methods=["GET"],
            ),
            Route("/tiles/{layer_id}/{z}/{x}/{y}.png", endpoint, methods=["GET"]),
        ]
    )
    app.add_middleware(DistributedRateLimitMiddleware, rate_limiter=limiter)

    async def hammer(path: str, client_ip: str, count: int) -> list[int]:
        transport = httpx.ASGITransport(app=app, client=(client_ip, 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://backend") as client:
            return [(await client.get(path)).status_code for _ in range(count)]

    async def run() -> tuple[list[int], list[int], list[int]]:
        fake = await hammer(fake_tile, "198.51.100.31", limiter.max_requests + 1)
        real = await hammer(real_tile, "198.51.100.32", limiter.max_requests + 5)
        worker = await hammer(worker_tile, "198.51.100.33", limiter.max_requests + 5)
        return fake, real, worker

    fake, real, worker = asyncio.run(run())
    assert fake[-1] == 429
    assert all(code == 200 for code in real)
    assert all(code == 200 for code in worker)
