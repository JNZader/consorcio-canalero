"""Pytest contract tests for the W4 test-infra config (and W10 workflow contract).

RED tests for change ``rainfall-multi-parcel-e2e-harness`` work unit W4:
Compose stack, Martin catalog, Playwright harness config, tsconfig.tests.json
enrolment and the package.json harness command.

These are CONFIG CONTRACT tests, not runtime tests:
  * The Compose contract resolves the file with a deterministic synthetic
    run-prefix via ``docker compose -f <file> config --format json`` (NO Docker
    daemon is required — ``config`` only resolves interpolation + schema) and
    asserts every published port binds loopback, no service uses the
    production name ``consorcio``, and project/volume/network/container names
    all derive from the run prefix (no fixed shared names — RMEH-001/010).
  * The Martin contract parses the harness catalog YAML and asserts exactly
    one source ``parcelas_catastro`` on the migration-owned materialized view
    ``vt_parcelas_catastro`` with the seven whitelisted properties and no
    auto-discovery (RMEH-002-C/003).
  * The enrolment contract asserts tsconfig.tests.json (hand-maintained
    include list, R3-004) lists the W2 helper + unit test, and that
    package.json adds ONE harness command while leaving the canary command
    byte-identical (RMEH-010-A/014-A).

The ``docker`` CLI is optional: tests skip if it is absent, since ``config``
resolution is the acceptance and a CI runner without Docker still runs the
YAML/Martin/tsconfig static contracts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "scripts" / "tests" / "rainfall-e2e.compose.yml"
MARTIN_FILE = REPO_ROOT / "scripts" / "tests" / "fixtures" / "martin-rainfall-e2e.yaml"
PLAYWRIGHT_HARNESS_CONFIG = (
    REPO_ROOT / "consorcio-web" / "tests" / "e2e" / "playwright.rainfall-harness.config.ts"
)
TSCONFIG_TESTS = REPO_ROOT / "consorcio-web" / "tsconfig.tests.json"
PACKAGE_JSON = REPO_ROOT / "consorcio-web" / "package.json"

# The seven frontend-whitelisted catastro properties (martin/config.yaml +
# src/lib/map/layerPropertyWhitelists.ts). The harness catalog publishes the
# SAME seven — drift would let a tile leak a column the public map never reads.
_EXPECTED_MARTIN_PROPERTIES = (
    "nro_cuenta",
    "desig_oficial",
    "superficie_ha",
    "departamento",
    "pedania",
    "nomenclatura",
    "tipo_parcela",
)

_LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


def _has_docker() -> bool:
    return shutil.which("docker") is not None


def _compose_config_json() -> dict:
    """Resolve the harness Compose file with a synthetic prefix + ports.

    The prefix mimics ``ResourceLease.plan``: ``rmeh-<prefix>`` project,
    ``rmeh_<prefix>`` database. The caller never accepts overrides for shared
    targets, so this is a deterministic test prefix, not a real credential.
    """
    env = {
        **os.environ,
        "RMEH_RUN_ID_PREFIX": "probepref",
        "RMEH_DB_PASSWORD": "synthpass",
        "RMEH_DB_HOST_PORT": "5433",
        "RMEH_BACKEND_HOST_PORT": "8001",
        "RMEH_MARTIN_HOST_PORT": "3001",
        "RMEH_FRONTEND_HOST_PORT": "5174",
    }
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "config", "--format", "json"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"docker compose config failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    return json.loads(result.stdout)


def _strip_jsonc(text: str) -> str:
    """Strip ``//`` line comments AND ``/* ... */`` block comments from JSONC
    (tsconfig.tests.json opens with a block comment). A regex is enough; do
    not import a JSONC parser just for this contract test."""
    import re

    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    out = []
    for line in text.splitlines():
        idx = line.find("//")
        if idx != -1:
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# W4.1 — Compose stack: loopback-only, generated identity, no shared names
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not _has_docker(), reason="docker CLI not available")
class TestComposeStackContract:
    def test_compose_file_exists(self):
        assert COMPOSE_FILE.is_file(), f"missing compose file: {COMPOSE_FILE}"

    def test_compose_resolves_with_generated_identity(self):
        cfg = _compose_config_json()
        # Project name derives from the run prefix, never a fixed/dir name.
        assert cfg["name"] == "rmeh-probepref", (
            f"compose project name must derive from RMEH_RUN_ID_PREFIX, got {cfg['name']!r}"
        )

    def test_every_published_port_binds_loopback(self):
        cfg = _compose_config_json()
        violations: list[str] = []
        for svc, spec in cfg.get("services", {}).items():
            for port in spec.get("ports", []) or []:
                host_ip = port.get("host_ip", "")
                if host_ip not in _LOOPBACK_HOSTS:
                    violations.append(f"{svc}: {host_ip!r} -> {port}")
        assert not violations, f"non-loopback published ports: {violations}"

    def test_db_and_redis_have_no_host_ports(self):
        cfg = _compose_config_json()
        for internal_only in ("db", "redis"):
            ports = cfg["services"].get(internal_only, {}).get("ports") or []
            assert ports == [], (
                f"{internal_only} must be internal-only (expose, no host ports); "
                f"resolved ports={ports}"
            )

    def test_database_name_is_generated_not_consorcio(self):
        cfg = _compose_config_json()
        db_env = cfg["services"]["db"].get("environment", {})
        postgres_db = db_env.get("POSTGRES_DB", "")
        assert postgres_db == "rmeh_probepref", (
            f"POSTGRES_DB must be rmeh_<prefix>, got {postgres_db!r}"
        )
        assert postgres_db != "consorcio", "default shared DB name 'consorcio' is forbidden"

    def test_database_user_is_synthetic_not_consorcio(self):
        cfg = _compose_config_json()
        db_env = cfg["services"]["db"].get("environment", {})
        assert db_env.get("POSTGRES_USER") != "consorcio", (
            "POSTGRES_USER must not be the production 'consorcio' role"
        )

    def test_no_fixed_shared_compose_names(self):
        cfg = _compose_config_json()
        # Project, volumes, networks, container names must NOT carry production
        # identifiers — every name must derive from the run prefix.
        for key in ("name",):
            assert "consorcio" not in cfg.get(key, "").lower(), (
                f"compose {key} carries a shared name: {cfg.get(key)!r}"
            )
        for vol_name in (cfg.get("volumes") or {}):
            assert not vol_name.startswith("consorcio"), (
                f"volume name carries shared prefix: {vol_name!r}"
            )
        for net_name in (cfg.get("networks") or {}):
            assert not net_name.startswith("consorcio"), (
                f"network name carries shared prefix: {net_name!r}"
            )
        for svc, spec in cfg.get("services", {}).items():
            cn = spec.get("container_name") or ""
            assert not cn.startswith("consorcio"), (
                f"{svc} container_name carries shared prefix: {cn!r}"
            )

    def test_compose_projects_volume_and_network_match_lease_convention(self):
        cfg = _compose_config_json()
        # ResourceLease.plan: volume_name = f"{project}_pgdata"; network =
        # f"{project}_net"; containers = f"{project}-<svc>-1"; db =
        # f"rmeh_<prefix>". The compose file must reproduce those EXACT names
        # so the runner's lease + assertion_no_resource_collision line up.
        # NOTE: `docker compose config` keeps the LOGICAL key as the map key
        # (pgdata/net) and puts the interpolated resolved name in the `name`
        # field — assert the resolved name, not the map key.
        vol_name = next(iter((cfg.get("volumes") or {}).values()))["name"]
        net_name = next(iter((cfg.get("networks") or {}).values()))["name"]
        assert vol_name == "rmeh-probepref_pgdata", f"volume name {vol_name!r}"
        assert net_name == "rmeh-probepref_net", f"network name {net_name!r}"
        for svc, expected in (
            ("db", "rmeh-probepref-db-1"),
            ("backend", "rmeh-probepref-backend-1"),
            ("martin", "rmeh-probepref-martin-1"),
            ("frontend", "rmeh-probepref-frontend-1"),
        ):
            if svc in cfg["services"]:
                assert cfg["services"][svc].get("container_name") == expected, (
                    f"{svc} container_name"
                )

    def test_yaml_source_pins_loopback_prefix_on_published_ports(self):
        """Defence-in-depth: the YAML must literally write ``127.0.0.1:`` on
        every published port, so a missing env var cannot resolve to a bare
        host port (which Compose binds on 0.0.0.0)."""
        text = COMPOSE_FILE.read_text()
        # Every line that maps a host port must begin with 127.0.0.1.
        bad = []
        for line in text.splitlines():
            stripped = line.strip()
            # Only inspect published-port mappings under `ports:`.
            if stripped.startswith('"') and ":5432" in stripped and "127.0.0.1" not in stripped:
                bad.append(stripped)
            if stripped.startswith('"') and ":8000" in stripped and "127.0.0.1" not in stripped:
                bad.append(stripped)
            if stripped.startswith('"') and ":3000" in stripped and "127.0.0.1" not in stripped:
                bad.append(stripped)
            if stripped.startswith('"') and ":5173" in stripped and "127.0.0.1" not in stripped:
                bad.append(stripped)
        assert not bad, f"ports missing 127.0.0.1 prefix: {bad}"


# --------------------------------------------------------------------------- #
# W4.2 — Martin catalog: one source, seven properties, no auto-discovery
# --------------------------------------------------------------------------- #
class TestMartinRainfallCatalogContract:
    def test_martin_file_exists(self):
        assert MARTIN_FILE.is_file(), f"missing martin catalog: {MARTIN_FILE}"

    def test_catalog_auto_publish_disabled(self):
        if not MARTIN_FILE.is_file():
            pytest.skip("martin catalog absent")
        data = yaml.safe_load(MARTIN_FILE.read_text())
        pg = data.get("postgres", {})
        assert pg.get("auto_publish") is False, "auto_publish must be false (no schema discovery)"
        assert not pg.get("functions"), "no functions may be auto-published"

    def test_catalog_publishes_exactly_one_source(self):
        if not MARTIN_FILE.is_file():
            pytest.skip("martin catalog absent")
        data = yaml.safe_load(MARTIN_FILE.read_text())
        tables = data["postgres"]["tables"]
        assert list(tables.keys()) == ["parcelas_catastro"], (
            f"exactly one source 'parcelas_catastro'; got {list(tables.keys())}"
        )

    def test_catalog_source_backs_migration_owned_view(self):
        if not MARTIN_FILE.is_file():
            pytest.skip("martin catalog absent")
        data = yaml.safe_load(MARTIN_FILE.read_text())
        table = data["postgres"]["tables"]["parcelas_catastro"]
        assert table["schema"] == "public"
        assert table["table"] == "vt_parcelas_catastro", (
            "source must back the migration-owned materialized view vt_parcelas_catastro"
        )
        assert table["geometry_column"] == "geometria"
        assert table["srid"] == 4326

    def test_catalog_publishes_exactly_seven_whitelist_properties(self):
        if not MARTIN_FILE.is_file():
            pytest.skip("martin catalog absent")
        data = yaml.safe_load(MARTIN_FILE.read_text())
        props = data["postgres"]["tables"]["parcelas_catastro"]["properties"]
        assert tuple(props.keys()) == _EXPECTED_MARTIN_PROPERTIES, (
            f"seven whitelist properties, in order; got {tuple(props.keys())}"
        )


# --------------------------------------------------------------------------- #
# W4.4 — tsconfig enrolment + package.json harness command (canary unchanged)
# --------------------------------------------------------------------------- #
# The canary command must remain byte-identical (RMEH-014-A): the harness adds
# one NEW command and must not perturb the production canary.
_CANARY_COMMAND = (
    "playwright test -c tests/e2e/playwright.config.ts "
    "tests/e2e/mapa-maplibre.spec.ts "
    "tests/e2e/mapa-viewport-movil.spec.ts "
    "tests/e2e/ficha-territorial.spec.ts"
)
_HARNESS_CONFIG_REL = "tests/e2e/playwright.rainfall-harness.config.ts"
_HARNESS_SCRIPT_NAME = "test:e2e:rainfall-harness"
_EXPECTED_ENROLLED_FILES = (
    "tests/e2e/helpers/rainfallMultiParcelHarness.ts",
    "tests/unit/rainfallMultiParcelHarness.test.ts",
)


class TestEnrolmentContract:
    def test_tsconfig_enrols_rainfall_harness_helper_and_unit_test(self):
        raw = _strip_jsonc(TSCONFIG_TESTS.read_text())
        data = json.loads(raw)
        include = data.get("include", [])
        for rel in _EXPECTED_ENROLLED_FILES:
            assert rel in include, (
                f"tsconfig.tests.json include must list {rel} (R3-004 hand-maintained gate)"
            )

    def test_package_json_has_one_harness_command(self):
        data = json.loads(PACKAGE_JSON.read_text())
        scripts = data["scripts"]
        assert _HARNESS_SCRIPT_NAME in scripts, (
            f"package.json must add a harness Playwright command {_HARNESS_SCRIPT_NAME!r}"
        )
        cmd = scripts[_HARNESS_SCRIPT_NAME]
        assert _HARNESS_CONFIG_REL in cmd, (
            f"harness command must point at {_HARNESS_CONFIG_REL}; got {cmd!r}"
        )
        assert "rainfall-v2-detail.spec.ts" in cmd, (
            "harness command must select only rainfall-v2-detail.spec.ts"
        )

    def test_package_json_canary_command_byte_identical(self):
        data = json.loads(PACKAGE_JSON.read_text())
        assert data["scripts"]["test:e2e:canary"] == _CANARY_COMMAND, (
            "canary command MUST stay byte-identical (RMEH-014-A)"
        )

    def test_playwright_harness_config_file_exists(self):
        assert PLAYWRIGHT_HARNESS_CONFIG.is_file(), (
            f"missing harness Playwright config: {PLAYWRIGHT_HARNESS_CONFIG}"
        )