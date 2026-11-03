"""GEE health probe. The Earth Engine client here is a fake.

Nothing in this module may call the real ``ee`` library. The probe reads
``gee_service.ee`` after ``_ensure_initialized``; both are replaced before
the call.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

import app.core.health as health
import app.domains.geo.gee_service as gee_service
from app.config import settings


class _Number:
    def __init__(self, value: object, *, error: BaseException | None = None) -> None:
        self.value = value
        self.error = error
        self.calls = 0
        self.release: threading.Event | None = None

    def getInfo(self) -> object:
        self.calls += 1
        if self.release is not None:
            self.release.wait(timeout=2.0)
        if self.error is not None:
            raise self.error
        return self.value


class _EE:
    def __init__(self, number: _Number) -> None:
        self.number = number
        self.seen: list[object] = []

    def Number(self, value: object) -> _Number:
        self.seen.append(value)
        return self.number


@pytest.fixture(autouse=True)
def _clear_gee_probe_cache() -> None:
    health._reset_gee_probe_cache()


def _install(monkeypatch: pytest.MonkeyPatch, number: _Number) -> tuple[_EE, list[str]]:
    ee = _EE(number)
    order: list[str] = []

    def init() -> None:
        order.append("init")

    monkeypatch.setattr(gee_service, "_ensure_initialized", init)
    monkeypatch.setattr(gee_service, "ee", ee)
    return ee, order


@pytest.mark.asyncio
async def test_gee_health_is_down_when_ee_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    number = _Number(1, error=RuntimeError("quota-token-SHOULD-NOT-LEAK"))
    _ee, order = _install(monkeypatch, number)

    result = await health.check_gee_health()

    assert order == ["init"]
    assert number.calls == 1
    assert result["status"] == "down"
    assert result["error"] == "gee_check_failed"
    assert result["project"] == settings.gee_project_id
    assert isinstance(result["latency_ms"], float)
    assert result["latency_ms"] >= 0
    assert "SHOULD-NOT-LEAK" not in str(result)


@pytest.mark.asyncio
async def test_gee_health_is_healthy_when_the_lightweight_call_returns_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    number = _Number(1)
    ee, order = _install(monkeypatch, number)

    result = await health.check_gee_health()

    assert order == ["init"]
    assert ee.seen == [1]
    assert number.calls == 1
    assert result == {
        "status": "healthy",
        "latency_ms": result["latency_ms"],
        "project": settings.gee_project_id,
    }
    assert isinstance(result["latency_ms"], float)
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_gee_health_is_degraded_when_the_value_is_not_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    number = _Number(0)
    _install(monkeypatch, number)

    result = await health.check_gee_health()

    assert result["status"] == "degraded"
    assert "error" not in result
    assert isinstance(result["latency_ms"], float)


@pytest.mark.asyncio
async def test_gee_health_cache_hit_avoids_a_second_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    number = _Number(1)
    _ee, order = _install(monkeypatch, number)

    first = await health.check_gee_health()
    second = await health.check_gee_health()

    assert second == first
    assert number.calls == 1
    assert order == ["init"]

    real = time.monotonic
    monkeypatch.setattr(
        health.time,
        "monotonic",
        lambda: real() + health.GEE_PROBE_CACHE_SECONDS + 1,
    )
    third = await health.check_gee_health()

    assert third["status"] == "healthy"
    assert number.calls == 2
    assert order == ["init", "init"]


@pytest.mark.asyncio
async def test_gee_health_is_down_when_the_probe_exceeds_its_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = threading.Event()
    number = _Number(1)
    number.release = release
    _install(monkeypatch, number)
    monkeypatch.setattr(health, "GEE_PROBE_TIMEOUT_SECONDS", 0.05)

    try:
        started = time.perf_counter()
        result = await health.check_gee_health()
        elapsed = time.perf_counter() - started
    finally:
        release.set()

    assert elapsed < 0.5
    assert result["status"] == "down"
    assert result["error"] == "check_timeout"
    assert result["latency_ms"] > 0

    cached = await health.check_gee_health()
    assert cached == result
    # The deadline wins even if the worker has not entered getInfo yet.
    # A cache hit must not start a second probe.
    assert number.calls <= 1


@pytest.mark.asyncio
async def test_public_health_bundle_does_not_probe_gee(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_if_called():
        raise AssertionError("public health must not call Earth Engine")

    async def ok():
        return {"status": "healthy"}

    monkeypatch.setattr(health, "check_gee_health", fail_if_called)
    monkeypatch.setattr(health, "check_database_health", ok)
    monkeypatch.setattr(health, "check_redis_health", ok)
    monkeypatch.setattr(health, "check_alembic_health", ok)

    results = await health.run_health_checks()

    assert set(results) == {"database", "redis", "alembic"}


@pytest.mark.asyncio
async def test_included_gee_probe_keeps_its_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def gee():
        await asyncio.sleep(0.05)
        return {"status": "healthy", "latency_ms": 50.0, "project": "cc10demayo"}

    async def slow():
        await asyncio.sleep(5)
        return {"status": "healthy"}

    monkeypatch.setattr(health, "GEE_PROBE_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(health, "check_gee_health", gee)
    monkeypatch.setattr(health, "check_database_health", slow)
    monkeypatch.setattr(health, "check_redis_health", slow)
    monkeypatch.setattr(health, "check_alembic_health", slow)

    results = await health.run_health_checks(
        include_gee=True,
        per_check_timeout=0.01,
        overall_timeout=0.02,
    )

    assert results["gee"]["status"] == "healthy"
    assert results["database"] == {"status": "unhealthy", "error": "check_timeout"}
    assert results["redis"] == {"status": "unhealthy", "error": "check_timeout"}
    assert results["alembic"] == {"status": "unhealthy", "error": "check_timeout"}
