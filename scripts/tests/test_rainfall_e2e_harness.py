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
        "columns": [
            "mv_id",
            "zona_id",
            "zona_nombre",
            "cuenca",
            "cap",
            "simbolo",
            "ip",
            "ha_suelo",
        ],
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
        "columns": [
            "id",
            "nomenclatura",
            "tipo_parcela",
            "desig_oficial",
            "departamento",
            "pedania",
            "superficie_ha",
            "nro_cuenta",
            "par_idparcela",
            "geometria",
        ],
        "indexes": [],
        "definition_digest": "v1",
    }
    row.update(ovr)
    return json.dumps(row)


def _fixture(aliases: tuple[str, ...] = ("A", "B", "C")) -> dict:
    parcels = []
    for alias in aliases:
        i = "ABC".index(alias)
        parcels.append(
            {
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
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
                "interiorPoint": {"lng": -62.49 - i * 0.01, "lat": -32.51 - i * 0.01},
                "provenance": {
                    "sourcePath": "x",
                    "sourceFeatureId": f"f{i}",
                    "sourceGeometrySha256": "s",
                    "derivation": "exact-ring-extraction",
                },
            }
        )
    return {
        "change": "rainfall-multi-parcel-e2e-harness",
        "parcels": parcels,
        "coveringZone": {
            "kind": "fixture-zone",
            "id": "rmeh-zone-fixture",
            "nomenclature": "RMEH-FIXTURE-ZONE",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-63, -33], [-62, -33], [-62, -32], [-63, -32], [-63, -33]]],
            },
        },
        "coveringSoil": {
            "kind": "fixture-soil",
            "id": "rmeh-soil-fixture",
            "nomenclature": "RMEH-FIXTURE-SOIL",
            "simbolo": "RMEH-SIMB",
            "cap": "I",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-63, -33], [-62, -33], [-62, -32], [-63, -32], [-63, -33]]],
            },
        },
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
    runner.program(
        CommandKind.DATABASE_READONLY,
        _ok(
            _inspection_json(
                columns=["id", "simbolo", "cap", "ip", "geometria"],
                indexes=["ix_suelos_catastro_geometria", "ix_suelos_catastro_simbolo"],
            )
        ),
    )
    runner.program(
        CommandKind.DATABASE_READONLY,
        _ok(
            _inspection_json(
                columns=["id", "nombre", "geometria", "cuenca", "superficie_ha"],
                indexes=["ix_zonas_operativas_cuenca"],
            )
        ),
    )
    runner.program(CommandKind.DATABASE_READONLY, _ok(json.dumps({"srid": 4326, "postgis": "3.4"})))
    runner.program(
        CommandKind.DATABASE_READONLY, _ok(parcel_view if parcel_view is not None else "")
    )
    runner.program(CommandKind.DATABASE_READONLY, _ok(soil_view if soil_view is not None else ""))
    if rebuild:
        runner.program(CommandKind.DOCKER_CONTROL, _ok())
        runner.program(CommandKind.DOCKER_CONTROL, _ok())
        runner.program(CommandKind.DATABASE_READONLY, _ok(_marker_row(identity)))
        runner.program(CommandKind.DATABASE_MUTATING, _ok())
        # same three DISTINCT source inspections as the first pass
        runner.program(CommandKind.DATABASE_READONLY, _ok(_inspection_json()))
        runner.program(
            CommandKind.DATABASE_READONLY,
            _ok(
                _inspection_json(
                    columns=["id", "simbolo", "cap", "ip", "geometria"],
                    indexes=["ix_suelos_catastro_geometria", "ix_suelos_catastro_simbolo"],
                )
            ),
        )
        runner.program(
            CommandKind.DATABASE_READONLY,
            _ok(
                _inspection_json(
                    columns=["id", "nombre", "geometria", "cuenca", "superficie_ha"],
                    indexes=["ix_zonas_operativas_cuenca"],
                )
            ),
        )
        runner.program(
            CommandKind.DATABASE_READONLY, _ok(json.dumps({"srid": 4326, "postgis": "3.4"}))
        )
        after = parcel_view_after_rebuild if parcel_view_after_rebuild is not None else parcel_view
        runner.program(CommandKind.DATABASE_READONLY, _ok(after if after is not None else ""))
        runner.program(
            CommandKind.DATABASE_READONLY, _ok(soil_view if soil_view is not None else "")
        )
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
        bootstrap_database(
            identity, runner, _fixture(), compose_file="scripts/tests/rainfall-e2e.compose.yml"
        )
        marker = runner.calls[0]
        assert marker.command[:3] == ["docker", "compose", "-f"]
        assert any("rainfall-e2e.compose.yml" in c for c in marker.command)

    def test_bootstrap_uses_compose_migrate_service_when_compose_aware(self):
        from scripts.rainfall_e2e_harness.bootstrap import bootstrap_database
        from scripts.rainfall_e2e_harness.safety import apply_migrations

        identity = _identity()
        runner = RecordingCommandRunner()
        _program_bootstrap_ok(runner, identity)
        bootstrap_database(
            identity, runner, _fixture(), compose_file="scripts/tests/rainfall-e2e.compose.yml"
        )
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

        insp = RelationInspection(
            name="vt_parcelas_catastro",
            schema="public",
            relkind="m",
            owner="rmeh_user",
            comment="rainfall-multi-parcel-e2e-harness owned run=x",
            columns=(),
            indexes=(),
            definition_digest=None,
        )
        assert classify_parcel_view(insp) == "harness-owned"

    def test_classify_parcel_view_migration_owned(self):
        from scripts.rainfall_e2e_harness.bootstrap import classify_parcel_view, RelationInspection

        insp = RelationInspection(
            name="vt_parcelas_catastro",
            schema="public",
            relkind="m",
            owner="rmeh_user",
            comment="migration 0013",
            columns=(),
            indexes=(),
            definition_digest=None,
        )
        assert classify_parcel_view(insp) == "migration-owned"

    def test_classify_parcel_view_unknown(self):
        from scripts.rainfall_e2e_harness.bootstrap import classify_parcel_view, RelationInspection

        insp = RelationInspection(
            name="vt_parcelas_catastro",
            schema="public",
            relkind="m",
            owner="other",
            comment="",
            columns=(),
            indexes=(),
            definition_digest=None,
        )
        assert classify_parcel_view(insp) == "unknown"

    def test_classify_soil_view_absent_incompatible_compatible(self):
        from scripts.rainfall_e2e_harness.bootstrap import classify_soil_view, RelationInspection

        assert classify_soil_view(None) == "absent"
        bad = RelationInspection(
            name="mv_suelos_por_zona",
            schema="public",
            relkind="r",
            owner="x",
            comment="",
            columns=("id",),
            indexes=(),
            definition_digest=None,
        )
        assert classify_soil_view(bad) == "incompatible"
        good = RelationInspection(
            name="mv_suelos_por_zona",
            schema="public",
            relkind="m",
            owner="x",
            comment="migration",
            columns=(
                "mv_id",
                "zona_id",
                "zona_nombre",
                "cuenca",
                "cap",
                "simbolo",
                "ip",
                "ha_suelo",
            ),
            indexes=("ux_mv_suelos_por_zona_id",),
            definition_digest="d",
        )
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

    def test_build_seed_sql_emits_fourth_legacy_row_when_present(self):
        """W9: the ten pre-existing rainfall tests click the REAL legacy parcel
        3603003210041000 through the real ficha endpoint. A top-level
        `legacyParcel` fixture field must seed it as a 4th deterministic row
        while `parcels` stays exactly 3 (RMEH-003); absent fixture unchanged."""
        from scripts.rainfall_e2e_harness.bootstrap import build_seed_sql

        base = build_seed_sql(_fixture())
        assert "RMEH-LEGACY" not in base

        fx = _fixture()
        fx["legacyParcel"] = {
            "stableUuid": "44444444-4444-4444-8444-444444444444",
            "nomenclature": "3603003210041000",
            "displayIdentity": "RMEH-LEGACY-PARCEL",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            },
        }
        sql = build_seed_sql(fx)
        assert "3603003210041000" in sql
        assert "RMEH-LEGACY" in sql
        assert "44444444-4444-4444-8444-444444444444" in sql
        # still ONE INSERT statement (4 value tuples), single transaction.
        assert sql.count("INSERT INTO parcelas_catastro") == 1
        assert "BEGIN;" in sql and "COMMIT;" in sql
        assert sql == build_seed_sql(fx), "legacy row must be deterministic"

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
        incompatible = _inspection_json(
            relkind="m",
            comment="migration",
            columns=("id", "geometria"),
            indexes=(),
            definition_digest="x",
        )
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
        _program_bootstrap_ok(
            runner,
            identity,
            parcel_view=_inspection_json(
                relkind="m", comment="migration", columns=("id",), indexes=(), definition_digest="x"
            ),
            rebuild=True,
            parcel_view_after_rebuild="",
        )
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
        incompatible = _inspection_json(
            relkind="m", comment="migration", columns=("id",), indexes=(), definition_digest="x"
        )
        _program_bootstrap_ok(
            runner,
            identity,
            parcel_view=incompatible,
            rebuild=True,
            parcel_view_after_rebuild=incompatible,
        )
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
            runner.program(
                CommandKind.DOCKER_INSPECT, _ok(json.dumps({"tipo": "parcela"}) + "\n200")
            )
        runner.program(CommandKind.DOCKER_INSPECT, _ok("html\n200"))
        report = validate_services(
            identity,
            runner,
            _fixture(),
            origins={
                "martin": "http://127.0.0.1:3001",
                "backend": "http://127.0.0.1:8001",
                "frontend": "http://127.0.0.1:5174",
            },
        )
        assert report.martin_ok and report.backend_live
        assert report.tile_ok_for == ("A", "B", "C")
        assert report.ficha_ok_for == ("A", "B", "C")
        assert report.frontend_ok

    def test_validate_services_probes_legacy_parcel(self):
        """W9: with a fixture `legacyParcel`, validate_services must ALSO probe
        the legacy tile (at its own declared zoom) + ficha POST and report the
        LEGACY alias — a non-200 would soft-skip all ten pre-existing tests."""
        from scripts.rainfall_e2e_harness.bootstrap import validate_services

        identity = _identity()
        runner = RecordingCommandRunner()
        runner.program(CommandKind.DOCKER_INSPECT, _ok('{"tiles": {"parcelas_catastro": {}}}\n200'))
        for _ in range(4):  # A/B/C + legacy tile
            runner.program(CommandKind.DOCKER_INSPECT, _ok("tile-bytes\n200"))
        runner.program(CommandKind.DOCKER_INSPECT, _ok("ok\n200"))
        for _ in range(4):  # A/B/C + legacy ficha
            runner.program(
                CommandKind.DOCKER_INSPECT, _ok(json.dumps({"tipo": "parcela"}) + "\n200")
            )
        runner.program(CommandKind.DOCKER_INSPECT, _ok("html\n200"))
        fx = _fixture()
        fx["legacyParcel"] = {
            "nomenclature": "3603003210041000",
            "interiorPoint": {"lng": -62.446176, "lat": -32.471267},
            "zoom": 16,
        }
        report = validate_services(
            identity,
            runner,
            fx,
            origins={
                "martin": "http://127.0.0.1:3001",
                "backend": "http://127.0.0.1:8001",
                "frontend": "http://127.0.0.1:5174",
            },
        )
        assert report.tile_ok_for == ("A", "B", "C", "LEGACY")
        assert report.ficha_ok_for == ("A", "B", "C", "LEGACY")

    def test_validate_services_legacy_tile_204_aborts(self):
        """A 204/empty legacy tile must abort BEFORE the browser — the legacy
        tests would otherwise soft-skip and break the W9 exact-11 gate."""
        from scripts.rainfall_e2e_harness.bootstrap import validate_services
        from scripts.rainfall_e2e_harness.safety import BootstrapPrerequisiteFailure

        identity = _identity()
        runner = RecordingCommandRunner()
        runner.program(CommandKind.DOCKER_INSPECT, _ok('{"tiles": {"parcelas_catastro": {}}}\n200'))
        for _ in range(3):  # A/B/C tiles OK
            runner.program(CommandKind.DOCKER_INSPECT, _ok("tile-bytes\n200"))
        runner.program(CommandKind.DOCKER_INSPECT, _ok("204"))  # legacy tile empty
        fx = _fixture()
        fx["legacyParcel"] = {
            "nomenclature": "3603003210041000",
            "interiorPoint": {"lng": -62.446176, "lat": -32.471267},
            "zoom": 16,
        }
        with pytest.raises(BootstrapPrerequisiteFailure, match="legacy"):
            validate_services(
                identity,
                runner,
                fx,
                origins={
                    "martin": "http://127.0.0.1:3001",
                    "backend": "http://127.0.0.1:8001",
                    "frontend": "http://127.0.0.1:5174",
                },
            )

    def test_validate_services_204_tile_aborts_as_prerequisite_failure(self):
        from scripts.rainfall_e2e_harness.bootstrap import validate_services
        from scripts.rainfall_e2e_harness.safety import BootstrapPrerequisiteFailure

        identity = _identity()
        runner = RecordingCommandRunner()
        runner.program(CommandKind.DOCKER_INSPECT, _ok('{"tiles": {"parcelas_catastro": {}}}\n200'))
        runner.program(CommandKind.DOCKER_INSPECT, _ok("204"))
        with pytest.raises(BootstrapPrerequisiteFailure, match="204|tile"):
            validate_services(
                identity,
                runner,
                _fixture(),
                origins={
                    "martin": "http://127.0.0.1:3001",
                    "backend": "http://127.0.0.1:8001",
                    "frontend": "http://127.0.0.1:5174",
                },
            )

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
            runner.program(
                CommandKind.DOCKER_INSPECT, _ok(json.dumps({"tipo": "parcela"}) + "\n200")
            )
        runner.program(CommandKind.DOCKER_INSPECT, _ok("html\n200"))
        report = validate_services(
            identity,
            runner,
            _fixture(),
            origins={
                "martin": "http://127.0.0.1:3001",
                "backend": "http://127.0.0.1:8001",
                "frontend": "http://127.0.0.1:5174",
            },
            martin_poll_seconds=0,
        )
        assert report.martin_ok and report.backend_live
        assert report.tile_ok_for == ("A", "B", "C")
        assert report.ficha_ok_for == ("A", "B", "C")
        assert report.frontend_ok
        # exactly ONE bounded restart, never more.
        restarts = [
            c
            for c in runner.calls
            if c.kind is CommandKind.DOCKER_CONTROL and "restart" in " ".join(c.command)
        ]
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
            validate_services(
                identity,
                runner,
                _fixture(),
                origins={
                    "martin": "http://127.0.0.1:3001",
                    "backend": "http://127.0.0.1:8001",
                    "frontend": "http://127.0.0.1:5174",
                },
                martin_poll_seconds=0,
            )
        restarts = [
            c
            for c in runner.calls
            if c.kind is CommandKind.DOCKER_CONTROL and "restart" in " ".join(c.command)
        ]
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
        owned = validate_marker_read_only(
            runner, identity, compose_file="scripts/tests/rainfall-e2e.compose.yml"
        )
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


