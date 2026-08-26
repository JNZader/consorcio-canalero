"""Static contracts for deterministic build, test, and release workflows."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TRIVY_ACTION = "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25"
TRIVY_VERSION = "v0.70.0"
GITHUB_WORKSPACE = "$" + "{{ github.workspace }}"
GHCR_ROOT = "ghcr.io/jnzader/consorcio-canalero"
# REBALANCED on measured PR #247 evidence (2026-08-26, run 33013524468). The
# first-pass move of ``RainfallMetricList.tsx`` from shard a to b was reverted
# before merge because it only relocated an UNMEASURED guess; this is the
# measured move that comment asked for. Shard a ran 55m25s against shard b's
# 19m01s (671 vs 318 incremental mutants, 25.18 vs 11.16 tests per mutant),
# and 27 of shard a's 28 timeouts sat in ONE file, ``authStore.ts``, whose
# mutants are covered by up to 55 tests each -- the store is in every blast
# radius. Reciprocal: ``src/lib/api/core.ts`` moves b -> a. It is shard b's
# ONLY timeout carrier (4 of 4) and its second-largest mutant block (278), so
# it compensates measured cost instead of just mutant count. ``typeGuards.ts``
# (478 mutants, the largest, 0 timeouts) was rejected as the reciprocal: it
# would overshoot (a -> 1860 mutants) and re-concentrate cost in a. What stays
# pinned here is the PARTITION contract: the two shards are disjoint and their
# union is exactly the canonical ``stryker.config.mjs`` target list.
STRYKER_SHARDS = {
    "a": [
        "src/lib/api/core.ts",
        "src/lib/auth.ts",
        "src/lib/validators.ts",
        "src/components/map2d/bpaPracticas.ts",
        "src/components/admin/pilarVerdeWidget/computeKpis.ts",
        "src/components/map2d/canalesFormat.ts",
        "src/components/map2d/rainfall/rainfallFormat.ts",
        "src/components/map2d/rainfall/RainfallMetricList.tsx",
    ],
    "b": [
        "src/stores/authStore.ts",
        "src/stores/configStore.ts",
        "src/lib/formatters.ts",
        "src/lib/errorHandler.ts",
        "src/lib/typeGuards.ts",
        "src/components/admin/pilarVerdeWidget/fmt.ts",
        "src/lib/api/rainfall.ts",
        "src/hooks/useRainfallAnalysis.ts",
        "src/components/map2d/rainfall/RainfallDetailPanel.tsx",
    ],
}
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


def _without_comments(workflow: str) -> str:
    """Drop full-line ``#`` comments.

    The canary workflow DOCUMENTS what it deliberately does not do ("no
    E2E_API_BASE", "not on pull_request"), so a naive substring assertion over
    the raw file fails on the prose that explains the very contract being
    asserted. Only the executable YAML is checked.
    """
    return "\n".join(line for line in workflow.splitlines() if not line.lstrip().startswith("#"))


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


def _stryker_config_targets() -> list[str]:
    config = _read("consorcio-web/stryker.config.mjs")
    targets = config.split("export const mutationTargets = [", 1)[1].split("\n];", 1)[0]
    return re.findall(r"'([^']+\.(?:ts|tsx))'", targets)


def _mutation_matrix(workflow: dict[str, object], job: str) -> dict[str, list[str]]:
    include = workflow["jobs"][job]["strategy"]["matrix"]["include"]
    return {entry["shard"]: entry["mutate"].split(",") for entry in include}


def _assert_fail_closed_trivy(job: str) -> None:
    upload = "uses: github/codeql-action/upload-sarif@v3"

    assert f"uses: {TRIVY_ACTION}" in job
    assert f"version: {TRIVY_VERSION}" in job
    assert "severity: CRITICAL,HIGH" in job
    assert "exit-code: '1'" in job
    assert "continue-on-error: true" not in job
    assert upload in job
    assert "if: always()" in job[job.index(upload) :]


def _assert_strict_image_trivy(job: str) -> None:
    assert f"uses: {TRIVY_ACTION}" in job
    assert "scan-type: image" in job
    assert "image-ref: ${{ env.CANDIDATE_IMAGE }}" in job
    assert "severity: CRITICAL,HIGH" in job
    assert "exit-code: '1'" in job
    assert "ignore-unfixed:" not in job
    assert "continue-on-error: true" not in job


def _assert_frozen_image_policy(
    job: str,
    role: str,
    *,
    workspace_rooted: bool = False,
) -> None:
    relative_report = f"image-security/{role}-trivy.json"
    relative_sarif = f"image-security/{role}-trivy.sarif"
    if workspace_rooted:
        report = f"{GITHUB_WORKSPACE}/{relative_report}"
        sarif = f"{GITHUB_WORKSPACE}/{relative_sarif}"
        convert = f'trivy convert --format sarif --output "{sarif}" "{report}"'
        validate = (
            f'python3 "{GITHUB_WORKSPACE}/gee-backend/scripts/'
            'validate_image_security_policy.py" validate'
        )
        policy_arg = f'--policy "{GITHUB_WORKSPACE}/gee-backend/security/frozen-image-debt.json"'
        report_arg = f'--report "{report}"'
        repo_root_arg = f'--repo-root "{GITHUB_WORKSPACE}"'
        expected_id_arg = '--expected-image-id "$EXPECTED_DAEMON_IMAGE_ID"'
        assert job.count(f"working-directory: {GITHUB_WORKSPACE}") == 3
        assert f'mkdir -p "{GITHUB_WORKSPACE}/image-security"' in job
    else:
        report = relative_report
        sarif = relative_sarif
        convert = f"trivy convert --format sarif --output {sarif} {report}"
        validate = "python3 gee-backend/scripts/validate_image_security_policy.py validate"
        policy_arg = "--policy gee-backend/security/frozen-image-debt.json"
        report_arg = f"--report {report}"
        repo_root_arg = "--repo-root ."
        expected_id_arg = '--expected-image-id "$EXPECTED_DAEMON_IMAGE_ID"'
    scan = f"uses: {TRIVY_ACTION}"

    assert f"uses: {TRIVY_ACTION}" in job
    assert "scan-type: image" in job
    assert "image-ref: " + "$" + "{{ env.CANDIDATE_IMAGE }}" in job
    assert f"version: {TRIVY_VERSION}" in job
    assert "scanners: vuln" in job
    assert "format: json" in job
    assert f"output: {report}" in job
    assert "severity: CRITICAL,HIGH" in job
    assert "exit-code: '0'" in job
    assert "ignore-unfixed:" not in job
    assert "continue-on-error: true" not in job
    assert ".trivyignore" not in job
    assert "--expected-manifest-digest" not in job
    assert convert in job
    assert validate in job
    assert policy_arg in job
    assert report_arg in job
    assert f"--image-role {role}" in job
    assert '--expected-image-ref "$CANDIDATE_IMAGE"' in job
    assert expected_id_arg in job
    assert "EXPECTED_CONFIG_IMAGE_ID" not in job
    assert "docker image inspect --format '{{.Id}}'" in job
    assert '--expected-source-revision "$GITHUB_SHA"' in job
    assert '--expected-source-repository "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY"' in job
    assert repo_root_arg in job
    assert job.index(scan) < job.index(convert) < job.index(validate)

    artifact = job.index("uses: actions/upload-artifact@v4")
    artifact_tail = job[artifact:]
    assert "if: always()" in artifact_tail
    assert "if-no-files-found: error" in artifact_tail
    assert report in artifact_tail
    assert sarif in artifact_tail

    upload_sarif = job.index("uses: github/codeql-action/upload-sarif@v3")
    upload_tail = job[upload_sarif:]
    assert "if: always()" in upload_tail
    assert f"sarif_file: {sarif}" in upload_tail


def _assert_image_policy_aggregate(
    workflow: str,
    producers: set[str],
    *,
    workspace_rooted: bool = False,
    guard_needs: frozenset[str] = frozenset(),
) -> None:
    """`producers` son los jobs cuyo resultado el agregador VALIDA.

    `guard_needs` son dependencias que estan en `needs` solo para poder leer
    sus outputs en el `if:` (hoy: `changes`). Van separadas a proposito: si se
    mezclaran con `producers`, el test exigiria un `<JOB>_RESULT` para ellas y
    la asercion de que cada productor se valida contra `success` se aflojaria.
    """
    aggregate = _job_block(workflow, "image-security-policy")

    assert "name: Image Security Policy" in aggregate
    assert _needs(workflow, "image-security-policy") == producers | guard_needs
    # Tiene que arrancar con always(): si no, un producer fallido saltea el job
    # agregador y la corrida queda verde sin haber exigido la evidencia. El
    # unico conjunto admitido es el guard de workflow_dispatch de deploy.yml,
    # donde la publicacion entera es a demanda.
    guards = re.findall(r"(?m)^    if: (.+)$", aggregate)
    assert guards == [
        g
        for g in guards
        if g
        in (
            "$" + "{{ always() }}",
            "$" + "{{ always() && github.event_name == 'workflow_dispatch' "
            "&& github.ref == 'refs/heads/main' }}",
            # backend.yml: `always()` para que un image gate FALLIDO no saltee
            # la politica y de verde falso, y el guard de area porque el paso
            # exige `success` y un job SALTEADO no lo es.
            "$"
            + "{{ always() && (github.base_ref == 'main' || github.event_name == 'workflow_dispatch') "
            "&& needs.changes.outputs.backend == 'true' }}",
        )
    ], guards
    assert len(guards) == 1, guards
    for producer in producers:
        env_name = producer.upper().replace("-", "_")
        needs_expression = "$" + "{{ needs." + producer + ".result }}"
        assert f"{env_name}_RESULT: {needs_expression}" in aggregate
        result_check = 'test "$' + f'{env_name}_RESULT" = "success"'
        assert result_check in aggregate
    assert "uses: actions/download-artifact@v4" in aggregate
    assert "pattern: image-security-*" in aggregate
    assert "merge-multiple: true" in aggregate
    if workspace_rooted:
        evidence = f"{GITHUB_WORKSPACE}/evidence"
        assert f"path: {evidence}" in aggregate
        assert aggregate.count(f"working-directory: {GITHUB_WORKSPACE}") == 2
        for role in ("backend", "geo-worker"):
            assert f'test -s "{evidence}/{role}-trivy.json"' in aggregate
            assert f'test -s "{evidence}/{role}-trivy.sarif"' in aggregate
    else:
        assert "path: evidence" in aggregate
        for role in ("backend", "geo-worker"):
            assert f"test -s evidence/{role}-trivy.json" in aggregate
            assert f"test -s evidence/{role}-trivy.sarif" in aggregate


def _assert_non_publishing_image_gate(
    job: str,
    dockerfile: str,
    candidate: str,
    policy_role: str | None = None,
    *,
    workspace_rooted: bool = False,
) -> None:
    build = "uses: docker/build-push-action@v5"
    scan = f"uses: {TRIVY_ACTION}"

    assert f'CANDIDATE_IMAGE: "{candidate}"' in job
    expected_dockerfile = f"{GITHUB_WORKSPACE}/{dockerfile}" if workspace_rooted else dockerfile
    assert f"file: {expected_dockerfile}" in job
    if workspace_rooted:
        assert f"context: {GITHUB_WORKSPACE}/gee-backend" in job
    assert job.count(build) == 1
    assert job.index(build) < job.index(scan)
    assert "load: true" in job
    assert "tags: " + "$" + "{{ env.CANDIDATE_IMAGE }}" in job
    assert "push: true" not in job
    assert "docker push" not in job
    assert "docker/login-action" not in job
    assert "contents: read" in job
    assert "packages: write" not in job
    # El gate no puede saltearse en los eventos que lo justifican. La UNICA
    # condicion admitida es excluir el cron semanal (que solo existe para
    # refrescar la baseline de mutacion y no construye imagenes): cualquier
    # otro `if:` haria que un push o un PR pudieran pasar sin escanear.
    for guard in re.findall(r"(?m)^    if: (.+)$", job):
        assert guard in (
            # frontend: excluye el cron semanal Y se saltea si el PR no toca
            # el frontend. Nada mas puede saltear un gate de escaneo.
            "$" + "{{ github.event_name != 'schedule' "
            "&& needs.changes.outputs.frontend == 'true' }}",
            # backend: solo el guard de area.
            # backend: los image gates son ~17 min (GDAL), solo en el release.
            "$" + "{{ (github.base_ref == 'main' || github.event_name == 'workflow_dispatch') "
            "&& needs.changes.outputs.backend == 'true' }}",
        ), guard
    if policy_role is None:
        _assert_strict_image_trivy(job)
    else:
        _assert_frozen_image_policy(
            job,
            policy_role,
            workspace_rooted=workspace_rooted,
        )


def _assert_scanned_manifest_is_published(
    job: str, candidate: str, repository: str, role: str
) -> None:
    build = "uses: docker/build-push-action@v5"
    scan = f"uses: {TRIVY_ACTION}"
    login = "uses: docker/login-action@v3"
    push_candidate = 'docker push "$CANDIDATE_IMAGE"'
    inspect_remote = (
        "docker buildx imagetools inspect \"$CANDIDATE_IMAGE\" --format '{{json .Manifest}}'"
    )

    assert f'CANDIDATE_IMAGE: "{candidate}"' in job
    assert f'IMAGE_REPOSITORY: "{repository}"' in job
    assert ":latest" not in job
    assert "LATEST_IMAGE" not in job
    assert "outputs:" in job
    assert "verified_digest: ${{ steps.publish.outputs.verified_digest }}" in job
    assert "immutable_ref: ${{ steps.publish.outputs.immutable_ref }}" in job
    assert job.count(build) == 1
    assert "id: build-image" in job
    assert "load: true" in job
    assert "tags: " + "$" + "{{ env.CANDIDATE_IMAGE }}" in job
    assert "push: true" not in job
    assert "BUILDX_METADATA: ${{ steps.build-image.outputs.metadata }}" in job
    assert '.["containerimage.digest"]' in job
    assert "containerimage.config.digest" not in job
    assert 'echo "digest=$BUILD_DIGEST" >> "$GITHUB_OUTPUT"' in job

    build_index = job.index(build)
    capture_index = job.index("id: capture-manifest")
    scan_index = job.index(scan)
    login_index = job.index(login)
    push_index = job.index(push_candidate)
    inspect_index = job.index(inspect_remote)
    compare_index = job.index('test "$REMOTE_DIGEST" = "$BUILD_DIGEST"')
    assert build_index < capture_index < scan_index < login_index < push_index
    assert push_index < inspect_index < compare_index
    assert "docker push" not in job[:scan_index]
    assert "docker login" not in job[:scan_index]
    assert build not in job[scan_index + len(scan) :]
    assert not re.search(
        r"(?m)^\s*docker(?:\s+build|\s+buildx\s+build)\b",
        job[scan_index:],
    )
    # La publicacion es a demanda (workflow_dispatch): esa es la UNICA
    # condicion admitida. Con cualquier otro `if:` el job podria saltearse en
    # una corrida que igual promueve manifests, y se publicaria sin escanear.
    for guard in re.findall(r"(?m)^    if: (.+)$", job):
        assert guard == (
            "$" + "{{ github.event_name == 'workflow_dispatch' "
            "&& github.ref == 'refs/heads/main' }}"
        ), guard
    assert 'echo "verified_digest=$REMOTE_DIGEST" >> "$GITHUB_OUTPUT"' in job
    assert 'echo "immutable_ref=$IMAGE_REPOSITORY@$REMOTE_DIGEST" >> "$GITHUB_OUTPUT"' in job
    _assert_frozen_image_policy(job, role)


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

    assert (
        "FROM ghcr.io/osgeo/gdal:ubuntu-small-3.13.1@sha256:66e200e63c7c2fd2534830caaf5a2dcbd0511680ab12a70f85886cc8330fa469"
        in dockerfile
    )
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


def test_geo_worker_uses_gdal_313_numpy_2_abi_without_legacy_pins() -> None:
    geo = _read("gee-backend/Dockerfile.geo")

    assert "--ignore-installed numpy" not in geo
    for obsolete_constraint in (
        '"numpy<2"',
        '"opencv-python-headless<4.12"',
        '"rasterio<1.5"',
        '"rioxarray<0.22"',
        '"scipy<1.17"',
    ):
        assert obsolete_constraint not in geo


def test_geo_worker_purges_python_build_headers_after_whitebox_setup() -> None:
    dockerfile = _read("gee-backend/Dockerfile.geo")
    install_marker = "apt-get install -y --no-install-recommends"
    install_start = dockerfile.index(install_marker)
    install_end = dockerfile.index("&& rm -rf /var/lib/apt/lists/*", install_start)
    install = dockerfile[install_start:install_end]

    for package in (
        "gcc",
        "gpgv",
        "libssl3t64",
        "openssl",
        "libtiff6",
        "python3-dev",
    ):
        assert re.search(rf"(?m)^\s+{re.escape(package)}\s+\\$", install)

    pip_install = dockerfile.index("pip install --no-cache-dir")
    whitebox_setup = dockerfile.index("import whitebox; wbt = whitebox.WhiteboxTools()")
    purge = dockerfile.index("apt-get purge -y --auto-remove gcc python3-dev")
    final_cleanup = dockerfile.index("rm -rf /var/lib/apt/lists/* /var/cache/apt/*", purge)
    assert install_start < pip_install < whitebox_setup < purge < final_cleanup
    purge_end = purge + len("apt-get purge -y --auto-remove gcc python3-dev")
    assert dockerfile.find("python3-dev", purge_end) == -1
    assert "libc6-dev" not in dockerfile
    assert "linux-libc-dev" not in dockerfile
    assert "rm -f /usr/bin/pebble" in dockerfile
    assert "apt-get upgrade" not in dockerfile
    assert "apt-get dist-upgrade" not in dockerfile


def test_frontend_pr_and_manual_runs_reach_applicable_quality_gates() -> None:
    frontend = _read(".github/workflows/frontend.yml")
    event_gate = "github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch'"
    release_gate = "(github.base_ref == 'main' || github.event_name == 'workflow_dispatch')"

    assert "pull_request:" in frontend
    assert "workflow_dispatch:" in frontend
    # `build` corre en TODO PR: es barato y su señal es inmediata.
    assert event_gate in _job_block(frontend, "build")
    # La matriz de accesibilidad corre solo en el PR de release (develop ->
    # main) o a demanda. Pagarla en cada PR a develop fue parte de lo que hizo
    # que bloquearan la cuenta.
    assert release_gate in _job_block(frontend, "accessibility")
    # La mutacion ordinaria corre solo en el PR de release. Un dispatch queda
    # reservado al productor full para no lanzar dos Stryker a la vez.
    mutation_guards = re.findall(r"(?m)^    if: (.+)$", _job_block(frontend, "mutation"))
    assert mutation_guards == [
        "$" + "{{ github.base_ref == 'main' && needs.changes.outputs.frontend == 'true' }}"
    ]

    build = _job_block(frontend, "build")
    # Sin `mutation` ni `accessibility`: se saltean en los PRs a develop y
    # arrastrarian al build al salteo.
    assert _needs(frontend, "build") == {"changes", "lint", "test", "typecheck", "smoke"}

    for script in (
        "npm run lint",
        "npm run test:coverage",
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
    assert "pull_request:" in backend
    # NINGUN filtro `paths:` en los triggers. Un workflow filtrado por paths no
    # corre cuando el PR no lo toca, y un check requerido que nunca corre deja
    # el PR colgado en "Expected — waiting for status". El filtrado vive dentro,
    # en el job `changes`; esta asercion existe para que no vuelva al trigger.
    for workflow in (frontend, backend):
        header = workflow.split("\njobs:", 1)[0]
        assert not re.search(r"(?m)^    paths:$", header), header
    assert _needs(frontend, "image") == {"changes", "lint", "test", "typecheck", "smoke"}
    assert _needs(backend, "image-backend") == {"changes", "lint", "typecheck", "test"}
    assert _needs(backend, "image-geo-worker") == {"changes", "lint", "typecheck", "test"}

    _assert_non_publishing_image_gate(
        _job_block(frontend, "image"),
        "consorcio-web/Dockerfile",
        "local/consorcio-frontend:${{ github.sha }}",
    )
    _assert_non_publishing_image_gate(
        _job_block(backend, "image-backend"),
        "gee-backend/Dockerfile",
        "local/consorcio-backend:${{ github.sha }}",
        "backend",
        workspace_rooted=True,
    )
    _assert_non_publishing_image_gate(
        _job_block(backend, "image-geo-worker"),
        "gee-backend/Dockerfile.geo",
        "local/consorcio-geo-worker:${{ github.sha }}",
        "geo-worker",
        workspace_rooted=True,
    )
    _assert_image_policy_aggregate(
        backend,
        {"image-backend", "image-geo-worker"},
        workspace_rooted=True,
        guard_needs=frozenset({"changes"}),
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
    release_gate = "(github.base_ref == 'main' || github.event_name == 'workflow_dispatch' || github.event_name == 'schedule')"

    assert release_gate in _job_block(backend, "mutation")
    # VTK offscreen corre en proceso pytest SEPARADO (segfaults compartiendo
    # proceso con la suite, 2026-07-30); el umbral de coverage vive en la
    # corrida final, que combina con --cov-append.
    assert "pytest tests/new/test_geo_visualization_renderer.py -v --cov=app" in backend
    assert "--ignore=tests/new/test_geo_visualization_renderer.py" in backend
    assert "--cov-append --cov-fail-under=60" in backend
    assert "python3 scripts/cosmic_gate.py --config .cosmic-ray.selected.toml" in backend
    assert "mutation_matrix: ${{ steps.detect.outputs.mutation_matrix }}" in backend
    assert "matrix: ${{ fromJSON(needs.changes.outputs.mutation_matrix) }}" in _job_block(
        backend, "mutation"
    )
    assert "scripts/cosmic_mutation_plan.py --target" in backend

    security = _job_block(backend, "security")
    # Trivy NO puede depender de `mutation`: un job salteado arrastra al salteo
    # a todo el que lo tenga en `needs`, y la mutacion ahora se saltea en los
    # PRs a develop. Con la dependencia puesta, el escaneo se apagaria ahi.
    assert _needs(backend, "security") == {"changes", "lint", "typecheck", "test"}
    assert "mutation" not in _needs(backend, "security")
    assert "contents: read" in security
    _assert_fail_closed_trivy(security)


def test_deploy_runs_gates_on_main_and_publishes_only_on_demand() -> None:
    """deploy.yml tiene DOS responsabilidades separadas por evento.

    En push a main corren solo los gates de calidad del backend (baratos). La
    construccion y publicacion de imagenes -la parte cara: el geo-worker trae
    GDAL- queda detras de workflow_dispatch, porque hacerla en cada push a main
    agoto la cuota de Actions y dejo el workflow deshabilitado a mano desde
    2026-03. Un `pull_request` NUNCA debe poder disparar publicacion: el
    trigger no existe, asi que codigo no revisado no llega a GHCR.
    """
    deploy = _read(".github/workflows/deploy.yml")
    trigger = deploy.split("\njobs:", 1)[0]

    assert re.search(r"(?m)^  push:\n    branches: \[main\]$", trigger)
    assert "pull_request:" not in trigger
    assert re.search(r"(?m)^  workflow_dispatch:$", trigger)

    # El guard exige el EVENTO y el REF. Sin `github.ref`, cualquiera con
    # permiso de escritura podia despachar desde una rama arbitraria y esa
    # build se publicaba a :latest y le pegaba al webhook de produccion.
    dispatch_only = (
        "$" + "{{ github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' }}"
    )
    # En push a main corren pytest (con la cadena alembic real) y Trivy: la
    # señal barata que main necesita para no quedarse a ciegas.
    for gate in ("quality-backend", "security-backend"):
        assert not re.search(r"(?m)^    if:", _job_block(deploy, gate)), gate
    # La mutacion NO: son ~14 min repitiendo lo que el PR de release acaba de
    # correr sobre el mismo contenido, ahora que main esta protegida con
    # `strict` y nada entra sin pasar por ahi. Queda para el despliegue a mano.
    assert re.findall(r"(?m)^    if: (.+)$", _job_block(deploy, "mutation-backend")) == [
        "$" + "{{ github.event_name == 'workflow_dispatch' }}"
    ]
    for publisher in ("build-backend", "build-geo-worker", "promote-images"):
        assert f"if: {dispatch_only}" in _job_block(deploy, publisher), publisher
    # El grupo de concurrencia se separa por evento: los gates en push no
    # pueden retener el grupo de despliegue (ver comentario en deploy.yml).
    assert "group: " + "$" + "{{ github.event_name == 'workflow_dispatch'" in deploy
    assert "'deploy-production'" in deploy
    assert "cancel-in-progress: false" in deploy

    policy = _job_block(deploy, "image-security-policy")
    assert (
        "if: "
        + "$"
        + "{{ always() && github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' }}"
        in policy
    )

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
    _assert_scanned_manifest_is_published(
        backend_publish,
        f"{GHCR_ROOT}/backend:${{{{ github.sha }}}}",
        f"{GHCR_ROOT}/backend",
        "backend",
    )
    _assert_scanned_manifest_is_published(
        geo_publish,
        f"{GHCR_ROOT}/geo-worker:${{{{ github.sha }}}}",
        f"{GHCR_ROOT}/geo-worker",
        "geo-worker",
    )
    _assert_image_policy_aggregate(deploy, {"build-backend", "build-geo-worker"})

    promotion = _job_block(deploy, "promote-images")
    assert _needs(deploy, "promote-images") == {
        "build-backend",
        "build-geo-worker",
        "image-security-policy",
    }
    assert "packages: write" in promotion
    assert promotion.count("docker buildx imagetools create --prefer-index=false") == 2
    assert promotion.count("--format '{{json .Manifest}}'") == 2
    assert "needs.build-backend.outputs.immutable_ref" in promotion
    assert "needs.build-geo-worker.outputs.immutable_ref" in promotion
    assert "needs.build-backend.outputs.verified_digest" in promotion
    assert "needs.build-geo-worker.outputs.verified_digest" in promotion
    assert 'test "$PROMOTED_BACKEND_DIGEST" = "$BACKEND_DIGEST"' in promotion
    assert 'test "$PROMOTED_GEO_WORKER_DIGEST" = "$GEO_WORKER_DIGEST"' in promotion
    assert f'BACKEND_LATEST: "{GHCR_ROOT}/backend:latest"' in promotion
    assert f'GEO_WORKER_LATEST: "{GHCR_ROOT}/geo-worker:latest"' in promotion

    rollout = _job_block(deploy, "deploy")
    # Match EXACTO, igual que los otros cuatro jobs: con un `in` suelto se
    # podia colar un `always()` delante y, ahora que promote-images se saltea
    # en push, eso disparaba el webhook de produccion en cada push a main con
    # las imagenes vacias.
    assert re.findall(r"(?m)^    if: (.+)$", rollout) == [
        "$" + "{{ vars.ENABLE_PRODUCTION_DEPLOY == 'true' && vars.DEPLOY_WEBHOOK_URL != '' }}"
    ], rollout
    assert _needs(deploy, "deploy") == {"promote-images"}
    assert "vars.ENABLE_PRODUCTION_DEPLOY == 'true'" in rollout
    assert "vars.DEPLOY_WEBHOOK_URL != ''" in rollout
    assert "secrets.DEPLOY_WEBHOOK_SECRET" in rollout
    assert "needs.promote-images.outputs.backend_image" in rollout
    assert "needs.promote-images.outputs.geo_worker_image" in rollout
    assert '--arg revision "$GITHUB_SHA"' in rollout
    assert '--arg backend_image "$BACKEND_IMAGE"' in rollout
    assert '--arg geo_worker_image "$GEO_WORKER_IMAGE"' in rollout
    assert (
        "'{revision: $revision, backend_image: $backend_image, geo_worker_image: $geo_worker_image}'"
        in rollout
    )
    assert '-H "Content-Type: application/json"' in rollout
    assert '--data "$PAYLOAD"' in rollout
    assert deploy.count("scan-type: image") == 2
    assert deploy.count('docker push "$CANDIDATE_IMAGE"') == 2
    assert "push: true" not in deploy


def test_deploy_image_paths_use_canonical_lowercase_ghcr_root() -> None:
    deploy = _read(".github/workflows/deploy.yml")

    assert "ghcr.io/${{ github.repository }}" not in deploy
    assert f"{GHCR_ROOT}/backend:${{{{ github.sha }}}}" in deploy
    assert f"{GHCR_ROOT}/geo-worker:${{{{ github.sha }}}}" in deploy
    assert f"{GHCR_ROOT}/backend:latest" in _job_block(deploy, "promote-images")
    assert f"{GHCR_ROOT}/geo-worker:latest" in _job_block(deploy, "promote-images")
    image_paths = re.findall(r"ghcr\.io/[A-Za-z0-9_./-]+", deploy)
    assert image_paths
    assert all(path == path.lower() for path in image_paths)


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
    assert "tests/test_image_security_policy.py" in quality
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


# The three read-only /mapa specs the canary is allowed to run. Any OTHER spec
# in `tests/e2e/` either creates records against the live site
# (production/denuncias/auth flows) or needs admin credentials, so adding one to
# the canary script must break this list on purpose.
CANARY_READ_ONLY_SPECS = (
    "tests/e2e/mapa-maplibre.spec.ts",
    "tests/e2e/mapa-viewport-movil.spec.ts",
    "tests/e2e/ficha-territorial.spec.ts",
)


def test_e2e_canary_stays_read_only_against_production() -> None:
    """The canary is the ONE workflow allowed to touch the deployed site.

    `test_ci_workflows_never_run_production_writing_e2e` cannot cover it — that
    guard forbids the very string the canary legitimately runs — so the
    equivalent protection lives here, asserted positively:

    (a) it runs ONLY `npm run test:e2e:canary`, never `test:e2e:prod` or a bare
        `test:e2e`;
    (b) it passes NO backend base URL and NO admin credentials, so nothing can
        authenticate and write;
    (c) the `test:e2e:canary` script lists EXACTLY the read-only specs, so
        widening it (e.g. adding `production.spec.ts`, which issues 24 writes)
        fails this test instead of silently seeding junk into production.
    """
    canary = _without_comments(_read(".github/workflows/e2e-canary.yml"))
    package = json.loads(_read("consorcio-web/package.json"))

    # (a) exactly one e2e invocation, and it is the canary script.
    run_lines = [line.strip() for line in canary.splitlines() if "npm run test:e2e" in line]
    assert run_lines == ["run: npm run test:e2e:canary"], run_lines
    assert "test:e2e:prod" not in canary
    assert "playwright test" not in canary

    # (b) no backend and no credentials reach the run.
    for forbidden in (
        "E2E_API_BASE",
        "E2E_ADMIN_EMAIL",
        "E2E_ADMIN_PASSWORD",
        "PLAYWRIGHT_BASE_URL",
    ):
        assert forbidden not in canary, forbidden

    # (c) the script itself is the allowlist.
    script = package["scripts"]["test:e2e:canary"]
    assert script.startswith("playwright test -c tests/e2e/playwright.config.ts ")
    listed = tuple(script.split()[4:])
    assert listed == CANARY_READ_ONLY_SPECS, listed

    # The deploy gate must reject a missing/short sha instead of matching `*`.
    assert '[ -n "$deployed" ]' in canary
    assert '[ "${#deployed}" -ge "$sha_len" ]' in canary


def test_e2e_canary_only_runs_after_a_main_push() -> None:
    """A canary is a POST-deploy probe: on `pull_request` it would burn minutes
    testing a URL that does not contain the PR's code yet."""
    canary = _without_comments(_read(".github/workflows/e2e-canary.yml"))
    assert "pull_request" not in canary
    assert "branches: [main]" in canary
    assert "cancel-in-progress: true" in canary


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


def test_backend_and_geo_compose_healthchecks_are_dependency_free_exec_form() -> None:
    compose_paths = (
        "docker-compose.yml",
        "docker-compose.prod.yml",
        "docker-compose.deploy.yml",
    )
    geo_probe = """test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8001/health', timeout=5).close()"]"""
    for path in compose_paths:
        compose = _read(path)
        backend = _compose_service_block(compose, "backend")
        geo = _compose_service_block(compose, "geo-worker")

        assert 'test: ["CMD", "python", "-m", "app.healthcheck"]' in backend
        assert "CMD-SHELL" not in backend
        assert "curl" not in backend.lower()
        assert "wget" not in backend.lower()
        assert geo_probe in geo
        assert "CMD-SHELL" not in geo
        assert "curl" not in geo.lower()
        assert "wget" not in geo.lower()


def test_production_compose_requires_verified_manifest_digests() -> None:
    production = _read("docker-compose.prod.yml")
    backend_image = (
        "image: ghcr.io/jnzader/consorcio-canalero/backend@"
        "${BACKEND_DIGEST:?BACKEND_DIGEST is required from the deploy webhook payload}"
    )
    geo_image = (
        "image: ghcr.io/jnzader/consorcio-canalero/geo-worker@"
        "${GEO_WORKER_DIGEST:?GEO_WORKER_DIGEST is required from the deploy webhook payload}"
    )

    for service in (
        "migrate",
        "uploads-init",
        "backend",
        "celery-worker",
        "celery-beat-init",
        "celery-beat",
    ):
        block = _compose_service_block(production, service)
        assert backend_image in block
        assert "BACKEND_IMAGE" not in block
        assert ":latest" not in block

    geo = _compose_service_block(production, "geo-worker")
    assert geo_image in geo
    assert "GEO_WORKER_IMAGE" not in geo
    assert ":latest" not in geo
    assert "revision, backend_image, and geo_worker_image" in production
    assert "BACKEND_DIGEST and GEO_WORKER_DIGEST" in production


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


def test_image_policy_uses_no_trivy_ignore_file() -> None:
    for directory in (REPO_ROOT, REPO_ROOT / "gee-backend"):
        for filename in (".trivyignore", ".trivyignore.yaml", ".trivyignore.yml"):
            assert not (directory / filename).exists()

    backend_ignore = _read("gee-backend/.gitignore")
    assert "!security/frozen-image-debt.json" in backend_ignore
    assert "!tests/fixtures/image_security/*.json" in backend_ignore


def _assert_ci_gate(workflow: str, display_name: str, expected_needs: set[str]) -> None:
    gate = _job_block(workflow, "ci-gate")

    assert f"name: {display_name}" in gate
    # Corre SIEMPRE. Sin esto, una dependencia fallida saltea el gate y el
    # check requerido nunca reporta rojo: el PR quedaria mergeable.
    assert re.search(r"(?m)^    if: " + re.escape("$" + "{{ always() }}") + r"$", gate)
    assert "contents: read" in gate
    assert _needs(workflow, "ci-gate") == expected_needs

    # `changes` se exige en success, no en success|skipped: es la fuente de
    # verdad del resto, y si se cae los demas se saltean y el gate no puede
    # darse por satisfecho.
    assert 'test "$CHANGES_RESULT" = "success"' in gate
    # Cada dependencia validada pasa por env en MAYUSCULAS y se acepta
    # unicamente success o skipped: cualquier otro resultado (failure,
    # cancelled) tiene que hundir el gate.
    assert "success|skipped" in gate
    for job in expected_needs - {"changes"}:
        env_name = job.upper().replace("-", "_")
        assert f"{env_name}_RESULT: " + "$" + "{{ needs." + job + ".result }}" in gate
        assert f'require {job} "${env_name}_RESULT"' in gate


def test_ci_gate_is_the_single_required_check_of_each_branch_workflow() -> None:
    """El check requerido de branch protection es UN job agregador por workflow.

    Los checks individuales no sirven como requeridos: se saltean cuando el PR
    no toca esa area, y apoyarse en como GitHub interpreta un job salteado es
    fragil. El agregador corre siempre y reporta conclusion propia. Registrar
    en la proteccion de rama el `name` ("Backend CI" / "Frontend CI"), no el id
    del job.
    """
    _assert_ci_gate(
        _read(".github/workflows/backend.yml"),
        "Backend CI",
        {
            "changes",
            "lint",
            "typecheck",
            "test",
            "mutation",
            "security",
            "image-backend",
            "image-geo-worker",
            "image-security-policy",
        },
    )
    # Los productores full quedan afuera a proposito: son del cron semanal, no
    # del PR. El gate de mutacion agregado SI es parte del PR de release.
    _assert_ci_gate(
        _read(".github/workflows/frontend.yml"),
        "Frontend CI",
        {
            "changes",
            "lint",
            "test",
            "typecheck",
            "smoke",
            "mutation",
            "mutation-gate",
            "accessibility",
            "build",
            "image",
        },
    )


def test_changes_job_detects_areas_without_third_party_actions() -> None:
    """El filtrado por area se hace con git pelado, no con acciones de terceros.

    Este repo pinnea acciones por SHA y endurecio su cadena de suministro;
    `tj-actions/changed-files` fue justamente el epicentro de un compromiso de
    supply-chain. Calcular un diff no justifica una dependencia de terceros en
    el camino critico del CI.
    """
    for path, area in (
        (".github/workflows/backend.yml", "backend"),
        (".github/workflows/frontend.yml", "frontend"),
    ):
        workflow = _read(path)
        changes = _job_block(workflow, "changes")

        assert f"{area}: " + "$" + "{{ steps.detect.outputs." + area + " }}" in changes
        for forbidden in ("dorny/paths-filter", "tj-actions/changed-files"):
            assert forbidden not in workflow, path
        # Historia completa: sin esto el merge-base no existe en el clon y el
        # diff contra la rama base miente o falla.
        assert "fetch-depth: 0" in changes
        # Tres puntos = merge-base. Con dos, un avance de la rama base
        # posterior a la apertura del PR contaria como cambio del PR.
        assert (
            f'git diff --name-{("status" if area == "backend" else "only")} "$BASE_SHA...HEAD"'
            in changes
        )
        # Fuera de un pull_request se declara todo cambiado: correr de mas es
        # preferible a saltear en silencio.
        assert '[ "$GITHUB_EVENT_NAME" != "pull_request" ]' in changes
        assert f"{area}=true" in changes
        assert f"{area}=false" in changes


def test_backend_changes_prefilter_checks_both_sides_of_rename_records(tmp_path: Path) -> None:
    """R3-001 regression: rename/copy name-status records carry TWO paths.

    A ``R100``/``C`` record is ``status<TAB>old<TAB>new``. A bare ``cut -f2-``
    keeps both paths in ONE line, so the anchored backend regex only inspected
    the OLD path: a rename from ``docs/`` into ``gee-backend/`` matched
    nothing, set ``backend=false``, and skipped backend tests, mutation, and
    security. The extractor must split fields 2 and 3 into separate lines so
    the anchored regex sees each path on its own.
    """
    changes = _job_block(_read(".github/workflows/backend.yml"), "changes")

    match = re.search(r'CHANGED="\$\((?P<extract>cut [^()]+)\)"\n', changes)
    assert match is not None, "the changes job must extract changed paths into CHANGED"
    extract = match.group("extract").replace("$RUNNER_TEMP", str(tmp_path))
    assert "tr" in extract and "\\t" in extract and "\\n" in extract, (
        "the extractor must split rename old/new paths into separate lines; "
        "a single-line cut leaves the new path invisible to the anchored regex"
    )
    # The planner still receives the FULL name-status file: rename/copy records
    # reach it and keep the fail-closed full-suite behavior for non-A/M statuses.
    assert (
        "python3 gee-backend/scripts/cosmic_mutation_plan.py "
        '--status-file "$RUNNER_TEMP/backend-changes.txt"'
    ) in changes

    backend_pattern = re.compile(r"^(gee-backend/|\.github/workflows/)", re.MULTILINE)
    status_file = tmp_path / "backend-changes.txt"

    def extract_paths() -> list[str]:
        result = subprocess.run(extract, shell=True, check=True, capture_output=True, text=True)
        return result.stdout.splitlines()

    # Rename INTO the backend: only the NEW path points at gee-backend/.
    status_file.write_text(
        "R100\tdocs/old-name.py\tgee-backend/app/domains/padron/new-name.py\n"
        "M\tconsorcio-web/src/App.tsx\n",
        encoding="utf-8",
    )
    extracted = extract_paths()
    assert any(backend_pattern.search(path) for path in extracted), extracted
    assert "gee-backend/app/domains/padron/new-name.py" in extracted

    # Rename OUT of the backend: only the OLD path points at gee-backend/.
    status_file.write_text(
        "R100\tgee-backend/app/domains/padron/service.py\tdocs/service.py\n",
        encoding="utf-8",
    )
    assert any(backend_pattern.search(path) for path in extract_paths())

    # Rename between two workflow files: detected via the NEW path.
    status_file.write_text(
        "R100\t.github/workflows/old.yml\t.github/workflows/backend.yml\n",
        encoding="utf-8",
    )
    assert any(backend_pattern.search(path) for path in extract_paths())

    # Plain modify records still yield exactly one path line each.
    status_file.write_text("M\tgee-backend/app/main.py\n", encoding="utf-8")
    assert extract_paths() == ["gee-backend/app/main.py"]


def test_pull_requests_to_develop_reach_ci() -> None:
    """El flujo es feature -> develop -> main, asi que develop necesita CI.

    Una rama de integracion sin checks es peor que no tenerla: da sensacion de
    red sin red. deploy.yml queda afuera a proposito: sus gates son de push a
    main post-merge.
    """
    for path in (
        ".github/workflows/backend.yml",
        ".github/workflows/frontend.yml",
        ".github/workflows/codeql.yml",
    ):
        header = _read(path).split("\njobs:", 1)[0]
        assert re.search(r"(?m)^    branches: \[main, develop\]$", header), path

    deploy = _read(".github/workflows/deploy.yml").split("\njobs:", 1)[0]
    assert "develop" not in deploy


def test_light_jobs_never_depend_on_release_only_jobs() -> None:
    """Un job SALTEADO arrastra al salteo a todo el que lo tenga en `needs`.

    Desde que la mutacion, los image gates y la matriz de accesibilidad corren
    solo en el PR de release, cualquier job barato que los tenga en `needs` se
    apagaria en los PRs a develop — silenciosamente, sin romper nada y sin que
    ningun check se ponga rojo. Este contrato existe para que esa dependencia
    no se cuele de nuevo.
    """
    backend = _read(".github/workflows/backend.yml")
    frontend = _read(".github/workflows/frontend.yml")

    solo_release = {
        "mutation",
        "image-backend",
        "image-geo-worker",
        "image-security-policy",
        "accessibility",
    }
    # `ci-gate` es la excepcion legitima: corre con `always()`, asi que un
    # `needs` salteado no lo apaga, y justamente necesita verlos a todos.
    for workflow, livianos in (
        (backend, ("lint", "typecheck", "test", "security")),
        (frontend, ("lint", "test", "typecheck", "smoke", "build", "image")),
    ):
        for job in livianos:
            assert not (_needs(workflow, job) & solo_release), job


def test_image_scans_set_an_explicit_trivy_timeout() -> None:
    """El default de Trivy son 5m0s y el geo-worker no entra ahi.

    La imagen trae GDAL mas todo el arbol de dependencias de Python: el
    analisis reventaba con "context deadline exceeded" a los 5 minutos justos.
    Eso NO es un hallazgo de seguridad, es el reloj interno del escaner — pero
    el gate lo reportaba como fallo (bien, es fail-closed) con el motivo real
    enterrado tres pasos mas arriba, en un job de 20 minutos.

    Sin un `timeout` explicito el gate depende de que la imagen no crezca, que
    es exactamente el tipo de supuesto que se rompe solo.
    """
    for path in (".github/workflows/backend.yml", ".github/workflows/deploy.yml"):
        workflow = _read(path)
        escaneos = workflow.count("scan-type: image")
        assert escaneos, path
        # Un `timeout` por cada escaneo de imagen.
        assert workflow.count("timeout: '20m'") == escaneos, path

    # El techo del job tiene que cubrir el escaneo MAS la construccion de la
    # imagen; si no, se cambia un fallo por reloj por otro fallo por reloj.
    geo = _job_block(_read(".github/workflows/backend.yml"), "image-geo-worker")
    assert "timeout-minutes: 45" in geo


def test_pgbouncer_is_declared_in_compose_not_hand_created() -> None:
    """El pooler tiene que vivir en el compose, no en la memoria de alguien.

    Estuvo meses corriendo en el servidor sin estar en ningun compose: se
    habia creado a mano. Al rotar la clave de Postgres hubo que reconstruirlo
    con `docker run` y se perdio un detalle que Compose pone solo: el ALIAS DE
    RED. Compose registra cada servicio con su NOMBRE DE SERVICIO como alias,
    y la DATABASE_URL de produccion apunta a `pgbouncer` — no al nombre del
    contenedor. Sin ese alias el DNS interno no resuelve, el backend se queda
    sin base, y los contenedores siguen reportando "healthy" porque su
    healthcheck solo mira que el proceso responda.

    De ahi que el nombre del servicio sea parte del contrato: renombrarlo
    rompe la resolucion en produccion.
    """
    compose = _read("docker-compose.yml")
    bloque = _job_block(compose, "pgbouncer")

    assert "image: edoburu/pgbouncer:" in bloque, "la imagen tiene que estar pinneada"
    assert "container_name: consorcio-pgbouncer" in bloque
    # Perfil: en desarrollo el backend va directo a postgres y levantar el
    # pooler seria una pieza de mas.
    assert 'profiles: ["pooler"]' in bloque
    # Transaction pooling es lo que hace que alembic NO pueda pasar por aca.
    assert "POOL_MODE: transaction" in bloque
    assert "AUTH_TYPE: scram-sha-256" in bloque
    # Sin healthcheck, `depends_on: service_healthy` de otros servicios no
    # tendria nada que esperar.
    assert "pg_isready" in bloque
    # La clave sale del entorno, nunca escrita en el archivo.
    assert "DB_PASSWORD: " + "$" + "{POSTGRES_PASSWORD" in bloque
    assert "postgres" in _needs_compose(compose, "pgbouncer")


def _needs_compose(compose: str, service: str) -> set[str]:
    """Servicios listados bajo `depends_on:` de un servicio del compose."""
    bloque = _job_block(compose, service)
    depende = bloque.split("depends_on:", 1)
    if len(depende) == 1:
        return set()
    encontrados = set()
    for linea in depende[1].splitlines():
        if re.match(r"^\s{6}[a-z-]+:\s*$", linea):
            encontrados.add(linea.strip().rstrip(":"))
        elif linea.strip() and not linea.startswith(" " * 6):
            break
    return encontrados


def test_geo_worker_mounts_the_map_canal_files() -> None:
    """Los escenarios queman las propuestas QUE EL MAPA MUESTRA.

    La fuente es el archivo del frontend (spec canales-relevados-y-propuestas),
    montado RO en el geo-worker. Sin este mount, el pipeline de escenarios
    falla al leer /app/data/canales/propuestas.geojson — y con una copia en la
    base en vez del mount, lo quemado podria divergir de lo dibujado, que es
    exactamente lo que el diseño quiso evitar.
    """
    compose = _read("docker-compose.yml")
    geo_worker = _job_block(compose, "geo-worker")

    assert "./consorcio-web/public/capas/canales:/app/data/canales:ro" in geo_worker


# Import names (not PyPI names) of the heavy ML stack. `FlagEmbedding` keeps
# its capital F because that is what an `import` statement actually says.
ML_IMPORT_ROOTS = frozenset(
    {
        "torch",
        "transformers",
        "sentence_transformers",
        "FlagEmbedding",
        "segmentation_models_pytorch",
    }
)

# The same stack by PEP 503 normalized distribution name, for requirements files.
ML_DISTRIBUTIONS = frozenset(
    {
        "torch",
        "transformers",
        "sentence-transformers",
        "flagembedding",
        "segmentation-models-pytorch",
    }
)


def _ml_imports(fuente: str) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """Split a module's heavy-ML imports into (eager, lazy) `(root, lineno)` pairs.

    An import is LAZY only when it is lexically nested inside a function or
    method body, because that is exactly the condition under which importing
    the module does not execute it. Everything else is EAGER — module scope,
    class bodies, and module-level ``try:``/``if:`` wrappers all run at import
    time, so a ``try: import torch`` at module scope pulls the CUDA stack into
    the image just as surely as a bare one, and the old substring guard could
    not tell any of these apart.
    """
    arbol = ast.parse(fuente)
    ansiosos: list[tuple[str, int]] = []
    perezosos: list[tuple[str, int]] = []

    def raiz(nombre: str) -> str:
        return nombre.split(".", 1)[0]

    def registrar(nodo: ast.AST, perezoso: bool) -> None:
        destino = perezosos if perezoso else ansiosos
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                if raiz(alias.name) in ML_IMPORT_ROOTS:
                    destino.append((raiz(alias.name), nodo.lineno))
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            if raiz(nodo.module) in ML_IMPORT_ROOTS:
                destino.append((raiz(nodo.module), nodo.lineno))

    def recorrer(nodo: ast.AST, perezoso: bool) -> None:
        for hijo in ast.iter_child_nodes(nodo):
            dentro = perezoso or isinstance(hijo, ast.FunctionDef | ast.AsyncFunctionDef)
            registrar(hijo, dentro)
            recorrer(hijo, dentro)

    recorrer(arbol, False)
    return ansiosos, perezosos


def _distribuciones_de_requirements(texto: str) -> set[str]:
    """PEP 503 normalized distribution names declared by a requirements file.

    Handles both hand-written files (``torch>=2.0.0``) and uv-compiled locks
    (``torch==2.1.0 \\`` plus ``--hash=`` continuation lines and ``# via``
    comments). Option lines (``-r``, ``--hash``) and comments are skipped.
    """
    nombres: set[str] = set()
    for linea in texto.splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith(("#", "-")):
            continue
        crudo = re.split(r"[<>=!~;\[\s]", limpia, maxsplit=1)[0]
        if crudo:
            nombres.add(re.sub(r"[-_.]+", "-", crudo).lower())
    return nombres


def test_training_ml_deps_never_reach_the_server_image() -> None:
    """torch y sus amigos NO viajan a las imagenes de servidor.

    torch arrastra el stack CUDA completo a un servidor SIN GPU: la imagen
    del geo-worker llego a pesar 8.2 GB para un modelo que ningun codigo de
    runtime importa — el unico consumidor es scripts/train_water_unet.py, que
    se corre en local. Ese peso no es cosmetico: es memoria y disco en un box
    compartido con otra produccion, y ya hubo un fallo transitorio de spawn
    de WhiteboxTools compatible con presion de memoria.

    **El split D8 se repenso, y por eso este guard cambio de forma.** El RAG
    (`app/domains/conocimiento/embedding.py`) necesita BGE-M3 y multilingual-e5
    para *ingestar*, nunca para servir, asi que la separacion NO es "app/ no
    nombra torch" sino tres hechos independientes:

    1. los imports pesados viven DENTRO de metodos (`__init__`, `encode`), asi
       que importar el modulo no ejecuta ninguno — verificado por AST, no por
       substring, que es lo que hacia rojo a un import perezoso legitimo;
    2. las deps viven en `requirements-rag.txt`, un extra de ingestion que se
       instala en un venv aparte (`venv-rag`) y en ninguna clausura de
       servidor — que es el hecho que este guard existe para proteger y que
       antes solo aproximaba;
    3. V0 no monta router de conocimiento, asi que la imagen del server ni
       siquiera puede llegar a ese codigo.

    Guard en las tres direcciones: si las deps vuelven a requirements-geo, si
    aparecen en la clausura del server, o si alguien sube un import de torch a
    scope de modulo en app/, esto se pone rojo con el culpable nombrado.
    """
    geo = _read("gee-backend/requirements-geo.txt")
    for linea in geo.splitlines():
        paquete = linea.split(">=")[0].split("==")[0].strip()
        assert paquete not in {"torch", "segmentation-models-pytorch"}, linea

    ml = _read("gee-backend/requirements-ml.txt")
    assert "torch" in ml and "segmentation-models-pytorch" in ml

    # El hecho de fondo: el stack pesado no esta en NINGUNA clausura que se
    # instale en una imagen de servidor ni en el CI que corre los tests.
    # `requirements.lock` es lo que el Dockerfile instala; `requirements.txt`
    # es su intencion declarada; `requirements-dev.lock` es lo que corre CI.
    for archivo in (
        "gee-backend/requirements.txt",
        "gee-backend/requirements.lock",
        "gee-backend/requirements-dev.lock",
    ):
        declaradas = _distribuciones_de_requirements(_read(archivo))
        intrusas = sorted(declaradas & ML_DISTRIBUTIONS)
        assert intrusas == [], f"{archivo} arrastra el stack ML: {intrusas}"

    # Ningun import pesado a scope de modulo en app/: importar cualquier modulo
    # de la app no puede ejecutar un import de torch. Los imports perezosos
    # (dentro de metodos) del embedder RAG pasan por diseño — ver el docstring.
    app_dir = REPO_ROOT / "gee-backend" / "app"
    culpables = []
    for archivo in sorted(app_dir.rglob("*.py")):
        ansiosos, _ = _ml_imports(archivo.read_text(encoding="utf-8"))
        culpables += [
            f"{archivo.relative_to(REPO_ROOT)}:{linea} -> {raiz}" for raiz, linea in ansiosos
        ]
    assert culpables == [], culpables


def test_the_rag_embedder_keeps_every_ml_import_inside_a_method() -> None:
    """`embedding.py` es el UNICO modulo de app/ que nombra el stack pesado.

    Lo hace adentro de `BGEM3Embedder.__init__` / `.encode` y de
    `E5Embedder.__init__`, que es lo que permite que `requirements-rag.txt`
    siga siendo un extra de ingestion (design.md D8). Este test lo fija por
    separado del guard general para que un refactor que suba cualquiera de
    esos imports a scope de modulo se ponga rojo con el archivo nombrado, en
    vez de aparecer como una linea mas de una lista sobre todo app/.

    La segunda mitad es la que impide que pase en vacio: si alguien borra los
    embedders, la mitad de arriba seguiria verde por ausencia. Los imports
    perezosos tienen que SEGUIR estando.
    """
    ruta = REPO_ROOT / "gee-backend" / "app" / "domains" / "conocimiento" / "embedding.py"
    ansiosos, perezosos = _ml_imports(ruta.read_text(encoding="utf-8"))

    assert ansiosos == [], (
        "embedding.py subio un import pesado a scope de modulo (o a un try/if "
        f"de modulo, que se ejecuta igual): {ansiosos}"
    )
    assert {"torch", "transformers", "sentence_transformers"} <= {raiz for raiz, _ in perezosos}, (
        f"los imports perezosos del embedder desaparecieron: {perezosos}"
    )


def test_baseline_de_mutacion_no_comparte_grupo_de_concurrencia_con_ci() -> None:
    """La baseline de mutacion (schedule/dispatch) NO puede compartir grupo de
    concurrencia con los push/PR de CI.

    Con cancel-in-progress, si comparten grupo un push a main CANCELA la corrida
    de baseline en vuelo — que fue lo que impidio sembrar la baseline en `main`
    y dejo a cada release pagando el scope completo de Stryker (hoy 3049
    mutantes y hasta 120 min alojados) en vez del incremental (diff + blast
    radius, minutos). El grupo tiene que
    diferenciar el evento de baseline del de CI.
    """
    import yaml

    frontend = yaml.safe_load(_read(".github/workflows/frontend.yml"))
    concurrency = frontend.get("concurrency", {})
    texto_grupo = str(concurrency.get("group", ""))
    assert texto_grupo, "no se encontro el group de concurrency del frontend"

    # El grupo tiene que ramificar por evento: schedule/dispatch -> un grupo,
    # el resto -> otro. Asi un push a main no cancela la baseline en vuelo.
    assert "schedule" in texto_grupo and "workflow_dispatch" in texto_grupo, (
        "el grupo de concurrencia no distingue el evento de baseline; un push "
        "a main volveria a cancelar mutation-full"
    )


def test_frontend_mutation_matrices_partition_the_canonical_scope() -> None:
    import yaml

    workflow = yaml.safe_load(_read(".github/workflows/frontend.yml"))
    pr_shards = _mutation_matrix(workflow, "mutation")
    full_shards = _mutation_matrix(workflow, "mutation-full")
    canonical = _stryker_config_targets()

    assert len(canonical) == len(set(canonical)) == 17
    assert pr_shards == STRYKER_SHARDS
    assert full_shards == STRYKER_SHARDS
    assert set(pr_shards) == {"a", "b"}
    assert set(pr_shards["a"]).isdisjoint(pr_shards["b"])
    assert set(pr_shards["a"] + pr_shards["b"]) == set(canonical)
    assert len(canonical) == len(pr_shards["a"] + pr_shards["b"])
    for job in ("mutation", "mutation-full"):
        assert workflow["jobs"][job]["strategy"]["fail-fast"] is False
        # 90 -> 120 (PR #242 incident, 2026-08-26): a COLD shard-a run measures
        # ~88 min and the previous frontend PR passed the 90-min axe by 23
        # seconds; the job was killed at 96% with ~2 min left. 120 is the
        # safety margin BEHIND the artifact-fallback baseline recovery (the
        # real fix) -- warm runs stay ~15-20 min. This pin caught the workflow
        # edit exactly as designed; acknowledge changes here, never bypass.
        assert workflow["jobs"][job]["timeout-minutes"] == 120


def test_frontend_mutation_shards_use_isolated_reports_artifacts_and_caches() -> None:
    frontend = _read(".github/workflows/frontend.yml")
    mutation = _job_block(frontend, "mutation")
    mutation_full = _job_block(frontend, "mutation-full")
    publish = _job_block(frontend, "mutation-full-publish")

    for producer, command in (
        (mutation, 'npm run mutation:run -- --mutate "$MUTATE"'),
        (mutation_full, 'npm run mutation:run -- --force --mutate "$MUTATE"'),
    ):
        assert "STRYKER_SHARD: ${{ matrix.shard }}" in producer
        assert "MUTATE: ${{ matrix.mutate }}" in producer
        assert command in producer
        assert "mutation-${{ matrix.shard }}.json" in producer
        assert "stryker-incremental-${{ matrix.shard }}.json" in producer
        assert "if-no-files-found: error" in producer

    assert "uses: actions/cache/restore@v4" in mutation
    assert "uses: actions/cache@v4" not in mutation
    assert "uses: actions/cache/save@v4" not in mutation
    assert "stryker-incremental-v2-${{ matrix.shard }}-" in mutation
    assert "stryker-incremental-${{ github.sha }}" not in mutation
    assert "mutation-pr-${{ matrix.shard }}-${{ github.run_id }}" in mutation

    assert "actions/cache/restore" not in mutation_full
    assert "actions/cache/save" not in mutation_full
    assert "mutation-full-${{ matrix.shard }}-${{ github.run_id }}" in mutation_full

    assert _needs(frontend, "mutation-full-publish") == {"mutation-full"}
    assert "if: ${{ always()" in publish
    assert 'test "$MUTATION_FULL_RESULT" = "success"' in publish
    assert publish.index('test "$MUTATION_FULL_RESULT" = "success"') < publish.index(
        "uses: actions/cache/save@v4"
    )
    assert publish.count("uses: actions/cache/save@v4") == 2
    for shard in ("a", "b"):
        assert f"stryker-incremental-{shard}.json" in publish
        assert f"stryker-incremental-v2-{shard}-${{{{ github.sha }}}}" in publish


def test_frontend_mutation_aggregate_and_required_gate_fail_closed() -> None:
    frontend = _read(".github/workflows/frontend.yml")
    aggregate = _job_block(frontend, "mutation-gate")
    full_aggregate = _job_block(frontend, "mutation-full-publish")
    gate = _job_block(frontend, "ci-gate")

    assert _needs(frontend, "mutation-gate") == {"changes", "mutation"}
    assert re.findall(r"(?m)^    if: (.+)$", aggregate) == [
        "$" + "{{ always() && github.base_ref == 'main' "
        "&& needs.changes.outputs.frontend == 'true' }}"
    ]
    assert 'test "$MUTATION_RESULT" = "success"' in aggregate
    assert "pattern: mutation-pr-*" in aggregate
    assert "merge-multiple: true" in aggregate
    expected_source_loader = (
        "import { mutationTargets } from './stryker.config.mjs'; "
        "process.stdout.write(mutationTargets.join(','))"
    )
    for aggregate_job in (aggregate, full_aggregate):
        assert expected_source_loader in aggregate_job
        assert '--expected-source "$EXPECTED_SOURCES"' in aggregate_job
        assert "python3 scripts/aggregate_stryker_reports.py --minimum 75" in aggregate_job
        assert "reports/mutation/mutation-a.json reports/mutation/mutation-b.json" in aggregate_job

    assert {"mutation", "mutation-gate"} <= _needs(frontend, "ci-gate")
    assert "MUTATION_GATE_RESULT: ${{ needs.mutation-gate.result }}" in gate
    assert '[ "$BASE_REF" = "main" ] && [ "$FRONTEND_CHANGED" = "true" ]' in gate
    assert 'test "$MUTATION_RESULT" = "success"' in gate
    assert 'test "$MUTATION_GATE_RESULT" = "success"' in gate
    assert 'require mutation "$MUTATION_RESULT"' in gate
    assert 'require mutation-gate "$MUTATION_GATE_RESULT"' in gate


def _write_mutation_report(path: Path, files: dict[str, list[str]]) -> None:
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "2.0",
                "files": {
                    source: {
                        "language": "typescript",
                        "source": "",
                        "mutants": [
                            {"id": str(index), "status": status}
                            for index, status in enumerate(statuses)
                        ],
                    }
                    for source, statuses in files.items()
                },
            }
        ),
        encoding="utf-8",
    )


