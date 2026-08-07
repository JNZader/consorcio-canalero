"""Adapter resilience: timeout, quota/rate-limit handling, retry, circuit and cache keys."""

import hashlib
import json
import math
import signal
import threading
import time
from abc import ABC, abstractmethod
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
    last_failure_at: float | None = None
    next_attempt_at: float | None = None

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.circuit = CircuitState.CLOSED
        self.opened_at = None
        self.last_failure_at = None
        self.next_attempt_at = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        self.last_failure_at = time.monotonic()
        if self.consecutive_failures >= self.failure_threshold:
            self.circuit = CircuitState.OPEN
            self.opened_at = self.last_failure_at
            self.next_attempt_at = self.opened_at + self.recovery_seconds

    def can_attempt(self) -> bool:
        if self.circuit in {CircuitState.CLOSED, CircuitState.HALF_OPEN}:
            return True
        if self.opened_at is None or time.monotonic() - self.opened_at >= self.recovery_seconds:
            self.circuit = CircuitState.HALF_OPEN
            return True
        raise CircuitOpen("circuit breaker is open")

    def to_store_dict(self) -> dict[str, Any]:
        return {
            "state": self.circuit.value,
            "failure_count": self.consecutive_failures,
            "last_failure_at": self.last_failure_at,
            "next_attempt_at": self.next_attempt_at,
        }

    @classmethod
    def from_store_dict(cls, raw: dict[str, Any]) -> "ResilientAdapterState":
        return cls(
            consecutive_failures=raw.get("failure_count", 0),
            circuit=CircuitState(raw["state"]),
            opened_at=raw.get("last_failure_at"),
            last_failure_at=raw.get("last_failure_at"),
            next_attempt_at=raw.get("next_attempt_at"),
        )


class CircuitStore(ABC):
    """Persist circuit-breaker state so separate workers see the same breaker."""

    @abstractmethod
    def read(
        self, role: str, default: ResilientAdapterState | None = None
    ) -> ResilientAdapterState:
        """Return the stored state for *role*, or *default* if none exists."""

    @abstractmethod
    def write(self, role: str, state: ResilientAdapterState) -> None:
        """Persist *state* for *role*."""


class MemoryCircuitStore(CircuitStore):
    """In-memory circuit store for tests and local development."""

    _shared: dict[str, ResilientAdapterState] = {}

    def __init__(self, _memory: dict[str, ResilientAdapterState] | None = None):
        self._memory = _memory if _memory is not None else self._shared

    def read(
        self, role: str, default: ResilientAdapterState | None = None
    ) -> ResilientAdapterState:
        if role not in self._memory:
            self._memory[role] = default if default is not None else ResilientAdapterState()
        return self._memory[role]

    def write(self, role: str, state: ResilientAdapterState) -> None:
        self._memory[role] = state

    def clear(self) -> None:
        self._memory.clear()


class RedisCircuitStore(CircuitStore):
    """Redis-backed circuit store shared across Celery workers."""

    def __init__(self, redis_url: str):
        import redis as _redis

        self._client = _redis.Redis.from_url(redis_url, decode_responses=True)

    def _key(self, role: str) -> str:
        return f"rainfall:circuit:{role}"

    def read(
        self, role: str, default: ResilientAdapterState | None = None
    ) -> ResilientAdapterState:
        raw = self._client.get(self._key(role))
        if raw is None:
            return default if default is not None else ResilientAdapterState()
        return ResilientAdapterState.from_store_dict(json.loads(raw))

    def write(self, role: str, state: ResilientAdapterState) -> None:
        self._client.set(self._key(role), json.dumps(state.to_store_dict()))


def _alarm_handler(_signum: int, _frame: Any) -> None:
    raise TimeoutError("timed out")


def _run_with_timeout(
    fn: Callable[..., Any], timeout_seconds: float, *args: Any, **kwargs: Any
) -> Any:
    """Run *fn* with a hard *timeout_seconds* ceiling.

    Preferred backend is ``func_timeout.func_timeout`` when the package is
    installed.  On Linux we fall back to ``SIGALRM`` so Celery prefork workers
    can interrupt a hanging fetch.  When signals cannot be used (non-main
    thread, Windows, etc.) we degrade to an unguarded call.
    """
    try:
        from func_timeout import FunctionTimedOut, func_timeout
    except ImportError:
        func_timeout = None  # type: ignore[assignment]

    if func_timeout is not None:
        try:
            return func_timeout(timeout_seconds, fn, args=args, kwargs=kwargs)
        except FunctionTimedOut as exc:
            raise TimeoutError("timed out") from exc

    if not hasattr(signal, "SIGALRM"):
        return fn(*args, **kwargs)

    if threading.current_thread() is not threading.main_thread():
        return fn(*args, **kwargs)

    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    try:
        if hasattr(signal, "setitimer"):
            signal.setitimer(signal.ITIMER_REAL, max(timeout_seconds, 0.001))
        else:
            signal.alarm(max(math.ceil(timeout_seconds), 1))
        return fn(*args, **kwargs)
    finally:
        if hasattr(signal, "setitimer"):
            signal.setitimer(signal.ITIMER_REAL, 0)
        else:
            signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


FetchFn = Callable[..., SourceBatch]


class ResilientAdapter:
    def __init__(
        self,
        fetch: FetchFn,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        failure_threshold: int = 3,
        recovery_seconds: float = 300.0,
        store: CircuitStore | None = None,
    ):
        self._inner_fetch = fetch
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self.store = store if store is not None else MemoryCircuitStore()
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
        state = self.store.read(
            role,
            default=ResilientAdapterState(
                failure_threshold=self.failure_threshold,
                recovery_seconds=self.recovery_seconds,
            ),
        )
        state.failure_threshold = self.failure_threshold
        state.recovery_seconds = self.recovery_seconds
        state.can_attempt()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = _run_with_timeout(
                    self._inner_fetch,
                    self.timeout_seconds,
                    source_id=source_id,
                    scope_kind=scope_kind,
                    scope_id=scope_id,
                    scope_version=scope_version,
                    start=start,
                    end=end,
                    **kwargs,
                )
                state.record_success()
                self.store.write(role, state)
                self.state = state
                return result
            except (TimeoutError, ConnectionError, RuntimeError) as exc:
                last_error = exc
                state.record_failure()
                self.store.write(role, state)
                self.state = state
                if attempt < self.max_retries:
                    time.sleep(backoff_seconds(attempt + 1))
        raise AdapterError(
            f"adapter failed after {self.max_retries + 1} attempts: {last_error}"
        ) from last_error
