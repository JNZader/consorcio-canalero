"""
Main entry point for FastAPI application.
Consorcio Canalero Backend — v2.
"""

# Sentry MUST initialise before ``app.config`` runs the prod fail-fast,
# so a misconfigured boot crash is still reported. The bootstrap reads
# SENTRY_DSN straight from the env and is a no-op when unset.
import app._sentry_bootstrap  # noqa: F401 — import-side-effect only

import asyncio
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.v2.router import api_router as api_v2_router
from app.core.logging import (
    get_logger,
    configure_structlog,
    RequestIdMiddleware,
)
from app.core.exceptions import AppException, RateLimitExceededError
from app.core.middleware import (
    DistributedRateLimitMiddleware,
    SecurityHeadersMiddleware,
    CSRFProtectionMiddleware,
    RequestLoggingMiddleware,
)
from app.core.rate_limit import get_auth_rate_limiter, get_rate_limiter
from app.core.health import (
    check_alembic_health,
    check_database_health,
    check_gee_health,
    check_redis_health,
)

APP_VERSION = "2.0.0"


def _admin_dep():
    """Lazy ``require_admin_or_operator`` import to avoid a circular dep
    between ``app.main`` and ``app.auth``.
    """
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _authenticated_dep():
    """Lazy ``require_authenticated`` import — any logged-in user."""
    from app.auth import require_authenticated

    return require_authenticated


