"""Static contracts for the v6 infrastructure and CI findings.

These checks read files and run the small deploy scripts. They do not import
the FastAPI app and they do not need Postgres.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
USE_LINE = re.compile(r"^[^\n#]*\buses:\s+(\S+)", re.M)
PINNED_USE = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
SERVICE_HEAD = re.compile(r"(?m)^  ([a-zA-Z0-9_-]+):\s*$")

READONLY_ANCHOR = {
    "migrate",
    "backend",
    "celery-worker",
    "celery-beat",
    "martin",
}
EXPLICIT_READONLY = {"uploads-init", "celery-beat-init"}
WRITABLE_ROOT = {
    "geo-worker",
    "backup-postgres",
    "backup-volumes",
    "pgbouncer",
    "postgres",
    "redis",
}
PRIV_DROP_CAPS = ("CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID")
CHOWN_CAPS = ("CHOWN", "DAC_OVERRIDE", "FOWNER")


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _service_blocks(path: str) -> dict[str, str]:
    text = _read(path)
    body = text.split("\nservices:\n", 1)[1]
    body = re.split(r"\n(?=[A-Za-z])", body, maxsplit=1)[0]
    parts = SERVICE_HEAD.split(body)
    names = parts[1::2]
    blocks = parts[2::2]
    assert names, path
    assert len(names) == len(blocks)
    return dict(zip(names, blocks, strict=True))


def test_every_action_is_pinned_to_a_sha_with_a_version_comment() -> None:
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        uses = USE_LINE.findall(text)
        assert uses, workflow.name
        for ref in uses:
            assert PINNED_USE.fullmatch(ref), f"{workflow.name}: {ref}"
            line = next(line for line in text.splitlines() if f"uses: {ref}" in line)
            assert re.search(r"#\s+v\d+\.\d+\.\d+\s*$", line), line
        assert re.search(r"(?m)^permissions:\n  contents: read\n", text), workflow.name
        assert not re.search(r"uses:\s+\S+@v\d", text), workflow.name


def test_deploy_job_waits_on_the_production_environment() -> None:
    job = _read(".github/workflows/deploy.yml").split("\n  deploy:\n", 1)[1]
    assert "environment: production" in job
    assert "permissions: {}" in job
    assert "vars.ENABLE_PRODUCTION_DEPLOY == 'true'" in job


@pytest.mark.parametrize("path", ["docker-compose.prod.yml", "docker-compose.deploy.yml"])
def test_production_services_drop_capabilities(path: str) -> None:
    text = _read(path)
    assert "no-new-privileges:true" in text
    assert "cap_drop:\n    - ALL" in text
    assert "driver: json-file" in text or "driver: json-file" in text
    blocks = _service_blocks(path)
    for name, block in blocks.items():
        assert "<<: *hardening" in block or "<<: [*hardening, *readonly]" in block, name
        assert "cap_drop:" not in block, name
        if name in READONLY_ANCHOR:
            assert "<<: [*hardening, *readonly]" in block, name
            assert "HOME: /tmp" in block, name
            assert "TMPDIR: /tmp" in block, name
        if name in EXPLICIT_READONLY:
            assert "read_only: true" in block, name
            assert 'user: "0:0"' in block, name
            for cap in CHOWN_CAPS:
                assert f"- {cap}" in block, (name, cap)
        if name in WRITABLE_ROOT:
            assert "*readonly" not in block, name
            assert "read_only:" not in block, name
    if path.endswith("deploy.yml"):
        for service in ("postgres", "redis"):
            for cap in PRIV_DROP_CAPS:
                assert f"- {cap}" in blocks[service]
        assert "pgrouting/pgrouting:16-3.5-3.8@sha256:" in blocks["postgres"]
        assert "redis:7-alpine@sha256:" in blocks["redis"]
    else:
        for cap in PRIV_DROP_CAPS:
            assert f"- {cap}" in blocks["pgbouncer"]
        assert "edoburu/pgbouncer:v1.26.0-p0@sha256:" in blocks["pgbouncer"]
    assert "ghcr.io/maplibre/martin:1.16.1@sha256:" in blocks["martin"]
    assert ":-" not in blocks["martin"]


def test_known_image_digests_are_the_ones_resolved_for_this_change() -> None:
    prod = _read("docker-compose.prod.yml")
    deploy = _read("docker-compose.deploy.yml")
    web = _read("consorcio-web/Dockerfile")
    backup = _read("scripts/Dockerfile.backup")
    assert (
        "redis:7-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499"
        in deploy
    )
    assert (
        "pgrouting/pgrouting:16-3.5-3.8@sha256:4c480c7f9e25a3490573cd6ef86b286fd21162e288cc355e8da2b52518ef6ab8"
        in deploy
    )
    assert (
        "edoburu/pgbouncer:v1.26.0-p0@sha256:b17551c776ef7e5769ef80b956d20f85e2fd25dd8912d31d58f782aad495b711"
        in prod
    )
    assert (
        "ghcr.io/maplibre/martin:1.16.1@sha256:59902019bf9038926ff0c71174237d6852e64c457830a6349abe7090be8818ca"
        in prod
    )
    assert (
        web.count(
            "node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402"
        )
        == 3
    )
    assert not re.search(r"^FROM node:22-alpine\s", web, re.M)
    assert (
        "alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8"
        in backup
    )
    assert "alpine:3.20" not in backup
    assert "postgresql16-client" in backup


def test_pages_promoter_does_not_force_push_or_check_out_the_trigger_sha() -> None:
    pages = "\n".join(
        line
        for line in _read(".github/workflows/pages.yml").splitlines()
        if not line.lstrip().startswith("#")
    )
    script = _read("deploy/promote-pages-ref.sh")
    assert "git push" not in pages
    assert "--force" not in pages
    assert "force=true" not in pages
    assert "ref: ${{ github.sha }}" in pages
    assert "persist-credentials: false" in pages
    assert pages.count("github.event.workflow_run.head_sha") == 1
    assert "PROMOTE_SHA: ${{ github.event.workflow_run.head_sha }}" in pages
    assert "force=false" in script
    assert "force=true" not in script
    assert "git push" not in script
    assert "identical|behind" in script


def test_legacy_deploy_compose_is_deprecated_and_unused_by_ci() -> None:
    text = _read("docker-compose.deploy.yml")
    assert "DEPRECATED (INF-07)" in text[:800]
    for workflow in WORKFLOWS.glob("*.yml"):
        assert "docker-compose.deploy.yml" not in workflow.read_text(encoding="utf-8"), (
            workflow.name
        )


def _caddy_block(text: str, header: str) -> str:
    marker = header + " {"
    start = text.index(marker)
    depth = 0
    for index in range(start + len(header), len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index]
    raise AssertionError(f"bloque sin cerrar: {header}")


_PUBLIC_CADDY_SITES = (
    "api.consorcio.{$DOMAIN}",
    "tiles.consorcio.{$DOMAIN}",
    "deploy.consorcio.{$DOMAIN}",
)


def test_public_caddy_returns_404_for_metrics() -> None:
    """OBS-02: /metrics is not proxied to the internet.

    The backend still serves it on the Docker network
    (``consorcio-backend:8000``). Every public site answers 404 first,
    in its own ``handle``, before ``reverse_proxy``.
    """
    for path in ("deploy/Caddyfile", "deploy/Caddyfile.with-ratelimit"):
        text = _read(path)
        for site_name in _PUBLIC_CADDY_SITES:
            site = _caddy_block(text, site_name)
            code = "\n".join(
                line for line in site.splitlines() if not line.lstrip().startswith("#")
            )
            matcher_at = code.find("@metrics path /metrics /metrics/*")
            handle_at = code.find("handle @metrics")
            proxy_at = code.find("reverse_proxy ")
            assert matcher_at != -1, (path, site_name)
            assert handle_at != -1, (path, site_name)
            assert proxy_at != -1, (path, site_name)
            assert matcher_at < handle_at < proxy_at, (path, site_name)
            assert "respond 404" in code[handle_at:proxy_at], (path, site_name)


def test_stock_caddyfile_has_no_rate_limit_directive() -> None:
    stock = _read("deploy/Caddyfile")
    limited = _read("deploy/Caddyfile.with-ratelimit")
    for text in (stock, limited):
        assert "encode zstd gzip" in text
        assert "format json" in text
        assert "Strict-Transport-Security" in text
        assert "preload" in text
        assert "-Server" in text
        assert "-Via" in text
        assert "defer" in text
        assert "max_size 20MB" in text
    assert "rate_limit {" not in stock
    assert "rate_limit {" in limited


def test_pages_node_pin_is_at_the_repo_root() -> None:
    """Pages reads .node-version from the repo root, before `cd consorcio-web`."""
    assert _read(".node-version").strip() == "22.23.3"
    assert _read("consorcio-web/.node-version").strip() == "22.23.3"


def test_recharts_react_is_is_a_direct_dependency() -> None:
    """recharts' peer stays direct so `npm ci` resolves without `--legacy-peer-deps`."""
    package = json.loads(_read("consorcio-web/package.json"))
    lock = json.loads(_read("consorcio-web/package-lock.json"))
    assert package["dependencies"]["react-is"] == "^19.3.0"
    assert "react-is" in lock["packages"][""]["dependencies"]
    react = lock["packages"]["node_modules/react"]["version"]
    installed = lock["packages"]["node_modules/react-is"]
    assert installed["version"] == react
    assert installed.get("peer") is not True


