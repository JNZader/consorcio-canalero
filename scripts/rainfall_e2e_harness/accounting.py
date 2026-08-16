"""Fail-closed exact accounting (W9, RMEH-009).

The runner performs two machine-readable gates before and after the browser
journey (design §Fail-Closed Test Accounting):

  1. **Collection gate** — run Playwright collection with JSON output BEFORE
     browser execution; require EXACTLY 11 discovered tests. Zero, ten, twelve,
     omitted file, ``.only``, and collection errors fail as
     ``HARNESS_ACCOUNTING_FAILURE`` (RMEH-009-C).
  2. **Result gate** — parse the JSON reporter and interaction evidence after
     execution; require 11 expected passes, zero unexpected failures, zero
     skipped/interrupted tests, zero flaky or Playwright-retried tests, helper
     retry count ``0``, exactly eight intended selection records, attempt count
     ``1`` and click count ``1`` in each, and the expected project/file identity
     (RMEH-009-D).

A run with zero discovered tests, any skipped test, any soft skip, or an empty
selected suite MUST fail and MUST NOT be reported as green. The zero-skip gate
makes any residual soft skip red (RMEH-009-B); the runner never translates a
missing prerequisite into a test annotation.

All functions are PURE (no subprocess, no filesystem) so the collection/result
parsers and gates are unit-testable with the recording adapter, matching the
safety/bootstrap layers. The runner driver shells out to Playwright and feeds
the captured stdout/JSON here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from scripts.rainfall_e2e_harness.safety import FailureClass


class HarnessAccountingFailure(Exception):
    """Collection or result accounting gate failed — ``HARNESS_ACCOUNTING_FAILURE``
    (RMEH-009-C/D, design §Fail-Closed Test Accounting)."""


EXPECTED_TEST_COUNT = 11
EXPECTED_SELECTION_RECORDS = 8
EXPECTED_SPEC_FILE = "rainfall-v2-detail.spec.ts"
EXPECTED_PROJECT = "rainfall-harness"


# --------------------------------------------------------------------------- #
# Collection gate (RMEH-009-C)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CollectionVerdict:
    """Outcome of the discovery gate: how many tests were discovered and whether
    the exact-cardinality contract held."""

    discovered: int
    ok: bool
    diagnostics: str


def _flatten_specs(suites: list[Mapping[str, Any]], acc: list[Mapping[str, Any]]) -> None:
    """Recursively flatten Playwright's nested ``suites`` into a flat list of
    ``specs`` (each spec == one discovered test)."""
    for suite in suites:
        for spec in suite.get("specs", []) or []:
            acc.append(spec)
        _flatten_specs(suite.get("suites", []) or [], acc)


def parse_collection_json(text: str) -> list[Mapping[str, Any]]:
    """Parse ``playwright test --list --reporter=json`` output into a flat list
    of spec dicts. Collection errors are surfaced as ``errors`` by Playwright;
    a collection error is itself an accounting failure (RMEH-009-C)."""
    data = json.loads(text)
    errors = data.get("errors", []) or []
    if errors:
        raise HarnessAccountingFailure(
            f"collection error: no harness tests discovered ({len(errors)} collection error(s))"
        )
    specs: list[Mapping[str, Any]] = []
    _flatten_specs(data.get("suites", []) or [], specs)
    return specs


def collection_spec_count(parsed: list[Mapping[str, Any]]) -> int:
    """Number of discovered tests from a flattened collection body."""
    return len(parsed)


def _spec_has_only(spec: Mapping[str, Any]) -> bool:
    """True when a spec carries a Playwright ``only`` annotation — a ``.only``
    would silently drop discovery below the expected cardinality (the config
    ``forbidOnly`` also refuses it; this is the runner's independent check)."""
    for annotation in spec.get("annotations", []) or []:
        if isinstance(annotation, Mapping) and annotation.get("type") == "only":
            return True
    return False


def assert_collection_expected(
    parsed: list[Mapping[str, Any]],
    *,
    expected: int = EXPECTED_TEST_COUNT,
    expected_file: str = EXPECTED_SPEC_FILE,
) -> CollectionVerdict:
    """Require EXACTLY ``expected`` discovered tests from the harness config.
    Zero, wrong cardinality, an omitted/renamed file, a ``.only``, or a
    collection error fail as ``HARNESS_ACCOUNTING_FAILURE`` (RMEH-009-C)."""
    discovered = collection_spec_count(parsed)
    if discovered == 0:
        raise HarnessAccountingFailure(
            "no harness tests executed: discovered 0 tests; an empty selected "
            "suite must fail, never report green"
        )
    only_specs = [s for s in parsed if _spec_has_only(s)]
    if only_specs:
        titles = [s.get("title") for s in only_specs]
        raise HarnessAccountingFailure(
            f"collection gate failed: {len(only_specs)} test(s) marked .only "
            f"({titles!r}); .only drops discovery below the exact count"
        )
    wrong_file = [s for s in parsed if s.get("file") != expected_file]
    if wrong_file:
        files = sorted({s.get("file") for s in wrong_file})
        raise HarnessAccountingFailure(
            f"collection gate failed: expected every spec under {expected_file!r}, "
            f"observed specs from {files!r}"
        )
    if discovered != expected:
        raise HarnessAccountingFailure(
            f"collection gate failed: expected exactly {expected} discovered "
            f"tests, observed {discovered}"
        )
    return CollectionVerdict(discovered=discovered, ok=True, diagnostics="")


# --------------------------------------------------------------------------- #
# Result gate (RMEH-009-D) + zero-skip gate (RMEH-009-B)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ResultVerdict:
    """Outcome of the post-run accounting: exact pass/fail/skip/retry counts."""

    passed: int
    failed: int
    skipped: int
    interrupted: int
    flaky: int
    retried: int
    ok: bool
    diagnostics: str


def parse_results_json(text: str) -> dict[str, Any]:
    """Parse the Playwright JSON-reporter result body (the file the config
    redirects ``RMEH_PLAYWRIGHT_JSON`` to). Returns the raw structure; the
    summary is derived by ``result_summary`` so counts are robust to both the
    top-level ``stats`` object and the per-test ``results`` arrays."""
    return json.loads(text)


def _test_top_status(test: Mapping[str, Any]) -> str:
    return str(test.get("status") or "unknown")


def _test_retries(test: Mapping[str, Any]) -> int:
    results = test.get("results", []) or []
    return max((int(r.get("retry", 0)) for r in results), default=0)


def result_summary(results: dict[str, Any]) -> ResultVerdict:
    """Derive the accounting counts from a Playwright result body.

    ``stats.expected/unexpected/skipped/flaky`` give the headline numbers; a
    per-test pass additionally counts ``interrupted`` (a test whose top-level
    status is ``interrupted``) and ``retried`` (any test whose ``results`` array
    has a retry index > 0 — the harness config fixes Playwright retries to 0,
    so a retry is an accounting violation, not a rescue)."""
    stats = results.get("stats", {}) or {}
    tests = results.get("tests", []) or []
    passed = int(stats.get("expected", 0))
    failed = int(stats.get("unexpected", 0))
    skipped = int(stats.get("skipped", 0))
    flaky = int(stats.get("flaky", 0))
    interrupted = sum(1 for t in tests if _test_top_status(t) == "interrupted")
    retried = sum(1 for t in tests if _test_retries(t) > 0)
    return ResultVerdict(
        passed=passed,
        failed=failed,
        skipped=skipped,
        interrupted=interrupted,
        flaky=flaky,
        retried=retried,
        ok=False,
        diagnostics="",
    )


def assert_result_expected(
    results: dict[str, Any],
    *,
    expected: int = EXPECTED_TEST_COUNT,
    expected_project: str = EXPECTED_PROJECT,
) -> ResultVerdict:
    """Require exactly ``expected`` passed, 0 failed, 0 skipped, 0 interrupted,
    0 flaky, and 0 Playwright-retried (RMEH-009-D). Any deviation, including a
    residual soft skip, turns the run red (RMEH-009-B)."""
    v = result_summary(results)
    diagnostics = []
    # Order surfaces the most specific violation first: the zero-violation
    # checks (failed/skipped/interrupted/flaky/retried) precede the expected-pass
    # count so a single deviant test names its own class rather than a generic
    # short-pass message.
    if v.failed != 0:
        diagnostics.append(f"{v.failed} failed (expected 0)")
    if v.skipped != 0:
        diagnostics.append(
            f"{v.skipped} skipped (expected 0) — a missing prerequisite "
            "is never translated into a test annotation (RMEH-009-B)"
        )
    if v.interrupted != 0:
        diagnostics.append(f"{v.interrupted} interrupted (expected 0)")
    if v.flaky != 0:
        diagnostics.append(f"{v.flaky} flaky (expected 0)")
    if v.retried != 0:
        diagnostics.append(
            f"{v.retried} retried (expected 0 Playwright retries) — a retry "
            "would hide a helper failure behind a second attempt"
        )
    if v.passed != expected:
        diagnostics.append(f"{v.passed} passed (expected exactly {expected})")
    for test in results.get("tests", []) or []:
        project = test.get("projectName")
        if project is not None and project != expected_project:
            diagnostics.append(f"unexpected project {project!r} (expected {expected_project!r})")
            break
    if diagnostics:
        raise HarnessAccountingFailure("result gate failed: " + "; ".join(diagnostics))
    return ResultVerdict(
        passed=v.passed,
        failed=v.failed,
        skipped=v.skipped,
        interrupted=v.interrupted,
        flaky=v.flaky,
        retried=v.retried,
        ok=True,
        diagnostics="",
    )


# --------------------------------------------------------------------------- #
# Manifest contract (RMEH-005/009-D): 8 one-click selection records
# --------------------------------------------------------------------------- #
def assert_manifest_contract(
    records: list[Mapping[str, Any]],
    *,
    expected: int = EXPECTED_SELECTION_RECORDS,
) -> str:
    """Require exactly ``expected`` selection records (4 mobile + 4 desktop),
    each with attempt count ``1`` and click count ``1`` (design D9; the helper
    interaction policy locks clicks/attempts to 1 and retries to 0). Returns an
    empty diagnostics string on success; raises otherwise."""
    if len(records) != expected:
        raise HarnessAccountingFailure(
            f"manifest contract failed: expected exactly {expected} selection "
            f"records, observed {len(records)}"
        )
    for i, record in enumerate(records):
        attempt = int(record.get("attemptCount", 0))
        click = int(record.get("clickCount", 0))
        if attempt != 1:
            raise HarnessAccountingFailure(
                f"manifest contract failed: record {i} has attemptCount {attempt}, "
                "expected 1 (one helper attempt per selection)"
            )
        if click != 1:
            raise HarnessAccountingFailure(
                f"manifest contract failed: record {i} has clickCount {click}, "
                "expected 1 (exactly one plain click per selection)"
            )
    return ""


# --------------------------------------------------------------------------- #
# Failure classification (RMEH-009-A/D, design §Fail-Closed Test Accounting)
# --------------------------------------------------------------------------- #
def classify_run_failure(
    *,
    collection_ok: bool,
    result_ok: bool,
    pre_click_integrity_ok: bool,
    click_occurred: bool,
) -> FailureClass:
    """Map an accounting/browser failure to its EXCLUSIVE manifest class.

    A discovery/result/evidence contract failure is ``HARNESS_ACCOUNTING_FAILURE``.
    Otherwise, a browser failure is ``BROWSER_INTEGRITY_FAILURE`` when the
    pre-click camera/projection/occlusion/tile integrity gate failed or no real
    click occurred, and ``PRODUCT_ASSERTION_FAILURE`` only when all pre-click
    integrity passed AND the single real click happened but the subsequent
    request/identity/continuity/freshness/scroll/geometry/focus behavior failed
    (reuses the exclusive split in ``taxonomy.classify_request_failure``)."""
    if not collection_ok or not result_ok:
        return FailureClass.HARNESS_ACCOUNTING_FAILURE
    if not pre_click_integrity_ok:
        return FailureClass.BROWSER_INTEGRITY_FAILURE
    if not click_occurred:
        return FailureClass.BROWSER_INTEGRITY_FAILURE
    return FailureClass.PRODUCT_ASSERTION_FAILURE
