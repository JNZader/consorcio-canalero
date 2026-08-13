#!/usr/bin/env python3
"""Aggregate exactly two Stryker mutation reports into one fail-closed score."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


DETECTED = frozenset({"Killed", "Timeout"})
UNDETECTED = frozenset({"Survived", "NoCoverage"})
EXCLUDED = frozenset({"Ignored", "CompileError", "RuntimeError"})
KNOWN = DETECTED | UNDETECTED | EXCLUDED | {"Pending"}


class ReportError(ValueError):
    """Raised when a report is missing, incomplete, or outside the schema contract."""


def minimum_score(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError("minimum must be a decimal number") from error
    if not parsed.is_finite() or not Decimal("0") <= parsed <= Decimal("100"):
        raise argparse.ArgumentTypeError("minimum must be between 0 and 100")
    return parsed


def source_paths(values: list[str]) -> set[str]:
    provided = [source.strip() for value in values for source in value.split(",")]
    if not provided or any(not source for source in provided):
        raise ReportError("at least one expected source file path is required")
    duplicates = sorted(
        source for source, count in Counter(provided).items() if count > 1
    )
    if duplicates:
        raise ReportError(
            f"duplicate expected source file paths: {', '.join(duplicates)}"
        )
    return set(provided)


def load_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReportError(f"cannot read valid JSON report {path}: {error}") from error
    if not isinstance(report, dict):
        raise ReportError(f"report {path} must be a JSON object")
    files = report.get("files")
    if not isinstance(files, dict):
        raise ReportError(f"report {path} field 'files' must be an object")
    return files


def count_report(path: Path, seen_files: set[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    files = load_report(path)
    if not files:
        raise ReportError(f"report {path} contains no source files")
    duplicates = sorted(seen_files.intersection(files))
    if duplicates:
        raise ReportError(
            f"duplicate source file paths across reports: {', '.join(duplicates)}"
        )
    seen_files.update(files)

    for source, file_report in files.items():
        if not isinstance(source, str) or not isinstance(file_report, dict):
            raise ReportError(f"report {path} contains an invalid file entry")
        mutants = file_report.get("mutants")
        if not isinstance(mutants, list):
            raise ReportError(
                f"report {path} file {source!r} field 'mutants' must be a list"
            )
        for index, mutant in enumerate(mutants):
            if not isinstance(mutant, dict):
                raise ReportError(
                    f"report {path} file {source!r} mutant {index} must be an object"
                )
            status = mutant.get("status")
            if not isinstance(status, str) or not status:
                raise ReportError(
                    f"report {path} file {source!r} mutant {index} has no status"
                )
            if status not in KNOWN:
                raise ReportError(f"report {path} has unknown mutant status {status!r}")
            if status == "Pending":
                raise ReportError(f"report {path} contains Pending mutants")
            counts[status] += 1
    if not counts:
        raise ReportError(f"report {path} contains no mutants")
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimum", required=True, type=minimum_score)
    parser.add_argument(
        "--expected-source",
        action="append",
        required=True,
        help="expected report source path; repeat or pass comma-separated paths",
    )
    parser.add_argument("reports", nargs=2, type=Path, metavar="REPORT")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        expected_files = source_paths(args.expected_source)
        counts: Counter[str] = Counter()
        seen_files: set[str] = set()
        for report in args.reports:
            counts.update(count_report(report, seen_files))
        missing = sorted(expected_files - seen_files)
        unexpected = sorted(seen_files - expected_files)
        if missing or unexpected:
            details = []
            if missing:
                details.append(f"missing source file paths: {', '.join(missing)}")
            if unexpected:
                details.append(f"unexpected source file paths: {', '.join(unexpected)}")
            raise ReportError("; ".join(details))
    except ReportError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    detected = sum(counts[status] for status in DETECTED)
    undetected = sum(counts[status] for status in UNDETECTED)
    excluded = sum(counts[status] for status in EXCLUDED)
    valid = detected + undetected
    if valid == 0:
        print("error: aggregate contains zero valid mutants", file=sys.stderr)
        return 2

    score = Decimal(detected) * Decimal("100") / Decimal(valid)
    print(
        f"detected={detected} undetected={undetected} valid={valid} "
        f"excluded={excluded} score={score:.2f}% minimum={args.minimum:.2f}%"
    )
    if score < args.minimum:
        print(
            f"error: aggregate mutation score {score:.2f}% is below {args.minimum:.2f}%",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
