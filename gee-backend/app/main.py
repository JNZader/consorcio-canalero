"""
Main entry point for FastAPI application.
Consorcio Canalero GEE Backend.
"""

import uuid
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from app.config import settings
from app.api.v1.router import api_router
from app.services.gee_service import initialize_gee
from app.core.logging import (
    get_logger,
    configure_structlog,
    RequestIdMiddleware,
)
from app.core.exceptions import AppException, RateLimitExceededError
from app.core.rate_limit import get_rate_limiter, DistributedRateLimiter

# Application version constant (used in FastAPI init, root, and health endpoints)
APP_VERSION = "1.0.0"

# Configure logging based on environment
configure_structlog(
    json_format=not settings.debug,
    log_level="DEBUG" if settings.debug else "INFO",
)

logger = get_logger(__name__)


class DistributedRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using distributed rate limiter with Redis."""

    def __init__(self, app, rate_limiter: DistributedRateLimiter):
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ["/", "/health"]:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        allowed, remaining, reset_time = await self.rate_limiter.check(client_ip)

        if not allowed:
            logger.warning(
                "Rate limit exceeded",
                client_ip=client_ip,
                path=request.url.path,
                remaining=remaining,
                reset_time=reset_time,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Demasiadas solicitudes. Intenta de nuevo mas tarde.",
                        "details": {
                            "retry_after": reset_time,
                            "limit": self.rate_limiter.max_requests,
                        },
                    }
                },
                headers={
                    "Retry-After": str(reset_time),
                    "X-RateLimit-Limit": str(self.rate_limiter.max_requests),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(reset_time),
                },
            )

        response = await call_next(request)

        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(self.rate_limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection for state-changing requests.

    For REST APIs, we protect against CSRF by:
    1. Requiring JSON Content-Type for POST/PUT/DELETE (forms can't send JSON)
    2. Validating Origin header matches allowed domains

    This protects public endpoints that don't require authentication.
    """

    # Paths that should skip CSRF check (webhooks from external services)
    CSRF_EXEMPT_PATHS: list[str] = []

    # Explicit upload paths that accept multipart/form-data without JSON content-type
    UPLOAD_PATHS: set[str] = {"/api/v1/public/upload-photo", "/api/v1/layers/upload"}

    async def dispatch(self, request: Request, call_next):
        # Only check state-changing methods
        if request.method not in ["POST", "PUT", "DELETE", "PATCH"]:
            return await call_next(request)

        # Skip CSRF check for exempt paths
        if any(request.url.path.startswith(path) for path in self.CSRF_EXEMPT_PATHS):
            return await call_next(request)

        # Skip CSRF check for health endpoints
        if request.url.path in ["/", "/health"]:
            return await call_next(request)

        # Check Origin header
        origin = request.headers.get("origin")
        if origin:
            # Validate origin is in allowed list
            if origin not in settings.cors_origins_list:
                logger.warning(
                    "CSRF: Invalid origin",
                    origin=origin,
                    path=request.url.path,
                    allowed=settings.cors_origins_list,
                )
                return JSONResponse(
                    status_code=403,
                    content={"error": {"code": "CSRF_INVALID_ORIGIN", "message": "Origin not allowed"}},
                )

        # For non-file-upload requests, verify JSON content type
        content_type = request.headers.get("content-type", "")
        is_multipart = "multipart/form-data" in content_type
        is_json = "application/json" in content_type

        # Allow multipart for file uploads, but require JSON for other requests
        if not is_multipart and not is_json:
            # Skip for explicitly listed upload endpoints
            if request.url.path not in self.UPLOAD_PATHS:
                logger.warning(
                    "CSRF: Invalid content type",
                    content_type=content_type,
                    path=request.url.path,
                )
                return JSONResponse(
                    status_code=415,
                    content={"error": {"code": "INVALID_CONTENT_TYPE", "message": "Content-Type must be application/json"}},
                )

        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all incoming requests and their responses."""

    async def dispatch(self, request: Request, call_next):
        import time

        # Skip logging for health checks to reduce noise
        if request.url.path in ["/", "/health"]:
            return await call_next(request)

        start_time = time.time()

        # Log request
        logger.info(
            "Request started",
            method=request.method,
            path=request.url.path,
            query=str(request.query_params),
            client_ip=request.client.host if request.client else "unknown",
        )

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            # Log response
            logger.info(
                "Request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(process_time * 1000, 2),
            )

            return response
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                "Request failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration_ms=round(process_time * 1000, 2),
            )
            raise


async def check_supabase_health() -> Dict[str, Any]:
    """Check Supabase connection health."""
    try:
        from app.services.supabase_service import get_supabase_service

        db = get_supabase_service()
        # Simple query to test connection
        result = db.client.table("capas").select("id").limit(1).execute()
        return {"status": "healthy", "latency_ms": None}
    except Exception as e:
        logger.error("Supabase health check failed", error=str(e))
        return {"status": "unhealthy", "error": str(e)}


async def check_redis_health() -> Dict[str, Any]:
    """Check Redis connection health."""
    try:
        rate_limiter = get_rate_limiter()
        redis_client = await rate_limiter._get_redis()

        if redis_client:
            import time

            start = time.time()
            await redis_client.ping()
            latency = round((time.time() - start) * 1000, 2)
            return {"status": "healthy", "latency_ms": latency}
        else:
            return {"status": "unavailable", "message": "Using in-memory fallback"}
    except Exception as e:
        logger.error("Redis health check failed", error=str(e))
        return {"status": "unhealthy", "error": str(e)}


async def check_gee_health() -> Dict[str, Any]:
    """Check Google Earth Engine connection health."""
    try:
        from app.services.gee_service import _gee_initialized

        # Check if initialized using our global flag
        if _gee_initialized:
            return {"status": "healthy", "project": settings.gee_project_id}
        else:
            return {"status": "not_initialized"}
    except Exception as e:
        logger.error("GEE health check failed", error=str(e))
        return {"status": "unhealthy", "error": str(e)}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager - initialize services on startup."""
    # Initialize Google Earth Engine
    logger.info("Initializing Google Earth Engine...")
    try:
        initialize_gee()
        logger.info("GEE initialized successfully", project=settings.gee_project_id)
    except Exception as e:
        logger.warning(
            "GEE initialization failed",
            error=str(e),
            message="GEE features will not be available",
        )

    # Initialize rate limiter (tests Redis connection)
    logger.info("Initializing rate limiter...")
    try:
        rate_limiter = get_rate_limiter()
        await rate_limiter._get_redis()
        logger.info("Rate limiter initialized")
    except Exception as e:
        logger.warning(
            "Rate limiter Redis connection failed",
            error=str(e),
            message="Using in-memory rate limiting",
        )

    yield

    # Cleanup on shutdown
    logger.info("Shutting down...")

    # Close rate limiter Redis connection
    try:
        rate_limiter = get_rate_limiter()
        await rate_limiter.close()
    except Exception as e:
        logger.warning("Error closing rate limiter", error=str(e))

    logger.info("Shutdown complete")