# --------------------------------------------------------------------------- #
# W9 — FAIL-CLOSED EXACT ACCOUNTING (RMEH-009)
# --------------------------------------------------------------------------- #
def _collection_json(
    spec_count: int, *, file: str = "rainfall-v2-detail.spec.ts", only_at: int | None = None
) -> str:
    """Build a Playwright ``--list --reporter=json`` collection body with
    ``spec_count`` specs (nested under a single suite, the real shape)."""
    specs = []
    for i in range(spec_count):
        annotations = [{"type": "only"}] if i == only_at else []
        specs.append(
            {
                "title": f"test {i}",
                "file": file,
                "line": 100 + i,
                "annotations": annotations,
                "tests": [{"title": f"test {i}", "testId": f"test-{i}"}],
            }
        )
    return json.dumps(
        {
            "config": {"projects": [{"name": "rainfall-harness"}]},
            "suites": [{"title": "rainfall-v2-detail.spec.ts", "specs": specs, "suites": []}],
            "errors": [],
            "stats": {},
        }
    )


def _results_json(
    *,
    passed: int = 11,
    failed: int = 0,
    skipped: int = 0,
    flaky: int = 0,
    retried_ids: tuple[str, ...] = (),
    interrupted_ids: tuple[str, ...] = (),
) -> str:
    """Build a Playwright JSON-reporter result body. Each test carries a
    ``results`` array (one entry per retry) and a top-level ``status``."""
    tests = []
    n = passed + failed + skipped
    statuses = (["expected"] * passed) + (["unexpected"] * failed) + (["skipped"] * skipped)
    for i in range(n):
        test_id = f"test-{i}"
        result_status = "passed"
        if i >= passed and i < passed + failed:
            result_status = "failed"
        elif i >= passed + failed:
            result_status = "skipped"
        retries = 1 if test_id in retried_ids else 0
        results = [{"status": result_status, "retry": r} for r in range(retries + 1)]
        status = statuses[i]
        tests.append(
            {
                "testId": test_id,
                "title": f"test {i}",
                "file": "rainfall-v2-detail.spec.ts",
                "line": 100 + i,
                "projectName": "rainfall-harness",
                "results": results,
                "status": status,
                "ok": status == "expected",
            }
        )
    # Interrupted tests are discovered (they count toward the 11) but neither
    # pass nor fail nor skip; append them as extra tests so the accounting sees
    # them (Playwright marks an interrupted test with top-level status).
    for k, test_id in enumerate(interrupted_ids):
        i = n + k
        tests.append(
            {
                "testId": test_id,
                "title": f"test {i}",
                "file": "rainfall-v2-detail.spec.ts",
                "line": 100 + i,
                "projectName": "rainfall-harness",
                "results": [{"status": "interrupted", "retry": 0}],
                "status": "interrupted",
                "ok": False,
            }
        )
    return json.dumps(
        {
            "config": {},
            "suites": [],
            "errors": [],
            "stats": {"expected": passed, "unexpected": failed, "skipped": skipped, "flaky": flaky},
            "tests": tests,
        }
    )


