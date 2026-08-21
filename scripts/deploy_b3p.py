#!/usr/bin/env python3
"""Fail-closed preparation CLI for the Consorcio B3-P backend deployment."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.request import Request, urlopen

TARGET_SHA = "1bb3985beb6817e2d7093203d515e8de2235a889"
TARGET_SERVICE = "backend"
COMPOSE_IMAGE = "consorcio-backend"
CONFIRMATION = "DEPLOY-B3P"
LOGICAL_VOLUMES = {"consorcio-backend-cache", "consorcio-geo-data", "consorcio-denuncia-uploads"}
EXPECTED_MOUNTS = {
    ("volume", "backend-cache", "/app/.cache", "rw"),
    ("volume", "geo-data", "/data/geo", "rw"),
    ("volume", "denuncia-uploads", "/app/uploads", "rw"),
}


class Refusal(RuntimeError):
    """A required admission gate did not pass."""


@dataclass(frozen=True)
class Config:
    host: str = "157.180.29.238"
    user: str = "javier"
    port: int = 2222
    key: Path = Path("~/.ssh/hetzner_ghagga")
    repo: str = "JNZader/consorcio-canalero"
    stack: str = "/home/javier/stacks/consorcio"
    target_sha: str = TARGET_SHA


DEFAULTS = Config()


@dataclass(frozen=True)
class Gate:
    name: str
    command: str
    kind: str = "read-only"


# One SSH call per read-only gate. Commands deliberately have no shell chaining.
GATES = (
    Gate("branch", "git -C /home/javier/stacks/consorcio branch --show-current"),
    Gate("compose-hash", "sha256sum /home/javier/stacks/consorcio/docker-compose.yml"),
    Gate("head", "git -C /home/javier/stacks/consorcio rev-parse HEAD"),
    Gate("worktree-status", "git -C /home/javier/stacks/consorcio status --porcelain"),
    Gate("staged", "git -C /home/javier/stacks/consorcio diff --cached --name-only"),
    Gate("untracked", "git -C /home/javier/stacks/consorcio ls-files --others --exclude-standard"),
    Gate("unfinished-git-operation", "git -C /home/javier/stacks/consorcio rev-parse --git-path MERGE_HEAD"),
    Gate("production-compose", "docker compose -f /home/javier/stacks/consorcio/docker-compose.yml config --quiet"),
    Gate("no-reload", "docker compose -f /home/javier/stacks/consorcio/docker-compose.yml config --services"),
    Gate("backend-mounts", "docker inspect consorcio-backend --format '{{json .Mounts}}'"),
    Gate("fetched-object", "git -C /home/javier/stacks/consorcio cat-file -e {sha}^{commit}"),
    Gate("ancestry", "git -C /home/javier/stacks/consorcio merge-base --is-ancestor HEAD {sha}"),
    Gate("incoming-collision", "git -C /home/javier/stacks/consorcio diff --name-only HEAD..{sha}"),
    Gate("no-compose-or-alembic", "git -C /home/javier/stacks/consorcio diff --name-only HEAD..{sha}"),
    Gate("resources", "docker stats --no-stream consorcio-backend"),
    Gate("loopback-port", "ss -H -ltn sport = :18080"),
    Gate("live-image", "docker inspect consorcio-backend --format '{{.Image}}|{{.Config.Image}}'"),
    Gate("consorcio-biogas-baseline", "docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}'"),
)


def redact(text: str) -> str:
    return re.sub(r"(?i)\b(password|token|secret|authorization)=\S+", r"\1=***", text)


def _run(argv: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def ssh_argv(config: Config, command: str) -> list[str]:
    return ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-i", str(config.key.expanduser()), "-p", str(config.port), f"{config.user}@{config.host}", "sh -lc " + shlex.quote(command)]


def remote_argv(config: Config, command: str) -> list[str]:
    return ssh_argv(config, f"cd {shlex.quote(config.stack)} && {command}")


def _validate_gate(gate: Gate, stdout: str) -> None:
    """Validate output that a successful read-only command alone cannot prove."""
    value = stdout.strip()
    if gate.name == "branch" and value != "main":
        raise Refusal("preflight branch is not main")
    if gate.name in {"worktree-status", "staged", "untracked"} and value:
        raise Refusal(f"preflight {gate.name} is not empty")
    if gate.name == "backend-mounts":
        try:
            normalize_mounts(json.loads(value))
        except (json.JSONDecodeError, TypeError) as exc:
            raise Refusal(f"preflight backend-mounts cannot be parsed: {exc}") from exc
    if gate.name == "no-compose-or-alembic" and re.search(r"(^|/)(docker-compose|alembic)", value):
        raise Refusal("preflight incoming change includes Compose or Alembic")
    if gate.name == "loopback-port" and value:
        raise Refusal("preflight canary port is occupied")
    if gate.name == "live-image" and (len(parts := value.split("|")) != 2 or not parts[0].startswith("sha256:") or parts[1] != COMPOSE_IMAGE):
        raise Refusal("preflight live image lacks exact validated compose image")
    if gate.name == "consorcio-biogas-baseline" and not {"consorcio", "biogas"} <= set(re.findall(r"[a-z]+", value.lower())):
        raise Refusal("preflight requires Consorcio and Biogas read-only baselines")


def preflight(config: Config, runner: Callable[[list[str]], tuple[int, str, str]] = _run) -> None:
    """Replay all read-only remote gates and stop at the first failure."""
    for gate in GATES:
        if gate.kind != "read-only":
            raise Refusal(f"preflight gate {gate.name} is not read-only")
        command = gate.command.format(sha=shlex.quote(config.target_sha))
        code, stdout, stderr = runner(ssh_argv(config, command))
        if code:
            raise Refusal(f"preflight {gate.name} failed: {redact(stderr or stdout).strip()}")
        _validate_gate(gate, stdout)


def normalize_mounts(mounts: Iterable[dict]) -> set[tuple[str, str, str, str]]:
    normalized = set()
    for mount in mounts:
        if mount.get("Type") != "volume":
            raise Refusal("mount contract rejects bind, anonymous, root, code, and docker-socket mounts")
        source = mount.get("Name") or mount.get("Source")
        if source not in LOGICAL_VOLUMES:
            raise Refusal("mount contract rejects unknown or anonymous volume")
        logical = source.removeprefix("consorcio-")
        normalized.add(("volume", logical, mount.get("Destination", ""), "rw" if mount.get("RW") else "ro"))
    if normalized != EXPECTED_MOUNTS:
        raise Refusal("mount contract is not the exact backend volume set")
    return normalized


def verify_github_commit(config: Config, target_sha: str, opener=urlopen) -> None:
    """Verify GitHub's official commit signature response; malformed means no-go."""
    url = f"https://api.github.com/repos/{config.repo}/commits/{target_sha}"
    try:
        request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "consorcio-b3p-deploy"})
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        verification = payload["commit"]["verification"]
        if payload["sha"] != target_sha or verification["verified"] is not True or verification["reason"] != "valid":
            raise ValueError("unverified commit")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise Refusal(f"GitHub commit verification failed closed: {exc}") from exc