app = FastAPI(
    title="Consorcio Canalero API",
    description="API para gestion de analisis satelital y denuncias del Consorcio Canalero 10 de Mayo",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)


# ===========================================
# EXCEPTION HANDLERS
# ===========================================


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handle all application-specific exceptions."""
    logger.warning(
        "Application exception",
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        path=request.url.path,
        details=exc.details,
    )

    response = JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )

    # Add Retry-After header for rate limit errors
    if isinstance(exc, RateLimitExceededError):
        response.headers["Retry-After"] = str(exc.retry_after)

    return response


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.exception(
        "Unhandled exception",
        error=str(exc),
        error_type=type(exc).__name__,
        path=request.url.path,
    )

    # Don't expose internal error details in production
    if settings.debug:
        detail = str(exc)
    else:
        detail = "Error interno del servidor"

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": detail,
                "details": {},
            }
        },
    )


# ===========================================
# MIDDLEWARE (order matters - last added is first executed)
# ===========================================

# Request ID middleware (for tracing)
app.add_middleware(RequestIdMiddleware)

# Request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# CSRF protection for state-changing requests
app.add_middleware(CSRFProtectionMiddleware)

# Rate limiting (using distributed rate limiter)
app.add_middleware(DistributedRateLimitMiddleware, rate_limiter=get_rate_limiter())

# GZip compression for responses > 500 bytes
app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS middleware with restricted settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    expose_headers=["X-Total-Count", "X-Page", "X-Per-Page", "X-Request-Id"],
    max_age=600,
)

# Include API router
app.include_router(api_router, prefix=settings.api_prefix)


# ===========================================
# HEALTH CHECK ENDPOINTS
# ===========================================


@app.get("/")
async def root():
    """Basic health check endpoint."""
    return {
        "status": "ok",
        "service": "Consorcio Canalero GEE Backend",
        "version": APP_VERSION,
    }


@app.get("/health")
async def health():
    """
    Detailed health check for deployment platforms.

    Checks connectivity to all external services:
    - Supabase (database)
    - Redis (rate limiting/caching)
    - Google Earth Engine (satellite analysis)
    """
    # Run all health checks
    supabase_health = await check_supabase_health()
    redis_health = await check_redis_health()
    gee_health = await check_gee_health()

    # Determine overall status
    services = {
        "supabase": supabase_health,
        "redis": redis_health,
        "gee": gee_health,
    }

    # Supabase is critical, Redis and GEE are optional
    is_healthy = supabase_health["status"] == "healthy"

    return {
        "status": "healthy" if is_healthy else "degraded",
        "services": services,
        "version": APP_VERSION,
    }


if __name__ == "__main__":
    import uvicorn

    logger.info(
        "Starting server",
        host="0.0.0.0",
        port=8000,
        debug=settings.debug,
    )

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