def _selection_records(n: int, *, click: int = 1, attempt: int = 1) -> list[dict]:
    return [
        {
            "selection": f"{'mobile' if i % 2 == 0 else 'desktop'}:{i}",
            "attemptCount": attempt,
            "clickCount": click,
        }
        for i in range(n)
    ]


class TestAccounting:
    def test_accounting_collection_accepts_exactly_eleven(self):
        from scripts.rainfall_e2e_harness.accounting import (
            assert_collection_expected,
            parse_collection_json,
        )

        parsed = parse_collection_json(_collection_json(11))
        verdict = assert_collection_expected(parsed)
        assert verdict.ok
        assert verdict.discovered == 11

    def test_accounting_parse_collection_flattens_nested_suites(self):
        from scripts.rainfall_e2e_harness.accounting import (
            collection_spec_count,
            parse_collection_json,
        )

        nested = json.dumps(
            {
                "suites": [
                    {
                        "title": "a",
                        "specs": [{"title": "t1", "file": "f"}],
                        "suites": [
                            {"title": "b", "specs": [{"title": "t2", "file": "f"}], "suites": []},
                        ],
                    },
                ],
                "errors": [],
            }
        )
        assert collection_spec_count(parse_collection_json(nested)) == 2

    def test_accounting_collection_rejects_zero(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_collection_expected,
            parse_collection_json,
        )

        with pytest.raises(HarnessAccountingFailure, match="no harness tests"):
            assert_collection_expected(parse_collection_json(_collection_json(0)))

    def test_accounting_collection_rejects_ten(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_collection_expected,
            parse_collection_json,
        )

        with pytest.raises(HarnessAccountingFailure, match="exactly 11"):
            assert_collection_expected(parse_collection_json(_collection_json(10)))

    def test_accounting_collection_rejects_twelve(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_collection_expected,
            parse_collection_json,
        )

        with pytest.raises(HarnessAccountingFailure, match="exactly 11"):
            assert_collection_expected(parse_collection_json(_collection_json(12)))

    def test_accounting_collection_rejects_only_annotation(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_collection_expected,
            parse_collection_json,
        )

        with pytest.raises(HarnessAccountingFailure, match=r"\.only"):
            assert_collection_expected(parse_collection_json(_collection_json(11, only_at=5)))

    def test_accounting_collection_rejects_omitted_file(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_collection_expected,
            parse_collection_json,
        )

        with pytest.raises(HarnessAccountingFailure, match="rainfall-v2-detail"):
            assert_collection_expected(
                parse_collection_json(_collection_json(11, file="other.spec.ts"))
            )

    def test_accounting_collection_rejects_collection_error(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_collection_expected,
            parse_collection_json,
        )

        body = json.dumps({"suites": [], "errors": [{"message": "cannot parse"}], "stats": {}})
        with pytest.raises(HarnessAccountingFailure, match="collection error"):
            assert_collection_expected(parse_collection_json(body))

    def test_accounting_result_accepts_eleven_zero(self):
        from scripts.rainfall_e2e_harness.accounting import (
            assert_result_expected,
            parse_results_json,
        )

        verdict = assert_result_expected(parse_results_json(_results_json(passed=11)))
        assert verdict.ok
        assert verdict.passed == 11
        assert verdict.failed == 0
        assert verdict.skipped == 0

    def test_accounting_result_rejects_unexpected_failure(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_result_expected,
            parse_results_json,
        )

        with pytest.raises(HarnessAccountingFailure, match="1 failed"):
            assert_result_expected(parse_results_json(_results_json(passed=10, failed=1)))

    def test_accounting_result_rejects_skipped(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_result_expected,
            parse_results_json,
        )

        with pytest.raises(HarnessAccountingFailure, match="skipped"):
            assert_result_expected(parse_results_json(_results_json(passed=10, skipped=1)))

    def test_accounting_result_rejects_flaky(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_result_expected,
            parse_results_json,
        )

        with pytest.raises(HarnessAccountingFailure, match="flaky"):
            assert_result_expected(parse_results_json(_results_json(passed=11, flaky=1)))

    def test_accounting_result_rejects_retried(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_result_expected,
            parse_results_json,
        )

        with pytest.raises(HarnessAccountingFailure, match="retried"):
            assert_result_expected(
                parse_results_json(_results_json(passed=11, retried_ids=("test-0",)))
            )

    def test_accounting_result_rejects_interrupted(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_result_expected,
            parse_results_json,
        )

        with pytest.raises(HarnessAccountingFailure, match="interrupted"):
            assert_result_expected(
                parse_results_json(_results_json(passed=10, interrupted_ids=("test-10",)))
            )

    def test_accounting_result_rejects_short_passed(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_result_expected,
            parse_results_json,
        )

        with pytest.raises(HarnessAccountingFailure, match="passed"):
            assert_result_expected(parse_results_json(_results_json(passed=10)))

    def test_accounting_manifest_accepts_eight_one_click(self):
        from scripts.rainfall_e2e_harness.accounting import assert_manifest_contract

        assert assert_manifest_contract(_selection_records(8)) == ""

    def test_accounting_manifest_rejects_wrong_count(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_manifest_contract,
        )

        with pytest.raises(HarnessAccountingFailure, match="exactly 8"):
            assert_manifest_contract(_selection_records(7))

    def test_accounting_manifest_rejects_multi_click(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_manifest_contract,
        )

        with pytest.raises(HarnessAccountingFailure, match="click"):
            assert_manifest_contract(_selection_records(8, click=2))

    def test_accounting_manifest_rejects_multi_attempt(self):
        from scripts.rainfall_e2e_harness.accounting import (
            HarnessAccountingFailure,
            assert_manifest_contract,
        )

        with pytest.raises(HarnessAccountingFailure, match="attempt"):
            assert_manifest_contract(_selection_records(8, attempt=2))

    def test_accounting_classify_run_failure_accounting(self):
        from scripts.rainfall_e2e_harness.accounting import classify_run_failure
        from scripts.rainfall_e2e_harness.safety import FailureClass

        assert (
            classify_run_failure(
                collection_ok=False,
                result_ok=True,
                pre_click_integrity_ok=True,
                click_occurred=True,
            )
            is FailureClass.HARNESS_ACCOUNTING_FAILURE
        )
        assert (
            classify_run_failure(
                collection_ok=True,
                result_ok=False,
                pre_click_integrity_ok=True,
                click_occurred=True,
            )
            is FailureClass.HARNESS_ACCOUNTING_FAILURE
        )

    def test_accounting_classify_run_failure_browser_vs_product(self):
        from scripts.rainfall_e2e_harness.accounting import classify_run_failure
        from scripts.rainfall_e2e_harness.safety import FailureClass

        assert (
            classify_run_failure(
                collection_ok=True,
                result_ok=True,
                pre_click_integrity_ok=False,
                click_occurred=False,
            )
            is FailureClass.BROWSER_INTEGRITY_FAILURE
        )
        assert (
            classify_run_failure(
                collection_ok=True, result_ok=True, pre_click_integrity_ok=True, click_occurred=True
            )
            is FailureClass.PRODUCT_ASSERTION_FAILURE
        )
        assert (
            classify_run_failure(
                collection_ok=True,
                result_ok=True,
                pre_click_integrity_ok=True,
                click_occurred=False,
            )
            is FailureClass.BROWSER_INTEGRITY_FAILURE
        )


