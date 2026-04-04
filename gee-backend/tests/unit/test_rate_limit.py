"""Unit tests for app.core.rate_limit — DistributedRateLimiter (in-memory mode).

Tests the sliding window algorithm, cleanup, reset, status, and edge cases.
Redis is NOT available in unit tests — all paths exercise the in-memory fallback.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.rate_limit import DistributedRateLimiter, MAX_MEMORY_ENTRIES


@pytest.fixture
def limiter():
    """Create a limiter with no Redis (in-memory only)."""
    return DistributedRateLimiter(
        redis_url=None,
        max_requests=5,
        window_seconds=10,
    )


def run(coro):
    """Helper to run async code in sync tests."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_values(self):
        lim = DistributedRateLimiter()
        assert lim.max_requests == 100
        assert lim.window_seconds == 60
        assert lim.key_prefix == "ratelimit:"
        assert lim._redis is None
        assert lim._redis_available is None

    def test_custom_values(self):
        lim = DistributedRateLimiter(
            redis_url="redis://localhost",
            max_requests=10,
            window_seconds=30,
            key_prefix="custom:",
        )
        assert lim.redis_url == "redis://localhost"
        assert lim.max_requests == 10
        assert lim.window_seconds == 30
        assert lim.key_prefix == "custom:"


# ---------------------------------------------------------------------------
# _get_redis
# ---------------------------------------------------------------------------


class TestGetRedis:
    def test_returns_none_when_no_redis_url(self, limiter):
        result = run(limiter._get_redis())
        assert result is None

    def test_returns_none_when_redis_marked_unavailable(self):
        lim = DistributedRateLimiter(redis_url="redis://fake")
        lim._redis_available = False
        result = run(lim._get_redis())
        assert result is None

    def test_marks_unavailable_on_connection_failure(self):
        lim = DistributedRateLimiter(redis_url="redis://nonexistent:9999")
        result = run(lim._get_redis())
        assert result is None
        assert lim._redis_available is False


# ---------------------------------------------------------------------------
# check() — in-memory sliding window
# ---------------------------------------------------------------------------


class TestCheckMemory:
    def test_allows_within_limit(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)
        allowed, remaining, reset = run(lim.check("user:1"))
        assert allowed is True
        assert remaining == 4
        assert reset == 10

    def test_tracks_multiple_requests(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)

        async def multi():
            for _ in range(4):
                await lim.check("user:2")
            return await lim.check("user:2")

        allowed, remaining, reset = run(multi())
        assert allowed is True
        assert remaining == 0

    def test_blocks_over_limit(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)

        async def exhaust():
            for _ in range(5):
                await lim.check("user:3")
            return await lim.check("user:3")

        allowed, remaining, reset = run(exhaust())
        assert allowed is False
        assert remaining == 0

    def test_cost_parameter(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)

        async def cost_test():
            allowed1, remaining1, _ = await lim.check("user:4", cost=3)
            allowed2, remaining2, _ = await lim.check("user:4", cost=3)
            return allowed1, remaining1, allowed2, remaining2

        a1, r1, a2, r2 = run(cost_test())
        assert a1 is True
        assert r1 == 2
        assert a2 is False

    def test_different_identifiers_independent(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)

        async def test():
            for _ in range(5):
                await lim.check("user:A")
            return await lim.check("user:B")

        allowed, _, _ = run(test())
        assert allowed is True

    def test_expired_entries_cleaned(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=2, window_seconds=1)

        async def test():
            await lim.check("user:5")
            await lim.check("user:5")
            a1, _, _ = await lim.check("user:5")
            return a1

        blocked = run(test())
        assert blocked is False

        time.sleep(1.1)

        allowed, remaining, _ = run(lim.check("user:5"))
        assert allowed is True

    def test_reset_time_when_blocked(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=1, window_seconds=60)

        async def test():
            await lim.check("user:6")
            return await lim.check("user:6")

        allowed, remaining, reset = run(test())
        assert allowed is False
        assert 1 <= reset <= 60

    def test_reset_time_when_blocked_and_store_empty(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=0, window_seconds=30)
        allowed, remaining, reset = run(lim.check("user:7"))
        assert allowed is False
        assert reset == 30


# ---------------------------------------------------------------------------
# _cleanup_memory_store
# ---------------------------------------------------------------------------