def _run_stryker_aggregate(
    tmp_path: Path,
    *reports: Path,
    minimum: str = "75",
    expected_sources: tuple[str, ...] = ("src/a.ts", "src/b.ts"),
) -> subprocess.CompletedProcess[str]:
    script = REPO_ROOT / "consorcio-web" / "scripts" / "aggregate_stryker_reports.py"
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--minimum",
            minimum,
            *(
                argument
                for source in expected_sources
                for argument in ("--expected-source", source)
            ),
            *(str(report) for report in reports),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )


def test_stryker_aggregate_global_score_boundaries_and_status_semantics(tmp_path: Path) -> None:
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    _write_mutation_report(first, {"src/a.ts": ["Killed", "Timeout", "Survived", "Ignored"]})
    _write_mutation_report(
        second, {"src/b.ts": ["Killed", "NoCoverage", "CompileError", "RuntimeError"]}
    )

    at_boundary = _run_stryker_aggregate(tmp_path, first, second, minimum="60")
    assert at_boundary.returncode == 0, at_boundary.stderr
    assert (
        "detected=3 undetected=2 valid=5 excluded=3 score=60.00% minimum=60.00%"
        in at_boundary.stdout
    )

    below = _run_stryker_aggregate(tmp_path, first, second, minimum="60.01")
    assert below.returncode != 0

    _write_mutation_report(first, {"src/a.ts": ["Killed"] * 3})
    _write_mutation_report(second, {"src/b.ts": ["NoCoverage"]})
    exact_75 = _run_stryker_aggregate(tmp_path, first, second)
    assert exact_75.returncode == 0
    assert "score=75.00%" in exact_75.stdout

    _write_mutation_report(first, {"src/a.ts": ["Killed"] * 7499})
    _write_mutation_report(second, {"src/b.ts": ["Survived"] * 2501})
    just_below = _run_stryker_aggregate(tmp_path, first, second)
    assert just_below.returncode != 0
    assert "score=74.99%" in just_below.stdout


