"""Bounded rescale policy for public raster tiles — single source of truth.

The anonymous tile endpoint lets a caller pick a ``rescale_min`` / ``rescale_max``
pair so a continuous layer (e.g. CHIRPS ``precip_normal`` normals) can be drawn
with different contrast without minting a new ``GeoLayer`` id. That pair flows
into the geo-worker cache key, so an attacker-controlled float range would
explode the cache-key cardinality and poison rendering.

This module is the ONLY place the supported ranges are defined. The public
proxy (``router_core.proxy_tile``) validates against it and returns 4xx; the
geo-worker tile service (``tile_service.get_tile``) tokenizes against it for the
cache key and decides whether to apply the override. Because both consume this
one module, the two boundaries cannot drift into inconsistent checks.

The policy is deliberately tiny and explicit: a fixed map from layer ``tipo`` to
a fixed set of canonical ``(min, max)`` pairs, each mapped to a short bounded
cache-key token. Cardinality is therefore provably finite (exactly two pairs for
``precip_normal`` today, and only ever grows by an explicit edit here).

Part of hardening H1 (multi-hazard-viewer review ledger).
"""

from __future__ import annotations

import math
from typing import Optional

from fastapi import HTTPException

# Canonical rescale overrides per layer ``tipo``. Each canonical ``(min, max)``
# pair maps to a short, bounded cache-key token. This is the ONLY place rescale
# cardinality is defined, so the cache key can never contain an arbitrary
# attacker-controlled float.
ALLOWED_RESCALE_BY_TIPO: dict[str, dict[tuple[float, float], str]] = {
    "precip_normal": {
        (0.0, 200.0): "m",  # monthly CHIRPS normals (0-200 mm)
        (0.0, 1800.0): "a",  # annual CHIRPS normals (0-1800 mm) == default
    }
}

# Tolerance for float comparison when matching a requested pair against the
# canonical map (covers float-parsing noise from the query string).
_RESCALE_EPS = 1e-6


def _match_canonical(tipo: str, rmin: float, rmax: float) -> Optional[tuple[float, float, str]]:
    """Return ``(cmin, cmax, token)`` for a canonical pair, else ``None``."""
    pairs = ALLOWED_RESCALE_BY_TIPO.get(tipo)
    if not pairs:
        return None
    for (cmin, cmax), token in pairs.items():
        if abs(cmin - rmin) <= _RESCALE_EPS and abs(cmax - rmax) <= _RESCALE_EPS:
            return (cmin, cmax, token)
    return None


# Flattened, value-only view used for cache-key tokenization. The token does not
# need the layer ``tipo`` (it only has to distinguish the supported ranges), so
# the worker can build the key before it has loaded the layer — preserving the
# fast cache-HIT path.
_ALL_CANONICAL_PAIRS: dict[tuple[float, float], str] = {
    pair: token for _pairs in ALLOWED_RESCALE_BY_TIPO.values() for pair, token in _pairs.items()
}


def validate_rescale(
    tipo: str, rmin: Optional[float], rmax: Optional[float]
) -> Optional[tuple[float, float]]:
    """Validate a rescale pair at the public edge.

    Returns the exact canonical ``(min, max)`` to forward when an override is
    allowed, or ``None`` when no override should be applied (so the existing
    default rendering is preserved). Raises ``HTTPException`` (4xx) for any
    malformed or unsupported input.

    Invariants enforced:
      * both params supplied together or neither;
      * values are finite (rejects NaN / ±infinity);
      * ``min < max`` (rejects equal / inverted ranges);
      * the pair is one of the canonical overrides for this layer ``tipo``.
    """
    # Both supplied together or neither.
    if (rmin is None) != (rmax is None):
        raise HTTPException(
            status_code=400,
            detail="rescale_min y rescale_max deben enviarse juntos o ninguno",
        )
    if rmin is None:
        return None

    # Reject non-finite values (NaN / ±infinity parse as floats in FastAPI).
    if not (math.isfinite(rmin) and math.isfinite(rmax)):
        raise HTTPException(
            status_code=400,
            detail="rescale_min y rescale_max deben ser valores finitos",
        )

    # Inverted or equal range.
    if rmin >= rmax:
        raise HTTPException(
            status_code=400,
            detail="rescale_min debe ser estrictamente menor que rescale_max",
        )

    # Per-layer canonical policy.
    match = _match_canonical(tipo, rmin, rmax)
    if match is None:
        raise HTTPException(
            status_code=400,
            detail=f"rango de rescale no soportado para la capa '{tipo}'",
        )
    return (match[0], match[1])


def rescale_cache_token(rmin: Optional[float], rmax: Optional[float]) -> str:
    """Bounded cache-key fragment for a rescale pair.

    Never embeds a raw float: returns ``-`` when there is no canonical override,
    otherwise the short token (``m`` / ``a``). The geo-worker uses this to keep
    its cache-key cardinality finite even if reached with an unvalidated pair.
    """
    if rmin is None or rmax is None:
        return "-"
    if not (math.isfinite(rmin) and math.isfinite(rmax)):
        return "-"
    for (cmin, cmax), token in _ALL_CANONICAL_PAIRS.items():
        if abs(cmin - rmin) <= _RESCALE_EPS and abs(cmax - rmax) <= _RESCALE_EPS:
            return token
    return "-"


def resolved_rescale(
    tipo: str, rmin: Optional[float], rmax: Optional[float]
) -> Optional[tuple[float, float]]:
    """The canonical rescale pair to apply, or ``None`` for default rendering.

    Used by the geo-worker render decision. A pair that is not canonical for the
    layer (e.g. a direct, unvalidated call that bypassed the proxy) degrades to
    the default rescale instead of crashing or poisoning the cache.
    """
    if rmin is None or rmax is None:
        return None
    if not (math.isfinite(rmin) and math.isfinite(rmax)):
        return None
    match = _match_canonical(tipo, rmin, rmax)
    return (match[0], match[1]) if match is not None else None
