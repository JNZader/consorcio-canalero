"""W5.6/W5.7 — idempotency probe + relation-drift negatives, REAL STACK.

These run ONLY against a provisioned owned disposable stack (the W5 runner
driver / manual workflow), never in CI:
* they provision the compose stack and bootstrap the SAME owned database twice,
  asserting byte/cardinality stability (RMEH-002-B, RMEH-003-D);
* they drive the migration-only repair and rebuild-budget-abort paths against a
  real Postgres/PostGIS (RMEH-002-A, JDA-001, JDB-004).

Run with:  `python3 -m pytest scripts/tests/test_rainfall_e2e_integration.py -m integration`
after `docker compose -f scripts/tests/rainfall-e2e.compose.yml build migrate`.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from scripts.rainfall_e2e_harness.bootstrap import (
    COMPOSE_FILE,
    bootstrap_database,
    seed_digest,
    validate_services,
)
from scripts.rainfall_e2e_harness.safety import (
    CommandKind,
    RealCommandRunner,
    RunIdentity,
    validate_marker_read_only,
    write_init_script,
)

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "consorcio-web" / "tests" / "e2e" / "fixtures" / "rainfall-multi-parcel.fixture.json"

# The real-stack probes only make sense against a provisioned owned stack. They
# are skipped unless the caller opts in with RMEH_INTEGRATION=1 (the W5 runner
# driver / manual workflow sets this). CI never provisions a stack.
_skip_no_stack = pytest.mark.skipif(
    os.environ.get("RMEH_INTEGRATION") != "1",
    reason="real-stack probes need RMEH_INTEGRATION=1 against a provisioned stack",
)


def _run_prefix() -> str:
    """Deterministic prefix for the disposable stack (integration only)."""
    return os.environ.get("RMEH_RUN_ID_PREFIX", "integtest")


def _load_fixture() -> dict:
    with open(FIXTURE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _origins() -> dict:
    """Loopback origins for the disposable stack — same env overrides as the
    compose file (RMEH_{BACKEND,MARTIN,FRONTEND}_HOST_PORT), with the compose
    defaults as fallback, so a run against a provisioned stack on non-default
    ports (e.g. when a dev stack occupies 8001) works unchanged."""
    return {
        "martin": f"http://127.0.0.1:{os.environ.get('RMEH_MARTIN_HOST_PORT', '3001')}",
        "backend": f"http://127.0.0.1:{os.environ.get('RMEH_BACKEND_HOST_PORT', '8001')}",
        "frontend": f"http://127.0.0.1:{os.environ.get('RMEH_FRONTEND_HOST_PORT', '5174')}",
    }


def _stack_env(prefix: str) -> dict:
    """Env for compose: container/db prefix + host ports (compose defaults or
    explicit overrides)."""
    env = dict(os.environ)
    env.update(
        RMEH_RUN_ID_PREFIX=prefix,
        RMEH_BACKEND_HOST_PORT=os.environ.get("RMEH_BACKEND_HOST_PORT", "8001"),
        RMEH_MARTIN_HOST_PORT=os.environ.get("RMEH_MARTIN_HOST_PORT", "3001"),
        RMEH_FRONTEND_HOST_PORT=os.environ.get("RMEH_FRONTEND_HOST_PORT", "5174"),
    )
    return env


@pytest.fixture(scope="module")
def provisioned_identity():
    """Provision the disposable stack once per module; teardown the exact
    run-owned resources afterwards."""
    runner = RealCommandRunner()
    prefix = _run_prefix()
    # Identity must match POSTGRES_DB = rmeh_<prefix> and the marker row that
    # the init script installs (a driver or this fixture runs `up -d` once).
    identity = RunIdentity(
        run_id=prefix,
        marker_nonce="integtestnonce" * 4,
        database_name=f"rmeh_{prefix}",
        evidence_dir=REPO_ROOT / ".artifacts" / "rainfall-multi-parcel" / prefix,
    )
    init = REPO_ROOT / "scripts" / "tests" / f"rmeh-init-{prefix}.sql"
    write_init_script(init, identity)
    env = _stack_env(prefix)

    up = runner.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d", "--build"],
        kind=CommandKind.DOCKER_CONTROL,
        env=env,
    )
    if up.exit_code != 0:
        pytest.fail(f"compose up failed:\n{up.stderr}")

    # Wait for backend liveness before the read-only marker gate.
    backend = _origins()["backend"]
    for _ in range(60):
        live = runner.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"{backend}/live"],
            kind=CommandKind.DOCKER_INSPECT,
        )
        if live.stdout.strip() == "200":
            break
        time.sleep(2)
    else:
        pytest.fail(f"backend /live never 200 at {backend}")

    # Wait for martin catalog readiness — the source list is what the browser
    # depends on, so validate_services must never race a still-booting martin.
    martin = _origins()["martin"]
    for _ in range(60):
        cat = runner.run(
            ["curl", "-s", "-w", "\\n%{http_code}", f"{martin}/catalog"],
            kind=CommandKind.DOCKER_INSPECT,
        )
        if cat.stdout.rstrip().endswith("200"):
            break
        time.sleep(2)
    else:
        pytest.fail(f"martin /catalog never ready at {martin}")

    # Read-only ownership gate — proves the marker before ANY mutation.
    validate_marker_read_only(runner, identity, compose_file=COMPOSE_FILE)

    yield identity, runner, env

    runner.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "down", "-v", "--remove-orphans"],
        kind=CommandKind.DOCKER_CONTROL,
        env=env,
    )


class TestRealStackIdempotency:
    @_skip_no_stack
    def test_bootstrap_twice_same_owned_db_is_stable(self, provisioned_identity):
        identity, runner, _ = provisioned_identity
        fixture = _load_fixture()
        first = bootstrap_database(identity, runner, fixture, compose_file=COMPOSE_FILE)
        # Second pass against the SAME owned DB: same digest, same actions,
        # same cardinality (RMEH-002-B, RMEH-003-D).
        second = bootstrap_database(identity, runner, fixture, compose_file=COMPOSE_FILE)
        assert first.seed_digest == second.seed_digest
        assert first.soil_rows == second.soil_rows == 1
        assert first.parcel_view_action == second.parcel_view_action
        assert first.srid == second.srid == 4326

    @_skip_no_stack
    def test_services_stable_after_second_pass(self, provisioned_identity):
        identity, runner, _ = provisioned_identity
        fixture = _load_fixture()
        report = validate_services(identity, runner, fixture, origins=_origins())
        assert report.tile_ok_for == ("A", "B", "C", "LEGACY")
        assert report.ficha_ok_for == ("A", "B", "C", "LEGACY")
        assert report.martin_ok and report.backend_live and report.frontend_ok
