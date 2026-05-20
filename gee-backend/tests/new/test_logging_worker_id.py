"""Phase 5 / F5-N — pin worker_id presence in log events.

The motivation in ``docs/KNOWN_LIMITATIONS.md``: 2 uvicorn workers
produce duplicate module-level boot logs. Downstream dedup
(Sentry / BetterStack) collapses them by message hash and HIDES
the second worker's events. The fix is to surface the per-worker
identifier in every log event so the dedup grouping becomes
``(message, worker_id)`` instead of ``(message,)``.

This test pins the contract: ``add_app_context`` always emits
``worker_id`` alongside ``app`` and ``service``, with a value
that's a non-empty string (the process PID, surfaced as str).
"""

from __future__ import annotations

import os

from app.core.logging import _WORKER_ID, add_app_context


def test_add_app_context_emits_worker_id():
    """The processor must surface worker_id on every event."""
    event: dict = {"event": "test boot line", "level": "info"}
    result = add_app_context(logger=None, method_name="info", event_dict=event)  # type: ignore[arg-type]

    assert "worker_id" in result, "every log event must carry worker_id"
    assert isinstance(result["worker_id"], str), "worker_id is serialised as str"
    assert result["worker_id"], "worker_id must not be empty"


def test_worker_id_matches_current_pid():
    """The value is the PID of the importing process, computed once
    at module load. Confirms the dedup grouping has a stable value
    per process for the entire run."""
    assert _WORKER_ID == str(os.getpid())


def test_app_context_includes_existing_fields():
    """Regression guard — adding worker_id must NOT drop the
    pre-existing ``app`` / ``service`` fields."""
    event: dict = {"event": "test"}
    result = add_app_context(logger=None, method_name="info", event_dict=event)  # type: ignore[arg-type]

    assert result["app"] == "consorcio-canalero-gee"
    assert result["service"] == "backend"
    assert "worker_id" in result