def test_pages_npmrc_keeps_dev_dependencies() -> None:
    """Pages can install with NODE_ENV=production, which omits tsc and vite."""
    npmrc = _read("consorcio-web/.npmrc")
    assert "include=dev" in npmrc
    assert "engine-strict=false" in npmrc


def test_mantine_patch_matches_the_installed_version() -> None:
    lock = json.loads(_read("consorcio-web/package-lock.json"))
    version = lock["packages"]["node_modules/@mantine/core"]["version"]
    patches = list((REPO_ROOT / "consorcio-web" / "patches").glob("@mantine+core+*.patch"))
    assert version == "9.7.2"
    assert [path.name for path in patches] == ["@mantine+core+9.7.2.patch"]
    body = patches[0].read_text(encoding="utf-8")
    assert "Transition.mjs" in body
    assert "get-env.mjs" in body


def test_frontend_coverage_thresholds_are_the_v6_floors() -> None:
    config = _read("consorcio-web/vitest.config.ts")
    assert "statements: 78" in config
    assert "branches: 73" in config
    assert "functions: 76" in config
    assert "lines: 79" in config


def test_critical_coverage_gate_rejects_a_regressed_module(tmp_path: Path) -> None:
    gate = _load("gee-backend/scripts/critical_coverage_gate.py", "critical_coverage_gate")
    assert gate.FLOORS == {
        "app/auth/router.py": 27.0,
        "app/core/rate_limit.py": 61.0,
        "app/domains/denuncias/router.py": 80.0,
    }
    report = {
        "files": {
            "app/auth/router.py": {"summary": {"percent_covered": 27.0}},
            "app/core/rate_limit.py": {"summary": {"percent_covered": 61.0}},
            "app/domains/denuncias/router.py": {"summary": {"percent_covered": 80.0}},
        }
    }
    assert gate.evaluate(report) == []
    report["files"]["app/auth/router.py"]["summary"]["percent_covered"] = 10
    failures = gate.evaluate(report)
    assert len(failures) == 1
    assert "auth/router.py" in failures[0]
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert gate.main([str(path)]) == 1


