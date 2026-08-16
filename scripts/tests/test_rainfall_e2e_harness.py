"""Pytest unit tests for the rainfall multi-parcel E2E harness runner.

RED tests for W1 (safety, cleanup, preflight) and W3 (lifecycle, signals,
taxonomy, events) of change ``rainfall-multi-parcel-e2e-harness``.

They exercise the PURE Python components with a recording command adapter (no
Docker daemon, no real database): the P0 destructive-process safety boundary
(RMEH-001/012), cleanup-before-marker-failure (RMEH-012-B/C), the pre-browser
preflight cardinality/distinctness contract (RMEH-009-A/013-A), the lifecycle
phase machine (RMEH-010-A), signal-safe cleanup (RMEH-010-D), the
mutually-exclusive failure taxonomy + redaction (RMEH-009/012-B), and the
append-only event stream (RMEH-010/012).

Integration tests against a real owned disposable stack live under a separate
``@pytest.mark.integration`` marker and are out of scope for this unit layer.
"""

from __future__ import annotations

import json
import signal
import threading

import pytest

from scripts.rainfall_e2e_harness import (
    BootstrapPrerequisiteFailure,
    BootstrapSafetyFailure,
    CleanupFailure,
    CommandKind,
    CommandResult,
    EventStream,
    FailureClass,
    LeaseResource,
    Lifecycle,
    OwnedBoundary,
    ParcelContract,
    RecordingCommandRunner,
    ResourceLease,
    RunIdentity,
    SceneManifest,
    apply_migrations,
    classify_request_failure,
    homepage_browse_failure,
    manifest_failure,
    preflight_parcel_contracts,
    redact_command,
    redact_text,
    validate_marker_read_only,
)


# --------------------------------------------------------------------------- #
# Shared fakes
# --------------------------------------------------------------------------- #
def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _err(message: str, code: int = 1) -> CommandResult:
    return CommandResult(exit_code=code, stdout="", stderr=message)


def _identity(**overrides) -> RunIdentity:
    """An identity built with NO caller DB overrides — the always-accepted path."""
    return RunIdentity.plan(evidence_dir=overrides.pop("evidence_dir", None))


def _marker_row(identity: RunIdentity, **ovr) -> str:
    """A JSON string the marker query returns when validation should SUCCEED."""
    row = {
        "run_id": identity.run_id,
        "marker_nonce": identity.marker_nonce,
        "database_name": identity.database_name,
    }
    row.update(ovr)
    return json.dumps(row)


