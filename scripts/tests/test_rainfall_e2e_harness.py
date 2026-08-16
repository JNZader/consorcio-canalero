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


# --------------------------------------------------------------------------- #
# W5 — BOOTSTRAP (RMEH-002-A, JDA-001, JDB-004)
# --------------------------------------------------------------------------- #
def _inspection_json(**ovr) -> str:
    row = {
        "schema": "public",
        "relkind": "r",
        "owner": "rmeh_user",
        "comment": "",
        "columns": ["id", "nomenclatura", "geometria", "tipo_parcela"],
        "indexes": ["ix_parcelas_catastro_geom", "ix_parcelas_catastro_nomenclatura"],
        "definition_digest": None,
    }
    row.update(ovr)
    return json.dumps(row)


def _soil_view_inspection(**ovr) -> str:
    row = {
        "schema": "public",
        "relkind": "m",
        "owner": "rmeh_user",
        "comment": "mv_suelos_por_zona",
        "columns": ["mv_id", "zona_id", "zona_nombre", "cuenca", "cap", "simbolo", "ip", "ha_suelo"],
        "indexes": ["ux_mv_suelos_por_zona_id", "ix_mv_suelos_cuenca", "ix_mv_suelos_zona"],
        "definition_digest": "d1",
    }
    row.update(ovr)
    return json.dumps(row)


def _harness_view_inspection(**ovr) -> str:
    row = {
        "schema": "public",
        "relkind": "m",
        "owner": "rmeh_user",
        "comment": "rainfall-multi-parcel-e2e-harness owned run=abc123",
        "columns": ["id", "nomenclatura", "tipo_parcela", "desig_oficial", "departamento",
                    "pedania", "superficie_ha", "nro_cuenta", "par_idparcela", "geometria"],
        "indexes": [],
        "definition_digest": "v1",
    }
    row.update(ovr)
    return json.dumps(row)


def _fixture(aliases: tuple[str, ...] = ("A", "B", "C")) -> dict:
    parcels = []
    for alias in aliases:
        i = "ABC".index(alias)
        parcels.append({
            "alias": alias,
            "stableUuid": f"00000000-0000-4000-8000-00000000000{i + 1}",
            "nomenclature": f"NC-{alias}",
            "displayIdentity": f"RMEH-PARCEL-{alias}",
            "rainfall": {
                "percentile": 11 * (i + 1),
                "scopeKind": "zone",
                "scopeId": f"zone:rmeh-zone-{alias.lower()}:v{i + 1}",
                "scopeVersion": f"v{i + 1}",
                "effectiveCacheKey": f"rainfall-analysis:zone:rmeh-zone-{alias.lower()}:v{i + 1}:2025",
                "accumulationMm": float(100 * (i + 1) + (i + 1) * 0.1),
                "analysisRevisionId": f"rmeh-rev-{alias.lower()}",
                "dataRevision": f"data-{alias.lower()}",
                "metricRevision": f"metric-{alias.lower()}",
            },
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            "interiorPoint": {"lng": -62.49 - i * 0.01, "lat": -32.51 - i * 0.01},
            "provenance": {"sourcePath": "x", "sourceFeatureId": f"f{i}", "sourceGeometrySha256": "s", "derivation": "exact-ring-extraction"},
        })
    return {
        "change": "rainfall-multi-parcel-e2e-harness",
        "parcels": parcels,
        "coveringZone": {"kind": "fixture-zone", "id": "rmeh-zone-fixture",
                         "nomenclature": "RMEH-FIXTURE-ZONE",
                         "geometry": {"type": "Polygon", "coordinates": [[[-63, -33], [-62, -33], [-62, -32], [-63, -32], [-63, -33]]]}},
        "coveringSoil": {"kind": "fixture-soil", "id": "rmeh-soil-fixture",
                         "nomenclature": "RMEH-FIXTURE-SOIL", "simbolo": "RMEH-SIMB", "cap": "I",
                         "geometry": {"type": "Polygon", "coordinates": [[[-63, -33], [-62, -33], [-62, -32], [-63, -32], [-63, -33]]]}},
    }


