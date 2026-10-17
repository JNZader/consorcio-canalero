"""Redis and in-memory branches of the distributed rate limiter.

The backend pytest job has no Redis service, so the sliding-window client
never ran there and ``app/core/rate_limit.py`` stayed under the 61% floor
(the higher figure came from the deploy job, which does have Redis). These
tests drive that client through a fake so the floor holds without a server.
"""

from __future__ import annotations

import builtins
from typing import Optional
from unittest.mock import patch

import pytest
import redis.asyncio as aioredis

from app.core.rate_limit import DistributedRateLimiter

NOW = 1_000_000.0


class _Pipe:
    def __init__(self, client: "_Redis") -> None:
        self._client = client
        self._ops: list[tuple] = []

    def zremrangebyscore(self, key: str, _min: str, max_score: float) -> "_Pipe":
        self._ops.append(("zrem", key, max_score))
        return self

    def zcard(self, key: str) -> "_Pipe":
        self._ops.append(("zcard", key))
        return self

    def zadd(self, key: str, mapping: dict[str, float]) -> "_Pipe":
        self._ops.append(("zadd", key, mapping))
        return self

    def expire(self, key: str, seconds: int) -> "_Pipe":
        self._ops.append(("expire", key, seconds))
        return self

    async def execute(self) -> list[object]:
        if self._client.execute_error is not None:
            raise self._client.execute_error
        results: list[object] = []
        for kind, *args in self._ops:
            if kind == "zrem":
                results.append(self._client.trim(args[0], args[1]))
            elif kind == "zcard":
                results.append(self._client.count(args[0]))
            elif kind == "zadd":
                results.append(self._client.add(args[0], args[1]))
            else:
                self._client.expires[args[0]] = args[1]
                results.append(True)
        return results


class _Redis:
    """Just enough of redis.asyncio for the sliding-window limiter."""

    def __init__(
        self,
        *,
        ping_error: Optional[Exception] = None,
        execute_error: Optional[Exception] = None,
        delete_error: Optional[Exception] = None,
        close_error: Optional[Exception] = None,
        direct_error: Optional[Exception] = None,
    ) -> None:
        self.zsets: dict[str, dict[str, float]] = {}
        self.expires: dict[str, int] = {}
        self.ping_error = ping_error
        self.execute_error = execute_error
        self.delete_error = delete_error
        self.close_error = close_error
        self.direct_error = direct_error
        self.close_attempts = 0
        self.closed = False

    def pipeline(self) -> _Pipe:
        return _Pipe(self)

    async def ping(self) -> bool:
        if self.ping_error is not None:
            raise self.ping_error
        return True

    def trim(self, key: str, max_score: float) -> int:
        current = self.zsets.get(key, {})
        kept = {member: score for member, score in current.items() if score > float(max_score)}
        removed = len(current) - len(kept)
        if kept:
            self.zsets[key] = kept
        else:
            self.zsets.pop(key, None)
        return removed

    def count(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    def add(self, key: str, mapping: dict[str, float]) -> int:
        bucket = self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[member] = float(score)
        return len(mapping)

    async def zremrangebyscore(self, key: str, _min: str, max_score: float) -> int:
        if self.direct_error is not None:
            raise self.direct_error
        return self.trim(key, max_score)

    async def zcard(self, key: str) -> int:
        if self.direct_error is not None:
            raise self.direct_error
        return self.count(key)

    async def zrange(self, key: str, start: int, end: int, withscores: bool = False) -> list:
        items = sorted(self.zsets.get(key, {}).items(), key=lambda item: item[1])
        window = items[start : end + 1 if end >= 0 else None]
        if withscores:
            return window
        return [member for member, _score in window]

    async def delete(self, key: str) -> int:
        if self.delete_error is not None:
            raise self.delete_error
        self.zsets.pop(key, None)
        return 1

    async def close(self) -> None:
        self.close_attempts += 1
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


def _freeze(monkeypatch: pytest.MonkeyPatch, now: float = NOW) -> float:
    monkeypatch.setattr("app.core.rate_limit.time.time", lambda: now)
    return now


def _limiter(**overrides: object) -> DistributedRateLimiter:
    params: dict[str, object] = {
        "redis_url": "redis://fake",
        "max_requests": 5,
        "window_seconds": 60,
    }
    params.update(overrides)
    return DistributedRateLimiter(**params)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_redis_sliding_window_allows_then_denies(monkeypatch: pytest.MonkeyPatch) -> None:
    now = _freeze(monkeypatch)
    client = _Redis()
    limiter = _limiter(max_requests=3)

    with patch.object(aioredis, "from_url", return_value=client):
        allowed, remaining, reset = await limiter.check("user", cost=2)
        denied, denied_remaining, retry = await limiter.check("user", cost=2)

    assert (allowed, remaining, reset) == (True, 1, 60)
    assert client.zsets["ratelimit:user"] == {f"{now}:0": now, f"{now}:1": now}
    assert client.expires["ratelimit:user"] == 61
    assert denied is False
    assert denied_remaining == 1
    assert retry == 60


@pytest.mark.asyncio
async def test_redis_deny_with_no_oldest_entry_uses_the_full_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(monkeypatch)
    client = _Redis()
    limiter = _limiter(max_requests=0)

    with patch.object(aioredis, "from_url", return_value=client):
        allowed, remaining, reset = await limiter.check("user", cost=1)

    assert (allowed, remaining, reset) == (False, 0, 60)
    assert client.zsets == {}


@pytest.mark.asyncio
async def test_redis_non_positive_cost_does_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch)
    client = _Redis()
    limiter = _limiter()

    with patch.object(aioredis, "from_url", return_value=client):
        allowed, remaining, reset = await limiter.check("user", cost=0)

    assert (allowed, remaining, reset) == (True, 5, 60)
    assert client.zsets == {}
    assert client.expires == {}


