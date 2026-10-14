"""Application middleware — rate limiting, security, CSRF, logging."""

import hashlib
import re
import time
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
import jwt
from jwt import PyJWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import DistributedRateLimiter, get_auth_rate_limiter

logger = get_logger(__name__)

# Tile traffic is high-volume and stays outside the generic budget, but only
# the real tile URLs. A substring match on ``/tiles/`` also exempted
# ``/api/v2/geo/layers/tiles/sentinel2`` and any future path that merely
# contains the fragment (BE-02).
_TILE_RATE_LIMIT_EXEMPT = (
    re.compile(r"^/tiles/[^/]+/\d+/\d+/\d+\.png$"),
    re.compile(r"^/api/v2/geo/layers/[^/]+/tiles/\d+/\d+/\d+\.png$"),
)


def _is_tile_request(path: str) -> bool:
    return any(pattern.fullmatch(path) for pattern in _TILE_RATE_LIMIT_EXEMPT)


def _etag_for_body(body: bytes) -> str:
    return f'"{hashlib.sha256(body).hexdigest()}"'


def _if_none_match_hits(header: Optional[str], etag: str) -> bool:
    if not header:
        return False
    for token in header.split(","):
        candidate = token.strip()
        if candidate.startswith("W/"):
            candidate = candidate[2:].strip()
        if candidate == "*" or candidate == etag:
            return True
    return False


async def _apply_public_map_cache(request: Request, response: Response) -> Response:
    """Cache-Control plus a strong ETag so a repeat GET can answer 304 (BE-01).

    ``BaseHTTPMiddleware`` hands back a streaming response whose ``.body`` is
    empty. The bytes are read from the iterator and the response is rebuilt.
    """
    cache_control = response.headers.get("cache-control")
    if not cache_control:
        cache_control = DistributedRateLimitMiddleware.PUBLIC_MAP_GET_CACHE_CONTROL
        response.headers["Cache-Control"] = cache_control

    etag = response.headers.get("etag")
    body: bytes | None = None
    if not etag:
        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                chunk = chunk.encode(getattr(response, "charset", None) or "utf-8")
            chunks.append(chunk)
        body = b"".join(chunks)
        if not body:
            empty = Response(
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
                background=response.background,
            )
            return empty
        etag = _etag_for_body(body)
        response.headers["ETag"] = etag

    if _if_none_match_hits(request.headers.get("if-none-match"), etag):
        not_modified = Response(status_code=304, background=response.background)
        not_modified.headers["ETag"] = etag
        not_modified.headers["Cache-Control"] = cache_control
        return not_modified

    if body is None:
        return response

    return Response(
        content=body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
        background=response.background,
    )


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
        user_id = payload.get("sub")
        return user_id if isinstance(user_id, str) and user_id else None
    except PyJWTError:
        return None


class DistributedRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using distributed rate limiter with Redis.

    Two tiers, same sliding-window infrastructure:

    - Generic tier: ``rate_limiter`` (default 100 req / 60 s per client)
      applies to every non-exempt path.
    - Auth brute-force tier: paths in ``AUTH_THROTTLE_PATHS`` are checked
      against the much stricter ``auth_rate_limiter`` (default
      10 req / 60 s) INSTEAD of the generic one. These endpoints are
      credential/code-guessing surfaces (login, forgot-password,
      exchange-code); the strict limit is a strict subset of the generic
      one, so swapping the limiter (rather than stacking both) keeps a
      single Redis round-trip per request while still capping abuse.
      The key is always the client IP for these paths — callers are
      unauthenticated, and keying by a (possibly attacker-supplied)
      token would let a bot rotate identities.
    """

    # Exact-match request paths that get the strict auth throttle.
    AUTH_THROTTLE_PATHS: set[str] = {
        "/api/v2/auth/jwt/login",
        "/api/v2/auth/forgot-password",
        "/api/v2/auth/exchange-code",
    }

    # Public /mapa bootstrap GETs. Counting them against 100/60 made the
    # first paint 429 (API-01 / BE-01). Mutations and /users/me still spend.
    # Exact paths — do not skip admin `/geo/gee/layers`.
    PUBLIC_MAP_GET_EXACT: frozenset[str] = frozenset(
        {
            "/api/v2/public/map/gee/zona",
            "/api/v2/public/map/gee/caminos",
            "/api/v2/public/map/gee/current-image",
            "/api/v2/public/map/gee/current-comparison",
            "/api/v2/public/settings/branding",
            "/api/v2/geo/canales/publico",
            "/api/v2/geo/layers/public",
            "/api/v2/geo/basins",
        }
    )
    PUBLIC_MAP_GET_NESTED_PREFIXES: tuple[str, ...] = ("/api/v2/geo/basins/",)
    PUBLIC_MAP_GET_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=60"

    @classmethod
    def _is_public_map_get(cls, method: str, path: str) -> bool:
        if method != "GET":
            return False
        if path in cls.PUBLIC_MAP_GET_EXACT:
            return True
        return path.startswith(cls.PUBLIC_MAP_GET_NESTED_PREFIXES)

    def __init__(
        self,
        app,
        rate_limiter: DistributedRateLimiter,
        auth_rate_limiter: Optional[DistributedRateLimiter] = None,
    ):
        super().__init__(app)
        self.rate_limiter = rate_limiter
        # Optional for backward compatibility with existing call sites /
        # tests that only pass the generic limiter.
        self.auth_rate_limiter = auth_rate_limiter or get_auth_rate_limiter()

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks and tile requests (tiles are high-volume)
        if request.url.path in ["/", "/health", "/live", "/ready", "/metrics"] or _is_tile_request(
            request.url.path
        ):
            return await call_next(request)

        # CORS preflight is not API usage. Counting OPTIONS against the generic
        # 100/60 budget made /mapa + login fail: login 200, then /users/me 429.
        if request.method == "OPTIONS":
            return await call_next(request)

        if self._is_public_map_get(request.method, request.url.path):
            response = await call_next(request)
            return await _apply_public_map_cache(request, response)

        # Skip rate limiting when disabled via settings (local dev / E2E).
        # ``settings.rate_limit_disabled`` is read once at boot from the
        # env var; the production fail-fast check in app/config.py refuses
        # to start if this is truthy outside dev, so reaching this branch
        # in prod is structurally impossible.
        if settings.rate_limit_disabled:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        if request.url.path in self.AUTH_THROTTLE_PATHS:
            # Brute-force tier: strict limiter, always keyed by IP (see
            # class docstring). Separate key namespace via the limiter's
            # own "ratelimit:auth:" prefix.
            limiter = self.auth_rate_limiter
            rate_limit_key = f"ip:{client_ip}"
        else:
            # Generic tier: prefer per-user rate limiting when
            # authenticated; fall back to IP.
            limiter = self.rate_limiter
            user_id = _extract_user_id_from_token(request.headers.get("authorization"))
            rate_limit_key = f"user:{user_id}" if user_id else f"ip:{client_ip}"

        allowed, remaining, reset_time = await limiter.check(rate_limit_key)

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
                    "X-RateLimit-Limit": str(limiter.max_requests),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(reset_time),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    # The only paths that ever return HTML meant to execute scripts: the
    # Swagger/ReDoc UIs, which pull their bundles from a CDN. They exist only
    # while ``settings.enable_docs`` is on, so the exemption is scoped to that
    # flag — with docs off these paths 404 and get the strict policy like
    # everything else.
    DOCS_PATHS: set[str] = {"/docs", "/docs/oauth2-redirect", "/redoc"}

    # The API serves JSON, never a document that should load subresources or
    # be framed. Denying everything by default is the accurate description of
    # that surface, and ``frame-ancestors`` is the modern counterpart of the
    # ``X-Frame-Options: DENY`` above (kept for legacy browsers).
    API_CSP = "default-src 'none'; frame-ancestors 'none'"

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        is_docs_ui = settings.enable_docs and request.url.path in self.DOCS_PATHS
        if not is_docs_ui:
            response.headers["Content-Security-Policy"] = self.API_CSP

        # Keep browser capability exposure low for API responses. The frontend
        # may request geolocation, but the API never needs direct device access.
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # Only emit HSTS when the request reached the public edge over HTTPS.
        # In local/dev and internal container traffic this app often sees HTTP.
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        if request.url.scheme == "https" or forwarded_proto == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        if request.url.path.startswith("/api/v2/auth/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"

        return response


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """CSRF protection: JSON Content-Type + Origin validation."""

    CSRF_EXEMPT_PATHS: list[str] = ["/api/v2/auth/", "/docs", "/openapi.json"]
    # Cookie session mutations. The SPA and the API are cross-site, so the
    # refresh cookie stays SameSite=None; Origin is the CSRF check (BE-03).
    # Login has no cookie yet and stays on the prefix exemption above.
    AUTH_ORIGIN_REQUIRED_PATHS: frozenset[str] = frozenset(
        {
            "/api/v2/auth/jwt/refresh",
            "/api/v2/auth/jwt/logout",
            "/api/v2/auth/jwt/logout-all",
        }
    )
    UPLOAD_PATHS: set[str] = {"/api/v2/public/upload-photo", "/api/v2/capas"}

    def _reject_origin(self, request: Request) -> JSONResponse:
        logger.warning(
            "CSRF: Invalid origin",
            origin=request.headers.get("origin"),
            path=request.url.path,
        )
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "CSRF_INVALID_ORIGIN",
                    "message": "Origin not allowed",
                }
            },
        )

    async def dispatch(self, request: Request, call_next):
        if request.method not in ["POST", "PUT", "DELETE", "PATCH"]:
            return await call_next(request)

        if request.url.path in ["/", "/health", "/live", "/ready", "/metrics"]:
            return await call_next(request)

        if request.url.path in self.AUTH_ORIGIN_REQUIRED_PATHS:
            origin = request.headers.get("origin")
            if not origin or origin not in settings.cors_origins_list:
                return self._reject_origin(request)
            # Refresh and logout may post an empty body. Origin is the check;
            # do not also require application/json.
            return await call_next(request)

        if any(request.url.path.startswith(path) for path in self.CSRF_EXEMPT_PATHS):
            return await call_next(request)

        origin = request.headers.get("origin")
        if origin and origin not in settings.cors_origins_list:
            return self._reject_origin(request)

        content_type = request.headers.get("content-type", "")
        is_multipart = "multipart/form-data" in content_type
        is_json = "application/json" in content_type

        if not is_multipart and not is_json and request.url.path not in self.UPLOAD_PATHS:
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
        if request.url.path in ["/", "/health", "/live", "/ready", "/metrics"]:
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