def _program_bootstrap_ok(
    runner: RecordingCommandRunner,
    identity: RunIdentity,
    *,
    parcel_view: str | None = None,
    soil_view: str | None = None,
    rebuild: bool = False,
    parcel_view_after_rebuild: str | None = None,
    compose_file: str | None = None,
) -> None:
    """Program a full happy-path bootstrap sequence (marker -> migrate ->
    inspect -> seed -> views -> postconditions). The parcel view defaults to
    ABSENT (harness slot -> create, no rebuild); the soil view defaults to
    COMPATIBLE (migration-owned, present after migrate -> refresh).
    ``parcel_view_after_rebuild`` lets a test program a DIFFERENT parcel-view
    inspection for the post-rebuild pass (recovery vs. persistent mismatch).
    ``compose_file`` programs the compose-aware migrate path
    (``docker compose ... run --rm migrate``) instead of the raw alembic call."""
    if soil_view is None:
        soil_view = _soil_view_inspection()
    runner.program(CommandKind.DATABASE_READONLY, _ok(_marker_row(identity)))
    runner.program(CommandKind.DATABASE_MUTATING, _ok())
    # source inspections + srid probe (read-only)
    runner.program(CommandKind.DATABASE_READONLY, _ok(_inspection_json()))
    runner.program(CommandKind.DATABASE_READONLY, _ok(_inspection_json(columns=["id", "simbolo", "cap", "ip", "geometria"], indexes=["ix_suelos_catastro_geometria", "ix_suelos_catastro_simbolo"])))
    runner.program(CommandKind.DATABASE_READONLY, _ok(_inspection_json(columns=["id", "nombre", "geometria", "cuenca", "superficie_ha"], indexes=["ix_zonas_operativas_cuenca"])))
    runner.program(CommandKind.DATABASE_READONLY, _ok(json.dumps({"srid": 4326, "postgis": "3.4"})))
    runner.program(CommandKind.DATABASE_READONLY, _ok(parcel_view if parcel_view is not None else ""))
    runner.program(CommandKind.DATABASE_READONLY, _ok(soil_view if soil_view is not None else ""))
    if rebuild:
        runner.program(CommandKind.DOCKER_CONTROL, _ok())
        runner.program(CommandKind.DOCKER_CONTROL, _ok())
        runner.program(CommandKind.DATABASE_READONLY, _ok(_marker_row(identity)))
        runner.program(CommandKind.DATABASE_MUTATING, _ok())
        # same three DISTINCT source inspections as the first pass
        runner.program(CommandKind.DATABASE_READONLY, _ok(_inspection_json()))
        runner.program(CommandKind.DATABASE_READONLY, _ok(_inspection_json(columns=["id", "simbolo", "cap", "ip", "geometria"], indexes=["ix_suelos_catastro_geometria", "ix_suelos_catastro_simbolo"])))
        runner.program(CommandKind.DATABASE_READONLY, _ok(_inspection_json(columns=["id", "nombre", "geometria", "cuenca", "superficie_ha"], indexes=["ix_zonas_operativas_cuenca"])))
        runner.program(CommandKind.DATABASE_READONLY, _ok(json.dumps({"srid": 4326, "postgis": "3.4"})))
        after = parcel_view_after_rebuild if parcel_view_after_rebuild is not None else parcel_view
        runner.program(CommandKind.DATABASE_READONLY, _ok(after if after is not None else ""))
        runner.program(CommandKind.DATABASE_READONLY, _ok(soil_view if soil_view is not None else ""))
    # seed + view work (mutating)
    runner.program(CommandKind.DATABASE_MUTATING, _ok())
    runner.program(CommandKind.DATABASE_MUTATING, _ok())
    runner.program(CommandKind.DATABASE_MUTATING, _ok())
    # soil row postcondition (read-only)
    runner.program(CommandKind.DATABASE_READONLY, _ok("1"))


