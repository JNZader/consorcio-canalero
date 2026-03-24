"""Health check functions for external services."""

from typing import Any, Dict

from sqlalchemy import text

from app.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import get_rate_limiter
from app.db.session import SessionLocal

logger = get_logger(__name__)


async def check_database_health() -> Dict[str, Any]:
    """Check PostgreSQL + PostGIS connection health."""
    try:
        db = SessionLocal()
        try:
            result = db.execute(text("SELECT 1"))
            result.close()

            postgis = db.execute(text("SELECT PostGIS_Version()"))
            version = postgis.scalar()
            postgis.close()

            return {"status": "healthy", "postgis_version": version}
        finally:
            db.close()
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return {"status": "unhealthy", "error": "database_check_failed"}


async def check_redis_health() -> Dict[str, Any]:
    """Check Redis connection health."""
    try:
        import time

        rate_limiter = get_rate_limiter()
        redis_client = await rate_limiter._get_redis()

        if redis_client:
            start = time.time()
            await redis_client.ping()
            latency = round((time.time() - start) * 1000, 2)
            return {"status": "healthy", "latency_ms": latency}
        else:
            return {"status": "unavailable", "message": "Using in-memory fallback"}
    except Exception as e:
        logger.error("Redis health check failed", error=str(e))
        return {"status": "unhealthy", "error": "redis_check_failed"}


async def check_gee_health() -> Dict[str, Any]:
    """Check Google Earth Engine connection health."""
    try:
        from app.domains.geo.gee_service import _gee_initialized

        if _gee_initialized:
            return {"status": "healthy", "project": settings.gee_project_id}
        else:
            return {"status": "not_initialized"}
    except ImportError:
        return {"status": "not_configured"}
    except Exception as e:
        logger.error("GEE health check failed", error=str(e))
        return {"status": "unhealthy", "error": "gee_check_failed"}
