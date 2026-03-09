import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import rate_limit
from app.core.rate_limit import DistributedRateLimiter


@pytest.mark.asyncio
async def test_memory_check_allows_until_limit_then_blocks(monkeypatch):
    limiter = DistributedRateLimiter(redis_url=None, max_requests=3, window_seconds=60)
    monkeypatch.setattr(time, "time", lambda: 1000.0)

    assert await limiter.check("ip:1") == (True, 2, 60)
    assert await limiter.check("ip:1") == (True, 1, 60)
    assert await limiter.check("ip:1") == (True, 0, 60)

    allowed, remaining, reset = await limiter.check("ip:1")
    assert allowed is False
    assert remaining == 0
    assert reset >= 1


def test_cleanup_memory_store_removes_expired_and_evicts_oldest(monkeypatch):
    limiter = DistributedRateLimiter(redis_url=None, max_requests=3, window_seconds=10)
    monkeypatch.setattr(rate_limit, "MAX_MEMORY_ENTRIES", 4)

    now = 100.0
    limiter._memory_store = {
        "old-empty": [50.0],
        "k1": [91.0],
        "k2": [92.0],
        "k3": [93.0],
        "k4": [94.0],
        "k5": [95.0],
    }

    limiter._cleanup_memory_store(now)

    assert "old-empty" not in limiter._memory_store
    assert len(limiter._memory_store) <= 4


@pytest.mark.asyncio
async def test_check_redis_allows_and_sets_expiry():
    limiter = DistributedRateLimiter(redis_url="redis://x", max_requests=3, window_seconds=60)
    redis_client = MagicMock()
    pipe = MagicMock()
    redis_client.pipeline.return_value = pipe
    pipe.execute = AsyncMock(return_value=[0, 1])
    redis_client.zadd = AsyncMock()
    redis_client.expire = AsyncMock()

    allowed, remaining, reset = await limiter._check_redis(redis_client, "u-1", 1)

    assert allowed is True
    assert remaining == 1
    assert reset == 60
    redis_client.zadd.assert_awaited_once()
    redis_client.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_redis_rejects_when_limit_exceeded():
    limiter = DistributedRateLimiter(redis_url="redis://x", max_requests=3, window_seconds=60)
    redis_client = MagicMock()
    pipe = MagicMock()
    redis_client.pipeline.return_value = pipe
    pipe.execute = AsyncMock(return_value=[0, 3])
    redis_client.zrange = AsyncMock(return_value=[("member", 1000.0)])

    allowed, remaining, reset = await limiter._check_redis(redis_client, "u-1", 1)

    assert allowed is False
    assert remaining == 0
    assert reset >= 1


@pytest.mark.asyncio
async def test_check_redis_falls_back_to_memory_on_error():
    limiter = DistributedRateLimiter(redis_url="redis://x", max_requests=3, window_seconds=60)
    redis_client = MagicMock()
    pipe = MagicMock()
    redis_client.pipeline.return_value = pipe
    pipe.execute = AsyncMock(side_effect=RuntimeError("redis down"))
    limiter._check_memory = AsyncMock(return_value=(True, 9, 30))

    result = await limiter._check_redis(redis_client, "u-1", 1)

    assert result == (True, 9, 30)
    limiter._check_memory.assert_awaited_once_with("u-1", 1)


@pytest.mark.asyncio
async def test_reset_and_status_in_memory_mode(monkeypatch):
    limiter = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=60)
    monkeypatch.setattr(time, "time", lambda: 2000.0)

    await limiter.check("user-1")
    await limiter.check("user-1")

    current, max_requests, reset = await limiter.get_status("user-1")
    assert current == 2
    assert max_requests == 5
    assert reset >= 1

    ok = await limiter.reset("user-1")
    assert ok is True
    assert "user-1" not in limiter._memory_store


@pytest.mark.asyncio
async def test_close_resets_redis_client_state():
    limiter = DistributedRateLimiter(redis_url="redis://x")
    limiter._redis = MagicMock()
    limiter._redis.close = AsyncMock()
    limiter._redis_available = True

    await limiter.close()

    assert limiter._redis is None
    assert limiter._redis_available is None
