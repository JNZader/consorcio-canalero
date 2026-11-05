"""Health check functions for external services."""

import asyncio
import threading
import time
from concurrent.futures import Future, InvalidStateError
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

# One constant Earth Engine read. The public /health and /ready probes do
# not include it. The coordinator budget is a second longer so a probe
# that hits its own deadline can still report ``down`` instead of being
# replaced by the generic check timeout.
GEE_PROBE_TIMEOUT_SECONDS = 5.0
GEE_PROBE_CACHE_SECONDS = 60.0
_gee_probe_cache: dict[str, Any] | None = None
_gee_probe_cached_at = 0.0
_gee_probe_lock: asyncio.Lock | None = None
_gee_probe_lock_loop: asyncio.AbstractEventLoop | None = None


class _DaemonProbeExecutor:
    """Runs each probe on a daemon thread.

    ``asyncio.wait_for`` abandons the await when the probe exceeds its
    deadline, but ``getInfo()`` keeps running. A non-daemon thread blocks
    interpreter shutdown, so a hung Earth Engine call stops the container
    from exiting (R1-006). Daemon threads do not. ``shutdown`` does not
    wait for them.
    """

    def submit(self, fn, /, *args, **kwargs):
        future: Future = Future()

        def run() -> None:
            try:
                result = fn(*args, **kwargs)
            except BaseException as exc:
                _settle_future(future, exc)
                return
            _settle_future(future, result)

        threading.Thread(target=run, name="gee-health", daemon=True).start()
        return future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        return None


def _settle_future(future: Future, outcome: object) -> None:
    """Ignore a probe that ``wait_for`` already cancelled."""
    try:
        if isinstance(outcome, BaseException):
            future.set_exception(outcome)
        else:
            future.set_result(outcome)
    except InvalidStateError:
        return


# A hung getInfo must not occupy the default pool. Each call gets its own
# daemon thread; the 5s deadline still returns while that thread runs.
_gee_probe_executor = _DaemonProbeExecutor()


def shutdown_gee_probe() -> None:
    """Drop a hung probe without waiting for Earth Engine to answer."""
    _gee_probe_executor.shutdown(wait=False, cancel_futures=True)


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


def _reset_gee_probe_cache() -> None:
    """Drop the cached probe so the next call talks to Earth Engine again."""
    global _gee_probe_cache, _gee_probe_cached_at
    _gee_probe_cache = None
    _gee_probe_cached_at = 0.0


def _gee_coordinator_budget() -> float:
    """Deadline for the GEE probe inside ``run_health_checks``."""
    return GEE_PROBE_TIMEOUT_SECONDS + 1.0


def _gee_probe_lock_for_this_loop() -> asyncio.Lock:
    """An asyncio lock bound to the running loop.

    A lock created on another loop (a previous test, or a restarted
    worker) cannot be awaited. Recreate it when the loop changes.
    """
    global _gee_probe_lock, _gee_probe_lock_loop
    loop = asyncio.get_running_loop()
    if _gee_probe_lock is None or _gee_probe_lock_loop is not loop:
        _gee_probe_lock = asyncio.Lock()
        _gee_probe_lock_loop = loop
    return _gee_probe_lock


def _read_gee_probe_cache(now: float) -> dict[str, Any] | None:
    if _gee_probe_cache is None:
        return None
    if now - _gee_probe_cached_at >= GEE_PROBE_CACHE_SECONDS:
        return None
    return dict(_gee_probe_cache)


def _store_gee_probe_cache(result: dict[str, Any], now: float) -> dict[str, Any]:
    global _gee_probe_cache, _gee_probe_cached_at
    _gee_probe_cache = dict(result)
    _gee_probe_cached_at = now
    return dict(result)


def _gee_probe_payload(
    status: str,
    started: float,
    *,
    error: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "project": settings.gee_project_id,
    }
    if error is not None:
        payload["error"] = error
    return payload


def _gee_lightweight_call() -> object:
    """Constant read through the same init path the workers use.

    ``gee_service.ee`` is the client ``_ensure_initialized`` just
    configured. Tests replace that object; this function must not import
    a second ``ee`` module.
    """
    from app.domains.geo import gee_service

    gee_service._ensure_initialized()
    return gee_service.ee.Number(1).getInfo()


def _run_gee_probe_blocking(started: float) -> dict[str, Any]:
    try:
        value = _gee_lightweight_call()
    except Exception as exc:
        # The exception text can echo a credential parser snippet. Keep
        # the log to the type and the response to a fixed code.
        logger.error("GEE health check failed", error_type=type(exc).__name__)
        return _gee_probe_payload("down", started, error="gee_check_failed")
    if value == 1:
        return _gee_probe_payload("healthy", started)
    return _gee_probe_payload("degraded", started)


async def check_gee_health() -> Dict[str, Any]:
    """Confirm Earth Engine with one constant read, cached for about a minute.

    ``healthy`` means ``ee.Number(1).getInfo()`` returned ``1``. A different
    value is ``degraded``. A raised call, a failed init, or the 5s deadline
    is ``down``. ``latency_ms`` is the probe that produced the cached body,
    not the time spent reading the cache.

    ``/live``, ``/ready`` and ``/health`` do not call this. Their response
    bodies stay ``ok``, ``ready``/``not_ready`` and ``healthy``/``degraded``.
    """
    now = time.monotonic()
    cached = _read_gee_probe_cache(now)
    if cached is not None:
        return cached

    async with _gee_probe_lock_for_this_loop():
        now = time.monotonic()
        cached = _read_gee_probe_cache(now)
        if cached is not None:
            return cached
        started = time.perf_counter()
        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    _gee_probe_executor,
                    _run_gee_probe_blocking,
                    started,
                ),
                timeout=GEE_PROBE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.error(
                "GEE health check timed out",
                timeout_s=GEE_PROBE_TIMEOUT_SECONDS,
            )
            result = _gee_probe_payload("down", started, error="check_timeout")
        except Exception as exc:
            logger.error("GEE health check failed", error_type=type(exc).__name__)
            result = _gee_probe_payload("down", started, error="gee_check_failed")
        return _store_gee_probe_cache(result, time.monotonic())


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

    async def bounded(name: str, check):
        # The GEE read has its own ~5s budget. Folding it into the 2s
        # deadline used by the database probe would report a timeout
        # before Earth Engine can answer, including on a warm cache miss
        # that still has to initialize.
        timeout = per_check_timeout
        if name == "gee":
            timeout = max(per_check_timeout, _gee_coordinator_budget())
        try:
            return await asyncio.wait_for(check(), timeout=timeout)
        except TimeoutError:
            return {"status": "unhealthy", "error": "check_timeout"}
        except Exception as exc:
            logger.error("Health check crashed", error=str(exc))
            return {"status": "unhealthy", "error": "check_failed"}

    tasks = {
        name: asyncio.create_task(bounded(name, check), name=f"health:{name}")
        for name, check in checks.items()
    }
    deadline = overall_timeout
    if include_gee:
        deadline = max(overall_timeout, _gee_coordinator_budget())
    done, pending = await asyncio.wait(tasks.values(), timeout=deadline)
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
