#!/usr/bin/env python3
"""Fail-closed selector and config writer for the Cosmic Ray CI targets."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_PREFIX = "gee-backend/"
WORKFLOW_PREFIX = ".github/workflows/"

# Resolved against the script, not the caller's cwd: the workflow invokes this
# planner from the repository root, so a cwd-relative default fails closed with
# "[Errno 2] No such file or directory" even though the manifest exists.
DEFAULT_MANIFEST = Path(__file__).resolve().parent / "cosmic_mutation_targets.json"


@dataclass(frozen=True)
class MutationTarget:
    name: str
    module: str
    owns: tuple[str, ...]
    tests: tuple[str, ...]
    min_kill_rate: float


def load_manifest(path: Path) -> list[MutationTarget]:
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1 or not isinstance(raw.get("targets"), list):
        raise ValueError("unsupported cosmic mutation target manifest")
    targets: list[MutationTarget] = []
    for entry in raw["targets"]:
        if not isinstance(entry, dict):
            raise ValueError("mutation target must be an object")
        name, module, owns, tests, rate = (
            entry.get(key) for key in ("name", "module", "owns", "tests", "min_kill_rate")
        )
        if (
            not isinstance(name, str)
            or not isinstance(module, str)
            or not isinstance(owns, list)
            or not all(isinstance(value, str) for value in owns)
            or not isinstance(tests, list)
            or not tests
            or not all(isinstance(value, str) for value in tests)
            or not isinstance(rate, (int, float))
            or not 0 <= rate <= 1
        ):
            raise ValueError(f"invalid mutation target: {entry!r}")
        targets.append(MutationTarget(name, module, tuple(owns), tuple(tests), float(rate)))
    if not targets or len({target.name for target in targets}) != len(targets):
        raise ValueError("mutation target names must be unique")
    return targets


def parse_name_status(path: Path) -> tuple[list[str], bool]:
    changed, full_required = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 2 or fields[0] not in {"A", "M"}:
            full_required = True
            continue
        changed.append(fields[1])
    return changed, full_required


def select_targets(
    targets: list[MutationTarget], changed_paths: list[str]
) -> tuple[list[MutationTarget], str]:
    selected: dict[str, MutationTarget] = {}
    for path in changed_paths:
        if path.startswith(WORKFLOW_PREFIX):
            return targets, "workflow-change"
        if not path.startswith(REPO_PREFIX):
            continue
        relative = path.removeprefix(REPO_PREFIX)
        if relative.startswith(("tests/", "scripts/")) or relative in {
            ".cosmic-ray.toml",
            "Dockerfile",
            "pyproject.toml",
            "pytest.ini",
            "requirements.lock",
            "requirements-dev.lock",
            "requirements.txt",
        }:
            return targets, "shared-harness-or-config-change"
        owners = [
            target
            for target in targets
            if any(relative.startswith(prefix) for prefix in target.owns)
        ]
        if not owners:
            return targets, "unowned-backend-change"
        selected.update({target.name: target for target in owners})
    return (
        (list(selected.values()), "owned-domain-change")
        if selected
        else (targets, "no-owned-target")
    )


def write_config(target: MutationTarget, destination: Path) -> None:
    tests = " ".join(target.tests)
    destination.write_text(
        "\n".join(
            [
                "[cosmic-ray]",
                f"module-path = [{json.dumps(target.module)}]",
                "timeout = 120.0",
                "excluded-modules = []",
                f"test-command = {json.dumps(f'python3 -m pytest {tests} -q')}",
                "",
                "[cosmic-ray.distributor]",
                'name = "local"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan fail-closed Cosmic Ray mutation targets")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--status-file", type=Path)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--target")
    parser.add_argument("--write-config", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        targets = load_manifest(args.manifest)
        if args.target:
            if not args.write_config:
                raise ValueError("--target requires --write-config")
            target = next((item for item in targets if item.name == args.target), None)
            if target is None:
                raise ValueError(f"unknown mutation target: {args.target}")
            write_config(target, args.write_config)
            return 0
        if args.full:
            selected, reason = targets, "manual-full-run"
        elif args.status_file:
            changed, unsupported = parse_name_status(args.status_file)
            selected, reason = (
                (targets, "renamed-or-deleted-change")
                if unsupported
                else select_targets(targets, changed)
            )
        else:
            raise ValueError("provide --status-file or --full")
        payload = json.dumps(
            {"include": [{"target": target.name} for target in selected]}, separators=(",", ":")
        )
        print(f"Cosmic mutation plan ({reason}): {', '.join(target.name for target in selected)}")
        print(payload)
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as output:
                output.write(f"mutation_matrix={payload}\n")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Mutation target planning failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