class TestCleanupMemoryStore:
    def test_removes_expired_entries(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)
        now = time.time()
        lim._memory_store["old_user"] = [now - 100]
        lim._memory_store["fresh_user"] = [now]

        lim._cleanup_memory_store(now)
        assert "old_user" not in lim._memory_store
        assert "fresh_user" in lim._memory_store

    def test_evicts_oldest_half_when_over_max(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)
        now = time.time()
        for i in range(MAX_MEMORY_ENTRIES + 100):
            lim._memory_store[f"user:{i}"] = [now]

        lim._cleanup_memory_store(now)
        assert len(lim._memory_store) <= (MAX_MEMORY_ENTRIES + 100) // 2 + 1

    def test_cleanup_triggered_on_check(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=100, window_seconds=60)
        now = time.time()
        for i in range(MAX_MEMORY_ENTRIES + 10):
            lim._memory_store[f"u:{i}"] = [now]

        run(lim.check("trigger_user"))
        assert len(lim._memory_store) <= MAX_MEMORY_ENTRIES + 1


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_identifier(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)

        async def test():
            await lim.check("user:reset")
            return await lim.reset("user:reset")

        result = run(test())
        assert result is True

    def test_reset_nonexistent_identifier(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)
        result = run(lim.reset("user:nonexistent"))
        assert result is True

    def test_reset_allows_new_requests(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)

        async def test():
            for _ in range(5):
                await lim.check("user:exhaust")
            a1, _, _ = await lim.check("user:exhaust")
            assert a1 is False

            await lim.reset("user:exhaust")
            a2, remaining, _ = await lim.check("user:exhaust")
            return a2, remaining

        allowed, remaining = run(test())
        assert allowed is True
        assert remaining == 4


# ---------------------------------------------------------------------------
# get_status()
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_status_empty_identifier(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)
        count, max_req, reset = run(lim.get_status("user:new"))
        assert count == 0
        assert max_req == 5
        assert reset == 10

    def test_status_with_requests(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)

        async def test():
            await lim.check("user:status")
            await lim.check("user:status")
            return await lim.get_status("user:status")

        count, max_req, reset = run(test())
        assert count == 2
        assert max_req == 5

    def test_status_shows_reset_time(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)

        async def test():
            await lim.check("user:st")
            return await lim.get_status("user:st")

        _, _, reset = run(test())
        assert 1 <= reset <= 10


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


class TestClose:
    def test_close_when_no_redis(self):
        lim = DistributedRateLimiter(redis_url=None)
        run(lim.close())
        assert lim._redis is None

    def test_close_resets_state(self):
        lim = DistributedRateLimiter(redis_url=None)
        mock_redis = AsyncMock()
        lim._redis = mock_redis
        lim._redis_available = True

        run(lim.close())
        mock_redis.close.assert_awaited_once()
        assert lim._redis is None
        assert lim._redis_available is None

    def test_close_handles_error(self):
        lim = DistributedRateLimiter(redis_url=None)
        mock_redis = AsyncMock()
        mock_redis.close.side_effect = ConnectionError("already closed")
        lim._redis = mock_redis
        lim._redis_available = True

        run(lim.close())
        assert lim._redis is None


# ---------------------------------------------------------------------------
# _check_redis paths
# ---------------------------------------------------------------------------


