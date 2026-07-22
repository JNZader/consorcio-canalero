"""Health check functions for external services."""

import asyncio
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import get_rate_limiter
from app.db.session import AsyncSessionLocal, SessionLocal

logger = get_logger(__name__)

# alembic.ini lives at gee-backend/alembic.ini.
# This file is at gee-backend/app/core/health.py, so parents[2] == gee-backend/.
ALEMBIC_INI_PATH = Path(__file__).resolve().parents[2] / "alembic.ini"

# The outer health coordinator has a per-probe deadline. Each individual
# database operation also has a driver-side cancellation deadline, while
# PostgreSQL gets a transaction-local statement timeout. This prevents a
# canceled health response from leaving SQL or a pool checkout alive.
DATABASE_DRIVER_TIMEOUT_SECONDS = 1.0
DATABASE_STATEMENT_TIMEOUT_MS = 750


def check_database_health_sync() -> Dict[str, Any]:
    """Run blocking PostgreSQL/PostGIS probes in a synchronous worker."""
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


async def _execute_with_driver_timeout(
    db: AsyncSession,
    statement: Any,
    parameters: dict[str, object] | None = None,
) -> Any:
    """Execute one async SQL operation with a cancellable driver deadline."""
    async with asyncio.timeout(DATABASE_DRIVER_TIMEOUT_SECONDS):
        if parameters is None:
            return await db.execute(statement)
        return await db.execute(statement, parameters)


async def _configure_statement_timeout(db: AsyncSession) -> None:
    result = await _execute_with_driver_timeout(
        db,
        text("SELECT set_config('statement_timeout', :timeout, true)"),
        {"timeout": f"{DATABASE_STATEMENT_TIMEOUT_MS}ms"},
    )
    result.close()


async def check_database_health() -> Dict[str, Any]:
    """Check PostgreSQL/PostGIS with cancellable async driver operations."""
    try:
        async with AsyncSessionLocal() as db:
            await _configure_statement_timeout(db)

            result = await _execute_with_driver_timeout(db, text("SELECT 1"))
            result.close()

            postgis = await _execute_with_driver_timeout(db, text("SELECT PostGIS_Version()"))
            version = postgis.scalar()
            postgis.close()
            return {"status": "healthy", "postgis_version": version}
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


def _check_alembic_revision(current_rev: str) -> Dict[str, Any]:
    """Compare one database revision with the local Alembic script tree."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        alembic_cfg = Config(str(ALEMBIC_INI_PATH))
        script_dir = ScriptDirectory.from_config(alembic_cfg)
    except Exception as e:
        logger.error("Alembic health check: script tree load failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": f"Failed to load alembic script tree: {e}",
            "current_rev": current_rev,
        }

    try:
        revision_obj = script_dir.get_revision(current_rev)
    except Exception as e:
        logger.error(
            "Alembic health check: phantom revision detected",
            current_rev=current_rev,
            error=str(e),
        )
        return {
            "status": "unhealthy",
            "error": f"Current DB revision {current_rev!r} not found in migration scripts: {e}",
            "current_rev": current_rev,
        }

    if revision_obj is None:
        logger.error(
            "Alembic health check: phantom revision detected",
            current_rev=current_rev,
        )
        return {
            "status": "unhealthy",
            "error": f"Current DB revision {current_rev!r} not found in migration scripts",
            "current_rev": current_rev,
        }

    heads = set(script_dir.get_heads())
    return {
        "status": "healthy",
        "current_rev": current_rev,
        "is_head": current_rev in heads,
        "heads": sorted(heads),
    }


def check_alembic_health_sync(db: Session) -> Dict[str, Any]:
    """Compatibility helper for synchronous callers and migration tests."""
    try:
        result = db.execute(text("SELECT version_num FROM alembic_version"))
        row = result.first()
        result.close()
    except Exception as e:
        logger.error("Alembic health check: DB query failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": f"Failed to query alembic_version: {e}",
        }

    if row is None:
        return {
            "status": "unhealthy",
            "error": "alembic_version table exists but is empty",
        }

    return _check_alembic_revision(str(row[0]))


async def check_alembic_health() -> Dict[str, Any]:
    """Read the DB stamp asynchronously, then inspect the local script tree."""
    try:
        async with AsyncSessionLocal() as db:
            await _configure_statement_timeout(db)
            result = await _execute_with_driver_timeout(
                db,
                text("SELECT version_num FROM alembic_version"),
            )
            row = result.first()
            result.close()
    except Exception as e:
        logger.error("Alembic health check: DB query failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": f"Failed to query alembic_version: {e}",
        }

    if row is None:
        return {
            "status": "unhealthy",
            "error": "alembic_version table exists but is empty",
        }

    # Loading and traversing local migration files is bounded local work; no
    # worker thread is needed, and there is no database operation left alive
    # if the surrounding health task is canceled.
    return _check_alembic_revision(str(row[0]))


async def run_health_checks(
    *,
    include_gee: bool = False,
    per_check_timeout: float = 2.0,
    overall_timeout: float = 3.0,
) -> dict[str, Dict[str, Any]]:
    """Run independent probes concurrently with per-check and overall deadlines."""
    checks = {
        "database": check_database_health,
        "redis": check_redis_health,
        "alembic": check_alembic_health,
    }
    if include_gee:
        checks["gee"] = check_gee_health

    async def bounded(check):
        try:
            return await asyncio.wait_for(check(), timeout=per_check_timeout)
        except TimeoutError:
            return {"status": "unhealthy", "error": "check_timeout"}
        except Exception as exc:
            logger.error("Health check crashed", error=str(exc))
            return {"status": "unhealthy", "error": "check_failed"}

    tasks = {
        name: asyncio.create_task(bounded(check), name=f"health:{name}")
        for name, check in checks.items()
    }
    done, pending = await asyncio.wait(tasks.values(), timeout=overall_timeout)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    results: dict[str, Dict[str, Any]] = {}
    for name, task in tasks.items():
        # A task can finish in the narrow window between asyncio.wait
        # returning and cancellation. Preserve that completed result rather
        # than overwriting it with an overall timeout.
        if task in done or (task.done() and not task.cancelled()):
            results[name] = task.result()
        else:
            results[name] = {"status": "unhealthy", "error": "overall_timeout"}
    return results
