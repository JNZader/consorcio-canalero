"""Static contracts for deterministic build, test, and release workflows."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TRIVY_ACTION = "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25"
NGINX_RUNTIME_IMAGE = (
    "nginx:1.30.4-alpine@sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46"
)
PYTHON_RUNTIME_IMAGE = "python:3.11.15-slim-trixie@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93"
SETUPTOOLS_RUNTIME_PIN = '"setuptools==80.10.2"'
WHEEL_RUNTIME_PIN = '"wheel==0.46.3"'


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _compose_service_block(compose: str, service: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|^networks:\n)",
        compose,
    )
    assert match is not None, f"service {service!r} is missing"
    return match.group("body")


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


def _assert_fail_closed_image_trivy(job: str) -> None:
    assert f"uses: {TRIVY_ACTION}" in job
    assert "scan-type: image" in job
    assert "image-ref: ${{ env.CANDIDATE_IMAGE }}" in job
    assert "severity: CRITICAL,HIGH" in job
    assert "exit-code: '1'" in job
    assert "ignore-unfixed:" not in job
    assert "continue-on-error: true" not in job


def _assert_non_publishing_image_gate(job: str, dockerfile: str, candidate: str) -> None:
    build = "uses: docker/build-push-action@v5"
    scan = f"uses: {TRIVY_ACTION}"

    assert f'CANDIDATE_IMAGE: "{candidate}"' in job
    assert f"file: {dockerfile}" in job
    assert job.count(build) == 1
    assert job.index(build) < job.index(scan)
    assert "load: true" in job
    assert "tags: ${{ env.CANDIDATE_IMAGE }}" in job
    assert "push: true" not in job
    assert "docker push" not in job
    assert "docker/login-action" not in job
    assert "contents: read" in job
    assert "packages: write" not in job
    assert not re.search(r"(?m)^\s+if:", job)
    _assert_fail_closed_image_trivy(job)


def _assert_scanned_artifact_is_published(job: str, candidate: str, latest: str) -> None:
    build = "uses: docker/build-push-action@v5"
    scan = f"uses: {TRIVY_ACTION}"
    login = "uses: docker/login-action@v3"
    push_candidate = 'docker push "$CANDIDATE_IMAGE"'
    tag_latest = 'docker tag "$CANDIDATE_IMAGE" "$LATEST_IMAGE"'
    push_latest = 'docker push "$LATEST_IMAGE"'

    assert f'CANDIDATE_IMAGE: "{candidate}"' in job
    assert f'LATEST_IMAGE: "{latest}"' in job
    assert job.count(build) == 1
    assert "load: true" in job
    assert "tags: ${{ env.CANDIDATE_IMAGE }}" in job
    assert "push: true" not in job
    _assert_fail_closed_image_trivy(job)

    build_index = job.index(build)
    scan_index = job.index(scan)
    login_index = job.index(login)
    push_index = job.index(push_candidate)
    assert build_index < scan_index < login_index < push_index
    assert "docker push" not in job[:scan_index]
    assert "docker login" not in job[:scan_index]
    assert build not in job[scan_index + len(scan) :]
    assert "docker build" not in job[scan_index:]
    assert not re.search(r"(?m)^\s+if:", job)
    assert push_index < job.index(tag_latest) < job.index(push_latest)


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


def test_geo_worker_bootstraps_verified_non_root_user_tools() -> None:
    dockerfile = _read("gee-backend/Dockerfile.geo")
    install = dockerfile.split("apt-get install -y --no-install-recommends", 1)[1].split(
        "&& rm -rf /var/lib/apt/lists/*", 1
    )[0]

    assert "FROM ghcr.io/osgeo/gdal:ubuntu-small-3.10.3" in dockerfile
    assert re.search(r"(?m)^\s+adduser\s+\\$", install)

    check_group = dockerfile.index("command -v addgroup")
    check_user = dockerfile.index("command -v adduser")
    create_group = dockerfile.index("addgroup --system app")
    create_user = dockerfile.index("adduser --system --ingroup app app")
    assert check_group < create_group < create_user
    assert check_user < create_user
    assert dockerfile.rsplit("USER ", 1)[1].startswith("app\n")


def test_frontend_runtime_is_pinned_standalone_and_non_root() -> None:
    dockerfile = _read("consorcio-web/Dockerfile")
    runtime = dockerfile.split("# Stage 4: Runtime", 1)[1]

    assert f"FROM {NGINX_RUNTIME_IMAGE} AS runtime" in runtime
    assert "user nginx;" not in runtime
    assert "pid /tmp/nginx.pid;" in runtime
    for directive in (
        "client_body_temp_path /tmp/nginx/client_temp;",
        "proxy_temp_path /tmp/nginx/proxy_temp;",
        "fastcgi_temp_path /tmp/nginx/fastcgi_temp;",
        "uwsgi_temp_path /tmp/nginx/uwsgi_temp;",
        "scgi_temp_path /tmp/nginx/scgi_temp;",
    ):
        assert directive in runtime

    assert "listen 8080;" in runtime
    assert "listen [::]:8080;" in runtime
    assert "EXPOSE 8080" in runtime
    assert "wget -q -T 5 --spider http://127.0.0.1:8080/health" in runtime
    assert "apk add" not in runtime
    assert "apk --no-network del curl" in runtime
    assert "CMD curl" not in runtime
    assert "location /api/" not in runtime
    assert "proxy_pass" not in runtime
    assert "error_log /dev/stderr warn;" in runtime
    assert "access_log /dev/stdout main;" in runtime
    assert runtime.rsplit("USER ", 1)[1].startswith("nginx\n")


def test_backend_production_runtime_is_pinned_and_dev_free() -> None:
    dockerfile = _read("gee-backend/Dockerfile")
    build = dockerfile.split("# --- Build stage", 1)[1].split("# --- Development stage", 1)[0]
    production = dockerfile.split("# --- Production stage", 1)[1]

    assert f"FROM {PYTHON_RUNTIME_IMAGE} AS build" in build
    assert f"FROM {PYTHON_RUNTIME_IMAGE} AS production" in production
    assert not re.search(r"apt-get install -y(?! --no-install-recommends)", dockerfile)

    runtime_install = production.split("apt-get install -y --no-install-recommends", 1)[1].split(
        "&& rm -rf /var/lib/apt/lists/*", 1
    )[0]
    assert "gcc" in build
    assert "libgdal-dev" in build
    for package in (
        "libgdal-dev",
        "libmariadb-dev",
        "libmariadb-dev-compat",
        "libxml2-dev",
        "linux-libc-dev",
    ):
        assert package not in runtime_install

    assert "libosmesa6" in runtime_install
    assert "ENV VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow" in production

    cleanup = production.index("RUN rm -rf")
    packages_copy = production.index("COPY --from=build /usr/local/lib/python3.11/site-packages")
    for stale_artifact in (
        "setuptools",
        "setuptools-*.dist-info",
        "pkg_resources",
        "wheel",
        "wheel-*.dist-info",
        "_distutils_hack",
        "distutils-precedence.pth",
    ):
        assert (
            f"/usr/local/lib/python3.11/site-packages/{stale_artifact}"
            in production[cleanup:packages_copy]
        )
    assert cleanup < packages_copy
    assert production.rsplit("USER ", 1)[1].startswith("app\n")
    assert 'CMD ["python", "-m", "app.server"]' in production


def test_container_runtimes_pin_safe_pkg_resources_tooling() -> None:
    for path in ("gee-backend/Dockerfile", "gee-backend/Dockerfile.geo"):
        dockerfile = _read(path)

        assert dockerfile.count(SETUPTOOLS_RUNTIME_PIN) == 1
        assert dockerfile.count(WHEEL_RUNTIME_PIN) == 1


def test_geo_worker_keeps_osgeo_numpy_abi_constraints_scoped() -> None:
    backend = _read("gee-backend/Dockerfile")
    geo = _read("gee-backend/Dockerfile.geo")
    geo_dependency_install = geo.split("RUN pip install --no-cache-dir", 1)[1].split(
        "# Pre-download WhiteboxTools", 1
    )[0]

    for constraint in (
        '"numpy<2"',
        '"opencv-python-headless<4.12"',
        '"rasterio<1.5"',
        '"rioxarray<0.22"',
        '"scipy<1.17"',
    ):
        assert geo.count(constraint) == 1
        assert constraint in geo_dependency_install
        assert constraint not in backend
    assert "--ignore-installed numpy" in geo_dependency_install


def test_geo_worker_purges_python_build_headers_after_whitebox_setup() -> None:
    dockerfile = _read("gee-backend/Dockerfile.geo")
    install_marker = "apt-get install -y --no-install-recommends"
    install_start = dockerfile.index(install_marker)
    install_end = dockerfile.index("&& rm -rf /var/lib/apt/lists/*", install_start)
    install = dockerfile[install_start:install_end]

    for package in (
        "gpgv",
        "libssl3t64",
        "openssl",
        "libtiff6",
        "python3-dev",
    ):
        assert re.search(rf"(?m)^\s+{re.escape(package)}\s+\\$", install)

    pip_install = dockerfile.index("pip install --no-cache-dir")
    whitebox_setup = dockerfile.index("import whitebox; wbt = whitebox.WhiteboxTools()")
    purge = dockerfile.index("apt-get purge -y --auto-remove python3-dev")
    final_cleanup = dockerfile.index("rm -rf /var/lib/apt/lists/* /var/cache/apt/*", purge)
    assert install_start < pip_install < whitebox_setup < purge < final_cleanup
    purge_end = purge + len("apt-get purge -y --auto-remove python3-dev")
    assert dockerfile.find("python3-dev", purge_end) == -1
    assert "libc6-dev" not in dockerfile
    assert "linux-libc-dev" not in dockerfile
    assert "apt-get upgrade" not in dockerfile
    assert "apt-get dist-upgrade" not in dockerfile


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


def test_branch_and_pr_workflows_scan_every_final_image_without_publishing() -> None:
    frontend = _read(".github/workflows/frontend.yml")
    backend = _read(".github/workflows/backend.yml")

    assert "push:" in frontend
    assert "pull_request:" in frontend
    assert "      - 'consorcio-web/**'" in frontend
    assert "push:" in backend
    assert "pull_request:" in backend
    assert "      - 'gee-backend/**'" in backend
    assert _needs(frontend, "image") == {"lint", "test", "typecheck", "smoke"}
    assert _needs(backend, "image-backend") == {"lint", "typecheck", "test"}
    assert _needs(backend, "image-geo-worker") == {"lint", "typecheck", "test"}

    _assert_non_publishing_image_gate(
        _job_block(frontend, "image"),
        "consorcio-web/Dockerfile",
        "local/consorcio-frontend:${{ github.sha }}",
    )
    _assert_non_publishing_image_gate(
        _job_block(backend, "image-backend"),
        "gee-backend/Dockerfile",
        "local/consorcio-backend:${{ github.sha }}",
    )
    _assert_non_publishing_image_gate(
        _job_block(backend, "image-geo-worker"),
        "gee-backend/Dockerfile.geo",
        "local/consorcio-geo-worker:${{ github.sha }}",
    )


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
    backend_publish = _job_block(deploy, "build-backend")
    geo_publish = _job_block(deploy, "build-geo-worker")
    assert _needs(deploy, "build-backend") == publish_gates
    assert _needs(deploy, "build-geo-worker") == publish_gates
    _assert_scanned_artifact_is_published(
        backend_publish,
        "ghcr.io/${{ github.repository }}/backend:${{ github.sha }}",
        "ghcr.io/${{ github.repository }}/backend:latest",
    )
    _assert_scanned_artifact_is_published(
        geo_publish,
        "ghcr.io/${{ github.repository }}/geo-worker:${{ github.sha }}",
        "ghcr.io/${{ github.repository }}/geo-worker:latest",
    )

    rollout = _job_block(deploy, "deploy")
    assert _needs(deploy, "deploy") == {"build-backend", "build-geo-worker"}
    assert "vars.ENABLE_PRODUCTION_DEPLOY == 'true'" in rollout
    assert "vars.DEPLOY_WEBHOOK_URL != ''" in rollout
    assert "secrets.DEPLOY_WEBHOOK_SECRET" in rollout
    assert deploy.count("scan-type: image") == 2
    assert deploy.count('docker push "$CANDIDATE_IMAGE"') == 2
    assert "push: true" not in deploy


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


def test_backend_runtime_manifest_owns_geopandas_and_skips_bad_fastapi_patches() -> None:
    requirements = _read("gee-backend/requirements.txt")
    geo_requirements = _read("gee-backend/requirements-geo.txt")
    dev_requirements = _read("gee-backend/requirements-dev.txt")

    assert requirements.count("geopandas>=1.0.0") == 1
    assert "geopandas" not in geo_requirements.lower()
    assert "-r requirements.txt" in dev_requirements
    assert "fastapi>=0.115.0,!=0.137.0,!=0.137.1" in requirements

    for path in ("gee-backend/Dockerfile.geo", "gee-backend/Dockerfile.worker"):
        dockerfile = _read(path)
        assert "COPY requirements.txt requirements-geo.txt ./" in dockerfile
        assert "-r requirements.txt" in dockerfile
        assert "-r requirements-geo.txt" in dockerfile

    trainer_dockerfile = _read("gee-backend/Dockerfile.trainer")
    assert "COPY requirements-geo.txt ./" in trainer_dockerfile
    assert "-r requirements-geo.txt" in trainer_dockerfile
    assert "requirements.txt" not in trainer_dockerfile

    trainer_tree = ast.parse(_read("gee-backend/scripts/train_water_unet.py"))
    trainer_imports = {
        alias.name.partition(".")[0]
        for node in ast.walk(trainer_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    trainer_imports.update(
        node.module.partition(".")[0]
        for node in ast.walk(trainer_tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert "geopandas" not in trainer_imports


def test_route_contract_helper_uses_only_public_fastapi_compatibility_surface() -> None:
    helper = _read("gee-backend/tests/route_contracts.py")

    assert "iter_route_contexts" in helper
    assert "_IncludedRouter" not in helper


def test_backend_images_use_dependency_free_python_healthchecks_without_curl() -> None:
    dockerfile = _read("gee-backend/Dockerfile")
    development = dockerfile.split("# --- Development stage ---", 1)[1].split(
        "# --- Production stage", 1
    )[0]
    production = dockerfile.split("# --- Production stage", 1)[1]

    assert "curl" not in dockerfile.lower()
    assert dockerfile.count('CMD ["python", "-m", "app.healthcheck"]') == 2
    assert 'CMD ["python", "-m", "app.healthcheck"]' in development
    assert 'CMD ["python", "-m", "app.healthcheck"]' in production

    healthcheck_tree = ast.parse(_read("gee-backend/app/healthcheck.py"))
    imported_roots = {
        alias.name.partition(".")[0]
        for node in ast.walk(healthcheck_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.partition(".")[0]
        for node in ast.walk(healthcheck_tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert imported_roots <= {"__future__", "collections", "http", "os", "urllib"}


def test_backend_compose_healthchecks_are_exec_form_and_geo_checks_are_unchanged() -> None:
    compose_paths = (
        "docker-compose.yml",
        "docker-compose.prod.yml",
        "docker-compose.deploy.yml",
    )
    for path in compose_paths:
        compose = _read(path)
        backend = _compose_service_block(compose, "backend")

        assert 'test: ["CMD", "python", "-m", "app.healthcheck"]' in backend
        assert "CMD-SHELL" not in backend
        assert "curl" not in backend.lower()
        assert "wget" not in backend.lower()

    base_geo = _compose_service_block(_read("docker-compose.yml"), "geo-worker")
    prod_geo = _compose_service_block(_read("docker-compose.prod.yml"), "geo-worker")
    deploy_geo = _compose_service_block(_read("docker-compose.deploy.yml"), "geo-worker")
    assert 'test: ["CMD", "curl", "-f", "http://localhost:8001/health"]' in base_geo
    assert "wget --no-verbose --tries=1 --spider http://localhost:8001/health" in prod_geo
    assert "curl -sf http://localhost:8001/health" in deploy_geo


def test_compose_healthcheck_change_preserves_migration_celery_and_upload_invariants() -> None:
    base = _read("docker-compose.yml")
    production = _read("docker-compose.prod.yml")
    deploy = _read("docker-compose.deploy.yml")

    base_migrate = _compose_service_block(base, "migrate")
    assert 'profiles: ["migrate"]' in base_migrate
    assert "command: alembic upgrade head" in base_migrate
    assert "USE_PGBOUNCER=false" in base_migrate

    production_migrate = _compose_service_block(production, "migrate")
    assert "command: alembic upgrade head" in production_migrate
    assert 'USE_PGBOUNCER: "false"' in production_migrate
    assert 'restart: "no"' in production_migrate

    deploy_migrate = _compose_service_block(deploy, "migrate")
    assert "command: alembic upgrade head" in deploy_migrate
    assert 'restart: "no"' in deploy_migrate

    for compose in (production, deploy):
        worker = _compose_service_block(compose, "celery-worker")
        beat = _compose_service_block(compose, "celery-beat")
        assert "celery -A app.core.celery_app worker --pool=prefork" in worker
        assert "celery -A app.core.celery_app beat --loglevel=info" in beat
        assert "condition: service_completed_successfully" in worker
        assert "condition: service_completed_successfully" in beat

    uploads = _compose_service_block(production, "uploads-init")
    assert 'user: "0:0"' in uploads
    assert "- sh" in uploads
    assert "- -ec" in uploads
    assert "chown -R app:app /app/uploads" in uploads
    assert "chmod 0750 /app/uploads" in uploads
    assert "- denuncia-uploads:/app/uploads" in uploads
    assert "network_mode: none" in uploads
    assert "read_only: true" in uploads


def test_celery_beat_schedule_volume_is_owned_by_nonroot_app_in_production_stacks() -> None:
    dockerfile = _read("gee-backend/Dockerfile")
    mkdir_position = dockerfile.index("mkdir -p credentials uploads /var/run/celery")
    user_position = dockerfile.index("USER app")

    assert mkdir_position < user_position
    assert "chown -R app:app /app /var/run/celery" in dockerfile[mkdir_position:user_position]

    for compose_path in ("docker-compose.prod.yml", "docker-compose.deploy.yml"):
        compose = _read(compose_path)
        init = _compose_service_block(compose, "celery-beat-init")
        beat = _compose_service_block(compose, "celery-beat")

        assert 'user: "0:0"' in init
        assert "chown -R app:app /var/run/celery" in init
        assert "chmod 0750 /var/run/celery" in init
        assert "- celery-beat-schedule:/var/run/celery" in init
        assert "network_mode: none" in init
        assert "read_only: true" in init
        assert 'restart: "no"' in init

        assert "celery-beat-init:" in beat
        assert "condition: service_completed_successfully" in beat
        assert "user: " not in beat
        assert "- celery-beat-schedule:/var/run/celery" in beat
