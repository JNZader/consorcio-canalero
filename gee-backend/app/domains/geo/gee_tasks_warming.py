"""Celery task that pre-warms the JSON cache for slow GEE layer endpoints.

The first user that hits a layer after startup pays the full GEE compute
latency (30 s to 2 min). This task removes that cost by hitting each
endpoint once at startup so subsequent requests are served from Redis.

Implementation notes
--------------------
The task talks to the backend over plain HTTP (`consorcio-backend:8000`
inside the docker compose network). This avoids duplicating handler logic
or sharing GEE auth state between worker and backend processes — the
backend handler does the work and writes to Redis as part of its normal
cache-miss path.

The task is fired from the FastAPI lifespan via ``apply_async`` with a
small ``countdown`` so the backend has finished booting before the worker
starts hammering it.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger

from app.core.celery_app import celery_app

logger = get_task_logger(__name__)


# Endpoints that the warming task will hit, in order of importance.
WARM_ENDPOINTS: tuple[str, ...] = (
    "/api/v2/geo/gee/layers/caminos/coloreados",
    "/api/v2/geo/gee/layers/caminos/estadisticas",
    "/api/v2/geo/gee/layers/zona",
    "/api/v2/geo/gee/layers/norte",
    "/api/v2/geo/gee/layers/noroeste",
    "/api/v2/geo/gee/layers/ml",
    "/api/v2/geo/gee/layers/candil",
)

# Per-endpoint timeout. GEE compute can take ~3 minutes for the heaviest
# layers; we give the request enough budget to actually populate the cache.
WARM_REQUEST_TIMEOUT_SECONDS: float = 240.0

# The worker hard-kills a task at 600s (SIGKILL, no cleanup). Seven
# sequential 240s calls never finish. The requests run together so the
# wall clock is one timeout, and the task limits sit under that kill.
WARM_TASK_SOFT_TIME_LIMIT_SECONDS = 540
WARM_TASK_TIME_LIMIT_SECONDS = 590


def _backend_base_url() -> str:
    """Internal HTTP base URL for the backend service.

    Defaults to the docker-compose service name. Override with
    ``BACKEND_INTERNAL_URL`` for local/dev runs.
    """
    return os.getenv("BACKEND_INTERNAL_URL", "http://consorcio-backend:8000").rstrip("/")


def _warm_one(base: str, path: str) -> dict:
    """GET one layer. A private client: httpx.Client is not thread-safe."""
    url = f"{base}{path}"
    try:
        with httpx.Client(timeout=WARM_REQUEST_TIMEOUT_SECONDS) as client:
            resp = client.get(url)
        summary = {
            "path": path,
            "status": resp.status_code,
            "x_cache": resp.headers.get("x-cache"),
            "ms": int(resp.elapsed.total_seconds() * 1000),
        }
        logger.info(
            "warmed %s status=%s x-cache=%s elapsed=%sms",
            path,
            resp.status_code,
            resp.headers.get("x-cache"),
            summary["ms"],
        )
        return summary
    except httpx.HTTPError as exc:
        logger.warning("warm failed for %s: %s", path, exc)
        return {"path": path, "error": str(exc)}


@celery_app.task(
    name="geo.warm_gee_layers",
    bind=True,
    max_retries=0,
    soft_time_limit=WARM_TASK_SOFT_TIME_LIMIT_SECONDS,
    time_limit=WARM_TASK_TIME_LIMIT_SECONDS,
)
def task_warm_gee_layers(self) -> dict:
    """Hit each slow GEE endpoint once so the cache is hot.

    The calls run concurrently. Sequential 240s timeouts (7 of them) used
    to outlive the worker's 600s hard limit and die by SIGKILL, which
    also drops whatever the worker was doing next.

    Returns a small per-endpoint summary so the result is greppable in
    Celery's result backend (Redis).
    """
    base = _backend_base_url()
    results: list[dict] = []
    pool = ThreadPoolExecutor(max_workers=len(WARM_ENDPOINTS), thread_name_prefix="gee-warm")
    futures = [pool.submit(_warm_one, base, path) for path in WARM_ENDPOINTS]
    try:
        for future in as_completed(futures):
            results.append(future.result())
    except SoftTimeLimitExceeded:
        logger.warning("warm stopped at the soft time limit with %s results", len(results))
        return {"warmed": results, "count": len(results), "stopped": "soft_time_limit"}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return {"warmed": results, "count": len(results)}