class TestCheckRedis:
    def _make_redis_and_pipe(self, execute_result):
        """Create redis + pipeline mocks with correct sync/async split."""
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
        mock_pipe.zcard = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(return_value=execute_result)

        # pipeline() is a sync method on the redis client
        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        # These are async on the redis client directly
        mock_redis.zrange = AsyncMock(return_value=[])
        mock_redis.zadd = AsyncMock()
        mock_redis.expire = AsyncMock()
        return mock_redis, mock_pipe

    def test_falls_back_to_memory_on_redis_error(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)
        mock_redis, mock_pipe = self._make_redis_and_pipe(None)
        mock_pipe.execute.side_effect = ConnectionError("redis down")

        allowed, remaining, reset = run(lim._check_redis(mock_redis, "user:fb", 1))
        assert allowed is True

    def test_redis_check_blocked(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=2, window_seconds=10)
        mock_redis, _ = self._make_redis_and_pipe([0, 3])
        mock_redis.zrange = AsyncMock(return_value=[("ts:0", time.time() - 5)])

        allowed, remaining, reset = run(lim._check_redis(mock_redis, "user:block", 1))
        assert allowed is False
        assert remaining == 0

    def test_redis_check_blocked_no_oldest(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=2, window_seconds=10)
        mock_redis, _ = self._make_redis_and_pipe([0, 3])
        mock_redis.zrange = AsyncMock(return_value=[])

        allowed, remaining, reset = run(lim._check_redis(mock_redis, "user:block2", 1))
        assert allowed is False
        assert reset == 10

    def test_redis_check_allowed(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)
        mock_redis, _ = self._make_redis_and_pipe([0, 2])

        allowed, remaining, reset = run(lim._check_redis(mock_redis, "user:ok", 1))
        assert allowed is True
        assert remaining == 2
        mock_redis.zadd.assert_awaited()
        mock_redis.expire.assert_awaited()

    def test_redis_check_allowed_with_cost(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=10, window_seconds=60)
        mock_redis, _ = self._make_redis_and_pipe([0, 5])

        allowed, remaining, reset = run(lim._check_redis(mock_redis, "user:cost", 3))
        assert allowed is True
        assert remaining == 2  # 10 - 5 - 3
        assert mock_redis.zadd.await_count == 3


# ---------------------------------------------------------------------------
# get_status with Redis
# ---------------------------------------------------------------------------


class TestGetStatusRedis:
    def test_redis_status_with_entries(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=10, window_seconds=60)
        mock_redis = AsyncMock()
        mock_redis.zremrangebyscore = AsyncMock()
        mock_redis.zcard = AsyncMock(return_value=3)
        mock_redis.zrange = AsyncMock(return_value=[("ts:0", time.time() - 10)])

        async def test():
            lim._get_redis = AsyncMock(return_value=mock_redis)
            return await lim.get_status("user:rs")

        count, max_req, reset = run(test())
        assert count == 3
        assert max_req == 10

    def test_redis_status_empty(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=10, window_seconds=60)
        mock_redis = AsyncMock()
        mock_redis.zremrangebyscore = AsyncMock()
        mock_redis.zcard = AsyncMock(return_value=0)
        mock_redis.zrange = AsyncMock(return_value=[])

        async def test():
            lim._get_redis = AsyncMock(return_value=mock_redis)
            return await lim.get_status("user:empty")

        count, max_req, reset = run(test())
        assert count == 0
        assert reset == 60

    def test_redis_status_falls_back_on_error(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=10, window_seconds=60)
        mock_redis = AsyncMock()
        mock_redis.zremrangebyscore = AsyncMock(side_effect=ConnectionError("nope"))

        async def test():
            lim._get_redis = AsyncMock(return_value=mock_redis)
            return await lim.get_status("user:fall")

        count, max_req, reset = run(test())
        assert count == 0


# ---------------------------------------------------------------------------
# reset() with Redis
# ---------------------------------------------------------------------------


class TestResetRedis:
    def test_redis_reset(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10, key_prefix="rl:")
        mock_redis = AsyncMock()

        async def test():
            lim._get_redis = AsyncMock(return_value=mock_redis)
            return await lim.reset("user:rr")

        result = run(test())
        assert result is True
        mock_redis.delete.assert_awaited_once_with("rl:user:rr")

    def test_redis_reset_failure(self):
        lim = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=10)
        mock_redis = AsyncMock()
        mock_redis.delete.side_effect = ConnectionError("fail")

        async def test():
            lim._get_redis = AsyncMock(return_value=mock_redis)
            return await lim.reset("user:fail")

        result = run(test())
        assert result is False


# ---------------------------------------------------------------------------
# get_rate_limiter() global singleton
# ---------------------------------------------------------------------------


class TestGetRateLimiter:
    @patch("app.core.rate_limit._rate_limiter", None)
    def test_creates_singleton(self):
        mock_settings = MagicMock()
        mock_settings.redis_url = None
        mock_settings.rate_limit_requests = 100
        mock_settings.rate_limit_window = 60

        with patch("app.config.settings", mock_settings):
            from app.core.rate_limit import get_rate_limiter
            import app.core.rate_limit as rl_mod

            rl_mod._rate_limiter = None
            lim = get_rate_limiter()
            assert isinstance(lim, DistributedRateLimiter)
            rl_mod._rate_limiter = None  # cleanup
