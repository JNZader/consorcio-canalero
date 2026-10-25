"""Request-id correlation contracts for the middleware logging (NUC-2).

A user reports a 429 or a 403. The only way to investigate is to join the
rejection log line to the X-Request-Id header the client received. These
tests drive the REAL app (middleware order as shipped in ``app.main``) and
assert that:

* the access log ("Request started" / "Request completed") carries the same
  request_id the response header returns, and
* the middleware-rejection logs ("Rate limit exceeded", "CSRF: Invalid
  origin") — which are emitted OUTSIDE the router, by middleware that used
  to run outside the request-id binding — carry it too.

Caplog idiom: ``get_logger`` wraps the stdlib logger through structlog's
``ProcessorFormatter``, so each captured ``record.msg`` IS the event dict
and bound fields can be asserted directly (same as
``test_proxy_tile_rescale_db_failure._refusal_records``).
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

# Non-exempt, non-throttled, non-health: RequestLoggingMiddleware logs it,
# the rate limiter counts it, CSRF skips it (GET).
PROBE_PATH = "/api/v2/__request_id_probe__"


@pytest.fixture(scope="module")
def client() -> TestClient:
    """TestClient against the real FastAPI app (full middleware stack).

    ``Host`` is forced to a trusted name so TrustedHostMiddleware doesn't
    400 the probe before the middleware under test fires (same as
    ``test_auth_gates.client``). No DB writes: the probe 404s in the
    router, which is all the logging middleware needs to observe.
    """
    from app.main import app

    tc = TestClient(app)
    tc.headers.update({"Host": "localhost"})
    return tc


def _events(caplog, name: str) -> list[dict]:
    """The structlog event dicts emitted with message ``name``."""
    return [
        record.msg
        for record in caplog.records
        if isinstance(record.msg, dict) and record.msg.get("event") == name
    ]


def test_access_log_carries_the_request_id_the_client_receives(client, caplog):
    """Request started/completed must join to the X-Request-Id header.

    RED on the pre-NUC-2 order: RequestIdMiddleware was innermost, so the
    contextvar binding lived in the child task BaseHTTPMiddleware.call_next
    spawns and never reached the dispatch context that logs these lines —
    the event dicts had NO request_id at all.
    """
    with caplog.at_level(logging.INFO, logger="app.core.middleware"):
        response = client.get(PROBE_PATH)

    assert response.status_code == 404, response.text
    request_id = response.headers["x-request-id"]
    assert request_id, "the client must receive an X-Request-Id header"

    started = _events(caplog, "Request started")
    completed = _events(caplog, "Request completed")
    assert len(started) == 1, caplog.text
    assert len(completed) == 1, caplog.text
    assert started[0]["request_id"] == request_id, caplog.text
    assert completed[0]["request_id"] == request_id, caplog.text
    assert completed[0]["status_code"] == 404


def test_csrf_rejection_log_carries_the_request_id_the_client_receives(client, caplog):
    """A CSRF 403 is minted OUTSIDE the router; its log must still join.

    Path is in AUTH_ORIGIN_REQUIRED_PATHS, so a POST without Origin is
    rejected by CSRFProtectionMiddleware — which on the pre-NUC-2 order ran
    outside the request-id binding.
    """
    with caplog.at_level(logging.WARNING, logger="app.core.middleware"):
        response = client.post("/api/v2/auth/jwt/refresh")

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "CSRF_INVALID_ORIGIN"

    rejections = _events(caplog, "CSRF: Invalid origin")
    assert len(rejections) == 1, caplog.text
    assert rejections[0]["request_id"] == response.headers["x-request-id"], caplog.text


@pytest.mark.rate_limited
def test_rate_limit_rejection_log_carries_the_request_id_the_client_receives(
    client, monkeypatch, caplog
):
    """A 429 from the generic tier must log the id the client header shows.

    ``rate_limit_disabled`` is pinned False explicitly (the suite fixture is
    what normally flips it — see ``test_global_rate_limit_contract`` for the
    same pin) and the singleton limiter's ``check`` is stubbed to refuse the
    first request so the refusal is deterministic regardless of Redis or
    bucket state. What is under test is the LOG/hdr correlation, not the
    limiter arithmetic (the contract module owns that).

    RED on the pre-NUC-2 order: DistributedRateLimitMiddleware ran entirely
    outside RequestIdMiddleware, so "Rate limit exceeded" had no request_id.
    """
    from app.config import settings
    from app.core.rate_limit import get_rate_limiter

    monkeypatch.setattr(settings, "rate_limit_disabled", False)
    limiter = get_rate_limiter()

    async def refuse(_key: str):
        return False, 0, 30

    monkeypatch.setattr(limiter, "check", refuse)

    with caplog.at_level(logging.WARNING, logger="app.core.middleware"):
        response = client.get(PROBE_PATH)

    assert response.status_code == 429, response.text
    assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert response.headers["Retry-After"] == "30"

    rejections = _events(caplog, "Rate limit exceeded")
    assert len(rejections) == 1, caplog.text
    assert rejections[0]["request_id"] == response.headers["x-request-id"], caplog.text