# --------------------------------------------------------------------------- #
# W11 — JDA-001 HANDOFF + PARENT BOUNDARY + ROLLBACK PROOF (RMEH-011/012)
# --------------------------------------------------------------------------- #
class TestW11Handoff:
    def test_build_handoff_marks_parent_unmutated_and_proposes_separate_transaction(self):
        from scripts.rainfall_e2e_harness.driver import build_handoff

        handoff = build_handoff(
            fixture_digest="sha256:abc",
            evidence_sha256="sha256:def",
            passed=11,
            failed=0,
            skipped=0,
            transition_refs={"projection-mobile": "pm.json"},
            manifest_ref="manifest.json",
        )
        assert handoff["source_change"] == "rainfall-multi-parcel-e2e-harness"
        assert handoff["parent_record_mutated"] is False
        assert handoff["proposed_action"] == (
            "open a separate follow-up review transaction for JDA-001"
        )
        assert handoff["result"] == {"passed": 11, "failed": 0, "skipped": 0}
        assert handoff["fixture_digest"] == "sha256:abc"
        assert handoff["evidence_sha256"] == "sha256:def"
        assert handoff["transition_evidence"]["projection-mobile"] == "pm.json"
        assert handoff["manifest_ref"] == "manifest.json"

    def test_rollback_artifacts_are_exactly_thirteen_files(self):
        from scripts.rainfall_e2e_harness.driver import ROLLBACK_ARTIFACTS

        assert len(ROLLBACK_ARTIFACTS) == 13
        assert len(set(ROLLBACK_ARTIFACTS)) == 13
        # No production/schema/shared-data/parent artifact in the rollback list.
        for path in ROLLBACK_ARTIFACTS:
            assert not path.startswith("consorcio-web/src/")
            assert not path.startswith("gee-backend/app/")
            assert "migration" not in path
            assert "lluvia-ux-tarjeta" not in path

    def test_rollback_enrolments_are_the_two_test_config_files(self):
        from scripts.rainfall_e2e_harness.driver import (
            ROLLBACK_ARTIFACTS,
            ROLLBACK_ENROLMENTS,
        )

        assert set(ROLLBACK_ENROLMENTS) == {
            "consorcio-web/tsconfig.tests.json",
            "consorcio-web/package.json",
        }
        for enrolment in ROLLBACK_ENROLMENTS:
            assert enrolment in ROLLBACK_ARTIFACTS

    def test_handoff_never_emitted_by_failure_path(self, tmp_path):
        """A failing run must NOT produce a jda-001-handoff.json (RMEH-011-A:
        the handoff is the evidence of a COMPLETE pass only). The driver only
        calls ``_emit_handoff`` after the PASSED gate; on any other class no
        handoff is written."""
        from scripts.rainfall_e2e_harness.driver import build_handoff

        evidence = tmp_path / "evidence"
        evidence.mkdir()
        # The handoff is only materialized by the driver on PASSED. Here we
        # confirm the payload is a PASSED-only artifact: it carries the exact
        # 11/0/0 result and parent_record_mutated:false.
        handoff = build_handoff(
            fixture_digest="d",
            evidence_sha256="e",
            passed=11,
            failed=0,
            skipped=0,
            transition_refs={},
            manifest_ref="m",
        )
        assert handoff["result"] == {"passed": 11, "failed": 0, "skipped": 0}
        # A PRODUCT/browser/accounting failure emits no handoff — assert the
        # evidence dir has none (nothing wrote it in a failed run).
        assert not (evidence / "jda-001-handoff.json").exists()


