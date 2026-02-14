"""
Distributed rate limiting module using Redis.
Implements sliding window algorithm with fallback to in-memory storage.
"""

import asyncio
import time
from collections import defaultdict
from typing import Optional, Tuple

from app.core.logging import get_logger

logger = get_logger(__name__)

# Maximum number of keys in the in-memory fallback store before cleanup
MAX_MEMORY_ENTRIES = 10000


class DistributedRateLimiter:
    """
    Distributed rate limiter using Redis with sliding window algorithm.

    Falls back to in-memory storage if Redis is not available.
    Thread-safe for both Redis and in-memory modes.

    Usage:
        limiter = DistributedRateLimiter(
            redis_url="redis://localhost:6379/0",
            max_requests=100,
            window_seconds=60,
        )

        allowed, remaining, reset_time = await limiter.check("user:123")
        if not allowed:
            raise RateLimitExceededError(retry_after=reset_time)
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        max_requests: int = 100,
        window_seconds: int = 60,
        key_prefix: str = "ratelimit:",
    ):
        """
        Initialize the rate limiter.

        Args:
            redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")
            max_requests: Maximum number of requests allowed in the window
            window_seconds: Time window in seconds
            key_prefix: Prefix for Redis keys
        """
        self.redis_url = redis_url
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix

        # Redis client (lazy initialization)
        self._redis: Optional["redis.asyncio.Redis"] = None
        self._redis_available: Optional[bool] = None

        # In-memory fallback storage
        self._memory_store: dict = defaultdict(list)
        self._memory_lock = asyncio.Lock()

        logger.info(
            "Rate limiter initialized",
            max_requests=max_requests,
            window_seconds=window_seconds,
            redis_configured=bool(redis_url),
        )

    async def _get_redis(self) -> Optional["redis.asyncio.Redis"]:
        """Get Redis client, initializing if necessary."""
        if self._redis_available is False:
            return None

        if self._redis is None and self.redis_url:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                # Test connection
                await self._redis.ping()
                self._redis_available = True
                logger.info("Redis connected for rate limiting")
            except ImportError:
                logger.warning("redis package not installed, using in-memory rate limiting")
                self._redis_available = False
                return None
            except Exception as e:
                logger.warning(
                    "Redis connection failed, using in-memory rate limiting",
                    error=str(e),
                )
                self._redis_available = False
                return None

        return self._redis

    async def check(
        self,
        identifier: str,
        cost: int = 1,
    ) -> Tuple[bool, int, int]:
        """
        Check if a request is allowed under the rate limit.

        Uses sliding window algorithm:
        - ZADD with timestamp as score to track requests
        - ZREMRANGEBYSCORE to remove expired entries
        - ZCARD to count current requests

        Args:
            identifier: Unique identifier for the rate limit (e.g., IP, user ID)
            cost: Number of "requests" this operation costs (default 1)

        Returns:
            Tuple of (allowed, remaining_requests, seconds_until_reset)
        """
        redis_client = await self._get_redis()

        if redis_client:
            return await self._check_redis(redis_client, identifier, cost)
        else:
            return await self._check_memory(identifier, cost)

    async def _check_redis(
        self,
        redis_client: "redis.asyncio.Redis",
        identifier: str,
        cost: int,
    ) -> Tuple[bool, int, int]:
        """Check rate limit using Redis ZADD sliding window."""
        key = f"{self.key_prefix}{identifier}"
        now = time.time()
        window_start = now - self.window_seconds

        try:
            # Use pipeline for atomic operations
            pipe = redis_client.pipeline()

            # Remove expired entries
            pipe.zremrangebyscore(key, "-inf", window_start)

            # Count current entries
            pipe.zcard(key)

            # Execute pipeline
            results = await pipe.execute()
            current_count = results[1]

            # Check if allowed
            if current_count + cost > self.max_requests:
                # Get the oldest entry to calculate reset time
                oldest = await redis_client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    reset_time = int(oldest[0][1] + self.window_seconds - now)
                else:
                    reset_time = self.window_seconds
                remaining = max(0, self.max_requests - current_count)
                return False, remaining, max(1, reset_time)

            # Add new entry(ies)
            for i in range(cost):
                await redis_client.zadd(key, {f"{now}:{i}": now})

            # Set expiry on the key
            await redis_client.expire(key, self.window_seconds + 1)

            remaining = self.max_requests - current_count - cost
            return True, max(0, remaining), self.window_seconds

        except Exception as e:
            logger.error(
                "Redis rate limit check failed, falling back to memory",
                error=str(e),
                identifier=identifier,
            )
            # Fallback to memory on Redis error
            return await self._check_memory(identifier, cost)

    def _cleanup_memory_store(self, now: float) -> None:
        """
        Remove expired entries and evict oldest keys if the store exceeds
        MAX_MEMORY_ENTRIES to prevent unbounded memory growth.

        Must be called while holding self._memory_lock.
        """
        window_start = now - self.window_seconds

        # First pass: remove expired timestamps from all keys and delete empty keys
        empty_keys = []
        for key in list(self._memory_store.keys()):
            self._memory_store[key] = [
                t for t in self._memory_store[key]
                if t > window_start
            ]
            if not self._memory_store[key]:
                empty_keys.append(key)

        for key in empty_keys:
            del self._memory_store[key]

        # Second pass: if still over limit, evict the oldest half of entries
        if len(self._memory_store) > MAX_MEMORY_ENTRIES:
            logger.warning(
                "In-memory rate limit store exceeded max entries, evicting oldest half",
                current_entries=len(self._memory_store),
                max_entries=MAX_MEMORY_ENTRIES,
            )
            # Sort keys by their oldest timestamp (most stale first)
            sorted_keys = sorted(
                self._memory_store.keys(),
                key=lambda k: min(self._memory_store[k]) if self._memory_store[k] else 0,
            )
            # Remove the oldest half
            keys_to_remove = sorted_keys[: len(sorted_keys) // 2]
            for key in keys_to_remove:
                del self._memory_store[key]

    async def _check_memory(
        self,
        identifier: str,
        cost: int,
    ) -> Tuple[bool, int, int]:
        """Check rate limit using in-memory storage."""
        now = time.time()
        window_start = now - self.window_seconds

        async with self._memory_lock:
            # Periodic cleanup when store grows large
            if len(self._memory_store) > MAX_MEMORY_ENTRIES:
                self._cleanup_memory_store(now)

            # Clean old entries for this identifier
            self._memory_store[identifier] = [
                t for t in self._memory_store[identifier]
                if t > window_start
            ]

            current_count = len(self._memory_store[identifier])

            # Check if allowed
            if current_count + cost > self.max_requests:
                if self._memory_store[identifier]:
                    oldest = min(self._memory_store[identifier])
                    reset_time = int(oldest + self.window_seconds - now)
                else:
                    reset_time = self.window_seconds
                remaining = max(0, self.max_requests - current_count)
                return False, remaining, max(1, reset_time)

            # Add new entries
            for _ in range(cost):
                self._memory_store[identifier].append(now)

            remaining = self.max_requests - current_count - cost
            return True, max(0, remaining), self.window_seconds

    async def reset(self, identifier: str) -> bool:
        """
        Reset rate limit for a specific identifier.

        Args:
            identifier: The identifier to reset

        Returns:
            True if reset was successful
        """
        redis_client = await self._get_redis()

        if redis_client:
            try:
                key = f"{self.key_prefix}{identifier}"
                await redis_client.delete(key)
                logger.info("Rate limit reset (Redis)", identifier=identifier)
                return True
            except Exception as e:
                logger.error("Failed to reset rate limit in Redis", error=str(e))
                return False
        else:
            async with self._memory_lock:
                if identifier in self._memory_store:
                    del self._memory_store[identifier]
                    logger.info("Rate limit reset (memory)", identifier=identifier)
                return True

    async def get_status(
        self,
        identifier: str,
    ) -> Tuple[int, int, int]:
        """
        Get current rate limit status for an identifier.

        Args:
            identifier: The identifier to check

        Returns:
            Tuple of (current_count, max_requests, seconds_until_reset)
        """
        redis_client = await self._get_redis()
        now = time.time()
        window_start = now - self.window_seconds

        if redis_client:
            try:
                key = f"{self.key_prefix}{identifier}"
                await redis_client.zremrangebyscore(key, "-inf", window_start)
                current_count = await redis_client.zcard(key)

                oldest = await redis_client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    reset_time = int(oldest[0][1] + self.window_seconds - now)
                else:
                    reset_time = self.window_seconds

                return current_count, self.max_requests, max(1, reset_time)
            except Exception as e:
                logger.error("Failed to get rate limit status from Redis", error=str(e))

        # Fallback to memory
        async with self._memory_lock:
            self._memory_store[identifier] = [
                t for t in self._memory_store[identifier]
                if t > window_start
            ]
            current_count = len(self._memory_store[identifier])

            if self._memory_store[identifier]:
                oldest = min(self._memory_store[identifier])
                reset_time = int(oldest + self.window_seconds - now)
            else:
                reset_time = self.window_seconds

            return current_count, self.max_requests, max(1, reset_time)

    async def close(self) -> None:
        """Close Redis connection if open."""
        if self._redis:
            try:
                await self._redis.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.warning("Error closing Redis connection", error=str(e))
            finally:
                self._redis = None
                self._redis_available = None


# Global rate limiter instance (lazy initialization)
_rate_limiter: Optional[DistributedRateLimiter] = None


def get_rate_limiter() -> DistributedRateLimiter:
    """Get global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        from app.config import settings

        _rate_limiter = DistributedRateLimiter(
            redis_url=settings.redis_url,
            max_requests=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window,
        )
    return _rate_limiter
