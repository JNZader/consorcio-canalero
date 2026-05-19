"""Auth-gate regression tests (Phase 4 / F4-D).

These tests are the deploy gate against a PII regression: every
sensitive endpoint here MUST refuse unauthenticated callers. They run
on every push via the existing pytest job; a future PR that
accidentally drops a ``Depends(_require_operator())`` from any of these
routes is caught at CI before reaching prod.

The list is deliberately exhaustive — when a new sensitive endpoint
lands, add it here in the same PR.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Build a TestClient against the real FastAPI app.

    No DB writes are required by these tests — every call should be
    rejected by ``Depends(_require_operator())`` before reaching the
    handler body, so we don't need a populated database. The Host
    header is forced to a value the dev ``CORS_ORIGINS`` includes
    (default ``http://localhost:5173``) so ``TrustedHostMiddleware``
    doesn't 400 the request before the auth check fires.
    """
    import os

    os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-auth-gates")
    # Make sure ``localhost`` is in CORS_ORIGINS so the dev derivation
    # of trusted_hosts includes it. In prod the fail-fast refuses
    # localhost there — fine, this only fires in tests.
    os.environ.setdefault(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
    )
    from app.main import app

    tc = TestClient(app)
    # Override the default ``Host: testserver`` so requests reach the
    # routes. ``localhost`` is in dev's trusted hosts via the
    # CORS_ORIGINS derivation above.
    tc.headers.update({"Host": "localhost"})
    return tc


# ---------------------------------------------------------------------------
# Padron — admin / operator only
# ---------------------------------------------------------------------------


class TestPadronAuthGates:
    """``/api/v2/padron/*`` rejects every unauthenticated caller."""

    def test_list_consorcistas_unauthenticated_401(self, client: TestClient):
        resp = client.get("/api/v2/padron")
        assert resp.status_code == 401, (
            f"Padron list MUST require auth — got {resp.status_code}"
        )

    def test_get_consorcista_unauthenticated_401(self, client: TestClient):
        # Existence of the row is irrelevant — auth must fail first.
        resp = client.get("/api/v2/padron/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 401, (
            f"Padron detail MUST require auth — got {resp.status_code}"
        )

    def test_stats_unauthenticated_401(self, client: TestClient):
        resp = client.get("/api/v2/padron/stats")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Denuncias — admin / operator only on the list+detail+update paths
# (citizens have /mine + /rate-limit which are SEPARATELY gated by
# ``_require_user`` — those endpoints accept any logged-in user)
# ---------------------------------------------------------------------------


class TestDenunciasAuthGates:
    def test_list_unauthenticated_401(self, client: TestClient):
        resp = client.get("/api/v2/denuncias")
        assert resp.status_code == 401

    def test_detail_unauthenticated_401(self, client: TestClient):
        resp = client.get("/api/v2/denuncias/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 401

    def test_mine_unauthenticated_401(self, client: TestClient):
        """Citizen-side endpoint also requires auth (any role)."""
        resp = client.get("/api/v2/denuncias/mine")
        assert resp.status_code == 401

    def test_delete_mine_unauthenticated_401(self, client: TestClient):
        """ARCO cancellation also requires auth — the owner must
        prove ownership before deletion.

        ``Content-Type: application/json`` is required by the CSRF
        middleware on every mutating method; without it the
        middleware short-circuits with 415 before the auth check
        even runs. Browsers attach it automatically; cURL / tests
        need to set it explicitly.
        """
        resp = client.delete(
            "/api/v2/denuncias/00000000-0000-0000-0000-000000000000/mine",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Finanzas — operator only (everything; nothing is public)
# ---------------------------------------------------------------------------


class TestFinanzasAuthGates:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/v2/finanzas/gastos",
            "/api/v2/finanzas/gastos/00000000-0000-0000-0000-000000000000",
            "/api/v2/finanzas/ingresos",
            "/api/v2/finanzas/ingresos/00000000-0000-0000-0000-000000000000",
            "/api/v2/finanzas/presupuesto",
            "/api/v2/finanzas/ejecucion/2026",
            "/api/v2/finanzas/resumen/2026",
        ],
    )
    def test_unauthenticated_401(self, client: TestClient, path: str):
        resp = client.get(path)
        assert resp.status_code == 401, (
            f"Finanzas endpoint {path} MUST require auth — got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# Monitoring sugerencias — list requires operator
# ---------------------------------------------------------------------------


class TestMonitoringAuthGates:
    def test_sugerencias_list_unauthenticated_401(self, client: TestClient):
        resp = client.get("/api/v2/sugerencias")
        assert resp.status_code == 401

    def test_sugerencias_stats_unauthenticated_401(self, client: TestClient):
        resp = client.get("/api/v2/sugerencias/stats")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Auth — refresh + logout-all
# ---------------------------------------------------------------------------


class TestAuthSessionGates:
    def test_refresh_without_cookie_401(self, client: TestClient):
        resp = client.post(
            "/api/v2/auth/jwt/refresh",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    def test_logout_all_unauthenticated_401(self, client: TestClient):
        resp = client.post(
            "/api/v2/auth/jwt/logout-all",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Uploads — denuncia photos require auth + ownership
# ---------------------------------------------------------------------------


class TestUploadsAuthGates:
    def test_denuncia_photo_unauthenticated_401(self, client: TestClient):
        # Even with a valid filename pattern, no token = 401.
        resp = client.get(
            "/uploads/denuncias/00000000-0000-0000-0000-000000000000.jpg"
        )
        assert resp.status_code == 401, (
            "Denuncia photos MUST require auth — public mount was removed in F2-F"
        )


# ---------------------------------------------------------------------------
# Admin readiness detail (sensitive info — version, schema rev)
# ---------------------------------------------------------------------------


class TestAdminReadyDetailedGate:
    def test_admin_ready_detailed_unauthenticated_401(self, client: TestClient):
        resp = client.get("/admin/ready/detailed")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Live / Ready — must remain PUBLIC (orchestrators need them)
# ---------------------------------------------------------------------------


class TestPublicHealthEndpointsStayPublic:
    """Inverse gate: these MUST stay open to unauthenticated callers,
    or every Docker / UptimeRobot healthcheck breaks."""

    def test_live_public(self, client: TestClient):
        resp = client.get("/live")
        assert resp.status_code == 200

    def test_ready_public(self, client: TestClient):
        # /ready may return 503 if deps are degraded, but the response
        # must be served (not 401).
        resp = client.get("/ready")
        assert resp.status_code in (200, 503)

    def test_health_public(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