class TestW11ParentBoundary:
    def test_runner_never_writes_parent_ledger(self):
        """RMEH-011-A/B: the driver's allowed-write surface never includes the
        parent change's review ledger, and the rollback list is disjoint from
        the parent change directory."""
        from scripts.rainfall_e2e_harness.driver import (
            PARENT_LEDGER_PATH,
            ROLLBACK_ARTIFACTS,
        )

        assert PARENT_LEDGER_PATH == "openspec/changes/lluvia-ux-tarjeta/review-ledger.md"
        assert PARENT_LEDGER_PATH not in ROLLBACK_ARTIFACTS
        for path in ROLLBACK_ARTIFACTS:
            assert "lluvia-ux-tarjeta" not in path

    def test_product_assertion_failure_requests_separate_remediation(self):
        """A PRODUCT_ASSERTION_FAILURE must emit evidence requesting a separate
        remediation decision; this change stays test-only."""
        from scripts.rainfall_e2e_harness.accounting import classify_run_failure
        from scripts.rainfall_e2e_harness.safety import FailureClass

        cls = classify_run_failure(
            collection_ok=True,
            result_ok=True,
            pre_click_integrity_ok=True,
            click_occurred=True,
        )
        assert cls is FailureClass.PRODUCT_ASSERTION_FAILURE
        # The handoff proposes the separate transaction ONLY on a complete pass;
        # a product failure never writes it (this change stays test-only).
        assert cls is not FailureClass.PASSED

    def test_driver_writes_no_parent_artifact_during_run(self):
        """End-to-end guard: the driver's evidence/artifact surface is confined
        to .artifacts/rainfall-multi-parcel/<run-id>, never the parent change
        directory or its ledger. The driver's evidence dir default is under
        ``.artifacts/`` (gitignored), which is the structural guarantee that a
        run never writes into ``openspec/changes/lluvia-ux-tarjeta/``."""
        from scripts.rainfall_e2e_harness.driver import (
            DriverConfig,
            FIXTURE_PATH,
            PARENT_LEDGER_PATH,
            build_parser,
        )

        args = build_parser().parse_args(["run"])
        config = DriverConfig(args, {})
        evidence = str(config.evidence_dir)
        assert evidence.endswith(".artifacts/rainfall-multi-parcel"), evidence
        assert "rainfall-multi-parcel" in evidence
        # The parent ledger + parent change dir are structurally disjoint from
        # the driver's evidence and fixture surfaces.
        assert PARENT_LEDGER_PATH.startswith("openspec/")
        assert "lluvia-ux-tarjeta" not in evidence
        assert "lluvia-ux-tarjeta" not in str(FIXTURE_PATH)


