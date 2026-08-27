#!/usr/bin/env python3
"""Restrict a Stryker incremental baseline to the current exact mutation scope."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class BaselineError(ValueError):
    """Raised when a baseline or requested scope cannot be interpreted safely."""


@dataclass(frozen=True)
class Scope:
    """An exact path or a Stryker line/column range."""

    path: str
    start: tuple[int, int] | None = None
    end: tuple[int, int] | None = None

    def contains(self, start: tuple[int, int], end: tuple[int, int]) -> bool:
        return self.start is None or (self.start <= start and end <= self.end)


RANGE = re.compile(
    r"^(?P<path>[^:*?\[\]{}]+):(?P<start_line>[1-9]\d*)(?::(?P<start_column>[1-9]\d*))?-(?P<end_line>[1-9]\d*)(?::(?P<end_column>[1-9]\d*))?$"
)


def parse_scope(value: str) -> dict[str, Scope]:
    scopes: dict[str, Scope] = {}
    for raw_scope in value.split(","):
        candidate = raw_scope.strip()
        if not candidate:
            raise BaselineError("mutation scope contains an empty entry")
        match = RANGE.fullmatch(candidate)
        if match:
            groups = match.groupdict()
            start = (int(groups["start_line"]), int(groups["start_column"] or "0"))
            end = (int(groups["end_line"]), int(groups["end_column"] or "999999999"))
            if end < start:
                raise BaselineError(
                    f"mutation range has an inverted boundary: {candidate}"
                )
            scope = Scope(groups["path"], start, end)
        elif ":" in candidate or any(symbol in candidate for symbol in "*?[]{}"):
            raise BaselineError(
                f"mutation scope is ambiguous or not an exact path: {candidate}"
            )
        else:
            scope = Scope(candidate)
        if scope.path in scopes:
            raise BaselineError(f"mutation scope repeats source path: {scope.path}")
        scopes[scope.path] = scope
    if not scopes:
        raise BaselineError("mutation scope is empty")
    return scopes


def _position(value: Any, source: str, index: int, name: str) -> tuple[int, int]:
    if not isinstance(value, dict):
        raise BaselineError(f"file {source!r} mutant {index} has no {name} location")
    line = value.get("line")
    column = value.get("column")
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        raise BaselineError(f"file {source!r} mutant {index} has invalid {name} line")
    if not isinstance(column, int) or isinstance(column, bool) or column < 0:
        raise BaselineError(f"file {source!r} mutant {index} has invalid {name} column")
    return line, column


def filter_baseline(path: Path, scopes: dict[str, Scope]) -> int:
    if not path.exists():
        print(f"No incremental baseline at {path}; Stryker will run the scope cold.")
        return 0
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BaselineError(
            f"cannot read valid JSON baseline {path}: {error}"
        ) from error
    if not isinstance(report, dict) or not isinstance(report.get("files"), dict):
        raise BaselineError(f"baseline {path} field 'files' must be an object")

    retained_files: dict[str, dict[str, Any]] = {}
    for source, file_report in report["files"].items():
        if (
            not isinstance(source, str)
            or not source
            or not isinstance(file_report, dict)
        ):
            raise BaselineError("baseline contains an invalid file entry")
        mutants = file_report.get("mutants")
        if not isinstance(mutants, list):
            raise BaselineError(
                f"baseline file {source!r} field 'mutants' must be a list"
            )
        scope = scopes.get(source)
        if scope is None:
            continue

        retained_mutants: list[dict[str, Any]] = []
        for index, mutant in enumerate(mutants):
            if not isinstance(mutant, dict):
                raise BaselineError(f"file {source!r} mutant {index} must be an object")
            location = mutant.get("location")
            if not isinstance(location, dict):
                raise BaselineError(f"file {source!r} mutant {index} has no location")
            start = _position(location.get("start"), source, index, "start")
            end = _position(location.get("end"), source, index, "end")
            if end < start:
                raise BaselineError(
                    f"file {source!r} mutant {index} has an inverted location"
                )
            if scope.contains(start, end):
                retained_mutants.append(mutant)

        retained_files[source] = {**file_report, "mutants": retained_mutants}

    report["files"] = retained_files
    path.write_text(json.dumps(report, separators=(",", ":")), encoding="utf-8")
    print(
        f"Filtered incremental baseline {path} to {len(retained_files)} source file(s)."
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mutate", required=True, help="exact Stryker mutation paths/ranges"
    )
    parser.add_argument("baseline", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return filter_baseline(args.baseline, parse_scope(args.mutate))
    except BaselineError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
