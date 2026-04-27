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

import httpx
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


def _backend_base_url() -> str:
    """Internal HTTP base URL for the backend service.

    Defaults to the docker-compose service name. Override with
    ``BACKEND_INTERNAL_URL`` for local/dev runs.
    """
    return os.getenv("BACKEND_INTERNAL_URL", "http://consorcio-backend:8000").rstrip("/")


@celery_app.task(name="geo.warm_gee_layers", bind=True, max_retries=0)
def task_warm_gee_layers(self) -> dict:
    """Hit each slow GEE endpoint once so the cache is hot.

    Returns a small per-endpoint summary so the result is greppable in
    Celery's result backend (Redis).
    """
    base = _backend_base_url()
    results: list[dict] = []

    with httpx.Client(timeout=WARM_REQUEST_TIMEOUT_SECONDS) as client:
        for path in WARM_ENDPOINTS:
            url = f"{base}{path}"
            try:
                resp = client.get(url)
                results.append(
                    {
                        "path": path,
                        "status": resp.status_code,
                        "x_cache": resp.headers.get("x-cache"),
                        "ms": int(resp.elapsed.total_seconds() * 1000),
                    }
                )
                logger.info(
                    "warmed %s status=%s x-cache=%s elapsed=%sms",
                    path,
                    resp.status_code,
                    resp.headers.get("x-cache"),
                    int(resp.elapsed.total_seconds() * 1000),
                )
            except httpx.HTTPError as exc:
                results.append({"path": path, "error": str(exc)})
                logger.warning("warm failed for %s: %s", path, exc)

    return {"warmed": results, "count": len(results)}