def test_stryker_aggregate_rejects_incomplete_or_invalid_reports(tmp_path: Path) -> None:
    valid = tmp_path / "valid.json"
    _write_mutation_report(valid, {"src/a.ts": ["Killed"]})

    cases: list[tuple[str, Path]] = []
    missing = tmp_path / "missing.json"
    cases.append(("missing", missing))
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    cases.append(("malformed", malformed))
    non_object_files = tmp_path / "non-object-files.json"
    non_object_files.write_text(json.dumps({"files": []}), encoding="utf-8")
    cases.append(("non-object files", non_object_files))
    non_list_mutants = tmp_path / "non-list-mutants.json"
    non_list_mutants.write_text(
        json.dumps({"files": {"src/b.ts": {"mutants": {}}}}), encoding="utf-8"
    )
    cases.append(("non-list mutants", non_list_mutants))
    empty = tmp_path / "empty.json"
    _write_mutation_report(empty, {})
    cases.append(("empty", empty))
    no_mutants = tmp_path / "no-mutants.json"
    _write_mutation_report(no_mutants, {"src/b.ts": []})
    cases.append(("no mutants", no_mutants))
    pending = tmp_path / "pending.json"
    _write_mutation_report(pending, {"src/b.ts": ["Pending"]})
    cases.append(("Pending", pending))
    unknown = tmp_path / "unknown.json"
    _write_mutation_report(unknown, {"src/b.ts": ["NewStatus"]})
    cases.append(("unknown", unknown))
    missing_status = tmp_path / "missing-status.json"
    missing_status.write_text(
        json.dumps({"files": {"src/b.ts": {"mutants": [{"id": "1"}]}}}), encoding="utf-8"
    )
    cases.append(("missing status", missing_status))

    for label, invalid in cases:
        result = _run_stryker_aggregate(tmp_path, valid, invalid)
        assert result.returncode != 0, label

    duplicate = tmp_path / "duplicate.json"
    _write_mutation_report(duplicate, {"src/a.ts": ["Killed"]})
    result = _run_stryker_aggregate(tmp_path, valid, duplicate)
    assert result.returncode != 0


