"""R1-005: cache warming must not run long enough to be SIGKILLed at 600s."""

from __future__ import annotations

import threading
import time

import httpx

from app.core.celery_app import celery_app
from app.domains.geo.gee_tasks_warming import (
    WARM_ENDPOINTS,
    WARM_REQUEST_TIMEOUT_SECONDS,
    WARM_TASK_SOFT_TIME_LIMIT_SECONDS,
    WARM_TASK_TIME_LIMIT_SECONDS,
    task_warm_gee_layers,
)


def test_warm_task_limits_sit_under_the_worker_hard_kill() -> None:
    assert celery_app.conf.task_time_limit == 600
    assert len(WARM_ENDPOINTS) * WARM_REQUEST_TIMEOUT_SECONDS > 600
    assert task_warm_gee_layers.soft_time_limit == WARM_TASK_SOFT_TIME_LIMIT_SECONDS
    assert task_warm_gee_layers.time_limit == WARM_TASK_TIME_LIMIT_SECONDS
    assert task_warm_gee_layers.time_limit < celery_app.conf.task_time_limit


def test_warm_hits_every_endpoint_concurrently(monkeypatch) -> None:
    current = 0
    peak = 0
    lock = threading.Lock()

    class _Response:
        status_code = 200
        headers: dict[str, str] = {}
        elapsed = type("Elapsed", (), {"total_seconds": staticmethod(lambda: 0.01)})()

    class _Client:
        def __init__(self, timeout: float):
            assert timeout == WARM_REQUEST_TIMEOUT_SECONDS

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str):
            nonlocal current, peak
            with lock:
                current += 1
                peak = max(peak, current)
            time.sleep(0.05)
            with lock:
                current -= 1
            return _Response()

    monkeypatch.setattr(httpx, "Client", _Client)
    summary = task_warm_gee_layers()

    assert summary["count"] == len(WARM_ENDPOINTS)
    assert peak > 1
    assert {item["path"] for item in summary["warmed"]} == set(WARM_ENDPOINTS)
