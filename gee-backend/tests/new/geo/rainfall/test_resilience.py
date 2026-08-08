"""ResilientAdapter timeout and shared circuit-breaker store tests."""

import time
from datetime import UTC, datetime, timedelta

import pytest

from app.domains.geo.rainfall.adapters.resilience import (
    AdapterError,
    CircuitOpen,
    MemoryCircuitStore,
    RedisCircuitStore,
    ResilientAdapter,
    ResilientAdapterState,
)
from app.domains.geo.rainfall.ports import SourceBatch, SourceInterval


def _source_batch() -> SourceBatch:
    start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    return SourceBatch(
        source_id="fake",
        scope_kind="zone",
        scope_id="z1",
        scope_version="v1",
        cadence=timedelta(days=1),
        intervals=(SourceInterval(start, start + timedelta(days=1), 1.0, "mm", "r1"),),
        coverage=1.0,
        completeness=1.0,
        quality={},
        discrepancies=(),
        checksum="c1",
    )


def test_resilient_fetch_raises_adapter_error_when_inner_fetch_times_out():
    """A hanging _inner_fetch must be interrupted and count as a failure."""

    def slow_fetch(**_kwargs):
        time.sleep(10)
        return _source_batch()

    adapter = ResilientAdapter(slow_fetch, timeout_seconds=0.1, max_retries=0)
    with pytest.raises(AdapterError, match="timed out"):
        adapter.fetch(
            source_id="fake",
            role="daily",
            scope_kind="zone",
            scope_id="z1",
            scope_version="v1",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 2, tzinfo=UTC),
        )
    assert adapter.state.consecutive_failures >= 1


def test_resilient_fetch_succeeds_when_inner_fetch_is_faster_than_timeout():
    """A fetch that finishes inside the timeout should return normally."""

    def fast_fetch(**_kwargs):
        return _source_batch()

    adapter = ResilientAdapter(fast_fetch, timeout_seconds=5)
    result = adapter.fetch(
        source_id="fake",
        role="daily",
        scope_kind="zone",
        scope_id="z1",
        scope_version="v1",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 2, tzinfo=UTC),
    )
    assert result == _source_batch()
    assert adapter.state.consecutive_failures == 0


def test_circuit_state_is_shared_across_adapter_instances():
    """Two adapters using the same store must see the same breaker state."""
    shared = MemoryCircuitStore()

    def failing_fetch(**_kwargs):
        raise TimeoutError("boom")

    first = ResilientAdapter(
        failing_fetch,
        store=shared,
        timeout_seconds=1,
        max_retries=0,
        failure_threshold=2,
        recovery_seconds=3600,
    )
    second = ResilientAdapter(
        _source_batch,
        store=shared,
        timeout_seconds=1,
        max_retries=0,
        failure_threshold=2,
        recovery_seconds=3600,
    )

    with pytest.raises(AdapterError):
        first.fetch(
            source_id="fake",
            role="daily",
            scope_kind="zone",
            scope_id="z1",
            scope_version="v1",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 2, tzinfo=UTC),
        )
    with pytest.raises(AdapterError):
        first.fetch(
            source_id="fake",
            role="daily",
            scope_kind="zone",
            scope_id="z1",
            scope_version="v1",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 2, tzinfo=UTC),
        )

    with pytest.raises(CircuitOpen):
        second.fetch(
            source_id="fake",
            role="daily",
            scope_kind="zone",
            scope_id="z1",
            scope_version="v1",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 2, tzinfo=UTC),
        )


def test_half_open_success_closes_circuit_and_failure_reopens():
    """After cooldown one probe is allowed; success closes, failure reopens."""
    shared = MemoryCircuitStore()

    def failing_fetch(**_kwargs):
        raise TimeoutError("boom")

    adapter = ResilientAdapter(
        failing_fetch,
        store=shared,
        timeout_seconds=1,
        max_retries=0,
        failure_threshold=1,
        recovery_seconds=0,
    )

    with pytest.raises(AdapterError):
        adapter.fetch(
            source_id="fake",
            role="daily",
            scope_kind="zone",
            scope_id="z1",
            scope_version="v1",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 2, tzinfo=UTC),
        )

    with pytest.raises(AdapterError):
        adapter.fetch(
            source_id="fake",
            role="daily",
            scope_kind="zone",
            scope_id="z1",
            scope_version="v1",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 2, tzinfo=UTC),
        )

    calls = []

    def flaky_fetch(**_kwargs):
        calls.append(1)
        return _source_batch()

    adapter_closed = ResilientAdapter(
        flaky_fetch,
        store=shared,
        timeout_seconds=1,
        max_retries=0,
        failure_threshold=1,
        recovery_seconds=0,
    )
    result = adapter_closed.fetch(
        source_id="fake",
        role="daily",
        scope_kind="zone",
        scope_id="z1",
        scope_version="v1",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 1, 2, tzinfo=UTC),
    )
    assert result == _source_batch()
    assert len(calls) == 1

    failing = ResilientAdapter(
        failing_fetch,
        store=shared,
        timeout_seconds=1,
        max_retries=0,
        failure_threshold=1,
        recovery_seconds=3600,
    )
    with pytest.raises(AdapterError):
        failing.fetch(
            source_id="fake",
            role="daily",
            scope_kind="zone",
            scope_id="z1",
            scope_version="v1",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 2, tzinfo=UTC),
        )

    with pytest.raises(CircuitOpen):
        failing.fetch(
            source_id="fake",
            role="daily",
            scope_kind="zone",
            scope_id="z1",
            scope_version="v1",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 2, tzinfo=UTC),
        )


def test_redis_circuit_store_degrades_when_redis_is_down():
    """A broken Redis must degrade to in-memory state, never fail the fetch.

    The store is persistence infrastructure; the fetch is the provider, so a
    ``redis.exceptions.ConnectionError`` (``RedisError`` — not the builtin
    ``ConnectionError``) inside ``read``/``write`` must not propagate.
    """
    from redis.exceptions import ConnectionError as RedisConnectionError

    class BrokenRedisClient:
        def get(self, _key: str) -> None:
            raise RedisConnectionError("redis connection refused")

        def set(self, _key: str, _value: str) -> None:
            raise RedisConnectionError("redis connection refused")

    store = object.__new__(RedisCircuitStore)
    store._client = BrokenRedisClient()

    default = ResilientAdapterState(failure_threshold=3, recovery_seconds=120)
    # read on a dead Redis returns the caller's default without raising…
    assert store.read("historical", default=default) is default
    # …and with no default it synthesizes a fresh state, never None.
    degraded = store.read("historical")
    assert isinstance(degraded, ResilientAdapterState)
    assert degraded.consecutive_failures == 0
    # write is a no-op, never raising.
    store.write("historical", default)
