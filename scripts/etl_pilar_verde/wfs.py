"""WFS fetch helper with deterministic exponential backoff and dual-host failover.

IDECor publishes WFS on two hostnames (see ``constants.WFS_HOSTS``); they mirror
the same layers.  The primary host (``gn-idecor``) is faster and more stable;
the secondary (``idecor-ws``) is kept as a fallback because it has been
observed returning 504 during peak hours while the primary stays green.

Contract (spec §ETL Script, design §3, task 0.24a):

- Up to 3 attempts total (tenacity-style — rolled by hand for testability).
- Waits 2s after the 1st failed attempt, 4s after the 2nd.
- Within EACH attempt we iterate ``WFS_HOSTS`` in order: host 1 → host 2.  No
  backoff between hosts inside the same attempt.  Only when BOTH hosts have
  failed inside an attempt does the attempt count toward the retry budget.
- Retries on ``HTTPError``, ``ConnectionError``, ``Timeout``.
- Uses ``CQL_FILTER=BBOX(geom,minx,miny,maxx,maxy,'EPSG:22174')`` — matches the
  memory #733 pattern that was proven to work on IDECor's layers.
- Requests the response reprojected to ``EPSG:4326`` via ``srsName``.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from scripts.etl_pilar_verde.constants import (
    CRS_IDECOR,
    CRS_LATLON,
    RETRY_ATTEMPTS,
    RETRY_WAIT_MAX_SECONDS,
    RETRY_WAIT_MIN_SECONDS,
    WFS_HOSTS,
    build_wfs_url,
)

logger = logging.getLogger(__name__)

_RETRIABLE_EXCEPTIONS = (
    requests.HTTPError,
    requests.ConnectionError,
    requests.Timeout,
)


def _cql_bbox_22174(bbox_22174: tuple[float, float, float, float]) -> str:
    minx, miny, maxx, maxy = bbox_22174
    return f"BBOX(geom,{minx},{miny},{maxx},{maxy},'{CRS_IDECOR}')"


def _wait_for_attempt(attempt: int) -> int:
    """Deterministic backoff: 2s after the 1st failure, 4s after the 2nd, ..."""
    seconds = RETRY_WAIT_MIN_SECONDS * (2 ** (attempt - 1))
    return min(seconds, RETRY_WAIT_MAX_SECONDS)


def fetch_layer(
    type_names: str,
    bbox_22174: tuple[float, float, float, float],
    *,
    timeout: int = 60,
    extra_params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch an IDECor WFS layer as a GeoJSON FeatureCollection.

    Iterates ``WFS_HOSTS`` inside each retry attempt for host-level resilience;
    the last ``requests`` exception is re-raised after the attempts budget is
    exhausted across all hosts.
    """
    params: dict[str, str] = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": type_names,
        "outputFormat": "application/json",
        "srsName": CRS_LATLON,
        "CQL_FILTER": _cql_bbox_22174(bbox_22174),
    }
    if extra_params:
        params.update(extra_params)

    last_exc: Exception | None = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        attempt_exhausted_hosts = True
        for host in WFS_HOSTS:
            url = build_wfs_url(host)
            started = time.monotonic()
            try:
                logger.info(
                    "wfs.fetch attempt=%d/%d host=%s layer=%s",
                    attempt,
                    RETRY_ATTEMPTS,
                    host,
                    type_names,
                )
                response = requests.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                payload = response.json()
                elapsed_ms = int((time.monotonic() - started) * 1000)
                logger.info(
                    "wfs.fetch ok host=%s layer=%s elapsed_ms=%d features=%d",
                    host,
                    type_names,
                    elapsed_ms,
                    len(payload.get("features", [])),
                )
                return payload
            except _RETRIABLE_EXCEPTIONS as exc:
                last_exc = exc
                logger.warning(
                    "wfs.fetch failed attempt=%d host=%s layer=%s error=%s",
                    attempt,
                    host,
                    type_names,
                    exc,
                )
                # Try the next host inside the same attempt — no backoff here.
                continue

        # Both hosts failed in this attempt — apply the inter-attempt backoff.
        if attempt_exhausted_hosts and attempt < RETRY_ATTEMPTS:
            time.sleep(_wait_for_attempt(attempt))

    assert last_exc is not None  # pragma: no cover — reachable only if the loop is buggy
    raise last_exc
