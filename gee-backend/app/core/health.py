"""Health check functions for external services."""

import asyncio
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import get_rate_limiter
from app.db.session import SessionLocal

logger = get_logger(__name__)

# alembic.ini lives at gee-backend/alembic.ini.
# This file is at gee-backend/app/core/health.py, so parents[2] == gee-backend/.
ALEMBIC_INI_PATH = Path(__file__).resolve().parents[2] / "alembic.ini"


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


async def check_database_health() -> Dict[str, Any]:
    """Check PostgreSQL/PostGIS without blocking the Uvicorn event loop."""
    return await asyncio.to_thread(check_database_health_sync)


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


def check_alembic_health_sync(db: Session) -> Dict[str, Any]:
    """
    Verify that alembic_version.version_num in the DB exists in the migration
    script tree.

    Catches phantom revisions introduced by manual ``alembic stamp <sha>`` with a
    fabricated ID (the root cause of the incident fixed in commits fce8c66 /
    95f59db / 3b08635). A broken stamp does NOT prevent the app from serving
    requests, but it DOES block future migrations, so we surface it on /health
    instead of failing startup.

    Returns dict shape:
      - healthy: {"status": "healthy", "current_rev": str, "is_head": bool, "heads": list[str]}
      - unhealthy: {"status": "unhealthy", "error": str, "current_rev": str | None}
    """
    # 1. Read the current stamp from the DB. Use a raw text query so this does
    #    not depend on alembic's context being initialized.
    try:
        result = db.execute(text("SELECT version_num FROM alembic_version"))
        row = result.first()
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

    current_rev = row[0]

    # 2. Load the alembic script tree from the repo.
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

    # 3. Check the current rev exists in the script tree.
    try:
        revision_obj = script_dir.get_revision(current_rev)
    except Exception as e:
        # alembic.util.exc.CommandError is raised for "Can't locate revision"
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

    # 4. Report whether the stamp is at head (false => pending migrations).
    heads = set(script_dir.get_heads())
    is_head = current_rev in heads

    return {
        "status": "healthy",
        "current_rev": current_rev,
        "is_head": is_head,
        "heads": sorted(heads),
    }


def _check_alembic_health_with_session() -> Dict[str, Any]:
    try:
        db = SessionLocal()
        try:
            return check_alembic_health_sync(db)
        finally:
            db.close()
    except Exception as e:
        logger.error("Alembic health check failed", error=str(e))
        return {"status": "unhealthy", "error": "alembic_check_failed"}


async def check_alembic_health() -> Dict[str, Any]:
    """Run the sync Alembic/SQL probe in a worker thread."""
    return await asyncio.to_thread(_check_alembic_health_with_session)


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

    tasks = {name: asyncio.create_task(bounded(check)) for name, check in checks.items()}
    done, pending = await asyncio.wait(tasks.values(), timeout=overall_timeout)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    results: dict[str, Dict[str, Any]] = {}
    for name, task in tasks.items():
        if task in done:
            results[name] = task.result()
        else:
            results[name] = {"status": "unhealthy", "error": "overall_timeout"}
    return results
