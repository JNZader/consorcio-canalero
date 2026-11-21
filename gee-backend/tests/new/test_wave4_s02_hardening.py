"""Regression tests for Wave 4 S-02 backend hardening items."""

from __future__ import annotations

import io
import os
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from PIL import Image
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.config import settings
from app.core.middleware import DistributedRateLimitMiddleware
from app.domains.geo import router as geo_router_mod
from app.shared.storage import LocalPhotoStorage


class _RecordingLimiter:
    def __init__(self, max_requests: int) -> None:
        self.max_requests = max_requests
        self.calls: list[str] = []

    async def check(self, key: str) -> tuple[bool, int, int]:
        self.calls.append(key)
        return True, self.max_requests - len(self.calls), 60


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "auth_path",
    [
        "/api/v2/auth/jwt/login",
        "/api/v2/auth/jwt/login-with-refresh",
        "/api/v2/auth/jwt/refresh",
        "/api/v2/auth/jwt/exchange-cookie",
        "/api/v2/auth/forgot-password",
        "/api/v2/auth/reset-password",
        "/api/v2/auth/register",
        "/api/v2/auth/request-verify-token",
        "/api/v2/auth/verify",
        "/api/v2/auth/exchange-code",
    ],
)
async def test_auth_throttle_paths_route_to_auth_limiter(monkeypatch, auth_path: str) -> None:
    monkeypatch.setattr(settings, "rate_limit_disabled", False)
    assert auth_path in DistributedRateLimitMiddleware.AUTH_THROTTLE_PATHS

    generic_limiter = _RecordingLimiter(max_requests=100)
    auth_limiter = _RecordingLimiter(max_requests=10)

    async def ok(_request: Request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route(auth_path, ok, methods=["POST"])])
    app.add_middleware(
        DistributedRateLimitMiddleware,
        rate_limiter=generic_limiter,
        auth_rate_limiter=auth_limiter,
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(auth_path)

    assert resp.status_code == 200
    assert len(auth_limiter.calls) == 1
    assert generic_limiter.calls == []


def test_submit_gee_analysis_forwards_authenticated_user_id() -> None:
    user_id = uuid.uuid4()
    fake_user = SimpleNamespace(id=user_id)
    fake_analisis = SimpleNamespace(id=uuid.uuid4())
    db = MagicMock()
    repo = MagicMock()
    repo.create_analisis.return_value = fake_analisis
    payload = SimpleNamespace(
        tipo="flood",
        parametros={"fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-10"},
    )

    with (
        patch(
            "app.domains.geo.router_misc_support.enqueue_celery_task",
            return_value=SimpleNamespace(id=uuid.uuid4()),
        ),
        patch(
            "app.domains.geo.router_misc_support.try_publish_celery_task",
            return_value=True,
        ),
    ):
        result = geo_router_mod.submit_gee_analysis(
            payload=payload,
            db=db,
            repo=repo,
            user=fake_user,
        )

    assert result is fake_analisis
    assert repo.create_analisis.call_args.kwargs["usuario_id"] == user_id


@pytest.mark.asyncio
async def test_local_photo_storage_save_offloads_atomic_write_and_fsync(
    tmp_path, monkeypatch
) -> None:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color="blue").save(buf, format="PNG")
    upload = StarletteUploadFile(
        file=io.BytesIO(buf.getvalue()),
        filename="canal.png",
        headers=Headers({"content-type": "image/png"}),
    )

    loop_thread_id = threading.get_ident()
    fsync_threads: list[int] = []
    real_fsync = os.fsync

    def tracked_fsync(fd: int) -> None:
        fsync_threads.append(threading.get_ident())
        real_fsync(fd)

    monkeypatch.setattr("app.shared.storage.os.fsync", tracked_fsync)
    storage = LocalPhotoStorage(root=str(tmp_path), public_base="/uploads")

    url = await storage.save(upload, f"denuncias/{uuid.uuid4()}")

    assert url.startswith("/uploads/denuncias/")
    assert len(fsync_threads) >= 2
    assert all(tid != loop_thread_id for tid in fsync_threads)