# --------------------------------------------------------------------------- #
# W1.1 — SAFETY (RMEH-001-A/B/C)
# --------------------------------------------------------------------------- #
class TestSafety:
    def test_safety_command_kinds_are_disjoint(self):
        kinds = {
            CommandKind.DOCKER_INSPECT,
            CommandKind.DOCKER_CONTROL,
            CommandKind.DATABASE_READONLY,
            CommandKind.DATABASE_MUTATING,
        }
        assert len(kinds) == 4
        assert len({k.value for k in kinds}) == 4

    def test_safety_plan_refuses_external_database_url(self):
        with pytest.raises(BootstrapSafetyFailure, match="database"):
            RunIdentity.plan(database_url="postgres://shared/prod")

    def test_safety_plan_refuses_explicit_database_host(self):
        with pytest.raises(BootstrapSafetyFailure, match="host"):
            RunIdentity.plan(database_host="db.internal")

    def test_safety_plan_refuses_explicit_database_name(self):
        with pytest.raises(BootstrapSafetyFailure, match="database"):
            RunIdentity.plan(database_name="some_other_db")

    def test_safety_plan_refuses_default_shared_database_name(self):
        with pytest.raises(BootstrapSafetyFailure, match="consorcio"):
            RunIdentity.plan(database_name="consorcio")

    def test_safety_plan_refuses_fixed_compose_project(self):
        with pytest.raises(BootstrapSafetyFailure, match="project"):
            RunIdentity.plan(compose_project="consorcio")

    def test_safety_loopback_only_rejects_non_loopback_binding(self):
        identity = _identity()
        runner = RecordingCommandRunner()
        with pytest.raises(BootstrapSafetyFailure, match="loopback"):
            ResourceLease.plan(identity).assert_loopback_only(
                {"postgres": "0.0.0.0:5432", "backend": "0.0.0.0:8000"}
            )
        assert runner.database_mutating_calls == []

    def test_safety_marker_absent_aborts_before_writes(self):
        identity = _identity()
        runner = RecordingCommandRunner()
        runner.program(CommandKind.DATABASE_READONLY, _ok(""))  # empty result → no row
        with pytest.raises(BootstrapSafetyFailure, match="marker"):
            validate_marker_read_only(runner, identity)
        assert runner.database_mutating_calls == []
        assert runner.database_readonly_calls, "marker query is the one read-only call"

    def test_safety_marker_query_error_aborts_before_writes(self):
        identity = _identity()
        runner = RecordingCommandRunner()
        runner.program(CommandKind.DATABASE_READONLY, _err("connection refused"))
        with pytest.raises(BootstrapSafetyFailure, match="marker"):
            validate_marker_read_only(runner, identity)
        assert runner.database_mutating_calls == []

    def test_safety_marker_nonce_mismatch_aborts_before_writes(self):
        identity = _identity()
        runner = RecordingCommandRunner()
        runner.program(
            CommandKind.DATABASE_READONLY,
            _ok(_marker_row(identity, marker_nonce="de" * 32)),
        )
        with pytest.raises(BootstrapSafetyFailure, match="nonce"):
            validate_marker_read_only(runner, identity)
        assert runner.database_mutating_calls == []

    def test_safety_marker_db_name_mismatch_aborts_before_writes(self):
        identity = _identity()
        runner = RecordingCommandRunner()
        runner.program(
            CommandKind.DATABASE_READONLY,
            _ok(_marker_row(identity, database_name="consorcio")),
        )
        with pytest.raises(BootstrapSafetyFailure, match="database"):
            validate_marker_read_only(runner, identity)
        assert runner.database_mutating_calls == []

    def test_safety_marker_run_id_mismatch_aborts_before_writes(self):
        identity = _identity()
        runner = RecordingCommandRunner()
        runner.program(
            CommandKind.DATABASE_READONLY,
            _ok(_marker_row(identity, run_id="b" * 32)),
        )
        with pytest.raises(BootstrapSafetyFailure, match="run"):
            validate_marker_read_only(runner, identity)
        assert runner.database_mutating_calls == []

    def test_safety_owned_boundary_is_sole_marker_gate_construction(self):
        identity = _identity()
        runner = RecordingCommandRunner()
        runner.program(CommandKind.DATABASE_READONLY, _ok(_marker_row(identity)))
        owned = validate_marker_read_only(runner, identity)
        assert isinstance(owned, OwnedBoundary)
        # apply_migrations MUST require the OwnedBoundary token.
        with pytest.raises(BootstrapSafetyFailure, match="owned"):
            apply_migrations(None, runner)

    def test_safety_pre_existing_resource_collision_aborts_without_adoption(self):
        identity = _identity()
        lease = ResourceLease.plan(identity)
        runner = RecordingCommandRunner()
        runner.program(
            CommandKind.DOCKER_INSPECT,
            _ok(json.dumps([{"Name": f"/{lease.volume_name}"}])),
        )
        with pytest.raises(BootstrapSafetyFailure, match="collision"):
            lease.assert_no_resource_collision(runner)
        assert lease.volume_name not in [r.name for r in lease.created_resources]
        assert runner.database_mutating_calls == []