def test_stryker_aggregate_requires_exact_canonical_source_union(tmp_path: Path) -> None:
    canonical = tuple(_stryker_config_targets())
    midpoint = len(canonical) // 2
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"

    _write_mutation_report(first, {source: ["Killed"] for source in canonical[:midpoint]})
    _write_mutation_report(second, {source: ["Killed"] for source in canonical[midpoint:]})
    exact = _run_stryker_aggregate(
        tmp_path,
        first,
        second,
        expected_sources=(",".join(canonical[:midpoint]), *canonical[midpoint:]),
    )
    assert exact.returncode == 0, exact.stderr

    _write_mutation_report(second, {source: ["Killed"] for source in canonical[midpoint:-1]})
    missing = _run_stryker_aggregate(
        tmp_path, first, second, expected_sources=(",".join(canonical),)
    )
    assert missing.returncode == 2
    assert f"missing source file paths: {canonical[-1]}" in missing.stderr

    unexpected_source = "src/lib/renamed-target.ts"
    _write_mutation_report(
        second,
        {
            **{source: ["Killed"] for source in canonical[midpoint:]},
            unexpected_source: ["Killed"],
        },
    )
    unexpected = _run_stryker_aggregate(
        tmp_path, first, second, expected_sources=(",".join(canonical),)
    )
    assert unexpected.returncode == 2
    assert f"unexpected source file paths: {unexpected_source}" in unexpected.stderr