configure_structlog(
    json_format=not settings.debug,
    log_level="DEBUG" if settings.debug else "INFO",
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager — initialize services on startup."""
    logger.info("Starting Consorcio Canalero Backend v2...")

    # Initialize rate limiter (tests Redis connection)
    try:
        rate_limiter = get_rate_limiter()
        await rate_limiter._get_redis()
        logger.info("Rate limiter initialized")
    except Exception as e:
        logger.warning("Rate limiter Redis failed, using in-memory", error=str(e))

    # Pre-initialize Earth Engine so the first user request does not pay the
    # 2-5 s OAuth handshake. Runs in a thread executor (sync ee.Initialize is
    # blocking) and must NOT abort startup — if GEE auth is broken, endpoints
    # that need it surface 503 individually instead of taking the API down.
    try:
        from app.domains.geo.gee_service import ensure_initialized_async

        await ensure_initialized_async()
        logger.info("Earth Engine pre-initialized")
    except Exception as e:
        logger.warning("Earth Engine pre-init failed", error=str(e))

    # Pre-warm the slow GEE layer endpoints so the first user doesn't pay
    # the cold-cache cost (~30 s to 2 min). The task is queued with a small
    # countdown so the backend is listening on :8000 before the worker
    # starts hitting it. Failures here MUST NOT block startup — if the
    # broker is unreachable we just skip warming.
    if os.getenv("DISABLE_GEE_CACHE_WARMING", "").lower() not in ("1", "true", "yes"):
        try:
            from app.domains.geo.gee_tasks_warming import task_warm_gee_layers

            task_warm_gee_layers.apply_async(countdown=10)
            logger.info("Queued GEE cache warming task (countdown=10s)")
        except Exception as e:
            logger.warning("Could not queue cache warming task", error=str(e))

    yield

    # Cleanup
    logger.info("Shutting down...")
    try:
        rate_limiter = get_rate_limiter()
        await rate_limiter.close()
    except Exception as e:
        logger.warning("Error closing rate limiter", error=str(e))
    try:
        await get_auth_rate_limiter().close()
    except Exception as e:
        logger.warning("Error closing auth rate limiter", error=str(e))
    try:
        from app.core.cache import get_cache

        await get_cache().close()
    except Exception as e:
        logger.warning("Error closing JSON cache", error=str(e))
    logger.info("Shutdown complete")


app = FastAPI(
    title="Consorcio Canalero API",
    description="API para gestion territorial y operativa de consorcios canaleros",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
)


# ===========================================
# EXCEPTION HANDLERS
# ===========================================


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    logger.warning(
        "Application exception",
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        path=request.url.path,
    )
    response = JSONResponse(status_code=exc.status_code, content=exc.to_dict())
    if isinstance(exc, RateLimitExceededError):
        response.headers["Retry-After"] = str(exc.retry_after)
    return response


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception", error=str(exc), path=request.url.path)
    detail = str(exc) if settings.debug else "Error interno del servidor"
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": detail, "details": {}}},
    )


# ===========================================
# MIDDLEWARE (last added = first executed)
# ===========================================

app.add_middleware(RequestIdMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFProtectionMiddleware)
app.add_middleware(
    DistributedRateLimitMiddleware,
    rate_limiter=get_rate_limiter(),
    # Strict brute-force throttle for login / forgot-password /
    # exchange-code (see AUTH_THROTTLE_PATHS in app/core/middleware.py).
    auth_rate_limiter=get_auth_rate_limiter(),
)
app.add_middleware(GZipMiddleware, minimum_size=500)
# Host-header validation — derived from CORS_ORIGINS + API_BASE_URL + the
# loopback aliases the Docker healthcheck uses. Refuses requests whose
# ``Host`` header doesn't match any allowed name, which closes URL-
# rewriting / cookie-scoping attacks based on a forged Host. Only added
# when we actually have a host list (dev with default settings would
# block /live calls from inside docker if we weren't careful, but the
# loopback aliases above prevent that).
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    expose_headers=["X-Total-Count", "X-Page", "X-Per-Page", "X-Request-Id"],
    # 24h preflight cache — the map page fires ~25 cross-origin requests on
    # every navigation; with max_age=600 the browser kept re-issuing OPTIONS
    # preflights that cost 800 ms (warm) to 8 s (cold) each.
    max_age=86400,
)

# ===========================================
# ROUTERS
# ===========================================

app.include_router(api_v2_router, prefix="/api/v2")


# ===========================================
# CITIZEN PHOTO UPLOADS — authenticated download endpoint
# ===========================================
# ``LocalPhotoStorage`` writes to ``settings.uploads_root`` (default
# ``/app/uploads``, mounted as the ``denuncia-uploads`` Docker volume).
#
# Previously this directory was served by a public StaticFiles mount —
# any client with the URL could fetch any denuncia photo, including
# operators' phone numbers / faces / license plates that citizens
# included in the report. We now require auth + ownership / operator
# role to download a denuncia photo (Phase 2 / item F2-F).
#
# When swapping to S3/MinIO, this endpoint becomes unnecessary — drop
# it together with ``LocalPhotoStorage`` and switch the frontend to
# signed URLs the storage backend mints.
os.makedirs(settings.uploads_root, exist_ok=True)


_DENUNCIA_FILENAME_RE = re.compile(
    r"^(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"\.(?:jpg|jpeg|png|webp)$",
    re.IGNORECASE,
)


@app.get(
    f"{settings.uploads_public_base}/denuncias/{{filename}}",
    response_class=Response,
    include_in_schema=False,
)
async def get_denuncia_photo(
    filename: str,
    request: Request,
    user=Depends(_authenticated_dep()),
):
    """Serve a denuncia photo to the owner or any operator+.

    Returns 404 (not 403) when the caller isn't authorised, so the
    endpoint doesn't leak whether the file exists.
    """
    import uuid as _uuid

    from sqlalchemy.orm import Session as _Session

    from app.db.session import get_db as _get_db
    from app.domains.denuncias.models import Denuncia
    from app.auth.models import UserRole

    match = _DENUNCIA_FILENAME_RE.match(filename)
    if match is None:
        # Either an attempt at path traversal or just a bad URL — both
        # respond 404 so the surface stays uniform.
        return Response(status_code=404)
    denuncia_id = _uuid.UUID(match.group("uuid"))
    # On-disk filenames are always lowercase (storage normalises via
    # ``uuid.UUID(...)`` before writing). The route regex is
    # case-insensitive so the auth check still works for an uppercased
    # URL — but the disk lookup would 404 without this normalisation.
    filename = filename.lower()

    # We need a DB session here but the dependency tree above didn't
    # give us one. Open a short-lived session manually rather than
    # leaning on a request-scoped one — this endpoint is hit once per
    # photo render, no need for the full Depends machinery.
    db_gen = _get_db()
    db: _Session = next(db_gen)
    try:
        denuncia = db.get(Denuncia, denuncia_id)
        if denuncia is None:
            return Response(status_code=404)
        is_operator = getattr(user, "role", None) in {UserRole.ADMIN, UserRole.OPERADOR}
        is_owner = denuncia.user_id is not None and str(denuncia.user_id) == str(
            getattr(user, "id", None)
        )
        if not (is_operator or is_owner):
            return Response(status_code=404)
    finally:
        db_gen.close()

    photo_path = Path(settings.uploads_root) / "denuncias" / filename
    if not photo_path.is_file():
        return Response(status_code=404)

    # Map extension → content type. ``image/webp`` is the only one
    # the FastAPI/uvicorn default doesn't infer reliably.
    ext = photo_path.suffix.lower().lstrip(".")
    media_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }.get(ext, "application/octet-stream")

    # Read on a worker thread so the 10 MB blocking I/O doesn't stall
    # the asyncio event loop. Bounded at MAX_PHOTO_BYTES on the write
    # path, so a single allocation is safe.
    content = await asyncio.to_thread(photo_path.read_bytes)
    return Response(
        content=content,
        media_type=media_type,
        headers={
            # Photos are immutable once uploaded — cache aggressively
            # but require revalidation when the client is offline.
            "Cache-Control": "private, max-age=3600, must-revalidate",
        },
    )


# ===========================================
# HEALTH CHECKS
# ===========================================


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "Consorcio Canalero Backend",
        "version": APP_VERSION,
    }


@app.get("/live")
async def live():
    """Liveness probe — process is up and the event loop is responsive.

    Intentionally does NOT touch DB, Redis, or GEE. A transient outage in
    a downstream dependency must NOT cause Docker / Kubernetes to kill
    and restart this container, because killing the app makes the outage
    worse. Use ``/ready`` for "is this instance OK to take traffic".
    """
    return {"status": "ok", "version": APP_VERSION}


@app.get("/ready")
async def ready(response: Response):
    """Public readiness probe — minimal body, just ready/not_ready.

    Returns 503 when a critical dependency (DB, Redis, Alembic) is
    degraded so a load balancer can drain this instance. We deliberately
    DO NOT expose which dependency is degraded, because the detailed
    services block previously published here (PostGIS version, Alembic
    revision SHA, GCP project id) gives an unauthenticated attacker
    fingerprinting information. Operators who need the breakdown should
    hit ``/admin/ready/detailed`` (operator+ auth required).
    """
    db_health = await check_database_health()
    redis_health = await check_redis_health()
    alembic_health = await check_alembic_health()

    critical_ok = (
        db_health["status"] == "healthy"
        and redis_health["status"] == "healthy"
        and alembic_health["status"] == "healthy"
    )

    if not critical_ok:
        response.status_code = 503

    return {"status": "ready" if critical_ok else "not_ready"}


@app.get("/health")
async def health():
    """Legacy combined endpoint — kept for external monitors that hit it.

    Always returns HTTP 200; degradation is signalled in the ``status``
    field of the body. New consumers should pick ``/live`` (liveness) or
    ``/ready`` (readiness) explicitly. The detailed services breakdown
    that used to live here is now under ``/admin/ready/detailed`` behind
    operator auth (it leaked PostGIS version + Alembic SHA + GCP project
    id to unauthenticated callers).
    """
    db_health = await check_database_health()
    redis_health = await check_redis_health()
    alembic_health = await check_alembic_health()

    is_healthy = (
        db_health["status"] == "healthy"
        and redis_health["status"] == "healthy"
        and alembic_health["status"] == "healthy"
    )

    return {"status": "healthy" if is_healthy else "degraded"}


@app.get("/admin/ready/detailed", tags=["admin"])
async def ready_detailed(
    _user=Depends(_admin_dep()),
):
    """Operator-authenticated readiness with per-service breakdown.

    Returns the same dict the public ``/ready`` used to expose, including
    PostGIS version, Alembic revision SHA, GCP project id, and any error
    strings from health probes. Gated behind ``require_admin_or_operator``
    because that information is useful for debugging but actively useful
    to an attacker doing reconnaissance.
    """
    db_health = await check_database_health()
    redis_health = await check_redis_health()
    gee_health = await check_gee_health()
    alembic_health = await check_alembic_health()
    return {
        "services": {
            "database": db_health,
            "redis": redis_health,
            "gee": gee_health,
            "alembic": alembic_health,
        },
        "version": APP_VERSION,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.debug)
