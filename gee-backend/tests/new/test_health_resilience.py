"""Health probes must be non-blocking, concurrent, and deadline bounded."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

import app.core.health as health


@pytest.mark.asyncio
async def test_database_probe_uses_non_blocking_async_sql_and_closes_session(
    monkeypatch,
) -> None:
    class SlowAsyncSession:
        def __init__(self) -> None:
            self.closed = False
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _tb) -> None:
            self.closed = True

        async def execute(self, statement, parameters=None):
            self.calls.append((str(statement), parameters))
            await asyncio.sleep(0.05)
            result = MagicMock()
            if "PostGIS_Version" in str(statement):
                result.scalar.return_value = "3.4"
            return result

    db = SlowAsyncSession()
    monkeypatch.setattr(health, "AsyncSessionLocal", lambda: db)

    probe = asyncio.create_task(health.check_database_health())
    started = time.perf_counter()
    await asyncio.sleep(0.005)

    assert time.perf_counter() - started < 0.03
    assert (await probe) == {"status": "healthy", "postgis_version": "3.4"}
    assert db.closed is True
    assert "set_config('statement_timeout'" in db.calls[0][0]
    assert db.calls[0][1] == {"timeout": f"{health.DATABASE_STATEMENT_TIMEOUT_MS}ms"}


@pytest.mark.asyncio
async def test_database_driver_deadline_cancels_operation_and_closes_session(
    monkeypatch,
) -> None:
    class BlockingAsyncSession:
        def __init__(self) -> None:
            self.active_operations = 0
            self.closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _tb) -> None:
            self.closed = True

        async def execute(self, _statement, _parameters=None):
            self.active_operations += 1
            try:
                await asyncio.Event().wait()
            finally:
                self.active_operations -= 1

    db = BlockingAsyncSession()
    monkeypatch.setattr(health, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(health, "DATABASE_DRIVER_TIMEOUT_SECONDS", 0.01)

    started = time.perf_counter()
    result = await health.check_database_health()

    assert time.perf_counter() - started < 0.05
    assert result == {"status": "unhealthy", "error": "database_check_failed"}
    assert db.closed is True
    assert db.active_operations == 0


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


@pytest.mark.asyncio
async def test_repeated_database_timeouts_leave_no_active_sessions_or_health_tasks(
    monkeypatch,
) -> None:
    sessions = []

    class BlockingAsyncSession:
        def __init__(self) -> None:
            self.active_operations = 0
            self.closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _tb) -> None:
            self.closed = True

        async def execute(self, _statement, _parameters=None):
            self.active_operations += 1
            try:
                await asyncio.Event().wait()
            finally:
                self.active_operations -= 1

    def session_factory():
        session = BlockingAsyncSession()
        sessions.append(session)
        return session

    async def fast_redis():
        return {"status": "healthy"}

    monkeypatch.setattr(health, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(health, "check_redis_health", fast_redis)

    for _ in range(3):
        results = await health.run_health_checks(
            per_check_timeout=0.01,
            overall_timeout=0.05,
        )
        assert results["database"] == {
            "status": "unhealthy",
            "error": "check_timeout",
        }
        assert results["alembic"] == {
            "status": "unhealthy",
            "error": "check_timeout",
        }
        assert results["redis"] == {"status": "healthy"}

    await asyncio.sleep(0)
    assert len(sessions) == 6
    assert all(session.closed for session in sessions)
    assert all(session.active_operations == 0 for session in sessions)
    current = asyncio.current_task()
    assert not [
        task
        for task in asyncio.all_tasks()
        if task is not current and task.get_name().startswith("health:") and not task.done()
    ]
