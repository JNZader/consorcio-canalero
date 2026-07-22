"""Static contracts for deterministic build, test, and release workflows."""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TRIVY_ACTION = "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25"


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _job_block(workflow: str, job: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(job)}:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
        workflow,
    )
    assert match is not None, f"job {job!r} is missing"
    return match.group("body")


def _needs(workflow: str, job: str) -> set[str]:
    match = re.search(
        r"(?m)^    needs:\s*\[(?P<jobs>[^\]]+)\]\s*$",
        _job_block(workflow, job),
    )
    assert match is not None, f"job {job!r} has no inline needs list"
    return {dependency.strip() for dependency in match.group("jobs").split(",")}


def _assert_fail_closed_trivy(job: str) -> None:
    upload = "uses: github/codeql-action/upload-sarif@v3"

    assert f"uses: {TRIVY_ACTION}" in job
    assert "severity: CRITICAL,HIGH" in job
    assert "exit-code: '1'" in job
    assert "continue-on-error: true" not in job
    assert upload in job
    assert "if: always()" in job[job.index(upload) :]


def test_frontend_docker_build_has_every_required_input_before_build() -> None:
    dockerfile = _read("consorcio-web/Dockerfile")
    version_script = _read("consorcio-web/scripts/gen-version.mjs")
    version_copy = "COPY scripts/gen-version.mjs ./scripts/gen-version.mjs"
    build = "RUN npm run build"

    assert dockerfile.index(version_copy) < dockerfile.index(build)
    assert "process.env.CF_PAGES_COMMIT_SHA" in version_script
    assert "ARG VITE_API_URL" in dockerfile
    assert "ARG VITE_MARTIN_URL" in dockerfile
    assert "ARG BUILD_COMMIT_SHA" in dockerfile
    assert "VITE_API_URL=$VITE_API_URL" in dockerfile
    assert "VITE_MARTIN_URL=$VITE_MARTIN_URL" in dockerfile
    assert "CF_PAGES_COMMIT_SHA=$BUILD_COMMIT_SHA" in dockerfile


def test_frontend_pr_and_manual_runs_reach_every_quality_gate() -> None:
    frontend = _read(".github/workflows/frontend.yml")
    event_gate = "github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch'"

    assert "pull_request:" in frontend
    assert "workflow_dispatch:" in frontend
    for job in ("mutation", "accessibility", "build"):
        assert event_gate in _job_block(frontend, job)

    build = _job_block(frontend, "build")
    assert "needs: [lint, test, typecheck, smoke, mutation, accessibility]" in build

    for script in (
        "npm run lint",
        "npm run test:run",
        "npm run typecheck",
        "npm run test:smoke",
        "npm run mutation:run",
        "npm run build",
    ):
        assert script in frontend


def test_accessibility_gate_uses_lockfile_playwright_across_all_browsers() -> None:
    frontend = _read(".github/workflows/frontend.yml")
    accessibility = _job_block(frontend, "accessibility")
    package = json.loads(_read("consorcio-web/package.json"))
    lockfile = json.loads(_read("consorcio-web/package-lock.json"))
    playwright = lockfile["packages"]["node_modules/@playwright/test"]
    config = _read("consorcio-web/tests/accessibility/playwright.config.ts")

    assert package["scripts"]["test:a11y"].startswith("playwright test")
    assert "@playwright/test" in package["devDependencies"]
    assert playwright["version"] == playwright["dependencies"]["playwright"]
    assert "npm ci --no-audit --no-fund --legacy-peer-deps" in accessibility
    assert "npx playwright install --with-deps chromium firefox webkit" in accessibility
    assert "@latest" not in accessibility
    assert "CI=1 npm run test:a11y" in accessibility
    assert "uses: actions/upload-artifact@v4" in accessibility
    assert "if: always()" in accessibility
    assert "consorcio-web/a11y-report/" in accessibility
    assert "consorcio-web/test-results/" in accessibility

    for project in (
        "Desktop Chrome",
        "Desktop Firefox",
        "Mobile Safari",
        "Mobile Android",
    ):
        assert project in config


