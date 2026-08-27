#!/usr/bin/env python3
"""Aggregate four or more Stryker reports into one fail-closed score."""

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


def source_paths(values: list[str], option: str) -> set[str]:
    provided = [source.strip() for value in values for source in value.split(",")]
    if not provided or any(not source for source in provided):
        raise ReportError(f"at least one {option} path is required")
    duplicates = sorted(
        source for source, count in Counter(provided).items() if count > 1
    )
    if duplicates:
        raise ReportError(f"duplicate {option} paths: {', '.join(duplicates)}")
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
    if not files:
        raise ReportError(f"report {path} contains no source files")
    return files


def _position(
    value: Any, path: Path, source: str, index: int, name: str
) -> tuple[int, int]:
    if not isinstance(value, dict):
        raise ReportError(
            f"report {path} file {source!r} mutant {index} has no {name} location"
        )
    line = value.get("line")
    column = value.get("column")
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        raise ReportError(
            f"report {path} file {source!r} mutant {index} has invalid {name} line"
        )
    if not isinstance(column, int) or isinstance(column, bool) or column < 0:
        raise ReportError(
            f"report {path} file {source!r} mutant {index} has invalid {name} column"
        )
    return line, column


def mutant_identity(
    mutant: dict[str, Any], path: Path, source: str, index: int
) -> tuple[object, ...]:
    mutator = mutant.get("mutatorName")
    replacement = mutant.get("replacement")
    location = mutant.get("location")
    if not isinstance(mutator, str) or not mutator:
        raise ReportError(
            f"report {path} file {source!r} mutant {index} has no mutator name"
        )
    if not isinstance(replacement, str):
        raise ReportError(
            f"report {path} file {source!r} mutant {index} has no replacement"
        )
    if not isinstance(location, dict):
        raise ReportError(
            f"report {path} file {source!r} mutant {index} has no location"
        )
    start = _position(location.get("start"), path, source, index, "start")
    end = _position(location.get("end"), path, source, index, "end")
    if end < start:
        raise ReportError(
            f"report {path} file {source!r} mutant {index} has an inverted location"
        )
    return source, start, end, mutator, replacement


def _validate_coverage(
    mutant: dict[str, Any], path: Path, source: str, index: int
) -> None:
    for field in ("coveredBy", "killedBy"):
        value = mutant.get(field)
        if value is not None and (
            not isinstance(value, list)
            or any(not isinstance(test, str) for test in value)
        ):
            raise ReportError(
                f"report {path} file {source!r} mutant {index} has invalid {field} metadata"
            )
    completed = mutant.get("testsCompleted")
    if completed is not None and (
        not isinstance(completed, int) or isinstance(completed, bool) or completed < 0
    ):
        raise ReportError(
            f"report {path} file {source!r} mutant {index} has invalid testsCompleted metadata"
        )
    static = mutant.get("static")
    if static is not None and not isinstance(static, bool):
        raise ReportError(
            f"report {path} file {source!r} mutant {index} has invalid static metadata"
        )


def merge_reports(
    reports: list[Path], expected_files: set[str], ranged_files: set[str]
) -> dict[str, list[dict[str, Any]]]:
    if len(reports) < 4:
        raise ReportError("at least four shard reports are required")

    merged_files: dict[str, dict[str, Any]] = {}
    identities: dict[tuple[object, ...], str] = {}
    merged_mutants: dict[str, list[tuple[tuple[object, ...], dict[str, Any]]]] = {}

    for path in reports:
        files = load_report(path)
        report_mutants = 0
        for source, file_report in files.items():
            if (
                not isinstance(source, str)
                or not source
                or not isinstance(file_report, dict)
            ):
                raise ReportError(f"report {path} contains an invalid file entry")
            mutants = file_report.get("mutants")
            if not isinstance(mutants, list):
                raise ReportError(
                    f"report {path} file {source!r} field 'mutants' must be a list"
                )
            language = file_report.get("language")
            source_text = file_report.get("source")
            if not isinstance(language, str) or not isinstance(source_text, str):
                raise ReportError(
                    f"report {path} file {source!r} has invalid file metadata"
                )

            prior = merged_files.get(source)
            if prior is not None and source not in ranged_files:
                raise ReportError(
                    f"duplicate non-ranged source path across reports: {source}"
                )
            if prior is None:
                merged_files[source] = {
                    "language": language,
                    "source": source_text,
                }
            elif prior["language"] != language or prior["source"] != source_text:
                raise ReportError(
                    f"conflicting file metadata across reports for source path: {source}"
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
                    raise ReportError(
                        f"report {path} has unknown mutant status {status!r}"
                    )
                if status == "Pending":
                    raise ReportError(f"report {path} contains Pending mutants")
                identity = mutant_identity(mutant, path, source, index)
                _validate_coverage(mutant, path, source, index)
                previous_status = identities.get(identity)
                if previous_status is not None:
                    if previous_status != status:
                        raise ReportError(
                            f"conflicting status for overlapping mutant identity in {source}"
                        )
                    raise ReportError(
                        f"overlapping mutant identity across reports in {source}"
                    )
                identities[identity] = status
                merged_mutants.setdefault(source, []).append((identity, mutant))
                report_mutants += 1
        if report_mutants == 0:
            raise ReportError(f"report {path} contains no mutants")

    seen_files = set(merged_files)
    missing = sorted(expected_files - seen_files)
    unexpected = sorted(seen_files - expected_files)
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing source file paths: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected source file paths: {', '.join(unexpected)}")
        raise ReportError("; ".join(details))
    if not identities:
        raise ReportError("aggregate contains no mutants")

    # Preserve all mutant and coverage metadata in a deterministic source/location
    # order, independent of the order in which matrix jobs finish or upload reports.
    return {
        source: [mutant for _, mutant in sorted(mutants)]
        for source, mutants in sorted(merged_mutants.items())
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimum", required=True, type=minimum_score)
    parser.add_argument(
        "--expected-source",
        action="append",
        required=True,
        help="expected report source path; repeat or pass comma-separated paths",
    )
    parser.add_argument(
        "--ranged-source",
        action="append",
        default=[],
        help="source path allowed to appear in multiple reports when mutant identities are disjoint",
    )
    parser.add_argument("reports", nargs="+", type=Path, metavar="REPORT")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        expected_files = source_paths(args.expected_source, "expected source file")
        ranged_files = (
            source_paths(args.ranged_source, "ranged source file")
            if args.ranged_source
            else set()
        )
        unknown_ranged = sorted(ranged_files - expected_files)
        if unknown_ranged:
            raise ReportError(
                f"ranged source paths are not expected sources: {', '.join(unknown_ranged)}"
            )
        merged_mutants = merge_reports(args.reports, expected_files, ranged_files)
    except ReportError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    counts = Counter(
        mutant["status"]
        for source in sorted(merged_mutants)
        for mutant in merged_mutants[source]
    )
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
