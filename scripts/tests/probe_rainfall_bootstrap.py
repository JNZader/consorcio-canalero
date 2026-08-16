#!/usr/bin/env python3
"""One-off W5 real-stack probe (NOT part of the repo test suite).

Provisions the disposable harness stack with non-conflicting loopback host
ports, writes the ownership init script, validates the marker, bootstraps the
SAME owned database TWICE (idempotency), validates services, then tears down the
exact run-owned resources.

Usage:
    python3 scripts/tests/probe_rainfall_bootstrap.py

Env (all optional, loopback-only by default):
    RMEH_RUN_ID_PREFIX     compose/container/database prefix  (default probedefault)
    RMEH_BACKEND_HOST_PORT host port for backend              (default 8101)
    RMEH_MARTIN_HOST_PORT  host port for martin               (default 3002)
    RMEH_FRONTEND_HOST_PORT host port for frontend            (default 5175)

This probe is a diagnostic: the authoritative W5 integration acceptance is the
`@pytest.mark.integration` suite driven by the W11 runner driver.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.rainfall_e2e_harness.safety import (  # noqa: E402
    RunIdentity,
    RealCommandRunner,
    write_init_script,
    validate_marker_read_only,
)
from scripts.rainfall_e2e_harness.bootstrap import (  # noqa: E402
    COMPOSE_FILE,
    bootstrap_database,
    validate_services,
)


def main() -> int:
    import json

    prefix = os.environ.get("RMEH_RUN_ID_PREFIX", "probedefault")
    backend_port = os.environ.get("RMEH_BACKEND_HOST_PORT", "8101")
    martin_port = os.environ.get("RMEH_MARTIN_HOST_PORT", "3002")
    frontend_port = os.environ.get("RMEH_FRONTEND_HOST_PORT", "5175")

    # Identity must match POSTGRES_DB = rmeh_<prefix> and the marker row.
    identity = RunIdentity(
        run_id=prefix,
        marker_nonce="probenonce" * 4,
        database_name=f"rmeh_{prefix}",
        evidence_dir=None,
    )
    init = REPO / "scripts" / "tests" / f"rmeh-init-{prefix}.sql"
    write_init_script(init, identity)
    print(f"[probe] wrote {init} (mode {oct(init.stat().st_mode & 0o777)})")

    runner = RealCommandRunner()
    env = dict(os.environ)
    env.update(
        RMEH_RUN_ID_PREFIX=prefix,
        RMEH_BACKEND_HOST_PORT=backend_port,
        RMEH_MARTIN_HOST_PORT=martin_port,
        RMEH_FRONTEND_HOST_PORT=frontend_port,
    )

    # 1. Provision the stack.
    up = runner.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d", "--build"],
        kind=__import__("scripts.rainfall_e2e_harness.safety", fromlist=["CommandKind"]).CommandKind.DOCKER_CONTROL,
        env=env,
    )
    if up.exit_code != 0:
        print(f"[probe] compose up FAILED:\n{up.stderr}")
        return 1
    print("[probe] compose up -d ok")

    # 2. Wait for backend health (poll /live) before marker validation.
    import time
    for _ in range(60):
        live = runner.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"http://127.0.0.1:{backend_port}/live"],
                          kind=__import__("scripts.rainfall_e2e_harness.safety", fromlist=["CommandKind"]).CommandKind.DOCKER_INSPECT)
        if live.stdout.strip() == "200":
            break
        time.sleep(2)
    else:
        print(f"[probe] backend /live never 200 on :{backend_port}")
        _teardown(runner, env, COMPOSE_FILE)
        return 1

    # 3. Validate the marker (read-only gate).
    owned = validate_marker_read_only(runner, identity, compose_file=COMPOSE_FILE)
    print(f"[probe] marker validated run={owned.run_id} db={owned.database_name}")

    # 4. Bootstrap the SAME owned DB TWICE (idempotency).
    fixture_path = REPO / "consorcio-web" / "tests" / "e2e" / "fixtures" / "rainfall-multi-parcel.fixture.json"
    with open(fixture_path, encoding="utf-8") as fh:
        fixture = json.load(fh)
    first = bootstrap_database(identity, runner, fixture, compose_file=COMPOSE_FILE)
    print(f"[probe] first pass: action={first.parcel_view_action} rebuilt={first.rebuilt} "
          f"soil_rows={first.soil_rows} srid={first.srid} digest={first.seed_digest[:12]}")
    second = bootstrap_database(identity, runner, fixture, compose_file=COMPOSE_FILE)
    print(f"[probe] second pass: action={second.parcel_view_action} rebuilt={second.rebuilt} "
          f"soil_rows={second.soil_rows} srid={second.srid} digest={second.seed_digest[:12]}")

    assert first.seed_digest == second.seed_digest, "seed digest not stable across passes"
    assert first.soil_rows == second.soil_rows == 1, "soil cardinality not stable"
    assert first.parcel_view_action == second.parcel_view_action, "view action not stable"
    print("[probe] IDEMPOTENCY OK (byte/cardinality stable across two passes)")

    # 5. Validate services against the probe ports.
    report = validate_services(
        identity, runner, fixture,
        origins={"martin": f"http://127.0.0.1:{martin_port}",
                 "backend": f"http://127.0.0.1:{backend_port}",
                 "frontend": f"http://127.0.0.1:{frontend_port}"},
    )
    print(f"[probe] services: tile={report.tile_ok_for} ficha={report.ficha_ok_for} "
          f"martin={report.martin_ok} live={report.backend_live} frontend={report.frontend_ok}")
    assert report.tile_ok_for == ("A", "B", "C")
    assert report.ficha_ok_for == ("A", "B", "C")

    _teardown(runner, env, COMPOSE_FILE)
    print("[probe] PROBE PASSED")
    return 0


def _teardown(runner, env, compose_file: str) -> None:
    kind = __import__("scripts.rainfall_e2e_harness.safety", fromlist=["CommandKind"]).CommandKind
    runner.run(["docker", "compose", "-f", compose_file, "down", "-v", "--remove-orphans"],
               kind=kind.DOCKER_CONTROL, env=env)
    print("[probe] teardown (down -v --remove-orphans) issued")


if __name__ == "__main__":
    raise SystemExit(main())
