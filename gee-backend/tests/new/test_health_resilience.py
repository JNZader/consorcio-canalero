"""Health probes must be non-blocking, concurrent, and deadline bounded."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

import app.core.health as health


@pytest.mark.asyncio
async def test_database_probe_offloads_sync_sql_from_event_loop(monkeypatch) -> None:
    result = MagicMock()
    result.scalar.return_value = "3.4"
    db = MagicMock()
    db.execute.return_value = result

    def slow_session():
        time.sleep(0.05)
        return db

    monkeypatch.setattr(health, "SessionLocal", slow_session)
    probe = asyncio.create_task(health.check_database_health())
    started = time.perf_counter()
    await asyncio.sleep(0.005)
    assert time.perf_counter() - started < 0.03
    assert (await probe)["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_checks_run_concurrently_and_apply_per_check_timeout(monkeypatch) -> None:
    async def slow():
        await asyncio.sleep(0.05)
        return {"status": "healthy"}

    monkeypatch.setattr(health, "check_database_health", slow)
    monkeypatch.setattr(health, "check_redis_health", slow)
    monkeypatch.setattr(health, "check_alembic_health", slow)

    started = time.perf_counter()
    results = await health.run_health_checks(per_check_timeout=0.01, overall_timeout=0.04)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.04
    assert set(results) == {"database", "redis", "alembic"}
    assert all(
        result == {"status": "unhealthy", "error": "check_timeout"} for result in results.values()
    )


@pytest.mark.asyncio
async def test_overall_deadline_keeps_fast_result_and_degrades_pending_check(monkeypatch) -> None:
    async def fast():
        return {"status": "healthy"}

    async def slow():
        await asyncio.sleep(0.2)
        return {"status": "healthy"}

    monkeypatch.setattr(health, "check_database_health", fast)
    monkeypatch.setattr(health, "check_redis_health", slow)
    monkeypatch.setattr(health, "check_alembic_health", slow)

    results = await health.run_health_checks(per_check_timeout=1.0, overall_timeout=0.02)

    assert results["database"] == {"status": "healthy"}
    assert results["redis"] == {"status": "unhealthy", "error": "overall_timeout"}
    assert results["alembic"] == {"status": "unhealthy", "error": "overall_timeout"}
