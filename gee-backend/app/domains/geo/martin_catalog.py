"""Martin ``/catalog`` fetch with a short in-process TTL.

The public layer catalog and the QGIS export both ask Martin for the same
document. Without a cache every map load opens a new HTTP call. The payload
is small and changes only when a tile source is published, so a one-minute
TTL is enough. Failures are not cached: the next request tries again.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx

MARTIN_CATALOG_TTL_SECONDS = 60.0

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_martin_catalog_cache() -> None:
    """Drop every cached catalog. Tests call this between cases."""
    with _lock:
        _cache.clear()


async def fetch_martin_catalog(
    martin_internal_url: str,
    *,
    ttl_seconds: float = MARTIN_CATALOG_TTL_SECONDS,
) -> dict[str, Any]:
    """Return Martin's ``/catalog`` JSON, reusing a fresh cached copy."""
    base = martin_internal_url.rstrip("/")
    now = time.monotonic()
    with _lock:
        cached = _cache.get(base)
        if cached is not None and cached[0] > now:
            return cached[1]

    catalog_url = f"{base}/catalog"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(catalog_url)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        payload = {}

    if ttl_seconds > 0:
        with _lock:
            _cache[base] = (time.monotonic() + ttl_seconds, payload)
    return payload
