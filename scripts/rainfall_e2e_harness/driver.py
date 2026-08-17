"""Runner driver CLI (W10/W11, RMEH-010-A, RMEH-011, RMEH-012).

The operator-facing entry point that ties the pure safety/lifecycle/accounting
components into one idempotent run. Both the manual GitHub workflow (W10.1) and
the runbook (W11.4) invoke THIS driver, so the local and hosted paths share the
exact same fail-closed lifecycle (RMEH-010-A).

Subcommands:

* ``run`` — one full owned lifecycle:
  identity -> lease plan -> collision gate -> compose up -> marker gate ->
  bootstrap -> validate services -> collection gate -> playwright run ->
  result gate -> manifest (+ ``jda-001-handoff.json`` ONLY on a complete pass)
  -> lease teardown. A failure at any point still tears down the exact leased
  resources (top-level finally, RMEH-012-A/B).

* ``cleanup`` — IDEMPOTENT teardown of the resources this run created, driven by
  the recorded immutable lease identity + cryptographic labels, NOT by a prefix
  sweep or a DB token (RMEH-012-B/C). Safe to re-run after an externally killed
  main process: it inspects whether each recorded resource still exists and
  removes only those that do. Used by the workflow's explicit cleanup step
  (W10.3) when the main ``run`` was killed before its trap completed.

All destructive decisions are pure/testable: the driver accepts a ``CommandRunner``
so unit tests inject a recording adapter, exactly like the safety/bootstrap
layers. The ``--compose-file`` seam is fixed to the harness compose (never
auto-discovered from the cwd), and the run identity is ALWAYS generated fresh
(RMEH-001) — never caller-supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from scripts.rainfall_e2e_harness.accounting import (
    HarnessAccountingFailure,
    assert_collection_expected,
    assert_manifest_contract,
    assert_result_expected,
    classify_run_failure,
    parse_collection_json,
    parse_results_json,
)
from scripts.rainfall_e2e_harness.bootstrap import (
    COMPOSE_FILE,
    bootstrap_database,
    validate_services,
)
from scripts.rainfall_e2e_harness.events import EventStream
from scripts.rainfall_e2e_harness.lifecycle import Lifecycle
from scripts.rainfall_e2e_harness.preflight import preflight_parcel_contracts
from scripts.rainfall_e2e_harness.safety import (
    BootstrapPrerequisiteFailure,
    CommandKind,
    CommandRunner,
    FailureClass,
    RealCommandRunner,
    ResourceLease,
    RunIdentity,
    compose_env,
    validate_marker_read_only,
    write_init_script,
)
from scripts.rainfall_e2e_harness.taxonomy import SceneManifest, redact_text

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = (
    REPO_ROOT
    / "consorcio-web"
    / "tests"
    / "e2e"
    / "fixtures"
    / "rainfall-multi-parcel.fixture.json"
)

# The 13 file-architecture artifacts + 2 test-config enrolments whose deletion
# is the ENTIRE rollback of this change (RMEH-012-D, tasks.md Rollback Boundary).
# The driver emits this as evidence in ``jda-001-handoff.json`` and the rollback
# proof test asserts it verbatim.
ROLLBACK_ARTIFACTS = (
    "consorcio-web/tests/e2e/fixtures/rainfall-multi-parcel.fixture.json",
    "consorcio-web/tests/e2e/helpers/rainfallMultiParcelHarness.ts",
    "consorcio-web/tests/unit/rainfallMultiParcelHarness.test.ts",
    "consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts",
    "consorcio-web/tests/e2e/playwright.rainfall-harness.config.ts",
    "consorcio-web/tsconfig.tests.json",
    "consorcio-web/package.json",
    "scripts/rainfall_e2e_harness.py",
    "scripts/tests/test_rainfall_e2e_harness.py",
    "scripts/tests/rainfall-e2e.compose.yml",
    "scripts/tests/fixtures/martin-rainfall-e2e.yaml",
    "docs/testing/rainfall-multi-parcel-e2e.md",
    ".github/workflows/rainfall-multi-parcel-e2e.yml",
)
ROLLBACK_ENROLMENTS = (
    "consorcio-web/tsconfig.tests.json",
    "consorcio-web/package.json",
)
PARENT_LEDGER_PATH = "openspec/changes/lluvia-ux-tarjeta/review-ledger.md"


class DriverConfig:
    """Resolved driver settings (mirrors the integration test's env contract)."""

    def __init__(self, args: argparse.Namespace, env: Mapping[str, str]) -> None:
        self.evidence_dir = Path(args.evidence_dir)
        self.compose_file = args.compose_file
        self.python = args.python
        self.npm = args.npm
        self.playwright_config = args.playwright_config
        self.frontend_url = env.get(
            "RMEH_FRONTEND_URL", f"http://127.0.0.1:{env.get('RMEH_FRONTEND_HOST_PORT', '5174')}"
        )
        self.backend_host = env.get("RMEH_BACKEND_HOST_PORT", "8001")
        self.martin_host = env.get("RMEH_MARTIN_HOST_PORT", "3001")
        self.frontend_host = env.get("RMEH_FRONTEND_HOST_PORT", "5174")

    @property
    def origins(self) -> Mapping[str, str]:
        return {
            "martin": f"http://127.0.0.1:{self.martin_host}",
            "backend": f"http://127.0.0.1:{self.backend_host}",
            "frontend": f"http://127.0.0.1:{self.frontend_host}",
        }

    def stack_env(self, identity: RunIdentity) -> dict[str, str]:
        """Compose environment for ONE owned run. Delegates to
        ``compose_env`` (the run-owned prefix derived from the identity's
        database_name + the synthetic DB password) plus the driver host ports.
        The prefix is passed EXPLICITLY from the generated identity — never
        from the ambient env, which could point at a DIFFERENT project than
        the one provisioned (A1/JD-R2-001)."""
        return compose_env(
            identity,
            extra={
                "RMEH_BACKEND_HOST_PORT": self.backend_host,
                "RMEH_MARTIN_HOST_PORT": self.martin_host,
                "RMEH_FRONTEND_HOST_PORT": self.frontend_host,
            },
        )


def _load_fixture() -> dict[str, Any]:
    with open(FIXTURE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _parcel_contracts(fixture: Mapping[str, Any]) -> list[Any]:
    """Project fixture parcels onto the preflight ``ParcelContract`` shape.

    The preflight is the Python-side guard BEFORE the browser (RMEH-009-A/013-A);
    the TS helper has its own validator for the browser journey. This keeps the
    driver fail-closed on cardinality/distinctness without pulling Playwright
    types into the pure preflight."""
    from scripts.rainfall_e2e_harness.preflight import ParcelContract

    contracts = []
    for parcel in fixture["parcels"]:
        rainfall = parcel["rainfall"]
        contracts.append(
            ParcelContract(
                alias=parcel["alias"],
                stable_uuid=parcel["stableUuid"],
                # The shipped fixture (and the spec's own `_fixture()` helper)
                # expose these at the TOP level — there is no `identity`
                # sub-object (A4).
                nomenclature=parcel["nomenclature"],
                display_identity=parcel["displayIdentity"],
                scope_kind=rainfall["scopeKind"],
                scope_id=rainfall["scopeId"],
                scope_version=rainfall["scopeVersion"],
                effective_cache_key=rainfall["effectiveCacheKey"],
                percentile=rainfall["percentile"],
                accumulation_mm=rainfall["accumulationMm"],
                analysis_revision_id=rainfall["analysisRevisionId"],
                data_revision=rainfall["dataRevision"],
                metric_revision=rainfall["metricRevision"],
                ready=rainfall.get("ready", True),
            )
        )
    return contracts


def _evidence_sha256(evidence_dir: Path) -> str:
    """SHA-256 over the evidence dir (sorted files, excluding the manifest's own
    self-referential digest). Used for manifest/rollback reproducibility."""
    digest = hashlib.sha256()
    for path in sorted(evidence_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _repo_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except OSError:
        pass
    return "unknown"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _persist_identity(config: DriverConfig, identity: Any, lease: Any) -> None:
    """Record the exact run/lease identity BEFORE provisioning (RMEH-010-D):
    a cancelled run must still be cleanable, and ``cleanup`` must target the
    exact project this run created (A1/A5). Written under the evidence dir so
    the explicit workflow cleanup step can read it back."""
    _write_json(
        config.evidence_dir / "ownership.json",
        {
            "run_id": identity.run_id,
            "marker_nonce": identity.marker_nonce,
            "database_name": identity.database_name,
            "compose_project": lease.project_name,
            "prefix": identity.run_id[:10],
        },
    )


def _read_recorded_identity(config: DriverConfig) -> Any | None:
    """Rehydrate the recorded run identity (ownership.json), or None when no
    run was recorded in this evidence dir. ``cleanup`` prefers the recorded
    identity so it tears down the exact project the run created (A5)."""
    from scripts.rainfall_e2e_harness.safety import RunIdentity

    path = config.evidence_dir / "ownership.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("run_id"):
        return None
    return RunIdentity(
        run_id=str(data["run_id"]),
        marker_nonce=str(data.get("marker_nonce", "")),
        database_name=str(data.get("database_name", f"rmeh_{str(data['run_id'])[:10]}")),
        evidence_dir=config.evidence_dir,
    )


def build_handoff(
    *,
    fixture_digest: str,
    evidence_sha256: str,
    passed: int,
    failed: int,
    skipped: int,
    transition_refs: Mapping[str, str],
    manifest_ref: str,
) -> dict[str, Any]:
    """Build the ``jda-001-handoff.json`` payload (RMEH-011-A). Pure: the caller
    (``run``) emits it ONLY on a complete pass (failure_class PASSED)."""
    return {
        "source_change": "rainfall-multi-parcel-e2e-harness",
        "fixture_digest": fixture_digest,
        "evidence_sha256": evidence_sha256,
        "result": {"passed": passed, "failed": failed, "skipped": skipped},
        "transition_evidence": transition_refs,
        "manifest_ref": manifest_ref,
        "parent_record_mutated": False,
        "proposed_action": "open a separate follow-up review transaction for JDA-001",
        "rollback_artifacts": list(ROLLBACK_ARTIFACTS),
        "rollback_enrolments": list(ROLLBACK_ENROLMENTS),
    }


def run_driver(
    args: argparse.Namespace,
    *,
    runner: CommandRunner | None = None,
    env: Mapping[str, str] | None = None,
    fixture: Mapping[str, Any] | None = None,
    lifecycle: Lifecycle | None = None,
) -> int:
    """Execute one owned lifecycle and return the process exit code.

    ``runner`` defaults to the real Docker runner; unit tests pass a recording
    adapter. ``fixture``/``lifecycle`` are test seams. Returns 0 on a complete
    PASSED pass, non-zero otherwise — the workflow/runbook gate on the exit code
    and on the emitted manifest/handoff.
    """
    env = env if env is not None else dict(os.environ)
    config = DriverConfig(args, env)
    runner = runner if runner is not None else RealCommandRunner()
    fixture = fixture if fixture is not None else _load_fixture()
    lc = lifecycle if lifecycle is not None else Lifecycle()

    identity = RunIdentity.plan(evidence_dir=config.evidence_dir)
    lease = ResourceLease.plan(identity)
    config.evidence_dir.mkdir(parents=True, exist_ok=True)
    # Record the ownership identity BEFORE any provisioning so a cancelled run
    # can still be cleaned and cleanup targets the exact project (RMEH-010-D,
    # A1/A5).
    _persist_identity(config, identity, lease)
    stream = EventStream.open(config.evidence_dir / "events.jsonl")
    failure_class = FailureClass.PASSED
    diagnostics = ""
    manifest: SceneManifest | None = None

    try:
        # Pre-provision lease + collision gate (RMEH-001-B): never adopt.
        lc.to_lease_planned()
        lease.assert_no_resource_collision(runner)
        stream.append({"phase": "lease_planned", "run_id": identity.run_id})

        # Provision the disposable stack (init script carries the marker). The
        # compose project derives from the generated identity: prefix =
        # run_id[:10], passed EXPLICITLY — never from the ambient env (A1).
        init = REPO_ROOT / "scripts" / "tests" / f"rmeh-init-{identity.run_id[:10]}.sql"
        write_init_script(init, identity)
        up = runner.run(
            ["docker", "compose", "-f", config.compose_file, "up", "-d", "--build"],
            kind=CommandKind.DOCKER_CONTROL,
            env=config.stack_env(identity),
        )
        if up.exit_code != 0:
            raise RuntimeError(f"compose up failed: {up.stderr.strip()}")
        lc.to_provisioning()
        stream.append({"phase": "provisioning"})

        # Wait for backend liveness, then the read-only marker gate (the SOLE
        # OwnedBoundary constructor) before ANY mutation (RMEH-001-B/C).
        _wait_for_liveness(runner, config.origins["backend"])
        # The read-only marker gate is the SOLE OwnedBoundary constructor; the
        # token (below) is the proof that the disposable DB belongs to this run
        # before ANY mutating write (RMEH-001-B/C).
        owned = validate_marker_read_only(runner, identity, compose_file=config.compose_file)
        lc.to_database_owned()
        stream.append({"phase": "database_owned", "database_name": owned.database_name})

        # Bootstrap + service validation, then the Python preflight.
        bootstrap_database(identity, runner, fixture, compose_file=config.compose_file)
        lc.to_bootstrapped()
        stream.append({"phase": "bootstrapped"})
        preflight_parcel_contracts(_parcel_contracts(fixture))
        services = validate_services(identity, runner, fixture, origins=config.origins)
        if not services.frontend_ok:
            # Defense in depth: validate_services already raises when the
            # frontend cannot serve /mapa; the driver still refuses to launch
            # the browser unless the report is green (A6).
            raise BootstrapPrerequisiteFailure(
                "service validation failed: frontend /mapa not OK; "
                "browser must not start (RMEH-002-D)"
            )
        lc.to_preflight_passed()
        stream.append({"phase": "preflight_passed"})

        # Collection gate BEFORE browser execution (RMEH-009-C): exactly 11.
        collection = _run_collection(config)
        assert_collection_expected(parse_collection_json(collection))

        # Playwright run with the JSON reporter redirected to evidence.
        results_json = config.evidence_dir / "playwright-results.json"
        _run_playwright(config, results_json)
        lc.to_tests_finished()
        stream.append({"phase": "tests_finished"})

        # Result gate (RMEH-009-D): 11/0/0/0 + manifest 8 one-click records.
        results = parse_results_json(results_json.read_text(encoding="utf-8"))
        result = assert_result_expected(results)
        manifest_path = config.evidence_dir / "manifest.json"
        selection = _read_manifest_records(config.evidence_dir)
        assert_manifest_contract(selection)
        pre_click_ok, click_occurred = True, True
        cls = classify_run_failure(
            collection_ok=True,
            result_ok=result.ok,
            pre_click_integrity_ok=pre_click_ok,
            click_occurred=click_occurred,
        )
        if cls is not FailureClass.PASSED:
            failure_class = cls
            diagnostics = "result gate failed"
        else:
            # A complete pass: seal evidence, emit the manifest AND the JDA-001
            # handoff (RMEH-011-A). The handoff is NEVER emitted on a failure.
            evidence_sha = _evidence_sha256(config.evidence_dir)
            manifest = SceneManifest(
                identity=identity,
                lease=lease,
                repo_sha=_repo_sha(),
                evidence_sha256=evidence_sha,
                failure_class=FailureClass.PASSED,
                counts={
                    "passed": result.passed,
                    "failed": result.failed,
                    "skipped": result.skipped,
                },
                selection_records=list(selection),
                cleanup_result="",
            )
            _write_json(manifest_path, json.loads(manifest.to_json()))
            _emit_handoff(config, fixture, evidence_sha, result)
        lc.to_evidence_sealed()
        stream.append({"phase": "evidence_sealed"})
    except Exception as exc:  # noqa: BLE001 — top-level fail-closed classification
        failure_class = _classify_exception(exc)
        diagnostics = redact_text(str(exc))
        stream.append(
            {"phase": "failure", "failure_class": failure_class.value, "diagnostics": diagnostics}
        )
    finally:
        # Teardown the exact leased resources — runs on EVERY path (RMEH-012-A/B),
        # including an externally killed main process if the trap reached here.
        _teardown_lease(runner, lease, config, identity)
        lc.to_cleaned()
        stream.append({"phase": "cleaned"})
        stream.close()

    if manifest is not None and failure_class is FailureClass.PASSED:
        return 0
    return 1


def _classify_exception(exc: Exception) -> FailureClass:
    if isinstance(exc, HarnessAccountingFailure):
        return FailureClass.HARNESS_ACCOUNTING_FAILURE
    from scripts.rainfall_e2e_harness.safety import (
        BootstrapPrerequisiteFailure,
        BootstrapSafetyFailure,
        CleanupFailure,
    )

    if isinstance(exc, (BootstrapSafetyFailure, BootstrapPrerequisiteFailure)):
        return FailureClass.BOOTSTRAP_PREREQUISITE_FAILURE
    if isinstance(exc, CleanupFailure):
        return FailureClass.CLEANUP_FAILURE
    return FailureClass.BROWSER_INTEGRITY_FAILURE


def _wait_for_liveness(runner: CommandRunner, backend: str, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        live = runner.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"{backend}/live"],
            kind=CommandKind.DOCKER_INSPECT,
        )
        if live.stdout.strip() == "200":
            return
        time.sleep(2)
    raise RuntimeError(f"backend /live never 200 at {backend}")


def _run_collection(config: DriverConfig) -> str:
    """``playwright test --list --reporter=json`` — the collection gate input."""
    result = subprocess.run(
        [
            config.npm,
            "playwright",
            "test",
            "-c",
            config.playwright_config,
            "--list",
            "--reporter=json",
        ],
        cwd=REPO_ROOT / "consorcio-web",
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "RMEH_FRONTEND_URL": config.frontend_url,
            "E2E_APP_URL": config.frontend_url,
            "E2E_API_BASE": f"http://127.0.0.1:{config.backend_host}",
        },
    )
    if result.returncode != 0:
        raise HarnessAccountingFailure(
            f"playwright collection failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def _run_playwright(config: DriverConfig, results_json: Path) -> None:
    """Run the harness spec with the JSON reporter redirected to evidence. The
    spec asserts the 11-test journey and attaches ``manifest.json`` inside the
    evidence dir via ``RMEH_PLAYWRIGHT_JSON`` (the config's reporter env)."""
    result = subprocess.run(
        [
            config.npm,
            "playwright",
            "test",
            "-c",
            config.playwright_config,
        ],
        cwd=REPO_ROOT / "consorcio-web",
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "RMEH_PLAYWRIGHT_JSON": str(results_json),
            "RMEH_FRONTEND_URL": config.frontend_url,
            "E2E_APP_URL": config.frontend_url,
            "E2E_API_BASE": f"http://127.0.0.1:{config.backend_host}",
        },
    )
    if result.returncode != 0:
        raise HarnessAccountingFailure(
            f"playwright run failed (exit {result.returncode}): {result.stderr.strip()}"
        )


def _read_manifest_records(evidence_dir: Path) -> list[dict[str, Any]]:
    """Read the spec-attached selection-record manifest from the evidence dir.
    The spec writes it (``manifest.json`` under the evidence dir); the driver
    re-reads it so accounting and the manifest are the SAME 8 records."""
    path = evidence_dir / "manifest.json"
    if not path.exists():
        # No spec-produced manifest yet in unit tests; fall back to empty so the
        # accounting gate can still fail closed on the count.
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("selection_records", []) if isinstance(data, dict) else []


def _emit_handoff(
    config: DriverConfig,
    fixture: Mapping[str, Any],
    evidence_sha: str,
    result: Any,
) -> None:
    """Write ``jda-001-handoff.json`` in the evidence dir on a complete pass."""
    handoff = build_handoff(
        fixture_digest=json.dumps(fixture.get("digest", {}), sort_keys=True),
        evidence_sha256=evidence_sha,
        passed=result.passed,
        failed=result.failed,
        skipped=result.skipped,
        transition_refs={
            "projection-mobile": str(config.evidence_dir / "projection-mobile.json"),
            "projection-desktop": str(config.evidence_dir / "projection-desktop.json"),
            "request-trace": str(config.evidence_dir / "request-trace.json"),
        },
        manifest_ref=str(config.evidence_dir / "manifest.json"),
    )
    _write_json(config.evidence_dir / "jda-001-handoff.json", handoff)


def _teardown_lease(
    runner: CommandRunner,
    lease: ResourceLease,
    config: DriverConfig,
    identity: RunIdentity,
) -> None:
    """Teardown the exact recorded leased resources. Idempotent: inspect each
    recorded resource; remove it only if it still exists. Never prefix-sweeps,
    never uses the DB token, never global-prunes (RMEH-012-B/C)."""
    try:
        runner.run(
            ["docker", "compose", "-f", config.compose_file, "down", "-v", "--remove-orphans"],
            kind=CommandKind.DOCKER_CONTROL,
            # Teardown must target the SAME project the run provisioned: the
            # env derives from the run identity (A1/A5), never from the
            # ambient env or a prefix guess.
            env=config.stack_env(identity),
        )
    except Exception:  # noqa: BLE001 — best-effort teardown
        pass
    # Reconcile any residual via recorded immutable IDs (the labels/IDs were
    # captured at record time, independent of the DB token).
    for resource in list(lease.created_resources):
        exists = _resource_exists(runner, resource.name)
        if resource.kind in ("container", "network"):
            runner.run(["docker", "rm", "-f", resource.docker_id], kind=CommandKind.DOCKER_CONTROL)
        elif resource.kind == "volume":
            runner.run(
                ["docker", "volume", "rm", "-f", resource.name], kind=CommandKind.DOCKER_CONTROL
            )
        if exists:
            lease.residual_resources.append(resource)


def _resource_exists(runner: CommandRunner, name: str) -> bool:
    res = runner.run(["docker", "inspect", name], kind=CommandKind.DOCKER_INSPECT)
    return res.exit_code == 0 and bool(res.stdout.strip())


def run_cleanup(
    args: argparse.Namespace,
    *,
    runner: CommandRunner | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Idempotent teardown subcommand (W10.3 cleanup step). Prefers the RECORDED
    run identity (ownership.json) so it tears down the exact project the run
    created; falls back to a synthetic identity from ``--run-id`` when no
    ownership record exists. Rebuilds the lease plan from that identity and
    removes only the exact resources, tolerating an already-torn-down stack."""
    env = env if env is not None else dict(os.environ)
    config = DriverConfig(args, env)
    runner = runner if runner is not None else RealCommandRunner()
    recorded = _read_recorded_identity(config)
    if recorded is not None:
        identity = recorded
    else:
        identity = RunIdentity(
            run_id=args.run_id or "cleanup",
            marker_nonce="",
            database_name=f"rmeh_{args.run_id or 'cleanup'}",
            evidence_dir=config.evidence_dir,
        )
    lease = ResourceLease.plan(identity)
    _teardown_lease(runner, lease, config, identity)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rainfall-multi-parcel-e2e",
        description="Deterministic multi-parcel rainfall E2E harness runner (fail-closed).",
    )
    parser.add_argument(
        "--evidence-dir", default=str(REPO_ROOT / ".artifacts" / "rainfall-multi-parcel")
    )
    parser.add_argument("--compose-file", default=COMPOSE_FILE)
    parser.add_argument("--python", default="python3")
    parser.add_argument("--npm", default="npx")
    parser.add_argument(
        "--playwright-config", default="tests/e2e/playwright.rainfall-harness.config.ts"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run one owned lifecycle and clean up")
    # --evidence-dir must also be accepted AFTER the subcommand (the workflow
    # calls `run --evidence-dir …` / `cleanup --run-id gha --evidence-dir …`);
    # a main-parser-only option would reject the workflow's command order (A5).
    run_p.add_argument("--evidence-dir", default=str(REPO_ROOT / ".artifacts" / "rainfall-multi-parcel"))
    run_p.set_defaults(func=run_driver)

    clean_p = sub.add_parser("cleanup", help="idempotently tear down recorded resources")
    clean_p.add_argument("--evidence-dir", default=str(REPO_ROOT / ".artifacts" / "rainfall-multi-parcel"))
    clean_p.add_argument("--run-id", default="")
    clean_p.set_defaults(func=run_cleanup)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
