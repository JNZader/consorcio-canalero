"""JSON response cache backed by Redis with graceful degradation.

Mirrors the pattern in :mod:`app.core.rate_limit`: lazy Redis connection,
graceful fallback when Redis is unreachable (cache becomes a no-op so the
handler still works), structured logging.

Used by slow GEE endpoints (`router_gee_support.py`) to avoid re-querying
Google Earth Engine on every request. TTLs per endpoint are decided at the
call site, not in this module.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, Optional

from app.core.logging import get_logger

if TYPE_CHECKING:
    import redis.asyncio

logger = get_logger(__name__)


class JSONCache:
    """Thin async Redis-backed JSON cache.

    Stores any JSON-serialisable value under a string key with a TTL.
    When Redis is not reachable, every operation becomes a no-op so the
    caller's logic continues to work (cache miss path always runs).
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "cache:",
        redis_retry_cooldown_seconds: float = 5.0,
    ):
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.redis_retry_cooldown_seconds = redis_retry_cooldown_seconds
        self._redis: Optional["redis.asyncio.Redis"] = None
        self._redis_available: Optional[bool] = None
        self._redis_retry_at = 0.0
        logger.info("JSON cache initialized", redis_configured=bool(redis_url))

    async def _mark_redis_unavailable(self) -> None:
        client = self._redis
        self._redis = None
        self._redis_available = False
        self._redis_retry_at = time.monotonic() + self.redis_retry_cooldown_seconds
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass

    async def _get_redis(self) -> Optional["redis.asyncio.Redis"]:
        """Initialize Redis lazily and retry after a bounded cooldown."""
        if self._redis_available is False:
            if time.monotonic() < self._redis_retry_at:
                return None
            self._redis_available = None
        if self._redis is None and self.redis_url:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis.ping()
                self._redis_available = True
                logger.info("Redis connected for JSON cache")
            except ImportError:
                logger.warning("redis package not installed, JSON cache disabled")
                self._redis_available = False
                return None
            except Exception as exc:
                logger.warning(
                    "Redis connection failed for JSON cache, operating as no-op",
                    error=str(exc),
                )
                await self._mark_redis_unavailable()
                return None
        return self._redis

    def _full_key(self, key: str) -> str:
        return f"{self.key_prefix}{key}"

    async def get(self, key: str) -> Optional[Any]:
        """Return the cached value for ``key`` or ``None`` on miss / error."""
        client = await self._get_redis()
        if client is None:
            return None
        try:
            raw = await client.get(self._full_key(key))
        except Exception as exc:
            logger.warning("Redis GET failed, treating as miss", key=key, error=str(exc))
            await self._mark_redis_unavailable()
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Cached value is not valid JSON, treating as miss",
                key=key,
                error=str(exc),
            )
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> bool:
        """Cache ``value`` under ``key`` with ``ttl_seconds``. Returns True on success."""
        if ttl_seconds <= 0:
            return False
        client = await self._get_redis()
        if client is None:
            return False
        try:
            payload = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Value is not JSON-serialisable, skipping cache",
                key=key,
                error=str(exc),
            )
            return False
        try:
            await client.setex(self._full_key(key), ttl_seconds, payload)
            return True
        except Exception as exc:
            logger.warning("Redis SETEX failed", key=key, error=str(exc))
            await self._mark_redis_unavailable()
            return False

    async def delete(self, key: str) -> bool:
        """Delete a single cached key. Returns True when the key existed."""
        client = await self._get_redis()
        if client is None:
            return False
        try:
            removed = await client.delete(self._full_key(key))
            return removed > 0
        except Exception as exc:
            logger.warning("Redis DELETE failed", key=key, error=str(exc))
            await self._mark_redis_unavailable()
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete every key matching ``pattern`` (with the cache prefix prepended).

        Uses SCAN to avoid blocking Redis on large keyspaces. Returns the
        number of keys deleted.
        """
        client = await self._get_redis()
        if client is None:
            return 0
        full_pattern = self._full_key(pattern)
        deleted = 0
        try:
            async for key in client.scan_iter(match=full_pattern, count=200):
                if await client.delete(key):
                    deleted += 1
        except Exception as exc:
            logger.warning("Redis SCAN/DELETE failed", pattern=pattern, error=str(exc))
            await self._mark_redis_unavailable()
        return deleted

    async def close(self) -> None:
        """Release the underlying Redis connection."""
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception as exc:
                logger.warning("Error closing Redis connection", error=str(exc))
            finally:
                self._redis = None
                self._redis_available = None


_cache: Optional[JSONCache] = None


def get_cache() -> JSONCache:
    """Return the process-global :class:`JSONCache` instance."""
    global _cache
    if _cache is None:
        from app.config import settings

        _cache = JSONCache(redis_url=settings.redis_url, key_prefix="cache:")
    return _cache


# ---------------------------------------------------------------------------
# Bytes cache — synchronous variant for binary payloads (e.g. rendered tiles).
# Lives next to :class:`JSONCache` because they share the same Redis backend
# and graceful-degradation pattern, but they need a separate client because
# the JSON cache uses ``decode_responses=True`` (returns ``str``) while bytes
# payloads must come back as raw ``bytes``.
# ---------------------------------------------------------------------------


class BytesCache:
    """Synchronous Redis-backed cache for binary payloads.

    Designed for hot paths that run inside FastAPI's threadpool (``def``
    endpoints), where running an async client would mean bouncing through
    ``asyncio.run`` per call. Falls back to a no-op when Redis is unreachable
    so the handler keeps working.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "bytes:",
        redis_retry_cooldown_seconds: float = 5.0,
    ):
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.redis_retry_cooldown_seconds = redis_retry_cooldown_seconds
        self._redis: Optional[Any] = None
        self._redis_available: Optional[bool] = None
        self._redis_retry_at = 0.0
        logger.info("Bytes cache initialized", redis_configured=bool(redis_url))

    def _mark_redis_unavailable(self) -> None:
        client = self._redis
        self._redis = None
        self._redis_available = False
        self._redis_retry_at = time.monotonic() + self.redis_retry_cooldown_seconds
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    def _get_redis(self) -> Optional[Any]:
        if self._redis_available is False:
            if time.monotonic() < self._redis_retry_at:
                return None
            self._redis_available = None
        if self._redis is None and self.redis_url:
            try:
                import redis  # type: ignore[import-not-found]

                self._redis = redis.Redis.from_url(
                    self.redis_url,
                    decode_responses=False,  # raw bytes
                )
                self._redis.ping()
                self._redis_available = True
                logger.info("Redis connected for bytes cache")
            except ImportError:
                logger.warning("redis package not installed, bytes cache disabled")
                self._redis_available = False
                return None
            except Exception as exc:
                logger.warning(
                    "Redis connection failed for bytes cache, operating as no-op",
                    error=str(exc),
                )
                self._mark_redis_unavailable()
                return None
        return self._redis

    def _full_key(self, key: str) -> str:
        return f"{self.key_prefix}{key}"

    def get(self, key: str) -> Optional[bytes]:
        client = self._get_redis()
        if client is None:
            return None
        try:
            return client.get(self._full_key(key))
        except Exception as exc:
            logger.warning("Redis GET failed, treating as miss", key=key, error=str(exc))
            self._mark_redis_unavailable()
            return None

    def set(self, key: str, value: bytes, ttl_seconds: int) -> bool:
        if ttl_seconds <= 0 or not value:
            return False
        client = self._get_redis()
        if client is None:
            return False
        try:
            client.setex(self._full_key(key), ttl_seconds, value)
            return True
        except Exception as exc:
            logger.warning("Redis SETEX failed", key=key, error=str(exc))
            self._mark_redis_unavailable()
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete every key matching ``pattern`` (prefix-aware, SCAN-based).

        Used to invalidate every cached tile of a GeoLayer when its
        underlying COG is regenerated by the DEM pipeline — without this
        hook tiles would stay stale until the 24 h TTL expires.
        """
        client = self._get_redis()
        if client is None:
            return 0
        full_pattern = self._full_key(pattern)
        deleted = 0
        try:
            for key in client.scan_iter(match=full_pattern, count=200):
                if client.delete(key):
                    deleted += 1
        except Exception as exc:
            logger.warning("Redis SCAN/DELETE failed", pattern=pattern, error=str(exc))
            self._mark_redis_unavailable()
        return deleted


def invalidate_layer_tiles(layer_id: str | object) -> int:
    """Invalidate every cached tile of a ``GeoLayer``.

    Call this from the COG-publish pipeline (``geo-worker`` task that
    finishes a DEM/COG regeneration) so the next tile request recomputes
    against the fresh raster. ``layer_id`` is stringified so passing a
    ``uuid.UUID`` works.
    """
    return get_bytes_cache().delete_pattern(f"v1:{layer_id}:*")


_bytes_cache: Optional[BytesCache] = None


def get_bytes_cache() -> BytesCache:
    """Return the process-global :class:`BytesCache` instance."""
    global _bytes_cache
    if _bytes_cache is None:
        from app.config import settings

        _bytes_cache = BytesCache(redis_url=settings.redis_url, key_prefix="tile:")
    return _bytes_cache
