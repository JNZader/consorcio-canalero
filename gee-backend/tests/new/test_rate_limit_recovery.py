"""Redis-backed rate limiting recovers after a bounded outage cooldown."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.rate_limit import DistributedRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_retries_redis_after_cooldown(monkeypatch) -> None:
    clock = [100.0]
    monkeypatch.setattr("app.core.rate_limit.time.monotonic", lambda: clock[0])

    failed = AsyncMock()
    failed.ping.side_effect = ConnectionError("redis down")
    recovered = AsyncMock()
    recovered.ping.return_value = True

    limiter = DistributedRateLimiter(
        redis_url="redis://fake",
        redis_retry_cooldown_seconds=5.0,
    )
    import redis.asyncio as aioredis

    with patch.object(aioredis, "from_url", side_effect=[failed, recovered]) as from_url:
        assert await limiter._get_redis() is None
        assert await limiter._get_redis() is None
        assert from_url.call_count == 1

        clock[0] += 5.1
        assert await limiter._get_redis() is recovered
        assert from_url.call_count == 2
