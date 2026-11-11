"""Per-operator rate limit on POST /api/v2/geo/gee/analysis (#713).

Every accepted run publishes a Celery task whose GEE work mints map tiles
against the project's metered quota, so the route now carries a dedicated
``DistributedRateLimiter`` keyed on the authenticated operator
(``operator:{user.id}``), mirroring the ficha/map-pdf limiters. These tests
pin the four properties the issue's acceptance criteria depend on:

* an operator under the budget gets the run accepted;
* the N+1 run is a 429 carrying ``Retry-After`` (header + body detail);
* ``settings.rate_limit_disabled`` short-circuits BEFORE the limiter;
* two operators never share a ceiling (one bucket per account, not per IP).

The handler body is stubbed (the DB write / Celery outbox row are not under
test here) and the limiter runs in its Redis-down in-memory mode with
``_get_redis`` neutralized, so the window is deterministic and no Redis is
needed. pytest runs in CI; locally these are validated by ruff + py_compile.
"""

from __future__ import annotations

import os
import types
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-gee-analysis-rate-limit")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long")

ANALYSIS_PATH = "/api/v2/geo/gee/analysis"
PAYLOAD = {"tipo": "flood", "parametros": {}}


def _respuesta_stub():
    from app.domains.geo.schemas import AnalisisGeoResponse

    marca = datetime(2026, 1, 1, 12, 0, 0)
    return AnalisisGeoResponse(
        id=uuid.uuid4(),
        tipo="flood",
        fecha_analisis=date(2026, 1, 1),
        estado="pendiente",
        created_at=marca,
        updated_at=marca,
    )


@pytest.fixture
def cliente_operador(monkeypatch):
    """TestClient with operator auth + handler stubbed to a valid 201 body.

    The fake operator is a mutable holder: tests swap ``usuario.id`` between
    requests to prove the limiter buckets per ACCOUNT (the dependency is
    re-solved — and re-reads ``user.id`` — on every request).
    """
    from app.auth import require_admin_or_operator
    from app.db.session import get_db
    from app.domains.geo import router as geo_router
    from app.main import app

    usuario = types.SimpleNamespace(id=uuid.uuid4())

    app.dependency_overrides[require_admin_or_operator] = lambda: usuario
    # The stubbed impl never touches the session; keep the real get_db out.
    app.dependency_overrides[get_db] = lambda: None
    monkeypatch.setattr(
        geo_router, "submit_gee_analysis_impl", lambda _p, _db, _r: _respuesta_stub()
    )

    client = TestClient(app)
    client.headers.update({"Host": "localhost"})
    yield client, usuario
    app.dependency_overrides.clear()


@pytest.fixture
def limiter_gee(monkeypatch):
    """Fresh singleton in deterministic in-memory mode, budget of 1 per hour.

    A fresh instance (not the possibly already-built module singleton) keeps
    these tests independent of execution order and of any Redis the box may
    have running: ``_get_redis`` neutralized → the sliding window is the
    per-process ``_memory_store``.
    """
    from app.domains.geo import router as geo_router

    monkeypatch.setattr(geo_router, "_gee_analysis_limiter", None)
    limiter = geo_router.get_gee_analysis_rate_limiter()
    monkeypatch.setattr(limiter, "_get_redis", AsyncMock(return_value=None))
    limiter.max_requests = 1
    limiter.window_seconds = 3600
    yield limiter
    monkeypatch.setattr(geo_router, "_gee_analysis_limiter", None)


def test_gee_analysis_within_limit_passes(cliente_operador, limiter_gee, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_disabled", False)

    client, _usuario = cliente_operador
    rs = client.post(ANALYSIS_PATH, json=PAYLOAD)

    assert rs.status_code == 201, rs.text
    assert rs.json()["tipo"] == "flood"


def test_gee_analysis_throttles_at_n_plus_one_with_retry(
    cliente_operador, limiter_gee, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_disabled", False)

    client, _usuario = cliente_operador
    primera = client.post(ANALYSIS_PATH, json=PAYLOAD)
    segunda = client.post(ANALYSIS_PATH, json=PAYLOAD)

    assert primera.status_code == 201, primera.text
    assert segunda.status_code == 429, segunda.text
    # Header by app.exception_handler (RateLimitExceededError), body detail by
    # the error itself — a full 1 h window was just spent, so the reset is
    # 3600 minus the milliseconds between the two POSTs (``int()`` truncates).
    reintento = int(segunda.headers.get("Retry-After", "0"))
    assert 3500 <= reintento <= 3600, reintento
    cuerpo = segunda.json()["error"]
    assert cuerpo["code"] == "RATE_LIMIT_EXCEEDED"
    assert 3500 <= cuerpo["details"]["retry_after"] <= 3600
    assert cuerpo["details"]["limit"] == 1


def test_gee_analysis_rate_limit_disabled_short_circuits(
    cliente_operador, limiter_gee, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_disabled", True)
    # If the flag were ignored, this exhausted bucket would 429 the request.
    limiter_gee.check = AsyncMock(return_value=(False, 0, 999))

    client, _usuario = cliente_operador
    rs = client.post(ANALYSIS_PATH, json=PAYLOAD)

    assert rs.status_code == 201, rs.text
    assert limiter_gee.check.await_count == 0, "the flag must skip the limiter entirely"


def test_gee_analysis_two_operators_do_not_share_ceiling(
    cliente_operador, limiter_gee, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_disabled", False)

    client, usuario = cliente_operador
    id_a = usuario.id
    corrida_a = client.post(ANALYSIS_PATH, json=PAYLOAD)  # A spends its only slot
    rebote_a = client.post(ANALYSIS_PATH, json=PAYLOAD)  # same account → 429
    usuario.id = uuid.uuid4()  # same route, DIFFERENT authenticated account
    corrida_b = client.post(ANALYSIS_PATH, json=PAYLOAD)  # B's bucket is its own

    assert corrida_a.status_code == 201, corrida_a.text
    assert rebote_a.status_code == 429, rebote_a.text
    assert corrida_b.status_code == 201, corrida_b.text

    # And the buckets really are distinct keys (``operator:{id}``), not one
    # shared counter: A's exhausted bucket plus B's single entry.
    claves = sorted(limiter_gee._memory_store.keys())
    assert claves == sorted([f"operator:{id_a}", f"operator:{usuario.id}"]), claves
    assert len(limiter_gee._memory_store[f"operator:{id_a}"]) == 1