def test_webhook_allowlist_replay_and_constant_time_compare(tmp_path: Path) -> None:
    hook = _load("deploy/deploy_webhook.py", "deploy_webhook")
    assert hook.token_matches("same-token", "same-token")
    assert not hook.token_matches("same-token", "same-tokem")
    assert not hook.token_matches("short", "short-but-longer")

    revision = "a" * 40
    digest = "b" * 64
    body = json.dumps(
        {
            "revision": revision,
            "backend_image": f"ghcr.io/jnzader/consorcio-canalero/backend@sha256:{digest}",
            "geo_worker_image": f"ghcr.io/jnzader/consorcio-canalero/geo-worker@sha256:{digest}",
        }
    ).encode()
    parsed = hook.parse_payload(body)
    assert parsed == (revision, f"sha256:{digest}", f"sha256:{digest}")

    tagged = body.replace(b"@sha256:" + digest.encode(), b":latest")
    with pytest.raises(hook.WebhookError) as tagged_error:
        hook.parse_payload(tagged)
    assert tagged_error.value.code == "image_not_allowlisted"

    other_repo = body.replace(b"jnzader/consorcio-canalero", b"other/consorcio-canalero")
    with pytest.raises(hook.WebhookError) as repo_error:
        hook.parse_payload(other_repo)
    assert repo_error.value.code == "image_not_allowlisted"

    state = tmp_path / "revisions"
    calls: list[tuple[str, str, str]] = []

    def apply(rev: str, backend: str, geo: str) -> None:
        calls.append((rev, backend, geo))

    accepted = hook.handle_deploy(
        authorization="Bearer secret",
        body=body,
        expected_token="secret",
        state_path=state,
        apply=apply,
    )
    assert accepted["revision"] == revision
    assert calls == [(revision, f"sha256:{digest}", f"sha256:{digest}")]

    with pytest.raises(hook.WebhookError) as replay:
        hook.handle_deploy(
            authorization="Bearer secret",
            body=body,
            expected_token="secret",
            state_path=state,
            apply=apply,
        )
    assert replay.value.status == 409
    assert len(calls) == 1

    fresh = tmp_path / "other-revisions"

    def fail(rev: str, backend: str, geo: str) -> None:
        raise hook.WebhookError(500, "compose_failed")

    with pytest.raises(hook.WebhookError):
        hook.handle_deploy(
            authorization="Bearer secret",
            body=body,
            expected_token="secret",
            state_path=fresh,
            apply=fail,
        )
    assert not fresh.exists()
    source = _read("deploy/deploy_webhook.py")
    assert "completed.stderr" not in source