# --------------------------------------------------------------------------- #
# W1.2 — CLEANUP (RMEH-001-B, RMEH-012-B/C)
# --------------------------------------------------------------------------- #
class TestCleanup:
    def test_cleanup_teardown_targets_exact_recorded_id_only(self):
        identity = _identity()
        lease = ResourceLease.plan(identity)
        lease.record_created(_resource("container", "rmeh-abc_db_1", "abc123", identity, lease))
        runner = RecordingCommandRunner()
        runner.program(CommandKind.DOCKER_CONTROL, _ok())
        lease.reconcile_then_teardown(runner, existing=lambda name: False)
        for call in runner.docker_control_calls:
            joined = " ".join(call.command)
            assert "abc123" in joined or "rmeh-abc_db_1" in joined

    def test_cleanup_never_searches_by_prefix(self):
        identity = _identity()
        lease = ResourceLease.plan(identity)
        runner = RecordingCommandRunner()
        lease.reconcile_then_teardown(runner, existing=lambda name: False)
        for call in runner.calls:
            joined = " ".join(call.command)
            assert "name=rmeh-" not in joined
            assert "--filter" not in joined or "name=rmeh-" not in joined

    def test_cleanup_never_global_prunes(self):
        identity = _identity()
        lease = ResourceLease.plan(identity)
        runner = RecordingCommandRunner()
        lease.reconcile_then_teardown(runner, existing=lambda name: False)
        for call in runner.calls:
            joined = " ".join(call.command)
            assert "system prune" not in joined
            assert "volume prune" not in joined
            assert "network prune" not in joined

    def test_cleanup_never_uses_db_token_for_docker_teardown(self):
        identity = _identity()
        lease = ResourceLease.plan(identity)
        lease.record_created(_resource("container", "c", "cid", identity, lease))
        runner = RecordingCommandRunner()
        runner.program(CommandKind.DOCKER_CONTROL, _ok())
        lease.reconcile_then_teardown(runner, existing=lambda name: False)
        for call in runner.docker_control_calls:
            for env_value in (call.env or {}).values():
                assert identity.marker_nonce not in env_value
            assert "POSTGRES_PASSWORD" not in call.command

    def test_cleanup_residual_leased_resource_overrides_passing_run(self):
        identity = _identity()
        lease = ResourceLease.plan(identity)
        lease.record_created(_resource("volume", "rmeh-abc_pgdata", "vid", identity, lease))
        runner = RecordingCommandRunner()
        runner.program(CommandKind.DOCKER_CONTROL, _ok())
        lease.reconcile_then_teardown(runner, existing=lambda name: name == "rmeh-abc_pgdata")
        with pytest.raises(CleanupFailure, match="residual"):
            lease.assert_no_residual_resources()

    def test_cleanup_before_marker_failure_works_without_owned_boundary(self):
        # JD-DES-003: ResourceLease created BEFORE provisioning authorizes Docker
        # teardown independently of the post-marker OwnedBoundary. A marker
        # failure (owned=None) still cleans the recorded Docker resources.
        identity = _identity()
        lease = ResourceLease.plan(identity)
        lease.record_created(_resource("container", "rmeh-abc_db_1", "cid", identity, lease))
        runner = RecordingCommandRunner()
        runner.program(CommandKind.DATABASE_READONLY, _err("marker query failed"))
        runner.program(CommandKind.DOCKER_CONTROL, _ok())
        owned = None
        try:
            validate_marker_read_only(runner, identity)
        except BootstrapSafetyFailure:
            pass
        finally:
            lease.reconcile_then_teardown(runner, existing=lambda name: False)
        assert owned is None
        assert runner.docker_control_calls, "owned=None still drove Docker teardown"


def _resource(
    kind: str, name: str, docker_id: str, identity: RunIdentity, lease: ResourceLease
) -> LeaseResource:
    return LeaseResource(
        kind=kind,
        name=name,
        docker_id=docker_id,
        labels={
            "rmeh.run": identity.run_id,
            "rmeh.lease": lease.lease_id,
            "rmeh.compose_project": lease.project_name,
        },
    )


# --------------------------------------------------------------------------- #
# W1.3 — PREFLIGHT (RMEH-009-A, RMEH-013-A)
# --------------------------------------------------------------------------- #
def _parcel(alias: str, **ovr) -> ParcelContract:
    idx = "ABCDEFGHI".index(alias) + 1
    base = dict(
        alias=alias,
        stable_uuid=f"uuid-{alias}",
        nomenclature=f"NC-{alias}",
        display_identity=f"RMEH-PARCEL-{alias}",
        scope_kind="zone",
        scope_id=f"zone:rmeh-zone-{alias.lower()}:v{idx}",
        scope_version=f"v{idx}",
        effective_cache_key=(f"rainfall-analysis:zone:rmeh-zone-{alias.lower()}:v{idx}:2025"),
        percentile=float(10 * idx + idx),  # 11 / 22 / 33 ...
        accumulation_mm=float(100 * idx + idx * 0.1),
        analysis_revision_id=f"rmeh-rev-{alias.lower()}",
        data_revision=f"data-{alias.lower()}",
        metric_revision=f"metric-{alias.lower()}",
        ready=True,
    )
    base.update(ovr)
    return ParcelContract(**base)