RAINFALL_HARNESS_WORKFLOW = ".github/workflows/rainfall-multi-parcel-e2e.yml"


def test_rainfall_harness_workflow_stays_optional_and_unreferenced() -> None:
    """RMEH-010-B / RMEH-014-A: the dedicated manual harness workflow must NOT
    become a PR-required check and must NOT leak into the required CI gates or
    the production canary.

    A dedicated `workflow_dispatch`-only workflow is safer than extending the
    required `Frontend`/`Backend`/`Deploy` gates (whose workflow contract
    forbids E2E wiring) or the canary (a stateful fixture harness must not point
    at production). This test pins that separation so the harness can never be
    silently promoted into a gate.
    """
    harness = _without_comments(_read(RAINFALL_HARNESS_WORKFLOW))
    header = harness.split("\njobs:", 1)[0]

    # (a) workflow_dispatch ONLY — never push/pull_request/schedule, so it can
    # never run as a required status check on a PR.
    assert "workflow_dispatch:" in header
    for forbidden_trigger in ("push:", "pull_request:", "schedule:"):
        assert forbidden_trigger not in header, forbidden_trigger

    # (b) NOT referenced by any required-gate workflow or the canary.
    for path in (
        ".github/workflows/frontend.yml",
        ".github/workflows/backend.yml",
        ".github/workflows/deploy.yml",
        ".github/workflows/e2e-canary.yml",
    ):
        text = _read(path)
        assert RAINFALL_HARNESS_WORKFLOW not in text, path

    # (c) NOT in the production canary three-spec read-only allowlist: the canary
    # script runs exactly CANARY_READ_ONLY_SPECS, and the harness spec is not one.
    package = json.loads(_read("consorcio-web/package.json"))
    canary_script = package["scripts"]["test:e2e:canary"]
    assert canary_script.startswith("playwright test -c tests/e2e/playwright.config.ts ")
    assert canary_script.split()[4:] == list(CANARY_READ_ONLY_SPECS)

    # (d) The harness itself is isolated: no secrets, serialized concurrency
    # (cancel-in-progress:false), 45-min job timeout, artifact upload with
    # 14-day retention and if-no-files-found:error (RMEH-010-D, design §Workflow).
    assert "permissions:" in harness
    assert "contents: read" in harness
    assert "cancel-in-progress: false" in harness
    assert "timeout-minutes: 45" in harness
    assert "retention-days: 14" in harness
    assert "if-no-files-found: error" in harness
    assert "if: always()" in harness


