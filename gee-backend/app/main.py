"""
Main entry point for FastAPI application.
Consorcio Canalero Backend — v2.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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
from app.core.rate_limit import get_rate_limiter
from app.core.health import (
    check_alembic_health,
    check_database_health,
    check_gee_health,
    check_redis_health,
)

APP_VERSION = "2.0.0"

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
app.add_middleware(DistributedRateLimitMiddleware, rate_limiter=get_rate_limiter())
app.add_middleware(GZipMiddleware, minimum_size=500)
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
# STATIC FILES (citizen photo uploads)
# ===========================================
# `LocalPhotoStorage` writes to `settings.uploads_root` (default `/app/uploads`,
# mounted as the `denuncia-uploads` Docker volume in compose). The matching
# StaticFiles mount serves them back at `settings.uploads_public_base`
# (default `/uploads`). When swapping to S3/MinIO, this mount becomes
# unnecessary — drop it together with `LocalPhotoStorage`.
os.makedirs(settings.uploads_root, exist_ok=True)
app.mount(
    settings.uploads_public_base,
    StaticFiles(directory=settings.uploads_root),
    name="uploads",
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


@app.get("/health")
async def health():
    db_health = await check_database_health()
    redis_health = await check_redis_health()
    gee_health = await check_gee_health()
    alembic_health = await check_alembic_health()

    services = {
        "database": db_health,
        "redis": redis_health,
        "gee": gee_health,
        "alembic": alembic_health,
    }

    is_healthy = (
        db_health["status"] == "healthy"
        and redis_health["status"] == "healthy"
        and alembic_health["status"] == "healthy"
    )

    return {
        "status": "healthy" if is_healthy else "degraded",
        "services": services,
        "version": APP_VERSION,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.debug)
