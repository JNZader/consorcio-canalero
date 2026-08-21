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

TARGET_SERVICE = "backend"
COMPOSE_IMAGE = "consorcio-backend"
CONFIRMATION = "DEPLOY-B3P"
LOGICAL_VOLUMES = {"consorcio-backend-cache", "consorcio-geo-data", "consorcio-denuncia-uploads"}
PRODUCTION_COMPOSE_FILE = "docker-compose.production-local.yml"
COMPOSE_FILES = ("docker-compose.yml", PRODUCTION_COMPOSE_FILE)
WATERWAYS_SOURCE_SUFFIX = "gee-backend/data/waterways"
WATERWAYS_DESTINATION = "/app/data/waterways"
EXPECTED_MOUNTS = {
    ("volume", "backend-cache", "/app/.cache", "rw"),
    ("volume", "geo-data", "/data/geo", "rw"),
    ("volume", "denuncia-uploads", "/app/uploads", "rw"),
    ("bind", "/home/javier/stacks/consorcio/gee-backend/data/waterways", WATERWAYS_DESTINATION, "rw"),
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
    target_sha: str | None = None


DEFAULTS = Config()


def compose_command(*args: str, stack: str | None = None) -> str:
    """Build the only accepted production-local Compose invocation."""
    files = COMPOSE_FILES if stack is None else tuple(f"{stack}/{name}" for name in COMPOSE_FILES)
    selector = " ".join(f"-f {shlex.quote(name)}" for name in files)
    return " ".join(("docker compose", selector, *(shlex.quote(arg) for arg in args)))


@dataclass(frozen=True)
class Gate:
    name: str
    command: str
    kind: str = "read-only"


# Current-checkout admission intentionally excludes target-only Compose checks.
CURRENT_CHECKOUT_GATES = (
    Gate("branch", "git -C /home/javier/stacks/consorcio branch --show-current"),
    Gate("base-compose-integrity", 'test "$(git -C /home/javier/stacks/consorcio hash-object docker-compose.yml)" = "$(git -C /home/javier/stacks/consorcio rev-parse HEAD:docker-compose.yml)"'),
    Gate("head", "git -C /home/javier/stacks/consorcio rev-parse HEAD"),
    Gate("worktree-status", "git -C /home/javier/stacks/consorcio status --porcelain"),
    Gate("staged", "git -C /home/javier/stacks/consorcio diff --cached --name-only"),
    Gate("untracked", "git -C /home/javier/stacks/consorcio ls-files --others --exclude-standard"),
    Gate("unfinished-git-operation", 'test ! -e "$(git -C /home/javier/stacks/consorcio rev-parse --git-path MERGE_HEAD)" && test ! -e "$(git -C /home/javier/stacks/consorcio rev-parse --git-path CHERRY_PICK_HEAD)" && test ! -e "$(git -C /home/javier/stacks/consorcio rev-parse --git-path REVERT_HEAD)" && test ! -d "$(git -C /home/javier/stacks/consorcio rev-parse --git-path rebase-merge)" && test ! -d "$(git -C /home/javier/stacks/consorcio rev-parse --git-path rebase-apply)"'),
    Gate("resources", "docker stats --no-stream consorcio-backend"),
    Gate("loopback-port", "ss -H -ltn sport = :18080"),
    Gate("live-image", "docker inspect consorcio-backend --format '{{.Image}}|{{.Config.Image}}'"),
    Gate("consorcio-biogas-baseline", "docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}'"),
)
TARGET_GIT_GATES = (
    Gate("fetched-object", "git -C /home/javier/stacks/consorcio cat-file -e {sha}^{commit}"),
    Gate("ancestry", "git -C /home/javier/stacks/consorcio merge-base --is-ancestor HEAD {sha}"),
)
_contract_script = "import json,sys; b=json.load(sys.stdin)['services']['backend']; print(json.dumps({'forwarded_allow_ips':b.get('environment',{}).get('FORWARDED_ALLOW_IPS'),'volumes':b.get('volumes',[]),'pgbouncer':b.get('depends_on',{}).get('pgbouncer')}))"
FULL_TARGET_CONTRACT_GATES = (
    Gate("target-head", "git -C /home/javier/stacks/consorcio rev-parse HEAD"),
    Gate("base-compose-integrity", 'test "$(git -C /home/javier/stacks/consorcio hash-object docker-compose.yml)" = "$(git -C /home/javier/stacks/consorcio rev-parse HEAD:docker-compose.yml)"'),
    Gate("worktree-status", "git -C /home/javier/stacks/consorcio status --porcelain"),
    Gate("staged", "git -C /home/javier/stacks/consorcio diff --cached --name-only"),
    Gate("untracked", "git -C /home/javier/stacks/consorcio ls-files --others --exclude-standard"),
    Gate("unfinished-git-operation", 'test ! -e "$(git -C /home/javier/stacks/consorcio rev-parse --git-path MERGE_HEAD)" && test ! -e "$(git -C /home/javier/stacks/consorcio rev-parse --git-path CHERRY_PICK_HEAD)" && test ! -e "$(git -C /home/javier/stacks/consorcio rev-parse --git-path REVERT_HEAD)" && test ! -d "$(git -C /home/javier/stacks/consorcio rev-parse --git-path rebase-merge)" && test ! -d "$(git -C /home/javier/stacks/consorcio rev-parse --git-path rebase-apply)"'),
    Gate("production-compose", compose_command("config", "--quiet", stack="/home/javier/stacks/consorcio")),
    Gate("target-compose-contract", f"{compose_command('config', '--format', 'json', stack='/home/javier/stacks/consorcio')} | python3 -c {shlex.quote(_contract_script)}"),
    Gate("backend-mounts", "docker inspect consorcio-backend --format '{{json .Mounts}}'"),
)
# Compatibility/readability surface for inspection-only consumers.
GATES = CURRENT_CHECKOUT_GATES + TARGET_GIT_GATES + FULL_TARGET_CONTRACT_GATES


def redact(text: str) -> str:
    return re.sub(r"(?i)\b(password|token|secret|authorization)=\S+", r"\1=***", text)


def _run(argv: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def ssh_argv(config: Config, command: str) -> list[str]:
    return ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-i", str(config.key.expanduser()), "-p", str(config.port), f"{config.user}@{config.host}", "sh -lc " + shlex.quote(command)]


def remote_argv(config: Config, command: str) -> list[str]:
    return ssh_argv(config, f"cd {shlex.quote(config.stack)} && {command}")


def require_target_sha(target_sha: str | None) -> str:
    if not target_sha or not re.fullmatch(r"[0-9a-f]{40}", target_sha):
        raise Refusal("exact 40-character lowercase --target-sha is required")
    return target_sha


def _validate_gate(gate: Gate, stdout: str, config: Config) -> None:
    """Validate output that a successful read-only command alone cannot prove."""
    value = stdout.strip()
    if gate.name == "branch" and value != "main":
        raise Refusal("preflight branch is not main")
    if gate.name == "head" and not re.fullmatch(r"[0-9a-f]{40}", value):
        raise Refusal("preflight current HEAD is not a known commit SHA")
    if gate.name == "target-head" and value != require_target_sha(config.target_sha):
        raise Refusal("target/full-contract readiness requires current HEAD to equal --target-sha")
    if gate.name in {"worktree-status", "staged", "untracked"} and value:
        raise Refusal(f"preflight {gate.name} is not empty")
    if gate.name == "loopback-port" and value:
        raise Refusal("preflight canary port is occupied")
    if gate.name == "live-image" and (len(parts := value.split("|")) != 2 or not parts[0].startswith("sha256:") or parts[1] != COMPOSE_IMAGE):
        raise Refusal("preflight live image lacks exact validated compose image")
    if gate.name == "consorcio-biogas-baseline" and not {"consorcio", "biogas"} <= set(re.findall(r"[a-z]+", value.lower())):
        raise Refusal("preflight requires Consorcio and Biogas read-only baselines")
    if gate.name == "target-compose-contract":
        try:
            contract = json.loads(value)
            validate_compose_contract(contract, config)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise Refusal(f"preflight target Compose contract cannot be parsed: {exc}") from exc
    if gate.name == "backend-mounts":
        try:
            normalize_mounts(json.loads(value), config)
        except (json.JSONDecodeError, TypeError) as exc:
            raise Refusal(f"preflight backend-mounts cannot be parsed: {exc}") from exc


def _run_gates(gates: Iterable[Gate], config: Config, runner: Callable[[list[str]], tuple[int, str, str]]) -> None:
    for gate in gates:
        if gate.kind != "read-only":
            raise Refusal(f"preflight gate {gate.name} is not read-only")
        command = gate.command.format(sha=shlex.quote(config.target_sha or ""))
        code, stdout, stderr = runner(ssh_argv(config, command))
        if code:
            raise Refusal(f"preflight {gate.name} failed: {redact(stderr or stdout).strip()}")
        _validate_gate(gate, stdout, config)


def current_checkout_preflight(config: Config, runner: Callable[[list[str]], tuple[int, str, str]] = _run) -> None:
    _run_gates(CURRENT_CHECKOUT_GATES, config, runner)


def target_git_preflight(config: Config, runner: Callable[[list[str]], tuple[int, str, str]] = _run) -> None:
    require_target_sha(config.target_sha)
    _run_gates(TARGET_GIT_GATES, config, runner)


def full_target_contract_preflight(config: Config, runner: Callable[[list[str]], tuple[int, str, str]] = _run) -> None:
    require_target_sha(config.target_sha)
    _run_gates(FULL_TARGET_CONTRACT_GATES, config, runner)


def preflight(config: Config, runner: Callable[[list[str]], tuple[int, str, str]] = _run) -> bool:
    """Current-checkout admission, plus target readiness only when target is current HEAD."""
    current_checkout_preflight(config, runner)
    if not config.target_sha:
        return False
    full_target_contract_preflight(config, runner)
    return True


def validate_compose_contract(contract: dict, config: Config) -> None:
    expected = {
        ("bind", f"{config.stack}/{WATERWAYS_SOURCE_SUFFIX}", WATERWAYS_DESTINATION, "rw"),
        ("volume", "backend-cache", "/app/.cache", "rw"),
        ("volume", "geo-data", "/data/geo", "rw"),
        ("volume", "denuncia-uploads", "/app/uploads", "rw"),
    }
    normalized = {
        (volume.get("type"), volume.get("source"), volume.get("target"), "ro" if volume.get("read_only") else "rw")
        for volume in contract["volumes"]
    }
    if len(contract["volumes"]) != len(expected) or normalized != expected:
        raise Refusal("target Compose contract is not the exact backend mount set")
    if contract["forwarded_allow_ips"] != "caddy":
        raise Refusal("target Compose contract requires FORWARDED_ALLOW_IPS=caddy")
    if contract["pgbouncer"] != {"condition": "service_healthy", "required": True}:
        raise Refusal("target Compose contract requires healthy-gated PgBouncer")


def normalize_mounts(mounts: Iterable[dict], config: Config = DEFAULTS) -> set[tuple[str, str, str, str]]:
    """Allow only the three named volumes and the canonical waterways RW bind."""
    expected_bind = ("bind", f"{config.stack}/{WATERWAYS_SOURCE_SUFFIX}", WATERWAYS_DESTINATION, "rw")
    expected = EXPECTED_MOUNTS if config == DEFAULTS else (EXPECTED_MOUNTS - {next(item for item in EXPECTED_MOUNTS if item[0] == "bind")}) | {expected_bind}
    normalized: list[tuple[str, str, str, str]] = []
    for mount in mounts:
        kind = mount.get("Type")
        mode = "rw" if mount.get("RW") is True else "ro"
        if kind == "volume":
            source = mount.get("Name")
            if source not in LOGICAL_VOLUMES:
                raise Refusal("mount contract rejects unknown or anonymous volume")
            normalized.append(("volume", source.removeprefix("consorcio-"), mount.get("Destination", ""), mode))
        elif kind == "bind":
            normalized.append(("bind", mount.get("Source", ""), mount.get("Destination", ""), mode))
        else:
            raise Refusal("mount contract rejects anonymous, root, code, and docker-socket mounts")
    if len(normalized) != len(expected) or set(normalized) != expected:
        raise Refusal("mount contract is not the exact backend mount set")
    return set(normalized)


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
    require_target_sha(config.target_sha)
    remote = lambda command: remote_argv(config, command)
    return [
        {"state": "backup-compose", "argv": remote("cp docker-compose.yml docker-compose.yml.b3p-backup")},
        {"state": "capture-old-id", "argv": remote("docker inspect consorcio-backend --format {{.Image}}")},
        {"state": "build-backend-only", "argv": remote(compose_command("build", "backend"))},
        {"state": "canary-loopback", "argv": remote(compose_command("run", "--rm", "--no-deps", "--publish", "127.0.0.1:18080:8000", "backend", "python", "-m", "app.server"))},
        {"state": "cutover-backend-only", "argv": remote(compose_command("up", "-d", "--no-deps", "backend"))},
        {"state": "rollback-old-id", "argv": rollback_plan("sha256:OLD_ID", config)},
    ]


def rollback_plan(old_id: str, config: Config = DEFAULTS) -> list[str]:
    if not old_id.startswith("sha256:"):
        raise Refusal("rollback requires an immutable old image ID")
    quote = shlex.quote
    tag = f"consorcio-backend:rollback-{old_id.removeprefix('sha256:')}"
    command = " && ".join((f"docker image tag {quote(old_id)} {quote(tag)}", f"docker image tag {quote(old_id)} {quote(COMPOSE_IMAGE)}", compose_command("up", "-d", "--no-deps", "--no-build", "--force-recreate", "backend"), f"test \"$(docker inspect --format '{{{{.Image}}}}' consorcio-backend)\" = {quote(old_id)}"))
    return remote_argv(config, command)

def execute(config: Config, target_sha: str | None, confirmation: str | None, environ: dict[str, str], opener=urlopen) -> None:
    require_target_sha(target_sha)
    if config.target_sha != target_sha:
        raise Refusal("configured target does not match the supplied --target-sha")
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
    config = Config(target_sha=args.target_sha)
    output = stdout or sys.stdout
    if args.action == "plan":
        require_target_sha(config.target_sha)
        print(f"plan: backend-only target={config.target_sha}; no subprocesses will run", file=output)
        for step in deployment_plan(config):
            print(json.dumps(step), file=output)
        print("credentialed smoke and automated mutation are intentionally refused; never migrate, stop workers, or touch Biogas", file=output)
        return 0
    if args.action == "preflight":
        ready = preflight(config, runner)
        print("current-checkout admission passed; target/full-contract readiness passed" if ready else "current-checkout admission passed; target/full-contract readiness not evaluated (exact --target-sha required)", file=output)
        return 0
    execute(config, args.target_sha, args.confirm, dict(os.environ if environ is None else environ))
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Refusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(2)
