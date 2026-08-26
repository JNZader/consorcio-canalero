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
