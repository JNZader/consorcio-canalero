"""Unit tests for app.main — FastAPI app creation, middleware, and health endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# App structure tests (no HTTP calls needed)
# ---------------------------------------------------------------------------


class TestAppConfiguration:
    def test_app_title(self):
        with patch("app.main.get_rate_limiter", return_value=MagicMock()):
            from app.main import app

            assert app.title == "Consorcio Canalero API"

    def test_app_version(self):
        with patch("app.main.get_rate_limiter", return_value=MagicMock()):
            from app.main import app, APP_VERSION

            assert app.version == APP_VERSION
            assert APP_VERSION == "2.0.0"

    def test_v2_router_is_included(self):
        with patch("app.main.get_rate_limiter", return_value=MagicMock()):
            from app.main import app

            route_paths = [r.path for r in app.routes]
            # The v2 router mounts under /api/v2
            has_v2 = any("/api/v2" in p for p in route_paths)
            assert has_v2, f"No /api/v2 route found in {route_paths}"

    def test_root_endpoint_exists(self):
        with patch("app.main.get_rate_limiter", return_value=MagicMock()):
            from app.main import app

            route_paths = [r.path for r in app.routes]
            assert "/" in route_paths

    def test_health_endpoint_exists(self):
        with patch("app.main.get_rate_limiter", return_value=MagicMock()):
            from app.main import app

            route_paths = [r.path for r in app.routes]
            assert "/health" in route_paths


class TestMiddleware:
    def test_cors_middleware_is_mounted(self):
        with patch("app.main.get_rate_limiter", return_value=MagicMock()):
            from app.main import app

            middleware_classes = [
                m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
                for m in app.user_middleware
            ]
            assert "CORSMiddleware" in middleware_classes

    def test_gzip_middleware_is_mounted(self):
        with patch("app.main.get_rate_limiter", return_value=MagicMock()):
            from app.main import app

            middleware_classes = [
                m.cls.__name__ if hasattr(m, "cls") else type(m).__name__
                for m in app.user_middleware
            ]
            assert "GZipMiddleware" in middleware_classes


class TestExceptionHandlers:
    def test_app_exception_handler_registered(self):
        with patch("app.main.get_rate_limiter", return_value=MagicMock()):
            from app.main import app
            from app.core.exceptions import AppException

            assert AppException in app.exception_handlers

    def test_generic_exception_handler_registered(self):
        with patch("app.main.get_rate_limiter", return_value=MagicMock()):
            from app.main import app

            assert Exception in app.exception_handlers


# ---------------------------------------------------------------------------
# Handler logic tests (call the handler directly)
# ---------------------------------------------------------------------------


class TestRootHandler:
    @pytest.mark.asyncio
    async def test_root_returns_status_ok(self):
        with patch("app.main.get_rate_limiter", return_value=MagicMock()):
            from app.main import root

            result = await root()
            assert result["status"] == "ok"
            assert "version" in result
            assert "service" in result


class TestHealthHandler:
    @pytest.mark.asyncio
    @patch("app.main.check_gee_health", new_callable=AsyncMock)
    @patch("app.main.check_redis_health", new_callable=AsyncMock)
    @patch("app.main.check_database_health", new_callable=AsyncMock)
    async def test_healthy_when_db_is_healthy(self, mock_db, mock_redis, mock_gee):
        with patch("app.main.get_rate_limiter", return_value=MagicMock()):
            from app.main import health

            mock_db.return_value = {"status": "healthy"}
            mock_redis.return_value = {"status": "healthy"}
            mock_gee.return_value = {"status": "healthy"}

            result = await health()

            assert result["status"] == "healthy"
            assert "services" in result

    @pytest.mark.asyncio
    @patch("app.main.check_gee_health", new_callable=AsyncMock)
    @patch("app.main.check_redis_health", new_callable=AsyncMock)
    @patch("app.main.check_database_health", new_callable=AsyncMock)
    async def test_degraded_when_db_is_unhealthy(self, mock_db, mock_redis, mock_gee):
        with patch("app.main.get_rate_limiter", return_value=MagicMock()):
            from app.main import health

            mock_db.return_value = {"status": "unhealthy"}
            mock_redis.return_value = {"status": "healthy"}
            mock_gee.return_value = {"status": "healthy"}

            result = await health()

            assert result["status"] == "degraded"
