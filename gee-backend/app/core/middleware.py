"""Application middleware — rate limiting, security, CSRF, logging."""

import time
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import DistributedRateLimiter

logger = get_logger(__name__)


def _extract_user_id_from_token(authorization: Optional[str]) -> Optional[str]:
    """Extract user ID from a Bearer JWT token without hitting the database.

    Returns the ``sub`` claim (user UUID) on success, or ``None`` if the header
    is missing, malformed, or the token is invalid/expired.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization[len("Bearer ") :]
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
        user_id: Optional[str] = payload.get("sub")
        return user_id if user_id else None
    except JWTError:
        return None


class DistributedRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using distributed rate limiter with Redis."""

    def __init__(self, app, rate_limiter: DistributedRateLimiter):
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks and tile requests (tiles are high-volume)
        if request.url.path in ["/", "/health"] or "/tiles/" in request.url.path:
            return await call_next(request)

        # Skip rate limiting when disabled via env (local dev / E2E)
        import os

        if os.getenv("RATE_LIMIT_DISABLED", "").lower() in ("1", "true", "yes"):
            return await call_next(request)

        # Prefer per-user rate limiting when authenticated; fall back to IP.
        user_id = _extract_user_id_from_token(request.headers.get("authorization"))
        client_ip = request.client.host if request.client else "unknown"
        rate_limit_key = f"user:{user_id}" if user_id else f"ip:{client_ip}"

        allowed, remaining, reset_time = await self.rate_limiter.check(rate_limit_key)

        if not allowed:
            logger.warning(
                "Rate limit exceeded",
                rate_limit_key=rate_limit_key,
                client_ip=client_ip,
                path=request.url.path,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Demasiadas solicitudes. Intenta de nuevo mas tarde.",
                        "details": {"retry_after": reset_time},
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
    """CSRF protection: JSON Content-Type + Origin validation."""

    CSRF_EXEMPT_PATHS: list[str] = ["/api/v2/auth/", "/docs", "/openapi.json"]
    UPLOAD_PATHS: set[str] = {"/api/v2/public/upload-photo", "/api/v2/capas"}

    async def dispatch(self, request: Request, call_next):
        if request.method not in ["POST", "PUT", "DELETE", "PATCH"]:
            return await call_next(request)

        if request.url.path in ["/", "/health"]:
            return await call_next(request)

        if any(request.url.path.startswith(path) for path in self.CSRF_EXEMPT_PATHS):
            return await call_next(request)

        origin = request.headers.get("origin")
        if origin and origin not in settings.cors_origins_list:
            logger.warning("CSRF: Invalid origin", origin=origin, path=request.url.path)
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "CSRF_INVALID_ORIGIN",
                        "message": "Origin not allowed",
                    }
                },
            )

        content_type = request.headers.get("content-type", "")
        is_multipart = "multipart/form-data" in content_type
        is_json = "application/json" in content_type

        if (
            not is_multipart
            and not is_json
            and request.url.path not in self.UPLOAD_PATHS
        ):
            return JSONResponse(
                status_code=415,
                content={
                    "error": {
                        "code": "INVALID_CONTENT_TYPE",
                        "message": "Content-Type must be application/json",
                    }
                },
            )

        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all incoming requests and their responses."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/", "/health"]:
            return await call_next(request)

        start_time = time.time()

        logger.info(
            "Request started",
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
        )

        try:
            response = await call_next(request)
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.info(
                "Request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return response
        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(
                "Request failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration_ms=duration_ms,
            )
            raise