def test_backup_age_and_restore_target_guards(tmp_path: Path) -> None:
    stamp = tmp_path / "backup-last-success"
    env = {
        **os.environ,
        "STACK_DIR": str(tmp_path),
        "BACKUP_STAMP_FILE": str(stamp),
        "BACKUP_MAX_AGE_HOURS": "26",
    }
    missing = subprocess.run(
        ["bash", str(REPO_ROOT / "deploy" / "backup-age-check.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 1

    stamp.write_text("2020-01-01T00:00:00Z\n", encoding="utf-8")
    old = subprocess.run(
        ["bash", str(REPO_ROOT / "deploy" / "backup-age-check.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert old.returncode == 1
    assert "old" in old.stderr

    fresh = subprocess.run(
        ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"],
        capture_output=True,
        text=True,
        check=True,
    )
    stamp.write_text(fresh.stdout, encoding="utf-8")
    current = subprocess.run(
        ["bash", str(REPO_ROOT / "deploy" / "backup-age-check.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert current.returncode == 0, current.stderr

    drill = str(REPO_ROOT / "deploy" / "restore-drill.sh")
    live = subprocess.run(
        ["bash", drill, "--check-target", "consorcio_canalero"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert live.returncode == 2
    ok = subprocess.run(
        ["bash", drill, "--check-target", "consorcio_restore_drill"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0


def test_shell_scripts_and_units_parse() -> None:
    scripts = [
        "deploy/backup.sh",
        "deploy/backup-age-check.sh",
        "deploy/restore-drill.sh",
        "deploy/notify-failure.sh",
        "deploy/promote-pages-ref.sh",
        "deploy/etl-refresh.sh",
    ]
    for script in scripts:
        result = subprocess.run(
            ["bash", "-n", str(REPO_ROOT / script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    etl = _read("deploy/etl-refresh.service")
    unit, service = etl.split("[Service]", 1)
    assert "OnFailure=notify@%n.service" in unit
    assert "OnFailure=" not in service
    assert "OnFailure=notify@%n.service" in _read("deploy/backup.service")
    assert "OnFailure=notify@%n.service" in _read("deploy/backup-age-check.service")
    py = subprocess.run(
        ["python3", "-m", "py_compile", str(REPO_ROOT / "deploy" / "deploy_webhook.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert py.returncode == 0, py.stderr


def test_npm_ci_does_not_pass_legacy_peer_deps() -> None:
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        assert "--legacy-peer-deps" not in workflow.read_text(encoding="utf-8"), workflow.name
    dockerfile = _read("consorcio-web/Dockerfile")
    assert "--legacy-peer-deps" not in dockerfile
    assert "npm ci --prefer-offline --no-audit\n" in dockerfile


def test_sast_workflow_runs_gitleaks_and_semgrep_with_a_baseline() -> None:
    sast = _read(".github/workflows/sast.yml")
    assert "gitleaks detect --source . --config .gitleaks.toml" in sast
    assert "version=8.30.1" in sast
    assert "linux_x64.tar.gz" in sast
    assert "--config p/python" in sast
    assert "--config p/typescript" in sast
    assert "--baseline-commit" in sast
    assert "--error" in sast
    assert "semgrep==1.180.0" in sast
    assert "fetch-depth: 0" in sast


def test_pages_prod_smoke_checks_deep_routes_without_calling_the_api() -> None:
    smoke = _read(".github/workflows/pages-prod-smoke.yml")
    header = smoke.split("\njobs:", 1)[0]
    assert "pull_request:" not in header
    assert "workflows: [Frontend]" in header
    assert "github.event.workflow_run.event == 'push'" in smoke
    assert "github.event.workflow_run.head_branch == 'main'" in smoke
    assert "ref: ${{ github.sha }}" in smoke
    assert "ref: ${{ github.event.workflow_run.head_sha }}" not in smoke
    assert "https://consorcio-canalero.pages.dev" in smoke
    assert 'node consorcio-web/scripts/check-pages-routing.mjs --url "$APP_URL"' in smoke
    for forbidden in ("E2E_API_BASE", "E2E_ADMIN_", "/api/v2", "api.consorcio"):
        assert forbidden not in smoke, forbidden
    routing = _read("consorcio-web/scripts/check-pages-routing.mjs")
    for path in ("'/'", "'/mapa'", "'/login'", "'/participacion'", "'/admin'"):
        assert path in routing
    assert "text/plain" in routing
    assert "soft-404 /esta-ruta-no-existe" in routing


def test_robots_and_not_found_are_not_indexed() -> None:
    robots = _read("consorcio-web/public/robots.txt")
    agents = [
        line.strip() for line in robots.splitlines() if line.lower().startswith("user-agent:")
    ]
    assert agents == ["User-agent: *"]
    assert "crawl-delay" not in robots.lower()
    route_tree = _read("consorcio-web/src/routeTree.gen.tsx")
    block = route_tree.split("const NotFoundComponent", 1)[1].split(
        "const rootRouteWithComponent", 1
    )[0]
    assert "noindex={true}" in block


def test_phase_reports_left_the_frontend_tree() -> None:
    web = REPO_ROOT / "consorcio-web"
    leftover = list(web.glob("PHASE_*.md")) + list(web.glob("MUTATION_*.md"))
    assert leftover == []
    archive = REPO_ROOT / "docs" / "archive"
    assert (archive / "MUTATION_TESTING.md").is_file()
    assert (archive / "PHASE_1_SUMMARY.md").is_file()