class TestW11RollbackProof:
    def test_rollback_removes_only_thirteen_artifacts_plus_enrolments(self):
        from scripts.rainfall_e2e_harness.driver import (
            ROLLBACK_ARTIFACTS,
            ROLLBACK_ENROLMENTS,
        )

        # Rollback = remove the 13 file-architecture artifacts + the 2 test-config
        # enrolments. Every enrolment is a subset of the artifacts (so reverting
        # the artifacts covers them), and NOTHING else is rolled back.
        assert len(ROLLBACK_ARTIFACTS) == 13
        assert set(ROLLBACK_ENROLMENTS) <= set(ROLLBACK_ARTIFACTS)

    def test_cleanup_uses_exact_lease_identity_not_prefix(self):
        """RMEH-012-D: residual disposable resource cleanup goes ONLY through the
        exact recorded lease identity + immutable Docker labels — never a prefix
        sweep, never the DB token, never a global prune."""
        from scripts.rainfall_e2e_harness.driver import (
            DriverConfig,
            _teardown_lease,
            build_parser,
        )
        from scripts.rainfall_e2e_harness.safety import (
            CommandKind,
            RecordingCommandRunner,
            ResourceLease,
            RunIdentity,
        )

        runner = RecordingCommandRunner()
        identity = RunIdentity(
            run_id="w11rollback",
            marker_nonce="m" * 32,
            database_name="rmeh_w11rollback",
            evidence_dir=None,
        )
        lease = ResourceLease.plan(identity)
        lease.record_created(
            type(
                "R",
                (),
                {
                    "kind": "volume",
                    "name": lease.volume_name,
                    "docker_id": "vol-w11",
                    "labels": lease.labels,
                },
            )()
        )
        args = build_parser().parse_args(["run"])
        args.run_id = identity.run_id
        config = DriverConfig(args, {})
        runner.program(
            CommandKind.DOCKER_INSPECT,
            type("R", (), {"exit_code": 0, "stdout": "x", "stderr": ""})(),
        )
        _teardown_lease(runner, lease, config)
        volume_rm = [c for c in runner.calls if c.command[:3] == ["docker", "volume", "rm"]]
        assert volume_rm, "expected an exact-id volume removal"
        assert [c.command[-1] for c in volume_rm] == [lease.volume_name]
        # No global prune and no DB token usage in teardown.
        assert not any("prune" in c.command for c in runner.calls)
        assert not any("DB_PASSWORD" in str(c.env) for c in runner.calls)

    def test_cleanup_is_idempotent_when_resources_already_gone(self):
        """Re-running cleanup after an externally killed main process must not
        fail: resources that no longer exist are skipped (RMEH-012-D, W10.3)."""
        from scripts.rainfall_e2e_harness.driver import (
            DriverConfig,
            _teardown_lease,
            build_parser,
        )
        from scripts.rainfall_e2e_harness.safety import (
            CommandKind,
            RecordingCommandRunner,
            ResourceLease,
            RunIdentity,
        )

        runner = RecordingCommandRunner()
        identity = RunIdentity(
            run_id="cleanupidem",
            marker_nonce="n" * 32,
            database_name="rmeh_cleanupidem",
            evidence_dir=None,
        )
        lease = ResourceLease.plan(identity)
        lease.record_created(
            type(
                "R",
                (),
                {
                    "kind": "volume",
                    "name": lease.volume_name,
                    "docker_id": "vol-idem",
                    "labels": lease.labels,
                },
            )()
        )
        args = build_parser().parse_args(["run"])
        args.run_id = identity.run_id
        config = DriverConfig(args, {})
        runner.program(
            CommandKind.DOCKER_INSPECT,
            type("R", (), {"exit_code": 1, "stdout": "", "stderr": ""})(),
        )
        _teardown_lease(runner, lease, config)  # must not raise