class TestPreflight:
    def test_preflight_accepts_three_distinct_ready_parcels(self):
        preflight = preflight_parcel_contracts([_parcel("A"), _parcel("B"), _parcel("C")])
        assert preflight.ok
        assert preflight.aliases == ("A", "B", "C")

    def test_preflight_rejects_cardinality_not_three(self):
        with pytest.raises(BootstrapPrerequisiteFailure, match="cardinality"):
            preflight_parcel_contracts([_parcel("A"), _parcel("B")])
        with pytest.raises(BootstrapPrerequisiteFailure, match="cardinality"):
            preflight_parcel_contracts([_parcel("A"), _parcel("B"), _parcel("C"), _parcel("D")])

    def test_preflight_rejects_missing_or_unexpected_alias(self):
        with pytest.raises(BootstrapPrerequisiteFailure, match="alias"):
            preflight_parcel_contracts([_parcel("A"), _parcel("B"), _parcel("D")])

    def test_preflight_rejects_duplicate_alias(self):
        with pytest.raises(BootstrapPrerequisiteFailure, match="alias"):
            preflight_parcel_contracts([_parcel("A"), _parcel("A"), _parcel("C")])

    def test_preflight_rejects_non_distinct_percentile(self):
        contracts = [_parcel("A"), _parcel("B", percentile=_parcel("A").percentile), _parcel("C")]
        with pytest.raises(BootstrapPrerequisiteFailure, match="percentile"):
            preflight_parcel_contracts(contracts)

    def test_preflight_rejects_non_distinct_accumulation(self):
        contracts = [
            _parcel("A"),
            _parcel("B"),
            _parcel("C", accumulation_mm=_parcel("A").accumulation_mm),
        ]
        with pytest.raises(BootstrapPrerequisiteFailure, match="accumulation"):
            preflight_parcel_contracts(contracts)

    def test_preflight_rejects_non_distinct_scope_identity(self):
        contracts = [_parcel("A"), _parcel("B", scope_id=_parcel("A").scope_id), _parcel("C")]
        with pytest.raises(BootstrapPrerequisiteFailure, match="scope"):
            preflight_parcel_contracts(contracts)

    def test_preflight_rejects_non_distinct_cache_key(self):
        contracts = [
            _parcel("A"),
            _parcel("B"),
            _parcel("C", effective_cache_key=_parcel("A").effective_cache_key),
        ]
        with pytest.raises(BootstrapPrerequisiteFailure, match="cache"):
            preflight_parcel_contracts(contracts)

    def test_preflight_rejects_unknown_scope_kind(self):
        contracts = [_parcel("A"), _parcel("B"), _parcel("C", scope_kind="planet")]
        with pytest.raises(BootstrapPrerequisiteFailure, match="scope_kind"):
            preflight_parcel_contracts(contracts)

    def test_preflight_rejects_non_ready_parcel(self):
        contracts = [_parcel("A"), _parcel("B"), _parcel("C", ready=False)]
        with pytest.raises(BootstrapPrerequisiteFailure, match="ready"):
            preflight_parcel_contracts(contracts)

    def test_preflight_rejects_non_distinct_revision(self):
        contracts = [
            _parcel("A"),
            _parcel("B"),
            _parcel("C", analysis_revision_id=_parcel("A").analysis_revision_id),
        ]
        with pytest.raises(BootstrapPrerequisiteFailure, match="revision"):
            preflight_parcel_contracts(contracts)

    def test_preflight_diagnostic_names_observed_values(self):
        collide = _parcel("A").percentile
        contracts = [_parcel("A"), _parcel("B", percentile=collide), _parcel("C")]
        with pytest.raises(BootstrapPrerequisiteFailure) as exc:
            preflight_parcel_contracts(contracts)
        msg = str(exc.value)
        assert "percentile" in msg
        assert str(collide) in msg


