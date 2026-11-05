"""Identical in-flight public GEE reads share one Earth Engine compute.

The cache is forced to miss, which is the TTL-expiry and Redis-down herd.
``_run_blocking`` is an async gate so the second caller is on the loop, not
racing a worker thread, when the assertion runs.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from fastapi import Response

from unittest.mock import AsyncMock, patch

from app.core.cache import JSONCache
from app.core.singleflight import SingleFlight
from app.domains.geo import public_map
from app.domains.geo import router_gee_support
from app.domains.geo.router_gee_support import (
    gee_layer_flight_key,
    get_gee_layer_impl,
    get_satellite_image_impl,
    satellite_image_flight_key,
)


TILE = "https://earthengine.googleapis.com/v1/projects/test/maps/{name}/tiles/{{z}}/{{x}}/{{y}}"


class _MissCache:
    """Redis-down cache: every read misses, and there is no cross-process lock."""

    def __init__(self) -> None:
        self.gets = 0

    async def get(self, key: str):
        self.gets += 1
        return None

    async def set(self, key: str, value: object, ttl_seconds: int) -> bool:
        return False

    async def acquire_lock(self, key: str, token: str, ttl_seconds: int):
        return None

    async def release_lock(self, key: str, token: str) -> None:
        return None


class _MemoryFlightCache:
    """Shared lock + value store standing in for Redis across two workers."""

    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.locks: dict[str, str] = {}
        self._mu = asyncio.Lock()

    async def get(self, key: str):
        async with self._mu:
            return self.values.get(key)

    async def set(self, key: str, value: object, ttl_seconds: int) -> bool:
        async with self._mu:
            self.values[key] = value
        return True

    async def acquire_lock(self, key: str, token: str, ttl_seconds: int):
        async with self._mu:
            if key in self.locks:
                return False
            self.locks[key] = token
            return True

    async def release_lock(self, key: str, token: str) -> None:
        async with self._mu:
            if self.locks.get(key) == token:
                del self.locks[key]


class _Settings:
    def __init__(self, raw: object) -> None:
        self.raw = raw

    def get_setting(self, _db: object, key: str):
        return self.raw


@pytest.fixture(autouse=True)
def _reset_flights():
    router_gee_support._gee_flights.reset()
    yield
    router_gee_support._gee_flights.reset()


def _explorer(get_image):
    explorer = type("Explorer", (), {"get_image": staticmethod(get_image)})
    return {"get_image_explorer": explorer}


def _image_payload(name: str) -> dict[str, object]:
    return {
        "tile_url": TILE.format(name=name),
        "visualization_description": "RGB",
        "images_count": 1,
    }


@pytest.mark.asyncio
async def test_cache_lock_uses_nx_and_releases_only_the_owner():
    cache = JSONCache(redis_url="redis://fake")
    stub = AsyncMock()
    stub.ping = AsyncMock(return_value=True)
    stub.set = AsyncMock(return_value=True)
    stub.eval = AsyncMock(return_value=1)
    with patch("redis.asyncio.from_url", return_value=stub):
        acquired = await cache.acquire_lock("gee:image:s2", "token-a", 240)
        await cache.release_lock("gee:image:s2", "token-a")
    assert acquired is True
    args, kwargs = stub.set.await_args
    assert args == ("cache:lock:gee:image:s2", "token-a")
    assert kwargs["nx"] is True
    assert kwargs["ex"] == 240
    eval_args = stub.eval.await_args.args
    assert eval_args[1] == 1
    assert eval_args[2] == "cache:lock:gee:image:s2"
    assert eval_args[3] == "token-a"
    assert "ARGV[1]" in eval_args[0]


@pytest.mark.asyncio
async def test_cache_lock_returns_false_when_held_and_none_without_redis():
    cache = JSONCache(redis_url="redis://fake")
    stub = AsyncMock()
    stub.ping = AsyncMock(return_value=True)
    stub.set = AsyncMock(return_value=None)
    with patch("redis.asyncio.from_url", return_value=stub):
        assert await cache.acquire_lock("gee:layer:zona", "token-b", 240) is False
    offline = JSONCache(redis_url=None)
    assert await offline.acquire_lock("gee:layer:zona", "token-b", 240) is None
    await offline.release_lock("gee:layer:zona", "token-b")


def test_flight_key_includes_every_argument_that_changes_the_image():
    base = dict(
        sensor="sentinel2",
        target_date=date(2026, 3, 5),
        days_buffer=10,
        max_cloud=20,
        visualization="rgb",
        mode="scene",
    )
    keys = {satellite_image_flight_key(**base)}
    variants = {
        "sensor": "landsat8",
        "target_date": date(2026, 3, 6),
        "days_buffer": 11,
        "max_cloud": 21,
        "visualization": "ndvi",
        "mode": "composite",
    }
    for field, value in variants.items():
        keys.add(satellite_image_flight_key(**{**base, field: value}))
    assert len(keys) == 7
    assert satellite_image_flight_key(**base) == ("gee:image:sentinel2:2026-03-05:10:20:rgb:scene")
    assert gee_layer_flight_key("zona") == "gee:layer:zona"
    assert gee_layer_flight_key("zona") != gee_layer_flight_key("caminos")


@pytest.mark.asyncio
async def test_singleflight_same_key_runs_factory_once():
    cache = _MissCache()
    flight = SingleFlight()
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def factory():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"ok": True, "calls": calls}

    leader = asyncio.create_task(flight.do("gee:image:same", factory, cache=cache))
    await started.wait()
    follower = asyncio.create_task(flight.do("gee:image:same", factory, cache=cache))
    await asyncio.sleep(0)
    assert calls == 1
    release.set()
    first, second = await leader, await follower
    assert first == second == {"ok": True, "calls": 1}
    assert first is not second


@pytest.mark.asyncio
async def test_singleflight_different_keys_run_side_by_side():
    cache = _MissCache()
    flight = SingleFlight()
    release = asyncio.Event()
    seen: list[str] = []

    async def factory(name: str):
        seen.append(name)
        if len(seen) == 2:
            release.set()
        await release.wait()
        return name

    left, right = await asyncio.wait_for(
        asyncio.gather(
            flight.do("gee:image:a", lambda: factory("a"), cache=cache),
            flight.do("gee:image:b", lambda: factory("b"), cache=cache),
        ),
        timeout=1,
    )
    assert {left, right} == {"a", "b"}
    assert sorted(seen) == ["a", "b"]


@pytest.mark.asyncio
async def test_two_workers_share_one_factory_through_the_lock():
    cache = _MemoryFlightCache()
    left_flight = SingleFlight(poll_seconds=0.01)
    right_flight = SingleFlight(poll_seconds=0.01)
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()
    key = "gee:image:shared"

    async def factory():
        nonlocal calls
        again = await cache.get(key)
        if again is not None:
            return again
        calls += 1
        started.set()
        await release.wait()
        payload = {"tile": "once"}
        await cache.set(key, payload, 30)
        return payload

    leader = asyncio.create_task(left_flight.do(key, factory, cache=cache))
    await started.wait()
    follower = asyncio.create_task(right_flight.do(key, factory, cache=cache))
    await asyncio.sleep(0.05)
    assert calls == 1
    release.set()
    first, second = await leader, await follower
    assert first == second == {"tile": "once"}


def _patch_miss_cache(monkeypatch: pytest.MonkeyPatch) -> _MissCache:
    cache = _MissCache()
    monkeypatch.setattr(router_gee_support, "get_cache", lambda: cache)
    return cache


def _patch_blocking(monkeypatch: pytest.MonkeyPatch, gate):
    async def _run(func, *args, **kwargs):
        return await gate(func, *args, **kwargs)

    monkeypatch.setattr(router_gee_support, "_run_blocking", _run)


async def _join_window() -> None:
    """Let the second caller reach the shared flight or start a duplicate.

    Public handlers read settings in a worker thread before Earth Engine.
    The duplicate path increments the counter on the loop before it waits,
    so this window is long enough to see that extra call.
    """
    for _ in range(20):
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_two_identical_current_images_call_gee_once(monkeypatch):
    _patch_miss_cache(monkeypatch)
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    def get_image(**kwargs):
        return _image_payload(kwargs["target_date"].isoformat())

    async def gate(func, *args, **kwargs):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return func(*args, **kwargs)

    _patch_blocking(monkeypatch, gate)
    monkeypatch.setattr(public_map, "_ensure_public_gee", lambda: _explorer(get_image))
    raw = {
        "sensor": "Sentinel-2",
        "target_date": "2026-03-05",
        "visualization": "rgb",
        "max_cloud": 20,
        "days_buffer": 10,
        "mode": "scene",
    }

    async def call():
        return await public_map.get_public_current_image(
            Response(), db=object(), service=_Settings(raw)
        )

    leader = asyncio.create_task(call())
    await asyncio.wait_for(started.wait(), timeout=1)
    follower = asyncio.create_task(call())
    await _join_window()
    assert calls == 1
    release.set()
    first, second = await leader, await follower
    assert first.status == "available"
    assert second.status == "available"
    assert first.image is not None and second.image is not None
    assert first.image.tile_url == second.image.tile_url
    assert "2026-03-05" in first.image.tile_url


@pytest.mark.asyncio
async def test_a_later_miss_computes_again(monkeypatch):
    _patch_miss_cache(monkeypatch)
    calls = 0
    release = asyncio.Event()

    def get_image(**_kwargs):
        return _image_payload("again")

    async def gate(func, *args, **kwargs):
        nonlocal calls
        calls += 1
        await release.wait()
        return func(*args, **kwargs)

    _patch_blocking(monkeypatch, gate)

    async def call():
        return await get_satellite_image_impl(
            sensor="sentinel2",
            target_date=date(2026, 3, 5),
            days_buffer=10,
            max_cloud=20,
            visualization="rgb",
            mode="scene",
            ensure_gee=lambda: _explorer(get_image),
        )

    release.set()
    await call()
    assert calls == 1
    await call()
    assert calls == 2


@pytest.mark.asyncio
async def test_different_image_keys_call_gee_separately(monkeypatch):
    _patch_miss_cache(monkeypatch)
    release = asyncio.Event()
    seen: list[str] = []

    def get_image(**kwargs):
        stamp = kwargs["target_date"].isoformat()
        return _image_payload(stamp)

    async def gate(func, *args, **kwargs):
        seen.append(kwargs["target_date"].isoformat())
        if len(seen) == 2:
            release.set()
        await release.wait()
        return func(*args, **kwargs)

    _patch_blocking(monkeypatch, gate)

    async def call(day: date):
        return await get_satellite_image_impl(
            sensor="sentinel2",
            target_date=day,
            days_buffer=10,
            max_cloud=20,
            visualization="rgb",
            mode="scene",
            ensure_gee=lambda: _explorer(get_image),
        )

    left, right = await asyncio.wait_for(
        asyncio.gather(call(date(2026, 1, 10)), call(date(2026, 2, 10))),
        timeout=1,
    )
    assert sorted(seen) == ["2026-01-10", "2026-02-10"]
    assert left["tile_url"] != right["tile_url"]
    assert "2026-01-10" in left["tile_url"]
    assert "2026-02-10" in right["tile_url"]


@pytest.mark.asyncio
async def test_comparison_of_identical_sides_calls_gee_once(monkeypatch):
    _patch_miss_cache(monkeypatch)
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    def get_image(**_kwargs):
        return _image_payload("pair")

    async def gate(func, *args, **kwargs):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return func(*args, **kwargs)

    _patch_blocking(monkeypatch, gate)
    monkeypatch.setattr(public_map, "_ensure_public_gee", lambda: _explorer(get_image))
    side = {
        "sensor": "Sentinel-2",
        "target_date": "2026-03-05",
        "visualization": "ndvi",
        "max_cloud": 15,
        "days_buffer": 8,
        "mode": "composite",
    }

    async def call():
        return await public_map.get_public_current_comparison(
            Response(),
            db=object(),
            service=_Settings({"enabled": True, "left": side, "right": dict(side)}),
        )

    leader = asyncio.create_task(call())
    await asyncio.wait_for(started.wait(), timeout=1)
    await _join_window()
    assert calls == 1
    release.set()
    result = await leader
    assert result.status == "available"
    assert result.left is not None and result.right is not None
    assert result.left.tile_url == result.right.tile_url
    assert result.left.visualization == "ndvi"


@pytest.mark.asyncio
async def test_two_zona_requests_call_gee_once(monkeypatch):
    _patch_miss_cache(monkeypatch)
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()
    payload = {"type": "FeatureCollection", "features": []}

    def get_layer_geojson(layer_name: str):
        assert layer_name == "zona"
        return payload

    async def gate(func, *args, **kwargs):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return func(*args, **kwargs)

    _patch_blocking(monkeypatch, gate)

    def ensure():
        return {"get_layer_geojson": get_layer_geojson}

    async def call():
        return await get_gee_layer_impl(layer_name="zona", ensure_gee=ensure)

    leader = asyncio.create_task(call())
    await asyncio.wait_for(started.wait(), timeout=1)
    follower = asyncio.create_task(call())
    await _join_window()
    assert calls == 1
    release.set()
    first, second = await leader, await follower
    assert first is not second
    assert first.body == second.body
    assert b"FeatureCollection" in first.body


@pytest.mark.asyncio
async def test_shared_gee_failure_is_not_retried_by_the_waiter(monkeypatch):
    _patch_miss_cache(monkeypatch)
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    def get_image(**_kwargs):
        raise RuntimeError("gee down")

    async def gate(func, *args, **kwargs):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return func(*args, **kwargs)

    _patch_blocking(monkeypatch, gate)

    monkeypatch.setattr(public_map, "_ensure_public_gee", lambda: _explorer(get_image))
    raw = {
        "sensor": "Sentinel-2",
        "target_date": "2024-01-02",
        "visualization": "rgb",
        "max_cloud": 20,
        "days_buffer": 10,
        "mode": "scene",
    }

    async def call():
        return await public_map.get_public_current_image(
            Response(), db=object(), service=_Settings(raw)
        )

    leader = asyncio.create_task(call())
    await asyncio.wait_for(started.wait(), timeout=1)
    follower = asyncio.create_task(call())
    await _join_window()
    assert calls == 1
    release.set()
    first, second = await leader, await follower
    assert first.status == "unavailable"
    assert second.status == "unavailable"
    assert first.reason == second.reason == "temporarily_unavailable"
