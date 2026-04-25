"""
Main entry point for FastAPI application.
Consorcio Canalero Backend — v2.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
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

    yield

    # Cleanup
    logger.info("Shutting down...")
    try:
        rate_limiter = get_rate_limiter()
        await rate_limiter.close()
    except Exception as e:
        logger.warning("Error closing rate limiter", error=str(e))
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
    max_age=600,
)

# ===========================================
# ROUTERS
# ===========================================

app.include_router(api_v2_router, prefix="/api/v2")


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
