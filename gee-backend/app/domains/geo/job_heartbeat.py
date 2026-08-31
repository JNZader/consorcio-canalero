"""Idle-watchdog heartbeat for geo jobs whose compute does not CAS."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import structlog

logger = structlog.get_logger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 60.0


@contextmanager
def heartbeat_running_job(
    touch: Callable[[], bool],
    *,
    interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
) -> Iterator[None]:
    """Call ``touch`` on an interval until the block exits.

    ``touch`` must compare-and-set the RUNNING row (bumping ``updated_at``) and
    return False when the fence is gone. Failures are swallowed so a watchdog
    never aborts live compute; the next CAS in the worker still fences.
    """
    if interval_seconds <= 0:
        yield
        return

    stop = threading.Event()

    def _loop() -> None:
        while not stop.wait(interval_seconds):
            try:
                if not touch():
                    return
            except Exception:
                logger.warning("geo_job.heartbeat_failed", exc_info=True)

    thread = threading.Thread(target=_loop, name="geo-job-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)
