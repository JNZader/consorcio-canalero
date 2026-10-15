"""Postgres cache for the longitudinal elevation profile.

Keyed by the geometry plus the identity of every raster that was actually
sampled. A new DEM run, a re-mosaicked MDE-Ar, or a bump of ``SERIES_VERSION``
all change the key, so a stored profile can never describe a different surface
than the one on disk.

The GEE comparison is never cached: AW3D30/NASADEM must not be served out of a
stored GLO-30 payload.

The key/identity helpers are stdlib-only on purpose — no shapely, no sqlalchemy —
so the invalidation contract can be exercised without a database. See
``docs/ALTIMETRIA-FUENTES.md`` for the new-source procedure.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

#: Bump when the SAMPLING changes (densify step, retrace unfolding, caps).
#: Adding a column to the payload alone does not require a bump.
SERIES_VERSION = 1

#: Rows older than this are pruned on write. Superseded DEM runs simply stop
#: being requested, so their rows age out instead of being tracked.
PRUNE_DAYS = 90


def file_identity(path: str | Path) -> str:
    """``size:mtime_ns`` of the file, or ``absent``. The file IS the truth."""
    try:
        stat = os.stat(path)
    except OSError:
        return "absent"
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def build_source_identity(dem_filled_path: str) -> str:
    """Identity of every raster the plain series samples, in one string."""
    from app.domains.geo.elevation_profile import MDE_AR_NOMBRE

    mde_ar_path = Path(dem_filled_path).with_name(MDE_AR_NOMBRE)
    return (
        f"series:v{SERIES_VERSION}"
        f"|dem_filled:{file_identity(dem_filled_path)}"
        f"|mde_ar:{file_identity(mde_ar_path)}"
    )


def canonical_geometry(geometry: dict[str, Any]) -> str:
    """Stable JSON: dict key order must not change the key."""
    return json.dumps(geometry, sort_keys=True, separators=(",", ":"))


def build_cache_key(geometry: dict[str, Any], source_identity: str) -> str:
    """sha256 of the canonical geometry plus the source identity.

    Coordinates are NOT rounded: a different trace must never hit another
    trace's row, even by a few centimetres.
    """
    raw = f"{canonical_geometry(geometry)}|{source_identity}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def prune_cutoff() -> datetime:
    """Rows older than this are pruned on write. App and DB share the host clock."""
    return datetime.now(timezone.utc) - timedelta(days=PRUNE_DAYS)


def _default_session():
    from app.db.session import SessionLocal

    return SessionLocal()


#: Test seam: lets a test point the cache at its own engine. Production keeps
#: the app session factory, and the cache still never touches the caller's session.
_session_factory = _default_session


def _session():
    """A session of its own.

    The cache must never commit or roll back the caller's request-scoped
    session: committing it ends a transaction the caller still owns, and rolling
    it back discards the caller's pending changes (review R3).
    """
    return _session_factory()


def read_cached_profile(cache_key: str) -> Optional[dict[str, Any]]:
    """Stored payload, or ``None`` on a miss.

    Reads on its own session so a failure here cannot abort the caller's
    transaction.
    """
    from app.domains.geo.models import ElevationProfileCache

    with _session() as session:
        row = session.get(ElevationProfileCache, cache_key)
        if row is None:
            return None
        payload = row.payload
        # Fail safe: anything that is not a mapping is a miss, never a guess.
        return payload if isinstance(payload, dict) else None


def write_cached_profile(
    *,
    cache_key: str,
    source_identity: str,
    payload: dict[str, Any],
) -> None:
    """Upsert the payload and prune old rows, in one transaction of its own.

    ``ON CONFLICT DO UPDATE``, not get-then-add: two requests computing the same
    key concurrently would both miss, and the loser's insert would raise a
    unique violation that the caller swallows as a cache failure — a silently
    lost write plus a repeated recomputation (review R2-001).
    """
    from sqlalchemy import delete, func
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.domains.geo.models import ElevationProfileCache

    with _session() as session:
        statement = pg_insert(ElevationProfileCache).values(
            cache_key=cache_key,
            source_identity=source_identity,
            payload=payload,
        )
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["cache_key"],
                set_={
                    "source_identity": statement.excluded.source_identity,
                    "payload": statement.excluded.payload,
                    "updated_at": func.now(),
                },
            )
        )
        # Parameterised cutoff instead of a raw SQL interval: no `text()`, nothing
        # for a scanner (or a reviewer) to second-guess.
        session.execute(
            delete(ElevationProfileCache).where(ElevationProfileCache.created_at < prune_cutoff())
        )
        session.commit()