@pytest.mark.asyncio
async def test_redis_check_error_falls_back_to_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(monkeypatch)
    client = _Redis(execute_error=ConnectionError("boom"), close_error=RuntimeError("close"))
    limiter = _limiter(max_requests=1)

    with patch.object(aioredis, "from_url", return_value=client):
        first = await limiter.check("user", cost=1)
        second = await limiter.check("user", cost=1)

    assert first[0] is True
    assert second[0] is False
    assert second[2] >= 1
    assert client.close_attempts == 1
    assert limiter._redis_available is False


@pytest.mark.asyncio
async def test_redis_retries_after_the_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [100.0]
    monkeypatch.setattr("app.core.rate_limit.time.monotonic", lambda: clock[0])
    down = _Redis(ping_error=ConnectionError("down"), close_error=OSError("close"))
    recovered = _Redis()
    limiter = _limiter(redis_retry_cooldown_seconds=5.0)

    with patch.object(aioredis, "from_url", side_effect=[down, recovered]) as from_url:
        assert await limiter._get_redis() is None
        assert await limiter._get_redis() is None
        assert from_url.call_count == 1
        assert down.close_attempts == 1

        clock[0] += 5.1
        assert await limiter._get_redis() is recovered
        assert from_url.call_count == 2


@pytest.mark.asyncio
async def test_missing_redis_package_uses_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def guarded(name: str, *args: object, **kwargs: object) -> object:
        if name == "redis.asyncio":
            raise ImportError("redis package not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    limiter = _limiter()

    assert await limiter._get_redis() is None
    assert limiter._redis_available is False
    allowed, _remaining, _reset = await limiter.check("user", cost=1)
    assert allowed is True


@pytest.mark.asyncio
async def test_reset_on_redis_deletes_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    now = _freeze(monkeypatch)
    client = _Redis()
    limiter = _limiter()

    with patch.object(aioredis, "from_url", return_value=client):
        await limiter.check("user", cost=1)
        assert await limiter.reset("user") is True

    assert "ratelimit:user" not in client.zsets
    assert f"{now}:0" not in client.zsets.get("ratelimit:user", {})


@pytest.mark.asyncio
async def test_reset_redis_error_returns_false_without_opening_the_limit() -> None:
    client = _Redis(delete_error=ConnectionError("nope"), close_error=RuntimeError("close"))
    limiter = _limiter()

    with patch.object(aioredis, "from_url", return_value=client):
        assert await limiter.reset("user") is False

    assert client.close_attempts == 1
    assert limiter._redis is None
    assert limiter._redis_available is False


@pytest.mark.asyncio
async def test_reset_memory_drops_the_bucket_and_missing_keys() -> None:
    limiter = DistributedRateLimiter(redis_url=None, max_requests=5, window_seconds=60)
    await limiter.check("user", cost=1)

    assert await limiter.reset("user") is True
    assert "user" not in limiter._memory_store
    assert await limiter.reset("user") is True


@pytest.mark.asyncio
async def test_get_status_reads_redis_then_an_empty_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(monkeypatch)
    client = _Redis()
    limiter = _limiter(max_requests=5)

    with patch.object(aioredis, "from_url", return_value=client):
        empty = await limiter.get_status("user")
        await limiter.check("user", cost=1)
        occupied = await limiter.get_status("user")

    assert empty == (0, 5, 60)
    assert occupied == (1, 5, 60)


@pytest.mark.asyncio
async def test_get_status_redis_error_falls_back_to_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = _freeze(monkeypatch)
    client = _Redis(direct_error=ConnectionError("status"), close_error=RuntimeError("close"))
    limiter = _limiter(max_requests=4)
    limiter._memory_store["user"] = [now - 10]

    with patch.object(aioredis, "from_url", return_value=client):
        current, maximum, reset = await limiter.get_status("user")

    assert (current, maximum) == (1, 4)
    assert reset == 50
    assert client.close_attempts == 1

    # Redis stays down for the cooldown, so a later read is pure memory.
    vacant, _maximum, vacant_reset = await limiter.get_status("other")
    assert vacant == 0
    assert vacant_reset == 60


@pytest.mark.asyncio
async def test_close_clears_the_client_and_swallows_close_errors() -> None:
    healthy = _Redis()
    broken = _Redis(close_error=RuntimeError("close"))
    ok = _limiter()
    failing = _limiter()

    with patch.object(aioredis, "from_url", side_effect=[healthy, broken]):
        assert await ok._get_redis() is healthy
        assert await failing._get_redis() is broken

    await ok.close()
    await failing.close()
    await ok.close()

    assert healthy.closed is True
    assert ok._redis is None
    assert failing._redis is None
    assert broken.close_attempts == 1


@pytest.mark.asyncio
async def test_memory_store_drops_expired_keys_and_evicts_the_oldest_half(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = _freeze(monkeypatch)
    monkeypatch.setattr("app.core.rate_limit.MAX_MEMORY_ENTRIES", 2)
    limiter = DistributedRateLimiter(redis_url=None, max_requests=10, window_seconds=60)
    limiter._memory_store["expired-a"] = [now - 120]
    limiter._memory_store["expired-b"] = [now - 120]
    limiter._memory_store["older"] = [now - 30]
    limiter._memory_store["middle"] = [now - 20]
    limiter._memory_store["newer"] = [now - 10]

    allowed, _remaining, _reset = await limiter.check("incoming", cost=1)

    assert allowed is True
    assert "expired-a" not in limiter._memory_store
    assert "expired-b" not in limiter._memory_store
    assert "older" not in limiter._memory_store
    assert "incoming" in limiter._memory_store


@pytest.mark.asyncio
async def test_memory_deny_with_an_empty_bucket_uses_the_full_window() -> None:
    limiter = DistributedRateLimiter(redis_url=None, max_requests=0, window_seconds=60)

    allowed, remaining, reset = await limiter.check("nobody", cost=1)

    assert (allowed, remaining, reset) == (False, 0, 60)


@pytest.mark.asyncio
async def test_getters_cache_one_limiter_per_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.core.rate_limit as module
    from app.config import settings

    monkeypatch.setattr(module, "_rate_limiter", None)
    monkeypatch.setattr(module, "_auth_rate_limiter", None)

    generic = module.get_rate_limiter()
    auth = module.get_auth_rate_limiter()

    assert generic is module.get_rate_limiter()
    assert auth is module.get_auth_rate_limiter()
    assert generic.max_requests == settings.rate_limit_requests
    assert auth.max_requests == settings.auth_rate_limit_requests
    assert auth.key_prefix == "ratelimit:auth:"
    assert generic is not auth
