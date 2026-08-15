"""Append-only, flushed, thread-safe event stream (RMEH-010, RMEH-012)."""

from __future__ import annotations

import json
import signal
import threading
from pathlib import Path
from typing import Mapping


class EventStream:
    """Append-only JSONL, flushed after each phase so cancellation still leaves an
    explanation. A signal handler may append from a different thread, so the
    per-record write is guarded by a lock (no partial-row interleaving)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._fh: object | None = None

    @classmethod
    def open(cls, path: Path) -> EventStream:
        stream = cls(path)
        stream._fh = open(path, "a", encoding="utf-8")  # noqa: SIM115
        return stream

    def append(self, record: Mapping[str, object]) -> None:
        line = json.dumps(record, sort_keys=True) + "\n"
        with self._lock:
            assert self._fh is not None
            self._fh.write(line)
            self._fh.flush()

    def append_cancellation(self, signum: int, explanation: str) -> None:
        self.append(
            {
                "kind": "cancellation",
                "signal": signal.Signals(signum).name,
                "explanation": explanation,
            }
        )

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
