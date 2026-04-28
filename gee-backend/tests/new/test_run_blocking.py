"""Unit tests for `_run_blocking` — proves it actually offloads to a thread.

The bug we fixed: `_run_blocking` used to be `return func(*args, **kwargs)`
which BLOCKED the event loop. Multiple slow GEE requests in flight made
unrelated endpoints (e.g. `/basins/approved-zones/current`) tail-latency
into the minute range. This test pins the new behaviour: the function MUST
run in a different thread than the caller, and concurrent calls MUST run
in parallel rather than serially.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from app.domains.geo.router_gee_support import _run_blocking


@pytest.mark.asyncio
async def test_run_blocking_runs_in_different_thread() -> None:
    main_thread_id = threading.get_ident()

    def capture_thread() -> int:
        return threading.get_ident()

    worker_thread_id = await _run_blocking(capture_thread)
    assert worker_thread_id != main_thread_id, (
        "Expected the sync function to run in a worker thread, "
        f"but it ran in the main event-loop thread ({main_thread_id})"
    )


@pytest.mark.asyncio
async def test_run_blocking_passes_args_and_kwargs() -> None:
    def add(a: int, b: int, *, c: int = 0) -> int:
        return a + b + c

    result = await _run_blocking(add, 2, 3, c=10)
    assert result == 15


@pytest.mark.asyncio
async def test_run_blocking_runs_concurrent_calls_in_parallel() -> None:
    """Two ~100ms blocking calls awaited via gather should finish in ~100ms,
    NOT ~200ms. This is the property that prevents the event-loop stall."""

    def slow() -> float:
        start = time.perf_counter()
        time.sleep(0.1)
        return time.perf_counter() - start

    t0 = time.perf_counter()
    durations = await asyncio.gather(_run_blocking(slow), _run_blocking(slow))
    elapsed = time.perf_counter() - t0

    assert all(d >= 0.09 for d in durations), durations
    # Allow some scheduler jitter but the wall clock MUST be well under 0.2s
    # if the two calls ran in parallel.
    assert elapsed < 0.18, (
        f"Concurrent _run_blocking calls finished in {elapsed:.3f}s "
        "— expected ~0.1s (parallel), got close to 0.2s (serial). "
        "The wrapper is probably blocking the event loop."
    )
