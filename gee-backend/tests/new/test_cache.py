"""Unit tests for app.core.cache.JSONCache.

These tests run the cache against an in-process AsyncMock that mimics the
``redis.asyncio.Redis`` surface we actually use (``ping``, ``get``, ``setex``,
``delete``, ``scan_iter``). Goal: exercise the hit / miss / error paths
without requiring a running Redis instance.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core.cache import JSONCache


def _stub_redis(*, ping_ok: bool = True) -> AsyncMock:
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True if ping_ok else False)
    if not ping_ok:
        redis.ping.side_effect = ConnectionError("no redis")
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    return redis


def _patch_aioredis_from_url(stub: AsyncMock):
    """Patch ``redis.asyncio.from_url`` to return ``stub``."""
    import redis.asyncio as aioredis

    return patch.object(aioredis, "from_url", return_value=stub)


@pytest.mark.asyncio
async def test_cache_miss_returns_none():
    cache = JSONCache(redis_url="redis://fake")
    stub = _stub_redis()
    with _patch_aioredis_from_url(stub):
        result = await cache.get("k")
    assert result is None
    stub.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_hit_returns_decoded_json():
    cache = JSONCache(redis_url="redis://fake")
    stub = _stub_redis()
    stub.get.return_value = json.dumps({"hello": "world"})
    with _patch_aioredis_from_url(stub):
        result = await cache.get("k")
    assert result == {"hello": "world"}


@pytest.mark.asyncio
async def test_cache_set_uses_setex_with_ttl():
    cache = JSONCache(redis_url="redis://fake")
    stub = _stub_redis()
    with _patch_aioredis_from_url(stub):
        ok = await cache.set("k", {"x": 1}, ttl_seconds=60)
    assert ok is True
    stub.setex.assert_awaited_once()
    full_key, ttl, payload = stub.setex.await_args.args
    assert full_key == "cache:k"
    assert ttl == 60
    assert json.loads(payload) == {"x": 1}


@pytest.mark.asyncio
async def test_cache_set_with_zero_ttl_is_noop():
    cache = JSONCache(redis_url="redis://fake")
    stub = _stub_redis()
    with _patch_aioredis_from_url(stub):
        ok = await cache.set("k", {}, ttl_seconds=0)
    assert ok is False
    stub.setex.assert_not_called()


@pytest.mark.asyncio
async def test_cache_no_redis_url_means_no_op():
    cache = JSONCache(redis_url=None)
    assert await cache.get("k") is None
    assert await cache.set("k", {"x": 1}, ttl_seconds=60) is False


@pytest.mark.asyncio
async def test_cache_redis_unreachable_falls_back_to_no_op():
    cache = JSONCache(redis_url="redis://fake")
    stub = _stub_redis(ping_ok=False)
    with _patch_aioredis_from_url(stub):
        # First call discovers Redis is dead, marks _redis_available=False
        first = await cache.get("k")
    assert first is None
    # Subsequent calls don't even try Redis
    assert await cache.get("k") is None
    assert await cache.set("k", {}, ttl_seconds=60) is False


@pytest.mark.asyncio
async def test_cache_set_skips_unserialisable_value():
    cache = JSONCache(redis_url="redis://fake")
    stub = _stub_redis()
    with _patch_aioredis_from_url(stub):
        ok = await cache.set("k", {"bad": object()}, ttl_seconds=60)
    assert ok is False
    stub.setex.assert_not_called()


@pytest.mark.asyncio
async def test_cache_delete_returns_true_when_key_existed():
    cache = JSONCache(redis_url="redis://fake")
    stub = _stub_redis()
    stub.delete = AsyncMock(return_value=1)
    with _patch_aioredis_from_url(stub):
        existed = await cache.delete("k")
    assert existed is True
    stub.delete.assert_awaited_once_with("cache:k")


@pytest.mark.asyncio
async def test_cache_get_handles_corrupt_json_as_miss():
    cache = JSONCache(redis_url="redis://fake")
    stub = _stub_redis()
    stub.get.return_value = "not-json{"
    with _patch_aioredis_from_url(stub):
        result = await cache.get("k")
    assert result is None


@pytest.mark.asyncio
async def test_cache_retries_redis_after_cooldown(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.core.cache.time.monotonic", lambda: clock[0])
    failed = _stub_redis(ping_ok=False)
    recovered = _stub_redis()
    recovered.get.return_value = json.dumps({"recovered": True})
    cache = JSONCache(redis_url="redis://fake", redis_retry_cooldown_seconds=5.0)

    import redis.asyncio as aioredis

    with patch.object(aioredis, "from_url", side_effect=[failed, recovered]) as from_url:
        assert await cache.get("k") is None
        assert await cache.get("k") is None
        assert from_url.call_count == 1
        clock[0] += 5.1
        assert await cache.get("k") == {"recovered": True}
        assert from_url.call_count == 2


@pytest.mark.asyncio
async def test_cache_pop_uses_atomic_getdel_on_redis():
    cache = JSONCache(redis_url="redis://fake")
    stub = _stub_redis()
    stub.getdel = AsyncMock(side_effect=[json.dumps({"access_token": "jwt-123"}), None])
    with _patch_aioredis_from_url(stub):
        first = await cache.pop("oauth:exchange:n1")
        second = await cache.pop("oauth:exchange:n1")
    assert first == {"access_token": "jwt-123"}
    assert second is None
    assert stub.getdel.await_count == 2


@pytest.mark.asyncio
async def test_cache_ephemeral_memory_fallback_is_single_use_and_expires(monkeypatch):
    clock = [500.0]
    monkeypatch.setattr("app.core.cache.time.monotonic", lambda: clock[0])
    cache = JSONCache(redis_url=None)

    assert await cache.set_ephemeral("k1", {"token": "abc"}, ttl_seconds=60) is True
    assert await cache.pop("k1") == {"token": "abc"}
    assert await cache.pop("k1") is None

    assert await cache.set_ephemeral("k2", {"token": "expired"}, ttl_seconds=10) is True
    clock[0] += 10.1
    assert await cache.pop("k2") is None
