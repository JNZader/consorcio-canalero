from __future__ import annotations

import time


def test_heartbeat_running_job_calls_touch_until_exit() -> None:
    from app.domains.geo.job_heartbeat import heartbeat_running_job

    hits: list[int] = []

    def touch() -> bool:
        hits.append(1)
        return True

    with heartbeat_running_job(touch, interval_seconds=0.05):
        time.sleep(0.18)

    assert len(hits) >= 2


def test_heartbeat_running_job_stops_when_touch_returns_false() -> None:
    from app.domains.geo.job_heartbeat import heartbeat_running_job

    hits: list[int] = []

    def touch() -> bool:
        hits.append(1)
        return False

    with heartbeat_running_job(touch, interval_seconds=0.05):
        time.sleep(0.2)

    assert hits == [1]