def smoke_tunnel_command(env: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    required = {key: env.get(key, "") for key in ("E2E_ADMIN_EMAIL", "E2E_ADMIN_PASSWORD")}
    if not all(required.values()):
        raise Refusal("credentialed smoke requires local E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD")
    return ssh_argv(DEFAULTS, "true")[:-4] + ["-N", "-L", "127.0.0.1:18080:127.0.0.1:18080", f"{DEFAULTS.user}@{DEFAULTS.host}"], required


def deployment_plan(config: Config) -> list[dict[str, object]]:
    """Printed argv templates only; this function never executes them."""
    remote = lambda command: remote_argv(config, command)
    return [
        {"state": "backup-compose", "argv": remote("cp docker-compose.yml docker-compose.yml.b3p-backup")},
        {"state": "capture-old-id", "argv": remote("docker inspect consorcio-backend --format {{.Image}}")},
        {"state": "build-backend-only", "argv": remote("docker compose build backend")},
        {"state": "canary-loopback", "argv": remote("docker run --rm -p 127.0.0.1:18080:8000 {NEW_IMAGE_ID}")},
        {"state": "cutover-backend-only", "argv": remote("docker compose up -d --no-deps backend")},
        {"state": "rollback-old-id", "argv": rollback_plan("sha256:OLD_ID", config)},
    ]


def rollback_plan(old_id: str, config: Config = DEFAULTS) -> list[str]:
    if not old_id.startswith("sha256:"):
        raise Refusal("rollback requires an immutable old image ID")
    quote = shlex.quote
    tag = f"consorcio-backend:rollback-{old_id.removeprefix('sha256:')}"
    command = " && ".join((f"docker image tag {quote(old_id)} {quote(tag)}", f"docker image tag {quote(old_id)} {quote(COMPOSE_IMAGE)}", "docker compose up -d --no-deps --no-build --force-recreate backend", f"test \"$(docker inspect --format '{{{{.Image}}}}' consorcio-backend)\" = {quote(old_id)}"))
    return remote_argv(config, command)

def execute(config: Config, target_sha: str | None, confirmation: str | None, environ: dict[str, str], opener=urlopen) -> None:
    if not target_sha or not re.fullmatch(r"[0-9a-f]{40}", target_sha):
        raise Refusal("exact --target-sha is required before execute")
    if confirmation != CONFIRMATION:
        raise Refusal("explicit confirmation --confirm DEPLOY-B3P is required")
    if environ.get("CONSORCIO_B3P_DEPLOY_ALLOW_EXECUTE") != "1":
        raise Refusal("environment opt-in is required before execute")
    verify_github_commit(config, target_sha, opener)
    raise Refusal("execute is intentionally not implemented: inspect the printed plan and complete a reviewed state-machine")


def main(argv: list[str] | None = None, *, runner=_run, environ=None, stdout=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("plan", "preflight", "execute"), default="plan")
    parser.add_argument("--target-sha")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    config = Config(target_sha=args.target_sha or TARGET_SHA)
    output = stdout or sys.stdout
    if args.action == "plan":
        print(f"plan: backend-only target={config.target_sha}; no subprocesses will run", file=output)
        for step in deployment_plan(config):
            print(json.dumps(step), file=output)
        print("credentialed smoke and automated mutation are intentionally refused; never migrate, stop workers, or touch Biogas", file=output)
        return 0
    if args.action == "preflight":
        preflight(config, runner)
        print("preflight passed", file=output)
        return 0
    execute(config, args.target_sha, args.confirm, dict(os.environ if environ is None else environ))
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Refusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(2)