def test_only_the_publishing_workflow_writes_full_buildkit_layer_caches() -> None:
    """BL-GHA-CACHE-CEILING: `mode=max` belongs to deploy.yml and nowhere else.

    The GitHub Actions cache has a HARD 10 GB per-repo ceiling and evicts by
    LRU, silently. Measured 2026-08-26: 12.1 GB across 259 entries and ZERO
    Stryker entries -- the ~1 MB mutation baselines the cron publishes were
    evicted inside 48 h by 300-400 MB of BuildKit layer blobs, and the PR #242
    mutation job then ran cold and died on the clock at 96%.

    The rule this pins: a workflow that BUILDS A CANDIDATE TO SCAN AND THROW
    AWAY (backend.yml, frontend.yml -- PR/dispatch only) writes `mode=min`; the
    workflow that PUBLISHES from main and actually feeds later runs
    (deploy.yml, `workflow_dispatch`) keeps `mode=max`. Reversing that is the
    incident, so it fails here instead of two days later in someone else's job.

    Matched by regex, not by substring: ``cache-to`` takes its parameters in ANY
    order, so ``type=gha,scope=frontend-image,mode=max`` is the same directive
    as ``type=gha,mode=max,scope=frontend-image``. A literal
    ``"cache-to: type=gha,mode=max" not in workflow`` would read as green while
    the reordered form silently reopened the incident.
    """
    # Comment-stripped input, so a `mode=max` mentioned in prose (there are
    # several, explaining exactly this rule) never counts as a directive.
    mode_max = re.compile(r"^\s*cache-to:\s*(?=[^\n]*\btype=gha\b)[^\n]*\bmode=max\b", re.M)
    mode_min = re.compile(r"^\s*cache-to:\s*(?=[^\n]*\btype=gha\b)[^\n]*\bmode=min\b", re.M)

    for path, expected_min in (
        (".github/workflows/backend.yml", 2),  # backend-image + geo-worker-image
        (".github/workflows/frontend.yml", 1),  # frontend-image
    ):
        workflow = _without_comments(_read(path))
        assert mode_max.findall(workflow) == [], path
        assert len(mode_min.findall(workflow)) == expected_min, path

    deploy = _without_comments(_read(".github/workflows/deploy.yml"))
    assert len(mode_max.findall(deploy)) == 2
    assert mode_min.findall(deploy) == []
