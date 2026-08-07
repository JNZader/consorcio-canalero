"""Adapter resilience: timeout, quota/rate-limit handling, retry, circuit and cache keys."""

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from app.domains.geo.rainfall.ports import SourceBatch


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpen(RuntimeError):
    pass


class AdapterError(RuntimeError):
    pass


def backoff_seconds(attempt: int, *, base: float = 5.0, cap: float = 900.0) -> float:
    safe = max(1, attempt)
    return min(base * (2 ** (safe - 1)), cap)


def cache_key_for(
    *, source_id: str, role: str, scope_kind: str, scope_id: str, scope_version: str, year: int
) -> str:
    canonical = json.dumps(
        [role, scope_kind, scope_id, scope_version, year], sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    safe_source = source_id.replace(".", "_").replace(":", "_")
    return f"rainfall:source:{safe_source}:{role}:{digest}"


@dataclass
class ResilientAdapterState:
    failure_threshold: int = 5
    recovery_seconds: float = 300.0
    consecutive_failures: int = 0
    circuit: CircuitState = field(default=CircuitState.CLOSED)
    opened_at: float | None = None

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.circuit = CircuitState.CLOSED
        self.opened_at = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.circuit = CircuitState.OPEN
            self.opened_at = time.monotonic()

    def can_attempt(self) -> bool:
        if self.circuit in {CircuitState.CLOSED, CircuitState.HALF_OPEN}:
            return True
        if self.opened_at is None or time.monotonic() - self.opened_at >= self.recovery_seconds:
            self.circuit = CircuitState.HALF_OPEN
            return True
        raise CircuitOpen("circuit breaker is open")


FetchFn = Callable[..., SourceBatch]


class ResilientAdapter:
    def __init__(
        self,
        fetch: FetchFn,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        failure_threshold: int = 5,
        recovery_seconds: float = 300.0,
    ):
        self._inner_fetch = fetch
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.state = ResilientAdapterState(
            failure_threshold=failure_threshold,
            recovery_seconds=recovery_seconds,
        )

    def fetch(
        self,
        *,
        source_id: str,
        role: str,
        scope_kind: str,
        scope_id: str,
        scope_version: str,
        start: datetime,
        end: datetime,
        **kwargs: Any,
    ) -> SourceBatch:
        self.state.can_attempt()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = self._inner_fetch(
                    source_id=source_id,
                    scope_kind=scope_kind,
                    scope_id=scope_id,
                    scope_version=scope_version,
                    start=start,
                    end=end,
                    **kwargs,
                )
                self.state.record_success()
                return result
            except (TimeoutError, ConnectionError, RuntimeError) as exc:
                last_error = exc
                self.state.record_failure()
                if attempt < self.max_retries:
                    time.sleep(backoff_seconds(attempt + 1))
        raise AdapterError(
            f"adapter failed after {self.max_retries + 1} attempts: {last_error}"
        ) from last_error
