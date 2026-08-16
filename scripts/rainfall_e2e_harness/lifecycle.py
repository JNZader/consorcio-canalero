"""Lifecycle phase machine (RMEH-010-A, RMEH-012-A/B)."""

from __future__ import annotations

from typing import Callable


class Lifecycle:
    """Top-level try/finally state. The ``OwnedBoundary`` is owned by the runner,
    not by this object; cleanup is valid when ``owned is None``."""

    def __init__(self) -> None:
        self.phase = "CREATED"
        self.cancelled = False
        self.second_signal_seen = False
        self._child_pid: int | None = None
        self._kill_group: Callable[[int], None] | None = None

    def to_lease_planned(self) -> None:
        self.phase = "LEASE_PLANNED"

    def to_provisioning(self) -> None:
        self.phase = "PROVISIONING"

    def to_database_owned(self) -> None:
        self.phase = "DATABASE_OWNED"

    def to_bootstrapped(self) -> None:
        self.phase = "BOOTSTRAPPED"

    def to_preflight_passed(self) -> None:
        self.phase = "PREFLIGHT_PASSED"

    def to_tests_finished(self) -> None:
        self.phase = "TESTS_FINISHED"

    def to_evidence_sealed(self) -> None:
        self.phase = "EVIDENCE_SEALED"

    def to_cleaned(self) -> None:
        self.phase = "CLEANED"

    def cancel(self) -> None:
        self.cancelled = True
        self.phase = "LEASE_CLEANUP"

    def attach_child(self, *, pid: int, kill_group: Callable[[int], None]) -> None:
        self._child_pid = pid
        self._kill_group = kill_group

    def signal_handler(self) -> Callable[[int, object], None]:
        """SIGINT/SIGTERM handler. Sets cancellation, forwards to the child process
        group. A second signal shortens waits; it never changes the cleanup
        target (RMEH-010-D)."""

        def handler(signum: int, _frame: object) -> None:
            if self.cancelled:
                self.second_signal_seen = True
                return
            self.cancelled = True
            self.phase = "LEASE_CLEANUP"
            if self._child_pid is not None and self._kill_group is not None:
                self._kill_group(self._child_pid)

        return handler