class TestBootstrap:
    def test_bootstrap_ordering_reads_marker_before_any_mutating_write(self):
        from scripts.rainfall_e2e_harness.bootstrap import bootstrap_database, COMPOSE_FILE

        identity = _identity()
        runner = RecordingCommandRunner()
        _program_bootstrap_ok(runner, identity)
        report = bootstrap_database(identity, runner, _fixture(), compose_file=COMPOSE_FILE)
        assert report.rebuilt is False
        assert report.parcel_view_action in ("create", "refresh")
        # The FIRST recorded call is the marker read; every mutating call comes after it.
        assert runner.calls[0].kind is CommandKind.DATABASE_READONLY
        marker_idx = runner.calls[0]
        assert "rmeh_ownership" in " ".join(marker_idx.command)
        for call in runner.database_mutating_calls:
            assert runner.calls.index(call) > 0, "a mutating write preceded the marker read"
        assert runner.database_mutating_calls, "bootstrap must write (seed + views)"

    def test_bootstrap_uses_compose_file_flag_on_marker_requery(self):
        from scripts.rainfall_e2e_harness.bootstrap import bootstrap_database

        identity = _identity()
        runner = RecordingCommandRunner()
        _program_bootstrap_ok(runner, identity)
        bootstrap_database(identity, runner, _fixture(), compose_file="scripts/tests/rainfall-e2e.compose.yml")
        marker = runner.calls[0]
        assert marker.command[:3] == ["docker", "compose", "-f"]
        assert any("rainfall-e2e.compose.yml" in c for c in marker.command)

    def test_bootstrap_uses_compose_migrate_service_when_compose_aware(self):
        from scripts.rainfall_e2e_harness.bootstrap import bootstrap_database
        from scripts.rainfall_e2e_harness.safety import apply_migrations
        identity = _identity()
        runner = RecordingCommandRunner()
        _program_bootstrap_ok(runner, identity)
        bootstrap_database(identity, runner, _fixture(), compose_file="scripts/tests/rainfall-e2e.compose.yml")
        # The FIRST mutating call is the compose-aware migrate-service invocation
        # (the same DDL path provision used), not the raw alembic command.
        migrate = runner.database_mutating_calls[0]
        assert migrate.command[:2] == ["docker", "compose"]
        assert "migrate" in migrate.command
        # raw alembic path (unit layer, W1 behavior) preserved when compose omitted
        runner2 = RecordingCommandRunner()
        runner2.program(CommandKind.DATABASE_READONLY, _ok(_marker_row(identity)))
        owned = validate_marker_read_only(runner2, identity)
        apply_migrations(owned, runner2)
        assert runner2.database_mutating_calls[0].command == ["alembic", "upgrade", "head"]

    def test_classify_parcel_view_absent(self):
        from scripts.rainfall_e2e_harness.bootstrap import classify_parcel_view
        assert classify_parcel_view(None) == "absent"

    def test_classify_parcel_view_harness_owned(self):
        from scripts.rainfall_e2e_harness.bootstrap import classify_parcel_view, RelationInspection
        insp = RelationInspection(name="vt_parcelas_catastro", schema="public", relkind="m",
                                  owner="rmeh_user", comment="rainfall-multi-parcel-e2e-harness owned run=x",
                                  columns=(), indexes=(), definition_digest=None)
        assert classify_parcel_view(insp) == "harness-owned"

    def test_classify_parcel_view_migration_owned(self):
        from scripts.rainfall_e2e_harness.bootstrap import classify_parcel_view, RelationInspection
        insp = RelationInspection(name="vt_parcelas_catastro", schema="public", relkind="m",
                                  owner="rmeh_user", comment="migration 0013", columns=(), indexes=(),
                                  definition_digest=None)
        assert classify_parcel_view(insp) == "migration-owned"

    def test_classify_parcel_view_unknown(self):
        from scripts.rainfall_e2e_harness.bootstrap import classify_parcel_view, RelationInspection
        insp = RelationInspection(name="vt_parcelas_catastro", schema="public", relkind="m",
                                  owner="other", comment="", columns=(), indexes=(),
                                  definition_digest=None)
        assert classify_parcel_view(insp) == "unknown"

    def test_classify_soil_view_absent_incompatible_compatible(self):
        from scripts.rainfall_e2e_harness.bootstrap import classify_soil_view, RelationInspection
        assert classify_soil_view(None) == "absent"
        bad = RelationInspection(name="mv_suelos_por_zona", schema="public", relkind="r", owner="x",
                                 comment="", columns=("id",), indexes=(), definition_digest=None)
        assert classify_soil_view(bad) == "incompatible"
        good = RelationInspection(name="mv_suelos_por_zona", schema="public", relkind="m", owner="x",
                                  comment="migration", columns=("mv_id", "zona_id", "zona_nombre", "cuenca",
                                                                "cap", "simbolo", "ip", "ha_suelo"),
                                  indexes=("ux_mv_suelos_por_zona_id",), definition_digest="d")
        assert classify_soil_view(good) == "compatible"

    def test_build_seed_sql_is_deterministic_and_covers_three_parcels(self):
        from scripts.rainfall_e2e_harness.bootstrap import build_seed_sql
        sql = build_seed_sql(_fixture())
        assert sql == build_seed_sql(_fixture()), "seed SQL must be byte-for-byte stable"
        assert "TRUNCATE parcelas_catastro, suelos_catastro, zonas_operativas" in sql
        assert "NC-A" in sql and "NC-B" in sql and "NC-C" in sql
        assert sql.count("INSERT INTO parcelas_catastro") == 1
        assert "INSERT INTO zonas_operativas" in sql
        assert "INSERT INTO suelos_catastro" in sql
        assert "ST_Multi" in sql, "soil geometry column is MULTIPOLYGON"
        assert "BEGIN;" in sql and "COMMIT;" in sql, "seed must be a single transaction"

    def test_build_seed_sql_rejects_non_three_cardinality(self):
        from scripts.rainfall_e2e_harness.bootstrap import build_seed_sql
        from scripts.rainfall_e2e_harness.safety import BootstrapPrerequisiteFailure
        with pytest.raises(BootstrapPrerequisiteFailure, match="exactly 3"):
            build_seed_sql(_fixture(aliases=("A", "B")))

    def test_bootstrap_absent_views_creates_parcel_view_and_refreshes_soil_view(self):
        from scripts.rainfall_e2e_harness.bootstrap import bootstrap_database, COMPOSE_FILE
        identity = _identity()
        runner = RecordingCommandRunner()
        _program_bootstrap_ok(runner, identity)  # both views absent
        report = bootstrap_database(identity, runner, _fixture(), compose_file=COMPOSE_FILE)
        assert report.parcel_view_action == "create"
        assert report.rebuilt is False
        assert report.seed_digest
        # mutating calls include the view CREATE + soil REFRESH
        sql = " ".join(" ".join(c.command) for c in runner.database_mutating_calls)
        assert "CREATE MATERIALIZED VIEW vt_parcelas_catastro" in sql
        assert "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_suelos_por_zona" in sql

    def test_bootstrap_harness_owned_view_is_recreated_not_relabeled(self):
        from scripts.rainfall_e2e_harness.bootstrap import bootstrap_database, COMPOSE_FILE
        identity = _identity()
        runner = RecordingCommandRunner()
        _program_bootstrap_ok(runner, identity, parcel_view=_harness_view_inspection())
        report = bootstrap_database(identity, runner, _fixture(), compose_file=COMPOSE_FILE)
        assert report.parcel_view_action == "recreate"
        sql = " ".join(" ".join(c.command) for c in runner.database_mutating_calls)
        assert sql.count("DROP MATERIALIZED VIEW IF EXISTS vt_parcelas_catastro") == 1
        assert sql.count("CREATE MATERIALIZED VIEW vt_parcelas_catastro") == 1

    def test_bootstrap_foreign_incompatible_view_consumes_one_rebuild_then_fails(self):
        from scripts.rainfall_e2e_harness.bootstrap import bootstrap_database, COMPOSE_FILE
        from scripts.rainfall_e2e_harness.safety import BootstrapPrerequisiteFailure
        identity = _identity()
        runner = RecordingCommandRunner()
        incompatible = _inspection_json(relkind="m", comment="migration",
                                        columns=("id", "geometria"),
                                        indexes=(), definition_digest="x")
        _program_bootstrap_ok(runner, identity, parcel_view=incompatible, rebuild=True)
        with pytest.raises(BootstrapPrerequisiteFailure, match="rebuild"):
            bootstrap_database(identity, runner, _fixture(), compose_file=COMPOSE_FILE)
        assert len(runner.docker_control_calls) >= 2, "one bounded rebuild (down -v + up -d)"
        # never relabeled a migration-owned object: no COMMENT ON ... VT_PARCELAS
        sql = " ".join(" ".join(c.command) for c in runner.database_mutating_calls)
        assert "rainfall-multi-parcel-e2e-harness owned" not in sql

    def test_bootstrap_rebuild_recovers_when_second_inspect_is_compatible(self):
        from scripts.rainfall_e2e_harness.bootstrap import bootstrap_database, COMPOSE_FILE
        identity = _identity()
        runner = RecordingCommandRunner()
        # First pass: migration-owned INCOMPATIBLE view -> rebuild; second pass:
        # the harness slot is now ABSENT -> create (recovery within budget).
        _program_bootstrap_ok(runner, identity,
                              parcel_view=_inspection_json(relkind="m", comment="migration",
                                                           columns=("id",), indexes=(), definition_digest="x"),
                              rebuild=True,
                              parcel_view_after_rebuild="")
        report = bootstrap_database(identity, runner, _fixture(), compose_file=COMPOSE_FILE)
        assert report.rebuilt is True
        assert report.parcel_view_action == "create"

    def test_bootstrap_rebuild_budget_exhausted_fails_without_ad_hoc_ddl(self):
        from scripts.rainfall_e2e_harness.bootstrap import bootstrap_database, COMPOSE_FILE
        identity = _identity()
        runner = RecordingCommandRunner()
        # First pass AND second pass are migration-owned/incompatible: the ONE
        # bounded rebuild is consumed and the bootstrap must abort — never
        # relabel, never hand-edit a migration-owned object.
        incompatible = _inspection_json(relkind="m", comment="migration",
                                        columns=("id",), indexes=(), definition_digest="x")
        _program_bootstrap_ok(runner, identity,
                              parcel_view=incompatible,
                              rebuild=True,
                              parcel_view_after_rebuild=incompatible)
        with pytest.raises(BootstrapPrerequisiteFailure, match="did not repair"):
            bootstrap_database(identity, runner, _fixture(), compose_file=COMPOSE_FILE)
        # No mutating write beyond the migrations/rebuild path: the harness
        # never hand-creates the foreign view.
        mutating = runner.database_mutating_calls
        assert all("vt_parcelas_catastro" not in " ".join(c.command) for c in mutating)
        assert all("CREATE MATERIALIZED" not in " ".join(c.command) for c in mutating)

    def test_validate_services_ok(self):
        from scripts.rainfall_e2e_harness.bootstrap import validate_services
        identity = _identity()
        runner = RecordingCommandRunner()
        # probe convention: last stdout line = HTTP code (curl -w '%{http_code}')
        # Martin v0.14.2 catalog shape uses the "tiles" key.
        runner.program(CommandKind.DOCKER_INSPECT, _ok('{"tiles": {"parcelas_catastro": {}}}\n200'))
        for _ in range(3):
            runner.program(CommandKind.DOCKER_INSPECT, _ok("tile-bytes\n200"))
        runner.program(CommandKind.DOCKER_INSPECT, _ok("ok\n200"))
        for _ in range(3):
            runner.program(CommandKind.DOCKER_INSPECT, _ok(json.dumps({"tipo": "parcela"}) + "\n200"))
        runner.program(CommandKind.DOCKER_INSPECT, _ok("html\n200"))
        report = validate_services(identity, runner, _fixture(),
                                   origins={"martin": "http://127.0.0.1:3001",
                                            "backend": "http://127.0.0.1:8001",
                                            "frontend": "http://127.0.0.1:5174"})
        assert report.martin_ok and report.backend_live
        assert report.tile_ok_for == ("A", "B", "C")
        assert report.ficha_ok_for == ("A", "B", "C")
        assert report.frontend_ok

    def test_validate_services_204_tile_aborts_as_prerequisite_failure(self):
        from scripts.rainfall_e2e_harness.bootstrap import validate_services
        from scripts.rainfall_e2e_harness.safety import BootstrapPrerequisiteFailure
        identity = _identity()
        runner = RecordingCommandRunner()
        runner.program(CommandKind.DOCKER_INSPECT, _ok('{"tiles": {"parcelas_catastro": {}}}\n200'))
        runner.program(CommandKind.DOCKER_INSPECT, _ok("204"))
        with pytest.raises(BootstrapPrerequisiteFailure, match="204|tile"):
            validate_services(identity, runner, _fixture(),
                              origins={"martin": "http://127.0.0.1:3001",
                                       "backend": "http://127.0.0.1:8001",
                                       "frontend": "http://127.0.0.1:5174"})

    def test_validate_services_one_bounded_martin_restart_repairs_empty_catalog(self):
        """A fresh stack boots martin BEFORE bootstrap creates the view, so the
        startup catalog is empty; exactly ONE bounded restart picks it up and
        the source is re-required (mirrors the one bounded DB rebuild)."""
        from scripts.rainfall_e2e_harness.bootstrap import validate_services
        identity = _identity()
        runner = RecordingCommandRunner()
        # 1) catalog up but EMPTY (martin booted pre-view) -> triggers restart.
        runner.program(CommandKind.DOCKER_INSPECT, _ok('{"tiles": {}}\n200'))
        # 2) the bounded restart itself.
        runner.program(CommandKind.DOCKER_CONTROL, _ok(""))
        # 3) post-restart catalog now publishes the source.
        runner.program(CommandKind.DOCKER_INSPECT, _ok('{"tiles": {"parcelas_catastro": {}}}\n200'))
        for _ in range(3):
            runner.program(CommandKind.DOCKER_INSPECT, _ok("tile-bytes\n200"))
        runner.program(CommandKind.DOCKER_INSPECT, _ok("ok\n200"))
        for _ in range(3):
            runner.program(CommandKind.DOCKER_INSPECT, _ok(json.dumps({"tipo": "parcela"}) + "\n200"))
        runner.program(CommandKind.DOCKER_INSPECT, _ok("html\n200"))
        report = validate_services(identity, runner, _fixture(),
                                   origins={"martin": "http://127.0.0.1:3001",
                                            "backend": "http://127.0.0.1:8001",
                                            "frontend": "http://127.0.0.1:5174"},
                                   martin_poll_seconds=0)
        assert report.martin_ok and report.backend_live
        assert report.tile_ok_for == ("A", "B", "C")
        assert report.ficha_ok_for == ("A", "B", "C")
        assert report.frontend_ok
        # exactly ONE bounded restart, never more.
        restarts = [c for c in runner.calls if c.kind is CommandKind.DOCKER_CONTROL
                    and "restart" in " ".join(c.command)]
        assert len(restarts) == 1

    def test_validate_services_empty_catalog_aborts_after_one_restart(self):
        """Restart does not heal the catalog -> explicit drift failure, never a
        silent pass or an unbounded restart loop."""
        from scripts.rainfall_e2e_harness.bootstrap import validate_services
        from scripts.rainfall_e2e_harness.safety import BootstrapPrerequisiteFailure
        identity = _identity()
        runner = RecordingCommandRunner()
        runner.program(CommandKind.DOCKER_INSPECT, _ok('{"tiles": {}}\n200'))
        runner.program(CommandKind.DOCKER_CONTROL, _ok(""))
        # 30 post-restart probes, all still empty -> abort.
        for _ in range(30):
            runner.program(CommandKind.DOCKER_INSPECT, _ok('{"tiles": {}}\n200'))
        with pytest.raises(BootstrapPrerequisiteFailure, match="catalog"):
            validate_services(identity, runner, _fixture(),
                              origins={"martin": "http://127.0.0.1:3001",
                                       "backend": "http://127.0.0.1:8001",
                                       "frontend": "http://127.0.0.1:5174"},
                              martin_poll_seconds=0)
        restarts = [c for c in runner.calls if c.kind is CommandKind.DOCKER_CONTROL
                    and "restart" in " ".join(c.command)]
        assert len(restarts) == 1

    def test_tile_xyz_known_values(self):
        from scripts.rainfall_e2e_harness.bootstrap import tile_xyz
        assert tile_xyz(0.0, 0.0, 0) == (0, 0, 0)
        # Web Mercator: at z=1, lng 0..180 -> x=1; lat=45 (north) -> y=0.
        assert tile_xyz(90.0, 45.0, 1) == (1, 0, 1)
        assert tile_xyz(-90.0, 45.0, 1) == (0, 0, 1)

    def test_marker_query_emits_json_and_honours_compose_file_flag(self):
        identity = _identity()
        runner = RecordingCommandRunner()
        runner.program(CommandKind.DATABASE_READONLY, _ok(_marker_row(identity)))
        owned = validate_marker_read_only(runner, identity, compose_file="scripts/tests/rainfall-e2e.compose.yml")
        assert owned.run_id == identity.run_id
        cmd = runner.calls[0].command
        assert "-f" in cmd
        assert any("rainfall-e2e.compose.yml" in c for c in cmd)
        sql = " ".join(cmd)
        assert "json_build_object" in sql, "psql -tA output must be JSON for json.loads"
        # no compose file flag by default (W1 behavior preserved)
        runner2 = RecordingCommandRunner()
        runner2.program(CommandKind.DATABASE_READONLY, _ok(_marker_row(identity)))
        validate_marker_read_only(runner2, identity)
        assert "-f" not in runner2.calls[0].command

    def test_render_init_script_carves_marker_and_matches_identity(self):
        from scripts.rainfall_e2e_harness.safety import render_init_script
        identity = _identity()
        script = render_init_script(identity)
        assert "CREATE TABLE IF NOT EXISTS rmeh_ownership" in script
        assert identity.run_id in script
        assert identity.marker_nonce in script
        assert identity.database_name in script
        # deterministic for the same identity
        assert render_init_script(identity) == script
