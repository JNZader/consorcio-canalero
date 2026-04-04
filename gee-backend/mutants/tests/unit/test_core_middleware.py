"""Unit tests for app.core.middleware — rate limiting, CSRF, security headers, logging."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.middleware import (
    CSRFProtectionMiddleware,
    DistributedRateLimitMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    _extract_user_id_from_token,
)


# ── _extract_user_id_from_token ───────────────────


class TestExtractUserIdFromToken:
    """Tests for JWT sub claim extraction helper."""

    def test_returns_none_when_no_header(self):
        assert _extract_user_id_from_token(None) is None

    def test_returns_none_when_empty_string(self):
        assert _extract_user_id_from_token("") is None

    def test_returns_none_when_not_bearer(self):
        assert _extract_user_id_from_token("Basic abc123") is None

    @patch("app.core.middleware.jwt")
    @patch("app.core.middleware.settings")
    def test_returns_sub_from_valid_token(self, mock_settings, mock_jwt):
        mock_settings.jwt_secret = "secret"
        mock_jwt.decode.return_value = {"sub": "user-uuid-123"}
        result = _extract_user_id_from_token("Bearer valid.token.here")
        assert result == "user-uuid-123"
        mock_jwt.decode.assert_called_once_with(
            "valid.token.here",
            "secret",
            algorithms=["HS256"],
            options={"verify_exp": True},
        )

    @patch("app.core.middleware.jwt")
    @patch("app.core.middleware.settings")
    def test_returns_none_when_sub_missing(self, mock_settings, mock_jwt):
        mock_settings.jwt_secret = "secret"
        mock_jwt.decode.return_value = {"aud": "something"}
        assert _extract_user_id_from_token("Bearer no.sub.token") is None

    @patch("app.core.middleware.jwt")
    @patch("app.core.middleware.settings")
    def test_returns_none_when_sub_empty(self, mock_settings, mock_jwt):
        mock_settings.jwt_secret = "secret"
        mock_jwt.decode.return_value = {"sub": ""}
        assert _extract_user_id_from_token("Bearer empty.sub.token") is None

    @patch("app.core.middleware.jwt")
    @patch("app.core.middleware.settings")
    def test_returns_none_on_jwt_error(self, mock_settings, mock_jwt):
        from jose import JWTError

        mock_settings.jwt_secret = "secret"
        mock_jwt.decode.side_effect = JWTError("expired")
        assert _extract_user_id_from_token("Bearer expired.token") is None


# ── SecurityHeadersMiddleware ─────────────────────


def _make_app_with_middleware(*middleware_classes_and_args):
    """Helper: build a minimal FastAPI app with the given middleware stack."""
    app = FastAPI()

    @app.get("/test")
    def _test_endpoint():
        return {"ok": True}

    @app.get("/health")
    def _health():
        return {"status": "ok"}

    @app.get("/")
    def _root():
        return {"root": True}

    @app.post("/api/v2/data")
    def _post_data():
        return {"created": True}

    @app.post("/api/v2/auth/login")
    def _login():
        return {"token": "abc"}

    @app.post("/api/v2/public/upload-photo")
    def _upload():
        return {"uploaded": True}

    for item in middleware_classes_and_args:
        if isinstance(item, tuple):
            cls, kwargs = item
            app.add_middleware(cls, **kwargs)
        else:
            app.add_middleware(item)

    return app


class TestSecurityHeadersMiddleware:
    """Verify security headers are injected in every response."""

    def setup_method(self):
        app = _make_app_with_middleware(SecurityHeadersMiddleware)
        self.client = TestClient(app)

    def test_x_content_type_options(self):
        resp = self.client.get("/test")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options(self):
        resp = self.client.get("/test")
        assert resp.headers["X-Frame-Options"] == "DENY"

    def test_x_xss_protection(self):
        resp = self.client.get("/test")
        assert resp.headers["X-XSS-Protection"] == "1; mode=block"

    def test_referrer_policy(self):
        resp = self.client.get("/test")
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


# ── CSRFProtectionMiddleware ──────────────────────


class TestCSRFProtectionMiddleware:
    """Verify CSRF origin/content-type validation."""

    def setup_method(self):
        app = _make_app_with_middleware(CSRFProtectionMiddleware)
        self.client = TestClient(app)

    def test_get_requests_pass_through(self):
        resp = self.client.get("/test")
        assert resp.status_code == 200

    def test_health_exempt(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200

    def test_root_exempt_for_post(self):
        # POST to root should be exempt from CSRF
        resp = self.client.post("/")
        # FastAPI returns 405 for POST on a GET-only route, but CSRF won't block it
        assert resp.status_code in (200, 405)

    @patch("app.core.middleware.settings")
    def test_blocks_invalid_origin(self, mock_settings):
        mock_settings.cors_origins_list = ["http://allowed.com"]
        app = _make_app_with_middleware(CSRFProtectionMiddleware)
        client = TestClient(app)
        resp = client.post(
            "/api/v2/data",
            headers={
                "origin": "http://evil.com",
                "content-type": "application/json",
            },
            json={},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "CSRF_INVALID_ORIGIN"

    def test_blocks_invalid_content_type(self):
        resp = self.client.post(
            "/api/v2/data",
            headers={"content-type": "text/plain"},
            content="hello",
        )
        assert resp.status_code == 415
        assert resp.json()["error"]["code"] == "INVALID_CONTENT_TYPE"

    def test_allows_json_content_type(self):
        resp = self.client.post(
            "/api/v2/data",
            headers={"content-type": "application/json"},
            json={"key": "value"},
        )
        assert resp.status_code == 200

    def test_allows_multipart(self):
        resp = self.client.post(
            "/api/v2/data",
            headers={"content-type": "multipart/form-data; boundary=---"},
            content=b"data",
        )
        assert resp.status_code == 200

    def test_auth_paths_exempt(self):
        resp = self.client.post(
            "/api/v2/auth/login",
            headers={"content-type": "text/plain"},
            content="whatever",
        )
        # Should NOT be blocked by CSRF — auth paths are exempt
        assert resp.status_code != 403
        assert resp.status_code != 415

    def test_upload_path_exempt_from_content_type_check(self):
        resp = self.client.post(
            "/api/v2/public/upload-photo",
            content=b"binary-data",
        )
        # Upload paths skip content-type enforcement
        assert resp.status_code != 415


# ── RequestLoggingMiddleware ──────────────────────


class TestRequestLoggingMiddleware:
    """Verify request logging skips health/root and logs others."""

    def setup_method(self):
        app = _make_app_with_middleware(RequestLoggingMiddleware)
        self.client = TestClient(app)

    @patch("app.core.middleware.logger")
    def test_skips_health_endpoint(self, mock_logger):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        # Should NOT have logged "Request started" for health
        for call in mock_logger.info.call_args_list:
            assert "Request started" not in str(call)

    @patch("app.core.middleware.logger")
    def test_skips_root_endpoint(self, mock_logger):
        self.client.get("/")
        for call in mock_logger.info.call_args_list:
            assert "Request started" not in str(call)

    @patch("app.core.middleware.logger")
    def test_logs_normal_request(self, mock_logger):
        self.client.get("/test")
        logged_messages = [str(c) for c in mock_logger.info.call_args_list]
        assert any("Request started" in m for m in logged_messages)
        assert any("Request completed" in m for m in logged_messages)


# ── DistributedRateLimitMiddleware ────────────────


class TestDistributedRateLimitMiddleware:
    """Verify rate limit middleware behavior (skip paths, headers, 429)."""

    def _make_rate_limited_app(self, limiter_mock):
        app = FastAPI()

        @app.get("/test")
        def _test():
            return {"ok": True}

        @app.get("/health")
        def _health():
            return {"status": "ok"}

        @app.get("/")
        def _root():
            return {"root": True}

        @app.get("/tiles/1/2/3/4.png")
        def _tile():
            return {"tile": True}

        app.add_middleware(DistributedRateLimitMiddleware, rate_limiter=limiter_mock)
        return TestClient(app)

    def test_skips_health_check(self):
        limiter = AsyncMock()
        client = self._make_rate_limited_app(limiter)
        resp = client.get("/health")
        assert resp.status_code == 200
        limiter.check.assert_not_called()

    def test_skips_root(self):
        limiter = AsyncMock()
        client = self._make_rate_limited_app(limiter)
        resp = client.get("/")
        assert resp.status_code == 200
        limiter.check.assert_not_called()

    def test_skips_tile_requests(self):
        limiter = AsyncMock()
        client = self._make_rate_limited_app(limiter)
        resp = client.get("/tiles/1/2/3/4.png")
        assert resp.status_code == 200
        limiter.check.assert_not_called()

    def test_allowed_request_adds_headers(self):
        limiter = AsyncMock()
        limiter.check.return_value = (True, 99, 60)
        limiter.max_requests = 100
        client = self._make_rate_limited_app(limiter)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "100"
        assert resp.headers["X-RateLimit-Remaining"] == "99"

    def test_blocked_request_returns_429(self):
        limiter = AsyncMock()
        limiter.check.return_value = (False, 0, 30)
        limiter.max_requests = 100
        client = self._make_rate_limited_app(limiter)
        resp = client.get("/test")
        assert resp.status_code == 429
        body = resp.json()
        assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert resp.headers["Retry-After"] == "30"
