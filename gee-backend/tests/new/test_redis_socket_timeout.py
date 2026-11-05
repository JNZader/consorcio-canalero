"""R1-003: Redis clients must time out instead of hanging the rate limiter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.redis_client import (
    REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS,
    REDIS_SOCKET_TIMEOUT_SECONDS,
)


def _assert_timeouts(kwargs: dict) -> None:
    assert kwargs["socket_timeout"] == REDIS_SOCKET_TIMEOUT_SECONDS
    assert kwargs["socket_connect_timeout"] == REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_json_cache_and_rate_limiter_pass_socket_timeouts() -> None:
    from app.core.cache import JSONCache
    from app.core.rate_limit import DistributedRateLimiter

    seen: list[dict] = []

    def from_url(url, **kwargs):
        seen.append(kwargs)
        client = AsyncMock()
        client.ping = AsyncMock()
        return client

    with patch("redis.asyncio.from_url", side_effect=from_url):
        cache = JSONCache(redis_url="redis://localhost:6379/0")
        limiter = DistributedRateLimiter(redis_url="redis://localhost:6379/0")
        assert await cache._get_redis() is not None
        assert await limiter._get_redis() is not None

    assert len(seen) == 2
    for kwargs in seen:
        _assert_timeouts(kwargs)
        assert kwargs["decode_responses"] is True


def test_bytes_cache_and_circuit_store_pass_socket_timeouts() -> None:
    from app.core.cache import BytesCache
    from app.domains.geo.rainfall.adapters.resilience import RedisCircuitStore

    seen: list[dict] = []

    def from_url(url, **kwargs):
        seen.append(kwargs)
        client = MagicMock()
        client.ping.return_value = True
        return client

    with patch("redis.Redis.from_url", side_effect=from_url):
        cache = BytesCache(redis_url="redis://localhost:6379/0")
        assert cache._get_redis() is not None
        RedisCircuitStore("redis://localhost:6379/0")

    assert len(seen) == 2
    _assert_timeouts(seen[0])
    assert seen[0]["decode_responses"] is False
    _assert_timeouts(seen[1])
    assert seen[1]["decode_responses"] is True
