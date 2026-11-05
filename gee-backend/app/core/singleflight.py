"""Coalesce identical in-flight work inside and across processes.

Production runs two uvicorn workers (``app/server.py``). An asyncio map
collapses callers that share a loop, including when Redis is down and the
JSON cache is a no-op. A Redis lock collapses the two workers: the waiter
polls the same cache key the leader fills, so only one of them runs the
factory.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Earth Engine composites on these routes take about 30s–2min. The lock
# outlives one compute so the other worker waits instead of starting a
# second one. A dead leader stops holding the key when the TTL expires.
GEE_FLIGHT_LOCK_TTL_SECONDS = 240
GEE_FLIGHT_POLL_SECONDS = 0.2


def _detach(result: Any) -> Any:
    """Give each waiter its own top-level dict.

    The shared task returns one object. A caller that writes a key must not
    change the payload the other waiter is still serialising.
    """
    if isinstance(result, dict):
        return dict(result)
    return result


class SingleFlight:
    """One factory execution per key while that execution is in flight."""

    def __init__(
        self,
        *,
        lock_ttl_seconds: int = GEE_FLIGHT_LOCK_TTL_SECONDS,
        poll_seconds: float = GEE_FLIGHT_POLL_SECONDS,
    ) -> None:
        self._lock_ttl_seconds = lock_ttl_seconds
        self._poll_seconds = poll_seconds
        self._loop: asyncio.AbstractEventLoop | None = None
        self._guard: asyncio.Lock | None = None
        self._inflight: dict[str, asyncio.Task[Any]] = {}

    def reset(self) -> None:
        """Drop the loop-bound map. Tests use this between cases."""
        self._loop = None
        self._guard = None
        self._inflight = {}

    def _guard_for_this_loop(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._guard is None or self._loop is not loop:
            self._loop = loop
            self._guard = asyncio.Lock()
            self._inflight = {}
        return self._guard

    def _drop(self, key: str, finished: asyncio.Task[Any]) -> None:
        if self._inflight.get(key) is finished:
            self._inflight.pop(key, None)
        if finished.cancelled():
            return
        # Retrieve the error so a flight with no remaining waiter does not
        # log "exception was never retrieved" when the task is collected.
        finished.exception()

    async def do(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        *,
        cache: Any,
    ) -> Any:
        """Run ``factory`` once for ``key`` and return that result to every waiter.

        ``cache`` is the JSON cache (or a test double) used for the
        cross-process lock. It must implement ``get``, ``acquire_lock`` and
        ``release_lock``.
        """
        if not key:
            raise ValueError("singleflight key is required")
        guard = self._guard_for_this_loop()
        async with guard:
            task = self._inflight.get(key)
            if task is None or task.done():
                task = asyncio.create_task(
                    self._lead(key, factory, cache),
                    name=f"singleflight:{key[:80]}",
                )
                self._inflight[key] = task

                def _done(finished: asyncio.Task[Any], flight_key: str = key) -> None:
                    self._drop(flight_key, finished)

                task.add_done_callback(_done)
        # A client disconnect cancels the request task, not the shared compute.
        result = await asyncio.shield(task)
        return _detach(result)

    async def _lead(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        cache: Any,
    ) -> Any:
        deadline = time.monotonic() + self._lock_ttl_seconds
        while True:
            cached = await cache.get(key)
            if cached is not None:
                return cached
            token = uuid.uuid4().hex
            acquired = await cache.acquire_lock(key, token, self._lock_ttl_seconds)
            if acquired is None:
                # Redis is down. This process already has one leader; run it.
                return await factory()
            if acquired:
                try:
                    return await factory()
                finally:
                    await cache.release_lock(key, token)
            if time.monotonic() >= deadline:
                logger.warning("GEE singleflight wait expired; computing locally", key=key)
                return await factory()
            await asyncio.sleep(self._poll_seconds)