# --------------------------------------------------------------------------- #
# W3.1 — LIFECYCLE (RMEH-010-A, RMEH-012-A/B)
# --------------------------------------------------------------------------- #
class TestLifecycle:
    def test_lifecycle_phases_progress_through_marker_gate(self):
        lf = Lifecycle()
        assert lf.phase == "CREATED"
        lf.to_lease_planned()
        lf.to_provisioning()
        lf.to_database_owned()
        lf.to_bootstrapped()
        lf.to_preflight_passed()
        lf.to_tests_finished()
        lf.to_evidence_sealed()
        assert lf.phase == "EVIDENCE_SEALED"

    def test_lifecycle_cancellation_phase_enters_lease_cleanup(self):
        lf = Lifecycle()
        lf.to_lease_planned()
        lf.to_provisioning()
        lf.cancel()
        assert lf.phase == "LEASE_CLEANUP"
        lf.to_cleaned()
        assert lf.phase == "CLEANED"

    def test_lifecycle_finally_runs_cleanup_when_owned_is_none(self):
        events: list[str] = []

        def run() -> None:
            lf = Lifecycle()
            lf.to_lease_planned()
            lf.to_provisioning()
            try:
                raise BootstrapSafetyFailure("marker")
            except BootstrapSafetyFailure:
                lf.cancel()
            finally:
                events.append("cleanup")
                lf.to_cleaned()

        run()
        assert events == ["cleanup"]


# --------------------------------------------------------------------------- #
# W3.2 — SIGNALS (RMEH-010-D, RMEH-012-B)
# --------------------------------------------------------------------------- #
class TestSignals:
    def test_signal_handler_sets_cancellation_phase(self):
        lf = Lifecycle()
        lf.to_lease_planned()
        lf.to_provisioning()
        lf.signal_handler()(signal.SIGINT, None)
        assert lf.phase == "LEASE_CLEANUP"
        assert lf.cancelled

    def test_second_signal_shortens_wait_without_changing_cleanup_target(self):
        lf = Lifecycle()
        lf.to_lease_planned()
        lf.to_provisioning()
        h = lf.signal_handler()
        h(signal.SIGINT, None)
        first = lf.cancelled
        # A second signal must NOT change the cleanup target — only shortens wait.
        h(signal.SIGTERM, None)
        assert lf.phase == "LEASE_CLEANUP"
        assert lf.cancelled is first
        assert lf.second_signal_seen

    def test_signal_forwards_termination_to_active_child_process_group(self):
        lf = Lifecycle()
        lf.to_provisioning()
        forwarded: list[int] = []
        lf.attach_child(pid=4242, kill_group=lambda pid: forwarded.append(pid))
        lf.signal_handler()(signal.SIGTERM, None)
        assert 4242 in forwarded


