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

from scripts.rainfall_e2e_harness.bootstrap import (
    COMPOSE_FILE,
    HARNESS_VIEW_MARKER,
    BootstrapReport,
    RelationInspection,
    RelationKind,
    ServiceReport,
    bootstrap_database,
    build_seed_sql,
    classify_parcel_view,
    classify_soil_view,
    inspect_relation,
    inspect_srid_contract,
    seed_digest,
    tile_xyz,
    validate_services,
)
from scripts.rainfall_e2e_harness.events import EventStream
from scripts.rainfall_e2e_harness.lifecycle import Lifecycle
from scripts.rainfall_e2e_harness.accounting import (
    EXPECTED_SPEC_FILE,
    EXPECTED_SELECTION_RECORDS,
    EXPECTED_TEST_COUNT,
    CollectionVerdict,
    HarnessAccountingFailure,
    ResultVerdict,
    assert_collection_expected,
    assert_manifest_contract,
    assert_result_expected,
    classify_run_failure,
    collection_spec_count,
    parse_collection_json,
    parse_results_json,
    result_summary,
)
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
    RealCommandRunner,
    ResourceLease,
    RunIdentity,
    apply_migrations,
    render_init_script,
    validate_marker_read_only,
    write_init_script,
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
    "CollectionVerdict",
    "CommandKind",
    "CommandResult",
    "CommandRunner",
    "EventStream",
    "EXPECTED_SPEC_FILE",
    "EXPECTED_SELECTION_RECORDS",
    "EXPECTED_TEST_COUNT",
    "FailureClass",
    "HarnessAccountingFailure",
    "LeaseResource",
    "Lifecycle",
    "OwnedBoundary",
    "ParcelContract",
    "Preflight",
    "RecordingCommandRunner",
    "RealCommandRunner",
    "ResourceLease",
    "ResultVerdict",
    "RunIdentity",
    "SceneManifest",
    "apply_migrations",
    "assert_collection_expected",
    "assert_manifest_contract",
    "assert_result_expected",
    "classify_request_failure",
    "classify_run_failure",
    "collection_spec_count",
    "homepage_browse_failure",
    "manifest_failure",
    "parse_collection_json",
    "parse_results_json",
    "preflight_parcel_contracts",
    "redact_command",
    "redact_text",
    "render_init_script",
    "result_summary",
    "validate_marker_read_only",
    "write_init_script",
]
