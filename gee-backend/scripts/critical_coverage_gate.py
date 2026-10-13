#!/usr/bin/env python3
"""CI-04: regression floors for critical modules.

The global ``--cov-fail-under`` stays a single number. These files were the
ones the v6 audit called out (auth, denuncias, rate limit). The floors sit
at the coverage measured on main (capped at 80%) so a deleted test fails CI
without demanding a suite the code does not have yet.

Coverage JSON is the pytest-cov ``--cov-report=json`` output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Measured on main 2026-10-13 (tests/new + .coveragerc): auth/router.py 27.1%,
# core/rate_limit.py 61.5%, denuncias/router.py 85.4%. Floors sit at the
# integer of that measurement, capped at the 80% target. Auth and rate limit
# stay under 80 because that is the coverage the suite already reaches.
FLOORS: dict[str, float] = {
    "app/auth/router.py": 27.0,
    "app/core/rate_limit.py": 61.0,
    "app/domains/denuncias/router.py": 80.0,
}


def _percent(files: dict[str, object], suffix: str) -> float | None:
    matches = [key for key in files if key.replace("\\", "/").endswith(suffix)]
    if len(matches) != 1:
        return None
    summary = files[matches[0]]
    if not isinstance(summary, dict):
        return None
    covered = summary.get("summary")
    if not isinstance(covered, dict):
        return None
    value = covered.get("percent_covered")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def evaluate(report: dict[str, object], floors: dict[str, float] = FLOORS) -> list[str]:
    files = report.get("files")
    if not isinstance(files, dict):
        return ["coverage report has no files object"]
    failures: list[str] = []
    for suffix, floor in floors.items():
        percent = _percent(files, suffix)
        if percent is None:
            failures.append(f"{suffix} missing from coverage report")
            continue
        if percent + 1e-9 < floor:
            failures.append(f"{suffix} covered {percent:.1f}% < floor {floor:.1f}%")
    return failures


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: critical_coverage_gate.py coverage.json", file=sys.stderr)
        return 2
    report = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        print("coverage report is not an object", file=sys.stderr)
        return 1
    failures = evaluate(report)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("critical coverage floors ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
