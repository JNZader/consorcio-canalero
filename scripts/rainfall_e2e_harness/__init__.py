"""Rainfall multi-parcel E2E harness — fail-closed lifecycle runner (package).

Pure components only, structured so every destructive decision is testable
without a Docker daemon or real database via a recording command adapter.

Safety invariants (RMEH-001/012, design §Safety Boundary):
  * ``ResourceLease`` is planned BEFORE provisioning; tears down exactly the
    Docker resources this run created — independent of the post-marker
    ``OwnedBoundary`` (JD-DES-003). A marker failure still cleans, with no DB
    write authority granted.
  * The runner refuses every caller DB URL/host/name and fixed Compose project;
    non-loopback ports and pre-existing resources abort before provisioning.
  * ``OwnedBoundary`` has ONE constructor: a successful read-only marker query.
    Every DB-mutating method requires it (zero DB-mutating calls on unsafe paths).
  * Teardown targets recorded immutable IDs + cryptographic labels — never a
    prefix, never the DB token, never a global prune. Residual → CLEANUP_FAILURE.
"""

from __future__ import annotations

from scripts.rainfall_e2e_harness.events import EventStream
from scripts.rainfall_e2e_harness.lifecycle import Lifecycle
from scripts.rainfall_e2e_harness.preflight import (
    ParcelContract,
    Preflight,
    preflight_parcel_contracts,
)
from scripts.rainfall_e2e_harness.safety import (
    BootstrapPrerequisiteFailure,
    BootstrapSafetyFailure,
    CleanupFailure,
    CommandKind,
    CommandResult,
    CommandRunner,
    FailureClass,
    LeaseResource,
    OwnedBoundary,
    RecordingCommandRunner,
    ResourceLease,
    RunIdentity,
    apply_migrations,
    validate_marker_read_only,
)
from scripts.rainfall_e2e_harness.taxonomy import (
    SceneManifest,
    classify_request_failure,
    homepage_browse_failure,
    manifest_failure,
    redact_command,
    redact_text,
)

__all__ = [
    "BootstrapPrerequisiteFailure",
    "BootstrapSafetyFailure",
    "CleanupFailure",
    "CommandKind",
    "CommandResult",
    "CommandRunner",
    "EventStream",
    "FailureClass",
    "LeaseResource",
    "Lifecycle",
    "OwnedBoundary",
    "ParcelContract",
    "Preflight",
    "RecordingCommandRunner",
    "ResourceLease",
    "RunIdentity",
    "SceneManifest",
    "apply_migrations",
    "classify_request_failure",
    "homepage_browse_failure",
    "manifest_failure",
    "preflight_parcel_contracts",
    "redact_command",
    "redact_text",
    "validate_marker_read_only",
]