def test_backend_pr_and_manual_runs_reach_mutation_and_security() -> None:
    backend = _read(".github/workflows/backend.yml")
    event_gate = "github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch'"

    assert event_gate in _job_block(backend, "mutation")
    assert "pytest tests/ -v --cov=app --cov-fail-under=60" in backend
    assert "python3 scripts/cosmic_gate.py --min-kill-rate 0.30" in backend

    security = _job_block(backend, "security")
    assert _needs(backend, "security") == {"lint", "typecheck", "test", "mutation"}
    assert "contents: read" in security
    _assert_fail_closed_trivy(security)


def test_deploy_publish_is_push_only_and_rollout_is_explicitly_opt_in() -> None:
    deploy = _read(".github/workflows/deploy.yml")
    trigger = deploy.split("\n# Frontend:", 1)[0]

    assert re.search(r"(?m)^  push:\n    branches: \[main\]$", trigger)
    assert "pull_request:" not in trigger
    assert "workflow_dispatch:" not in trigger

    mutation = _job_block(deploy, "mutation-backend")
    assert _needs(deploy, "mutation-backend") == {"quality-backend"}
    assert "python3 scripts/cosmic_gate.py --min-kill-rate 0.30" in mutation

    security = _job_block(deploy, "security-backend")
    assert _needs(deploy, "security-backend") == {"quality-backend"}
    assert "contents: read" in security
    _assert_fail_closed_trivy(security)

    publish_gates = {"quality-backend", "mutation-backend", "security-backend"}
    for job in ("build-backend", "build-geo-worker"):
        build = _job_block(deploy, job)
        assert _needs(deploy, job) == publish_gates
        assert "push: true" in build

    rollout = _job_block(deploy, "deploy")
    assert _needs(deploy, "deploy") == {"build-backend", "build-geo-worker"}
    assert "vars.ENABLE_PRODUCTION_DEPLOY == 'true'" in rollout
    assert "vars.DEPLOY_WEBHOOK_URL != ''" in rollout
    assert "secrets.DEPLOY_WEBHOOK_SECRET" in rollout
    assert deploy.count("push: true") == 2


def test_deploy_quality_gate_only_references_current_contract_tests() -> None:
    deploy = _read(".github/workflows/deploy.yml")
    quality = _job_block(deploy, "quality-backend")
    references = set(re.findall(r"(?<![\w/-])(tests/[a-zA-Z0-9_./-]+\.py)\b", quality))

    assert references
    for reference in references:
        assert (REPO_ROOT / "gee-backend" / reference).is_file(), reference

    assert "tests/test_reports_contract.py" not in quality
    assert "tests/test_sugerencias_contract.py" not in quality
    assert "tests/test_ci_workflow_contracts.py" in quality
    assert "tests/new/ --cov=app" in quality
    assert "ruff check ." in quality
    assert "mypy app/auth app/domains/padron app/domains/denuncias" in quality


def test_workflow_shell_and_package_script_references_exist() -> None:
    frontend = _read(".github/workflows/frontend.yml")
    backend = _read(".github/workflows/backend.yml")
    deploy = _read(".github/workflows/deploy.yml")
    package = json.loads(_read("consorcio-web/package.json"))

    invoked_scripts = set(re.findall(r"\bnpm run ([a-zA-Z0-9:_-]+)", frontend))
    assert invoked_scripts <= package["scripts"].keys()

    python_scripts = set(
        re.findall(
            r"\bpython3?\s+(scripts/[a-zA-Z0-9_./-]+\.py)",
            backend + "\n" + deploy,
        )
    )
    assert python_scripts
    for reference in python_scripts:
        assert (REPO_ROOT / "gee-backend" / reference).is_file(), reference


def test_ci_workflows_never_run_production_writing_e2e() -> None:
    for workflow in (
        ".github/workflows/frontend.yml",
        ".github/workflows/backend.yml",
        ".github/workflows/deploy.yml",
    ):
        text = _read(workflow)
        assert "test:e2e" not in text
        assert "tests/e2e" not in text
        assert "PLAYWRIGHT_BASE_URL" not in text


def test_codeql_keeps_javascript_and_python_security_scans() -> None:
    codeql = _read(".github/workflows/codeql.yml")

    assert "javascript-typescript" in codeql
    assert "python" in codeql
    assert "pull_request:" in codeql
    assert "schedule:" in codeql
    assert "github/codeql-action/analyze@" in codeql