# --------------------------------------------------------------------------- #
# W3.3 — TAXONOMY + REDACTION (RMEH-009, RMEH-012-B)
# --------------------------------------------------------------------------- #
class TestTaxonomy:
    def test_taxonomy_seven_failure_classes_are_distinct(self):
        classes = {
            FailureClass.BOOTSTRAP_SAFETY_FAILURE,
            FailureClass.BOOTSTRAP_PREREQUISITE_FAILURE,
            FailureClass.HARNESS_ACCOUNTING_FAILURE,
            FailureClass.BROWSER_INTEGRITY_FAILURE,
            FailureClass.PRODUCT_ASSERTION_FAILURE,
            FailureClass.CLEANUP_FAILURE,
            FailureClass.PASSED,
        }
        assert len(classes) == 7
        assert len({c.value for c in classes}) == 7

    def test_taxonomy_classify_request_failure_is_exclusive(self):
        assert (
            classify_request_failure(pre_click_integrity_ok=True, click_occurred=True)
            == FailureClass.PRODUCT_ASSERTION_FAILURE
        )
        assert (
            classify_request_failure(pre_click_integrity_ok=False, click_occurred=False)
            == FailureClass.BROWSER_INTEGRITY_FAILURE
        )
        assert (
            classify_request_failure(pre_click_integrity_ok=False, click_occurred=True)
            == FailureClass.BROWSER_INTEGRITY_FAILURE
        )

    def test_redaction_strips_password_values_and_authorization_headers(self):
        redacted = redact_text(
            'POSTGRES_PASSWORD=hunter2 curl -H "Authorization: Bearer abc.def.ghi" '
            '-H "Cookie: sid=secret" /api/v2/geo/analisis-zona'
        )
        assert "hunter2" not in redacted
        assert "Bearer abc.def.ghi" not in redacted
        assert "sid=secret" not in redacted
        assert "POSTGRES_PASSWORD=***" in redacted
        assert "Authorization: Bearer ***" in redacted

    def test_redact_command_redacts_env_password_secret(self):
        redacted = redact_command(
            ["psql", "-c", "SELECT 1"],
            env={"POSTGRES_PASSWORD": "hunter2", "PATH": "/usr/bin"},
        )
        joined = json.dumps(redacted)
        assert "hunter2" not in joined
        assert "POSTGRES_PASSWORD" in joined
        assert "/usr/bin" in joined

    def test_manifest_records_evidence_sha_repo_sha_and_identity(self, tmp_path):
        identity = _identity(evidence_dir=tmp_path)
        lease = ResourceLease.plan(identity)
        manifest = SceneManifest(
            identity=identity,
            lease=lease,
            repo_sha="abc1234",
            evidence_sha256="deadbeef" * 8,
            failure_class=FailureClass.PASSED,
            counts={"passed": 11, "failed": 0, "skipped": 0},
            selection_records=[],
            cleanup_result="cleaned",
        )
        rendered = manifest.to_json()
        assert identity.run_id in rendered
        assert lease.lease_id in rendered
        assert "abc1234" in rendered
        assert "deadbeef" in rendered
        assert FailureClass.PASSED.value in rendered

    def test_manifest_failure_factory_sets_class_and_diagnostics(self, tmp_path):
        identity = _identity(evidence_dir=tmp_path)
        lease = ResourceLease.plan(identity)
        manifest = manifest_failure(
            identity=identity,
            lease=lease,
            failure_class=FailureClass.BOOTSTRAP_SAFETY_FAILURE,
            diagnostics="external DATABASE_URL rejected",
        )
        rendered = manifest.to_json()
        assert FailureClass.BOOTSTRAP_SAFETY_FAILURE.value in rendered
        assert "external DATABASE_URL rejected" in rendered

    def test_homepage_browse_failure_is_browser_integrity(self, tmp_path):
        identity = _identity(evidence_dir=tmp_path)
        lease = ResourceLease.plan(identity)
        manifest = homepage_browse_failure(
            identity=identity,
            lease=lease,
            diagnostics="compass bearing != identity",
        )
        assert manifest.failure_class == FailureClass.BROWSER_INTEGRITY_FAILURE

    def test_accounting_failure_class_is_exclusive(self):
        identity = _identity()
        lease = ResourceLease.plan(identity)
        manifest = manifest_failure(
            identity=identity,
            lease=lease,
            failure_class=FailureClass.HARNESS_ACCOUNTING_FAILURE,
            diagnostics="discovered=0",
        )
        assert manifest.failure_class == FailureClass.HARNESS_ACCOUNTING_FAILURE


# --------------------------------------------------------------------------- #
# W3.4 — EVENTS (RMEH-010, RMEH-012)
# --------------------------------------------------------------------------- #
class TestEvents:
    def test_event_stream_is_append_only_jsonl_flushed_each_phase(self, tmp_path):
        path = tmp_path / "events.jsonl"
        stream = EventStream.open(path)
        stream.append({"phase": "LEASE_PLANNED", "ok": True})
        stream.append({"phase": "PROVISIONING", "ok": True})
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 2
        stream.append({"phase": "DATABASE_OWNED", "ok": True})
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 3
        assert rows[0]["phase"] == "LEASE_PLANNED"  # append-only: untouched

    def test_event_stream_records_cancellation_explanation(self, tmp_path):
        path = tmp_path / "events.jsonl"
        stream = EventStream.open(path)
        stream.append({"phase": "PROVISIONING", "ok": True})
        stream.append_cancellation(signal.SIGTERM, explanation="second signal shortens waits")
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        cancellation = [r for r in rows if r.get("kind") == "cancellation"]
        assert cancellation and cancellation[0]["signal"] == "SIGTERM"
        assert "second signal" in cancellation[0]["explanation"]

    def test_event_stream_concurrent_append_is_safe(self, tmp_path):
        path = tmp_path / "events.jsonl"
        stream = EventStream.open(path)
        errors: list[Exception] = []

        def writer(i: int) -> None:
            try:
                stream.append({"phase": "PROVISIONING", "i": i})
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(rows) == 20
        assert len({r["i"] for r in rows}) == 20
