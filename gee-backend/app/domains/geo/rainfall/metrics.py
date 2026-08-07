"""Metrics-ready seam for Rainfall v2 (Task 4.3).

A tiny, dependency-free seam over the standard library logger so every metric
event has ONE stable shape (``rainfall.<area>.<event>``) and a future metrics
backend (Prometheus / OTel / statsd) can be wired here without touching call
sites. The deployment owners document lives at
``docs/lluvia-v2-observability-workbook.md``; the metric catalogue there is
the contract for what these events mean.

Production rendering: the app's single structlog configuration routes ALL
stdlib records through its ``ProcessorFormatter`` ``foreign_pre_chain``, so
these INFO records already ship as the same JSON envelope as structured logs
(event, level, service, worker_id, timestamp). No extra dependency required.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("rainfall")


def record_event(name: str, **fields: Any) -> None:
    """Emit one labelled metric event (e.g. ``rainfall.analysis.served``)."""
    logger.info(
        "%s %s",
        name,
        json.dumps(fields, sort_keys=True, default=str, ensure_ascii=True),
    )


def record_gauge(name: str, value: int | float) -> None:
    """Emit a gauge snapshot (e.g. ``rainfall.outbox.backlog``)."""
    record_event(name, value=value)
