from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MutationSummary:
    total: int
    killed: int
    survived: int
    timeout: int
    incompetent: int
    other: int
    pending: int

    @property
    def kill_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.killed / self.total


def _run_command(args: list[str]) -> None:
    completed = subprocess.run(args, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(args)}")


def _collect_summary(session_file: Path) -> MutationSummary:
    dump = subprocess.run(
        ["cosmic-ray", "dump", str(session_file)],
        check=True,
        capture_output=True,
        text=True,
    )
    outcomes: Counter[str] = Counter()
    pending = 0

    for line in dump.stdout.splitlines():
        _, result = json.loads(line)
        if result is None:
            pending += 1
            continue
        outcomes[result.get("test_outcome", "other")] += 1

    total = sum(outcomes.values())
    return MutationSummary(
        total=total,
        killed=outcomes.get("killed", 0),
        survived=outcomes.get("survived", 0),
        timeout=outcomes.get("timeout", 0),
        incompetent=outcomes.get("incompetent", 0),
        other=outcomes.get("other", 0),
        pending=pending,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run cosmic-ray mutation quality gate")
    parser.add_argument("--config", default=".cosmic-ray.toml")
    parser.add_argument("--session", default=".cosmic-ray.sqlite")
    parser.add_argument(
        "--min-kill-rate",
        type=float,
        default=float(os.getenv("COSMIC_MIN_KILL_RATE", "0.12")),
        help="Minimum accepted kill rate between 0 and 1",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config_file = Path(args.config)
    session_file = Path(args.session)

    if not config_file.exists():
        print(f"Config file not found: {config_file}", file=sys.stderr)
        return 2

    if session_file.exists():
        session_file.unlink()

    try:
        _run_command(["cosmic-ray", "baseline", str(config_file)])
        _run_command(["cosmic-ray", "init", str(config_file), str(session_file)])
        _run_command(["cosmic-ray", "exec", str(config_file), str(session_file)])
        summary = _collect_summary(session_file)
    except Exception as exc:
        print(f"Mutation gate failed to run: {exc}", file=sys.stderr)
        return 1

    print(
        "Mutation summary: "
        f"total={summary.total} "
        f"killed={summary.killed} "
        f"survived={summary.survived} "
        f"timeout={summary.timeout} "
        f"incompetent={summary.incompetent} "
        f"other={summary.other} "
        f"pending={summary.pending}"
    )
    print(f"Kill rate: {summary.kill_rate:.2%} (required >= {args.min_kill_rate:.2%})")

    if summary.pending > 0:
        print(
            "Mutation gate failed: pending mutations remain after exec", file=sys.stderr
        )
        return 1

    if summary.kill_rate < args.min_kill_rate:
        print("Mutation gate failed: kill rate below threshold", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
