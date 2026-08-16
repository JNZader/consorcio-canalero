"""Safety layer: identity, lease, owned boundary, command adapter (RMEH-001/012)."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping


# -- Failure taxonomy: seven mutually-exclusive manifest classes (RMEH-009/012-B) --
class FailureClass(Enum):
    BOOTSTRAP_SAFETY_FAILURE = "BOOTSTRAP_SAFETY_FAILURE"
    BOOTSTRAP_PREREQUISITE_FAILURE = "BOOTSTRAP_PREREQUISITE_FAILURE"
    HARNESS_ACCOUNTING_FAILURE = "HARNESS_ACCOUNTING_FAILURE"
    BROWSER_INTEGRITY_FAILURE = "BROWSER_INTEGRITY_FAILURE"
    PRODUCT_ASSERTION_FAILURE = "PRODUCT_ASSERTION_FAILURE"
    CLEANUP_FAILURE = "CLEANUP_FAILURE"
    PASSED = "PASSED"


class BootstrapSafetyFailure(Exception):
    """Ownership/host/marker mismatch — aborts before any bootstrap write."""


class BootstrapPrerequisiteFailure(Exception):
    """Owned stack could not satisfy a hard postcondition (incl. preflight)."""


class CleanupFailure(Exception):
    """One or more exact run-owned resources remain after teardown."""


# -- Command adapter: the seam that proves zero DB-mutating writes --
class CommandKind(Enum):
    DOCKER_INSPECT = "docker_inspect"
    DOCKER_CONTROL = "docker_control"
    DATABASE_READONLY = "database_readonly"
    DATABASE_MUTATING = "database_mutating"


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass
class RecordedCall:
    command: list[str]
    kind: CommandKind
    env: Mapping[str, str] | None


class CommandRunner:
    """Abstract runner. Real impl shells out; tests use RecordingCommandRunner."""

    def run(
        self,
        command: list[str],
        *,
        kind: CommandKind,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:  # pragma: no cover - abstract
        raise NotImplementedError


class RecordingCommandRunner(CommandRunner):
    """Fake runner: records every call by kind, returns programmed results."""

    def __init__(self) -> None:
        self._programmed: dict[CommandKind, list[CommandResult]] = {}
        self.calls: list[RecordedCall] = []

    def program(self, kind: CommandKind, result: CommandResult) -> None:
        self._programmed.setdefault(kind, []).append(result)

    def run(
        self,
        command: list[str],
        *,
        kind: CommandKind,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        self.calls.append(RecordedCall(list(command), kind, env))
        queue = self._programmed.get(kind)
        if queue:
            return queue.pop(0)
        return CommandResult(0, "", "")

    @property
    def database_mutating_calls(self) -> list[RecordedCall]:
        return [c for c in self.calls if c.kind is CommandKind.DATABASE_MUTATING]

    @property
    def database_readonly_calls(self) -> list[RecordedCall]:
        return [c for c in self.calls if c.kind is CommandKind.DATABASE_READONLY]

    @property
    def docker_control_calls(self) -> list[RecordedCall]:
        return [c for c in self.calls if c.kind is CommandKind.DOCKER_CONTROL]

    @property
    def docker_inspect_calls(self) -> list[RecordedCall]:
        return [c for c in self.calls if c.kind is CommandKind.DOCKER_INSPECT]


# -- Run identity: generated, never caller-supplied (RMEH-001) --
@dataclass(frozen=True)
class RunIdentity:
    run_id: str
    marker_nonce: str
    database_name: str
    evidence_dir: Path | None

    @classmethod
    def plan(
        cls,
        *,
        evidence_dir: Path | None = None,
        database_url: str | None = None,
        database_host: str | None = None,
        database_name: str | None = None,
        compose_project: str | None = None,
        cleanup_target: str | None = None,
    ) -> RunIdentity:
        # Accept NO database/Compose overrides — a shared/real target must never
        # be repairable (RMEH-001-B/C).
        if database_url is not None:
            raise BootstrapSafetyFailure(
                "caller-supplied database URL (DATABASE_URL) refused; runner "
                "accepts no database overrides"
            )
        if database_host is not None:
            raise BootstrapSafetyFailure(
                "caller-supplied database host refused; runner derives its own loopback host"
            )
        if database_name is not None:
            suffix = (
                " (the default shared DB name 'consorcio' is forbidden)"
                if database_name == "consorcio"
                else ""
            )
            raise BootstrapSafetyFailure(
                f"caller-supplied database name refused ({database_name!r}){suffix}"
            )
        if compose_project is not None:
            raise BootstrapSafetyFailure(
                "caller-supplied compose project refused; runner generates a "
                "cryptographically unique project"
            )
        if cleanup_target is not None:
            raise BootstrapSafetyFailure(
                "caller-supplied cleanup target refused; teardown targets only the "
                "exact resources this run recorded"
            )
        run_id = secrets.token_hex(16)  # 128-bit
        marker_nonce = secrets.token_hex(32)  # 256-bit
        return cls(
            run_id=run_id,
            marker_nonce=marker_nonce,
            database_name=f"rmeh_{run_id[:10]}",
            evidence_dir=evidence_dir,
        )


# -- Owned boundary: sole constructor = successful marker gate (RMEH-001-B/C) --
@dataclass(frozen=True)
class OwnedBoundary:
    """In-memory token proving the disposable DB belongs to this run. Constructed
    ONLY by ``validate_marker_read_only``; every DB-mutating method requires it,
    so an unsafe path (marker absent/error/mismatch) issues zero mutating writes."""

    run_id: str
    database_name: str


def validate_marker_read_only(runner: CommandRunner, identity: RunIdentity) -> OwnedBoundary:
    """Read-only marker query — the SOLE OwnedBoundary constructor. Issued as
    ``DATABASE_READONLY`` so the recording adapter proves no ``DATABASE_MUTATING``
    call precedes a constructed boundary."""
    result = runner.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "psql",
            "-tA",
            "-c",
            "SELECT run_id, marker_nonce, database_name FROM rmeh_ownership LIMIT 1",
        ],
        kind=CommandKind.DATABASE_READONLY,
    )
    if result.exit_code != 0:
        raise BootstrapSafetyFailure(f"marker query error: {result.stderr.strip()}")
    body = result.stdout.strip()
    if not body:
        raise BootstrapSafetyFailure("marker absent: no rmeh_ownership row")
    row = json.loads(body)
    if row.get("run_id") != identity.run_id:
        raise BootstrapSafetyFailure("marker run_id mismatch")
    if row.get("marker_nonce") != identity.marker_nonce:
        raise BootstrapSafetyFailure("marker nonce mismatch")
    if row.get("database_name") != identity.database_name:
        raise BootstrapSafetyFailure("marker database_name mismatch")
    return OwnedBoundary(run_id=identity.run_id, database_name=row["database_name"])


def apply_migrations(owned: OwnedBoundary | None, runner: CommandRunner) -> None:
    """``alembic upgrade head`` against the run-owned DB. Requires OwnedBoundary."""
    if owned is None:
        raise BootstrapSafetyFailure(
            "apply_migrations requires a proven owned boundary; no OwnedBoundary "
            "token (no marker proof) means no database writes"
        )
    runner.run(["alembic", "upgrade", "head"], kind=CommandKind.DATABASE_MUTATING)


# -- ResourceLease: Docker teardown authority, independent of the DB token --
@dataclass
class LeaseResource:
    kind: str  # "container" | "volume" | "network"
    name: str
    docker_id: str
    labels: Mapping[str, str]


@dataclass
class ResourceLease:
    """Exact Docker teardown authority granted before provisioning. Carries NO
    database capability. Tears down only by recorded immutable ID + cryptographic
    run/lease/compose labels. Never prefix-sweeps, never DB-token-driven, never
    global-prunes (RMEH-012-B/C)."""

    lease_id: str
    run_id: str
    project_name: str
    volume_name: str
    network_name: str
    container_names: Mapping[str, str]
    labels: Mapping[str, str]
    created_resources: list[LeaseResource] = field(default_factory=list)
    residual_resources: list[LeaseResource] = field(default_factory=list)

    @classmethod
    def plan(cls, identity: RunIdentity) -> ResourceLease:
        lease_id = secrets.token_hex(32)  # 256-bit, independent of marker_nonce
        project_name = f"rmeh-{identity.run_id[:10]}"
        services = ("db", "redis", "migrate", "backend", "martin", "frontend")
        container_names = {svc: f"{project_name}-{svc}-1" for svc in services}
        labels = {
            "rmeh.run": identity.run_id,
            "rmeh.lease": lease_id,
            "rmeh.compose_project": project_name,
        }
        return cls(
            lease_id=lease_id,
            run_id=identity.run_id,
            project_name=project_name,
            volume_name=f"{project_name}_pgdata",
            network_name=f"{project_name}_net",
            container_names=container_names,
            labels=labels,
        )

    def assert_loopback_only(self, resolved: Mapping[str, str]) -> None:
        for service, binding in resolved.items():
            host = binding.rsplit(":", 1)[0]
            if host not in ("127.0.0.1", "::1", "localhost"):
                raise BootstrapSafetyFailure(
                    f"non-loopback binding for {service}: {binding}; "
                    "every published port MUST bind 127.0.0.1"
                )

    def assert_no_resource_collision(self, runner: CommandRunner) -> None:
        planned = [self.volume_name, self.network_name, *self.container_names.values()]
        for name in planned:
            res = runner.run(["docker", "inspect", name], kind=CommandKind.DOCKER_INSPECT)
            if res.exit_code == 0 and res.stdout.strip():
                # Never adopt a collision: record nothing, delete nothing here.
                raise BootstrapSafetyFailure(
                    f"resource collision: {name} already exists; refusing to adopt"
                )

    def record_created(self, resource: LeaseResource) -> None:
        for required in ("rmeh.run", "rmeh.lease", "rmeh.compose_project"):
            if required not in resource.labels:
                raise BootstrapSafetyFailure(
                    f"refusing to record unlabelled resource {resource.name!r} "
                    f"(missing label {required!r})"
                )
        self.created_resources.append(resource)

    def reconcile_then_teardown(
        self, runner: CommandRunner, existing: Callable[[str], bool]
    ) -> None:
        self.residual_resources = []
        for resource in self.created_resources:
            if resource.kind in ("container", "network"):
                runner.run(["docker", "stop", resource.docker_id], kind=CommandKind.DOCKER_CONTROL)
                runner.run(
                    ["docker", "rm", "-f", resource.docker_id], kind=CommandKind.DOCKER_CONTROL
                )
            elif resource.kind == "volume":
                runner.run(
                    ["docker", "volume", "rm", "-f", resource.name], kind=CommandKind.DOCKER_CONTROL
                )
            if existing(resource.name):
                self.residual_resources.append(resource)

    def assert_no_residual_resources(self) -> None:
        if self.residual_resources:
            names = [r.name for r in self.residual_resources]
            raise CleanupFailure(
                f"residual leased resources remain after teardown: {names}; "
                "run overrides an otherwise passing result"
            )
