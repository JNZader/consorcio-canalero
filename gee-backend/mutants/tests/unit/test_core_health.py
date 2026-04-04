"""Unit tests for app.core.health — DB, Redis, GEE health checks."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.health import check_database_health, check_gee_health, check_redis_health


# ── check_database_health ─────────────────────────


class TestCheckDatabaseHealth:
    """Tests for PostgreSQL + PostGIS connectivity probe."""

    @pytest.mark.asyncio
    @patch("app.core.health.SessionLocal")
    async def test_healthy_returns_postgis_version(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        # First execute: SELECT 1
        mock_result_1 = MagicMock()
        # Second execute: PostGIS_Version()
        mock_result_2 = MagicMock()
        mock_result_2.scalar.return_value = "3.4.0"

        mock_db.execute.side_effect = [mock_result_1, mock_result_2]

        result = await check_database_health()

        assert result["status"] == "healthy"
        assert result["postgis_version"] == "3.4.0"
        mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.core.health.SessionLocal")
    async def test_unhealthy_on_exception(self, mock_session_cls):
        mock_session_cls.side_effect = Exception("Connection refused")

        result = await check_database_health()

        assert result["status"] == "unhealthy"
        assert result["error"] == "database_check_failed"

    @pytest.mark.asyncio
    @patch("app.core.health.SessionLocal")
    async def test_unhealthy_on_query_failure(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.execute.side_effect = Exception("syntax error")

        result = await check_database_health()

        assert result["status"] == "unhealthy"
        assert result["error"] == "database_check_failed"
        mock_db.close.assert_called_once()


# ── check_redis_health ────────────────────────────


class TestCheckRedisHealth:
    """Tests for Redis connectivity and latency probe."""

    @pytest.mark.asyncio
    @patch("app.core.health.get_rate_limiter")
    async def test_healthy_redis_returns_latency(self, mock_get_limiter):
        mock_limiter = MagicMock()
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_limiter._get_redis = AsyncMock(return_value=mock_redis)
        mock_get_limiter.return_value = mock_limiter

        result = await check_redis_health()

        assert result["status"] == "healthy"
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], float)

    @pytest.mark.asyncio
    @patch("app.core.health.get_rate_limiter")
    async def test_unavailable_when_no_redis_client(self, mock_get_limiter):
        mock_limiter = MagicMock()
        mock_limiter._get_redis = AsyncMock(return_value=None)
        mock_get_limiter.return_value = mock_limiter

        result = await check_redis_health()

        assert result["status"] == "unavailable"
        assert "fallback" in result["message"].lower()

    @pytest.mark.asyncio
    @patch("app.core.health.get_rate_limiter")
    async def test_unhealthy_on_ping_failure(self, mock_get_limiter):
        mock_limiter = MagicMock()
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = Exception("Connection lost")
        mock_limiter._get_redis = AsyncMock(return_value=mock_redis)
        mock_get_limiter.return_value = mock_limiter

        result = await check_redis_health()

        assert result["status"] == "unhealthy"
        assert result["error"] == "redis_check_failed"


# ── check_gee_health ─────────────────────────────


class TestCheckGeeHealth:
    """Tests for Google Earth Engine initialization probe."""

    @pytest.mark.asyncio
    @patch("app.core.health.settings")
    async def test_healthy_when_initialized(self, mock_settings):
        mock_settings.gee_project_id = "test-project"
        with patch.dict(
            "sys.modules",
            {"app.domains.geo.gee_service": MagicMock(_gee_initialized=True)},
        ):
            result = await check_gee_health()

        assert result["status"] == "healthy"
        assert result["project"] == "test-project"

    @pytest.mark.asyncio
    async def test_not_initialized(self):
        with patch.dict(
            "sys.modules",
            {"app.domains.geo.gee_service": MagicMock(_gee_initialized=False)},
        ):
            result = await check_gee_health()

        assert result["status"] == "not_initialized"

    @pytest.mark.asyncio
    async def test_not_configured_on_import_error(self):
        # Simulate ImportError by removing the module and patching __import__
        import sys

        saved = sys.modules.pop("app.domains.geo.gee_service", None)
        try:
            with patch(
                "builtins.__import__",
                side_effect=ImportError("No module named 'ee'"),
            ):
                result = await check_gee_health()

            assert result["status"] == "not_configured"
        finally:
            if saved is not None:
                sys.modules["app.domains.geo.gee_service"] = saved

    @pytest.mark.asyncio
    async def test_unhealthy_on_generic_exception(self):
        mock_module = MagicMock()
        # Accessing _gee_initialized raises
        type(mock_module)._gee_initialized = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        with patch.dict("sys.modules", {"app.domains.geo.gee_service": mock_module}):
            result = await check_gee_health()

        assert result["status"] == "unhealthy"
        assert result["error"] == "gee_check_failed"
