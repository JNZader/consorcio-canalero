"""Regression tests for Wave 4 W-BE-04 security, lifecycle, settings, and readiness fixes."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.main as main_mod
from app.auth import require_admin_or_operator, require_authenticated
from app.config import settings
from app.db.session import get_db
from app.domains.geo import router_gee_support
from app.domains.geo.router_core import get_geo_layer_file
from app.domains.settings.service import SettingsService
from app.shared.audit_log import AuditLog


@pytest.mark.asyncio
async def test_operator_geo_endpoints_emit_private_cache_control(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tif = tmp_path / "dem.tif"
    tif.write_bytes(b"II*\x00")
    layer_id = uuid.uuid4()
    repo = MagicMock()
    repo.get_layer_by_id.return_value = SimpleNamespace(
        id=layer_id, archivo_path=str(tif), formato="geotiff"
    )
    resp = get_geo_layer_file(layer_id=layer_id, db=MagicMock(), repo=repo, _user=MagicMock())
    assert resp.headers["cache-control"] == "private, max-age=3600"

    fake_explorer = SimpleNamespace(get_available_dates=lambda **_kw: {"dates": []})

    def ensure():
        return {
            "get_available_layers": lambda: {"layers": []},
            "get_consorcios_camineros": lambda: ["C1"],
            "get_caminos_by_consorcio": lambda _c: {"type": "FeatureCollection", "features": [1]},
            "get_caminos_by_consorcio_nombre": lambda _n: {
                "type": "FeatureCollection",
                "features": [1],
            },
            "get_caminos_con_colores": lambda: {"type": "FeatureCollection", "features": []},
            "get_estadisticas_consorcios": lambda: {"total": 0},
            "get_layer_geojson": lambda _name: {"type": "FeatureCollection", "features": []},
            "get_image_explorer": lambda: fake_explorer,
        }

    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    cache.acquire_lock = AsyncMock(return_value=None)
    cache.release_lock = AsyncMock()
    monkeypatch.setattr(router_gee_support, "get_cache", lambda: cache)

    responses = [
        await router_gee_support.list_gee_layers_impl(ensure),
        await router_gee_support.list_consorcios_camineros_impl(ensure_gee=ensure),
        await router_gee_support.get_caminos_consorcio_impl(codigo="01", ensure_gee=ensure),
        await router_gee_support.get_caminos_por_nombre_consorcio_impl(
            nombre="Test", ensure_gee=ensure
        ),
        await router_gee_support.get_caminos_coloreados_impl(ensure_gee=ensure),
        await router_gee_support.get_estadisticas_caminos_impl(ensure_gee=ensure),
        await router_gee_support.get_gee_layer_impl(layer_name="zona", ensure_gee=ensure),
        await router_gee_support.get_available_image_dates_impl(
            year=2026, month=1, sensor="sentinel2", ensure_gee=ensure
        ),
        await router_gee_support.get_available_visualizations_impl(),
    ]
    # Exercise HIT paths too.
    cache.get = AsyncMock(return_value={"cached": True})
    responses.extend(
        [
            await router_gee_support.get_caminos_coloreados_impl(ensure_gee=ensure),
            await router_gee_support.get_estadisticas_caminos_impl(ensure_gee=ensure),
            await router_gee_support.get_gee_layer_impl(layer_name="zona", ensure_gee=ensure),
        ]
    )

    for r in responses:
        cc = r.headers.get("cache-control", "")
        assert cc.startswith("private, "), f"Expected private Cache-Control, got {cc!r}"


@pytest.mark.asyncio
async def test_lifespan_closes_conocimiento_and_informe_rate_limiters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import cache as cache_mod, health as health_mod, rate_limit as rl_mod
    from app.domains.conocimiento import router as conocimiento_router
    from app.domains.geo.informe_area import router as informe_router

    closed: list[str] = []

    def _limiter(name: str):
        obj = MagicMock()
        obj._get_redis = AsyncMock(return_value=None)
        obj.close = AsyncMock(side_effect=lambda: closed.append(name))
        return obj

    monkeypatch.setattr(main_mod, "get_rate_limiter", lambda: _limiter("generic"))
    monkeypatch.setattr(main_mod, "get_auth_rate_limiter", lambda: _limiter("auth"))
    monkeypatch.setattr(
        "app.domains.geo.router_ficha.get_ficha_rate_limiter",
        lambda: _limiter("ficha"),
    )
    monkeypatch.setattr(
        "app.domains.geo.router_common.get_map_pdf_rate_limiter",
        lambda: _limiter("map_pdf"),
    )
    monkeypatch.setattr(
        "app.domains.geo.router.get_gee_analysis_rate_limiter",
        lambda: _limiter("gee_analysis"),
    )
    monkeypatch.setattr(
        conocimiento_router, "get_conocimiento_rate_limiter", lambda: _limiter("conocimiento")
    )
    monkeypatch.setattr(
        informe_router, "get_informe_rate_limiter", lambda: _limiter("informe_area")
    )
    fake_cache = MagicMock()
    fake_cache.close = AsyncMock(side_effect=lambda: closed.append("cache"))
    monkeypatch.setattr(cache_mod, "get_cache", lambda: fake_cache)
    monkeypatch.setattr(health_mod, "shutdown_gee_probe", lambda: closed.append("gee_probe"))
    monkeypatch.setenv("DISABLE_GEE_CACHE_WARMING", "true")
    monkeypatch.setattr(
        "app.domains.geo.gee_service.ensure_initialized_async",
        AsyncMock(return_value=None),
    )

    # Keep rl_mod reference used so ruff doesn't flag unused import if adjusted later.
    _ = rl_mod

    async with main_mod.lifespan(main_mod.app):
        pass

    assert "conocimiento" in closed
    assert "informe_area" in closed


@pytest.mark.parametrize(
    "bad_url",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "data:image/svg+xml,<svg/>",
        "vbscript:msgbox(1)",
        "//evil.example/logo.png",
        "/\\evil.example/logo.png",
        "https://",
    ],
)
def test_branding_logo_url_rejects_unsafe_schemes_and_filters_on_read(
    db: Session,
    bad_url: str,
) -> None:
    import app.domains.settings.service as settings_mod

    settings_mod._invalidate_branding_cache()
    service = SettingsService()

    with pytest.raises(HTTPException) as exc:
        service.update_setting(db, "branding/logo_url", bad_url)
    assert exc.value.status_code == 422

    # Defense-in-depth if a bad scheme already existed in the DB row.
    service.repo.upsert(db, clave="branding/logo_url", valor=bad_url, categoria="branding")
    db.flush()
    settings_mod._invalidate_branding_cache()
    assert service.get_branding(db)["logo_url"] is None


def test_branding_logo_url_accepts_safe_urls_and_upsert_is_audited(db: Session) -> None:
    import app.domains.settings.service as settings_mod

    settings_mod._invalidate_branding_cache()
    service = SettingsService()

    for good in ("/static/logo.png", "https://cdn.example.com/logo.png", ""):
        saved = service.upsert_setting(
            db,
            key="branding/logo_url",
            valor=good,
            categoria="branding",
        )
        assert saved.valor == good

    audits = list(
        db.execute(
            select(AuditLog).where(
                AuditLog.action == "settings.upsert",
                AuditLog.resource == "clave=branding/logo_url",
            )
        ).scalars()
    )
    assert len(audits) == 3


def test_ready_tolerates_redis_fallback_and_fails_on_db_or_alembic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(main_mod.app)
    client.headers.update({"Host": "localhost"})

    monkeypatch.setattr(
        main_mod,
        "run_health_checks",
        AsyncMock(
            return_value={
                "database": {"status": "healthy"},
                "redis": {"status": "unavailable", "message": "Using in-memory fallback"},
                "alembic": {"status": "healthy"},
            }
        ),
    )
    ready_resp = client.get("/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json() == {"status": "ready"}
    assert client.get("/health").json() == {"status": "degraded"}

    for failing_key in ("database", "alembic"):
        services = {
            "database": {"status": "healthy"},
            "redis": {"status": "healthy"},
            "alembic": {"status": "healthy"},
        }
        services[failing_key] = {"status": "unhealthy"}
        monkeypatch.setattr(main_mod, "run_health_checks", AsyncMock(return_value=services))
        bad_resp = client.get("/ready")
        assert bad_resp.status_code == 503
        assert bad_resp.json() == {"status": "not_ready"}


def test_public_elevation_and_sugerencias_enforce_pre_parse_body_caps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_user = SimpleNamespace(
        id=uuid.uuid4(),
        email="vecino@example.com",
        role="ciudadano",
        is_active=True,
    )
    main_mod.app.dependency_overrides[require_authenticated] = lambda: fake_user
    main_mod.app.dependency_overrides[require_admin_or_operator] = lambda: fake_user
    main_mod.app.dependency_overrides[get_db] = lambda: MagicMock()
    monkeypatch.setattr(settings, "public_elevation_max_body_bytes", 64)
    monkeypatch.setattr(settings, "sugerencia_max_body_bytes", 64)

    try:
        client = TestClient(main_mod.app)
        client.headers.update({"Host": "localhost"})
        oversized = (
            b'{"geometry":{"type":"LineString","coordinates":[[-62,-32],[-62,-32.1],[-62,-32.2]]}}'
        )
        assert len(oversized) > 64

        for path in ("/api/v2/public/map/elevation-profile", "/api/v2/sugerencias"):
            resp = client.post(
                path,
                content=oversized,
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code == 413, f"{path}: {resp.text}"

            # Streaming request without Content-Length triggers chunk counter before body parse.
            chunked_resp = client.post(
                path,
                content=(oversized[i : i + 16] for i in range(0, len(oversized), 16)),
                headers={"Content-Type": "application/json"},
            )
            assert chunked_resp.status_code == 413, f"{path} chunked: {chunked_resp.text}"
    finally:
        main_mod.app.dependency_overrides.clear()
