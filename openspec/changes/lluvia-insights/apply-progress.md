# Apply Progress: Lluvia Insights — Rainfall v2 Product Layer

## Slice 1: Historical Baseline Backfill (D1, D2) — COMPLETE (17/17 tasks)

**Branch**: `feat/lluvia-insights-01-baseline` (base: `feat/lluvia-insights`, tracker for `main`)
**Mode**: Strict TDD (RED → GREEN → REFACTOR), enforced via git-stash isolation per cycle (see Baseline section).

### Baseline (before slice-1 changes, same branch, source at tracker HEAD)

```
pytest tests/new/geo/rainfall/ tests/test_mutation_targets_rainfall.py -q
=> 350 passed, 0 failed, 1 warning (pre-existing SAWarning, unrelated)
```

### Final (after slice-1 changes)

```
pytest tests/new/geo/rainfall/ tests/test_mutation_targets_rainfall.py -q
=> 365 passed, 0 failed, 1 warning (same pre-existing warning)
   (350 baseline + 15 new tests, 0 regressions)

pytest tests/new/ -q   (full backend regression, all domains)
=> 1931 passed, 5 skipped (pre-existing, live-backend/Martin-only skips), 0 failed
   — re-run after ruff format: 1931 passed, 5 skipped, 0 failed (unchanged)
```

`ruff check` and `ruff format --check` both clean on every changed/created file.

### TDD Cycle Evidence

| Task | Test | RED evidence | GREEN evidence |
|---|---|---|---|
| 1.1/1.2 | `test_provider_asset_scope_key_persists_and_reads_back` | `ImportError: cannot import name 'BASELINE_ASSET_VERSION'` against original code | passes after `gee_client.py::asset_name_for` gains the `provider_asset` branch + `BASELINE_ASSET_VERSION` export |
| 1.3/1.4 | `test_baseline_cumulatives_returns_per_year_totals` (+ `test_baseline_cumulatives_omits_years_with_no_persisted_rows`) | `ImportError: cannot import name 'baseline_cumulatives'` | passes after `repository.py::baseline_cumulatives` (SQL `GROUP BY` aggregate, anti-joined on supersession) |
| 1.5/1.6 | `test_zoning_republication_does_not_orphan_baseline` | same ImportError chain (depends on 1.2/1.4) | passes with **no additional code** beyond 1.2/1.4 — confirms the asset key structurally excludes `scope_version` (task 1.6's own "assert-only" framing) |
| 1.7/1.8 | `test_unmapped_basin_raises_unknown_provider_scope` | passes even against original code (pre-existing `asset_name_for` basin-rejection, same "assert-only, already-true" shape as 1.5/1.6) — see Deviations | N/A (regression pin, not a new-behavior proof) |
| 1.7/1.8 (added) | `test_persist_analysis_revision_suppresses_baseline_for_unmapped_basin` | passes even against original code too (no baseline resolution existed pre-1.8, so nothing could crash) — see Deviations | proves the unmapped-basin path is *still* non-crashing post-wiring |
| 1.7/1.8 (added, load-bearing) | `test_persist_analysis_revision_resolves_mapped_baseline_and_passes_it_through` | `ImportError: cannot import name 'BASELINE_ASSET_VERSION'` against original code (genuinely RED) | passes after 1.8's wiring — proves `build_snapshot` receives the REAL `baseline_cumulatives` dict for a mapped scope, not just `None` |
| 1.9/1.10 | `test_backfill_dedupes_shared_asset_one_fetch_per_year` | `AttributeError: module 'tasks' has no attribute 'backfill_baseline_range'` | passes after `tasks.py::backfill_baseline_range` |
| 1.11/1.12 | `test_backfill_resumes_after_interruption_no_refetch` | same AttributeError | passes with **no additional code** beyond 1.10 — `backfill_missing`'s own `already_complete` checkpoint short-circuit (task 1.12's "assert-only" framing) |
| 1.13/1.15 | `test_backfill_stops_labelled_on_circuit_open` | same AttributeError | passes after the `except (AdapterError, CircuitOpen)` wrap in `backfill_baseline_range` |
| 1.14/1.15 | `test_backfill_stops_labelled_on_adapter_error` | same AttributeError | passes after the same except clause |
| 1.16 | `test_backfill_cli_main_delegates_to_backfill_baseline_range`, `test_backfill_cli_main_reports_a_labelled_stop_as_nonzero_exit`, `test_backfill_cli_help_documents_the_recovery_window_wait_out_rule` | `ImportError: cannot import name 'backfill_cli'` | pass after `backfill_cli.py` created |
| boundary (added) | `test_backfill_baseline_range_with_empty_years_is_a_safe_no_op` | covered by the same "function didn't exist" RED batch as 1.9-1.15 | passes: empty `years` makes zero provider calls, returns a clean non-stopped empty completion |

**RED verification method**: for every task-file pair, the SOURCE changes (`gee_client.py`, `compute.py`, `ports.py`, `repository.py`, `tasks.py`, `backfill_cli.py`) were `git stash push -u`'d while the NEW test files stayed in the working tree, `pytest` was run against the untouched code to capture the failure (`ImportError`/`AttributeError`, recorded above), then `git stash pop` restored the implementation and the full suite was re-run to confirm GREEN. This is the literal artifact of the git-native TDD-evidence protocol this repo already uses for slices with this rigor.

### Files Changed

| File | Action | What |
|---|---|---|
| `gee-backend/app/domains/geo/rainfall/adapters/gee_client.py` | Modified | `asset_name_for` gains the `scope_kind == "provider_asset"` passthrough branch; `BASELINE_ASSET_VERSION = "v1"` exported (task 1.2) |
| `gee-backend/app/domains/geo/rainfall/repository.py` | Modified | `baseline_cumulatives(db, *, source_id, asset, dates)` — one SQL `GROUP BY` aggregate over a union of per-year windows, anti-joined on supersession exactly like `intervals_in_window` (task 1.4) |
| `gee-backend/app/domains/geo/rainfall/compute.py` | Modified | `build_snapshot` gains an accepted-but-unused `baseline: dict[int, tuple[float,int,int]] \| None = None` keyword (consumed starting slice 2a) |
| `gee-backend/app/domains/geo/rainfall/tasks.py` | Modified | `RAINFALL_BACKFILL_PACE_SECONDS = 5`; `_persist_analysis_revision` resolves the scope's baseline (`asset_name_for` + `repository.baseline_cumulatives`, catching `UnknownProviderScope` → `baseline=None`) and reuses one pre-computed `comparison_end_date` instead of re-deriving it from the snapshot; new `backfill_baseline_range(asset, *, years, source_id, role)` orchestrator (task 1.10/1.15) |
| `gee-backend/app/domains/geo/rainfall/ports.py` | Modified (deviation, see below) | `SourceBatch.scope_kind` and `RainfallSourceAdapter.scope_kind` widened from `Literal["zone","basin"]` to include `"provider_asset"` |
| `gee-backend/app/domains/geo/rainfall/backfill_cli.py` | Created | One-shot `__main__` runner (task 1.16) |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_baseline.py` | Created | Tasks 1.1, 1.3, 1.5, 1.7 + two extra 1.8-wiring tests (see Deviations) |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_backfill.py` | Created | Tasks 1.9, 1.11, 1.13, 1.14 + CLI tests (task 1.16) + one boundary test |
| `openspec/changes/lluvia-insights/tasks.md` | Modified | Slice 1 (1.1-1.17) marked `[x]`, with inline deviation notes on 1.8 and 1.13 |

### Deviations from Design/Tasks

1. **`ports.py::SourceBatch.scope_kind` widened to include `"provider_asset"` (file:line `gee-backend/app/domains/geo/rainfall/ports.py:49-53`, pre-change).** Not named in tasks.md 1.1-1.17. Design D1/D2 requires the backfill write path (`ingest_source_scope` → `ChirpsV3Adapter.fetch` → `build_zonal_batch` → `SourceBatch(...)`) to run under `scope_kind="provider_asset"` for `persist_intervals` to land the fixed baseline key. `SourceBatch.__post_init__` validated `scope_kind in {"zone", "basin"}` only — a real backfill run would have raised `ValueError("source batch scope kind is not supported")` on its very first year, before any GEE call. Widened the `Literal` and the validation set (and the `RainfallSourceAdapter` Protocol's type hint, for consistency) to `{"zone", "basin", "provider_asset"}`. No existing test pinned the narrower set (verified by search); full regression (1931/1931 `tests/new/`) confirms no breakage. This was necessary for the ops runbook's real `backfill_cli.py` run to work at all, not optional polish.

2. **Task 1.7's literal RED test (`test_unmapped_basin_raises_unknown_provider_scope`) is "assert-only" in the same sense tasks 1.6/1.12 already are** — it re-confirms `asset_name_for`'s pre-existing basin-rejection (from the merged rainfall-materialization change), which was already true before any slice-1 code. Kept it as a regression pin per its literal task description, and added two further tests that ARE genuinely RED-provable against the wiring 1.8 actually adds: `test_persist_analysis_revision_suppresses_baseline_for_unmapped_basin` (proves the unmapped path still doesn't crash post-wiring — though this one ALSO happened to already pass pre-1.8, since nothing attempted resolution yet) and, load-bearingly, `test_persist_analysis_revision_resolves_mapped_baseline_and_passes_it_through` (genuinely `ImportError`-RED pre-1.8, GREEN after — proves the MAPPED-scope happy path, which 1.8's literal text does not name a test for at all).

3. **Task 1.9's "30 total" language interpreted as structural, not literal-30-in-test.** The RED test uses a 2-year range (`[1991, 1992]`) to keep the suite fast; the "not per scope" claim is proven by calling `backfill_baseline_range` twice (once per zone scope id) against the SAME resolved asset and asserting the call count equals `len(years)`, not `2 * len(years)`. The literal 30-year, 1991-2020 range is exercised only by `Ops.1-3` (real runbook, explicitly out of this agent's scope per the hard safety rule).

4. **Task 1.13's `FakeGeeClient` framing replaced with a drop-in fake `CircuitStore`.** `ingest_source_scope` hardcodes `RedisCircuitStore(settings.redis_url)` with no injection seam reachable from a `FakeGeeClient` at the adapter level, and this sandbox's `REDIS_URL` for tests (`redis://localhost:6379/1`, `tests/new/conftest.py:98`) resolves to a *different* project's authenticated Redis instance, not this repo's own (`consorcio-redis` on port 16379) — a real-Redis pre-open would silently degrade to a no-op circuit (`RedisCircuitStore.read`/`write` catch all exceptions and fall back to a fresh in-memory default) rather than actually open. Instead, `resilience.RedisCircuitStore` is monkeypatched (the same class-substitution seam `test_resilience.py::test_redis_circuit_store_degrades_when_redis_is_down` already uses) to a fake `CircuitStore` whose `read()` returns an already-OPEN `ResilientAdapterState` for any role. `ResilientAdapterState.can_attempt()` raises `CircuitOpen` *before* `ResilientAdapter.fetch`'s retry loop ever calls `_inner_fetch` (`resilience.py:262`, confirmed by reading the source), so the real `ChirpsV3Adapter`/`ee` path is provably never reached — the hard safety rule (no real GEE calls) holds exactly as it would with a `FakeGeeClient`, just at one seam lower.

5. **Celery `retry()`-on-direct-call semantics verified against vendored source, not just trusted from the review ledger.** `venv/lib/python3.14/site-packages/celery/app/task.py:750` confirms `if request.called_directly: raise_with_context(exc or Retry(...))` — a directly-called task's `self.retry(exc=exc, ...)` re-raises the *original* exception (here, `AdapterError`) rather than Celery's `Retry` wrapper. This is what lets `backfill_baseline_range`'s `except (AdapterError, CircuitOpen)` catch a simulated `AdapterError` at all in `test_backfill_stops_labelled_on_adapter_error` (which calls `ingest_source_scope` synchronously, never through a worker).

6. **`_persist_analysis_revision` restructured to compute `comparison_end_date` once, before `build_snapshot`, and reuse it afterward** (`tasks.py`, was `date.fromisoformat(snapshot["comparison_end"])` post-hoc). Necessary because the baseline resolution (which must happen before `build_snapshot` so its result can be passed in) needs `comparison_end_date` for `temporal.baseline_dates(...)`. Verified the two computations are provably identical (`temporal.comparison_end(row.year, temporal.buenos_aires_date(now))` — same `year`/`now` inputs `build_snapshot` uses internally at `compute.py:108`), so this is a behavior-preserving refactor, not a new decision. Confirmed by the full regression run (0 change in any existing snapshot-shape assertion).

### Author Counterexample Self-Check

| Category | Evidence | Result |
|---|---|---|
| Null / absence | `test_baseline_cumulatives_omits_years_with_no_persisted_rows` (empty result dict, never a fabricated zero); `baseline=None` path for unmapped scopes (`test_unmapped_basin_raises_unknown_provider_scope` + the unmapped-basin wiring test) | Pass |
| Boundaries | `test_baseline_cumulatives_returns_per_year_totals` pins exact day-count arithmetic across a leap year (1992) and non-leap years (1991/1993); `test_backfill_baseline_range_with_empty_years_is_a_safe_no_op` (empty `years` iterable) | Pass |
| Concurrency / idempotency | `test_backfill_resumes_after_interruption_no_refetch` (checkpoint-based rerun makes zero duplicate provider calls for already-completed years); `test_backfill_dedupes_shared_asset_one_fetch_per_year` (two callers resolving the same asset never double-fetch a year) | Pass |
| Malicious input / security | N/A — `backfill_baseline_range`/`backfill_cli.py` are operator-run, server-side-only surfaces (no new HTTP route, no new user-facing input); `asset`/`years` come from an operator's CLI invocation, not untrusted request input | N/A (reason given) |
| Partial failure / recovery | `test_backfill_stops_labelled_on_circuit_open` and `test_backfill_stops_labelled_on_adapter_error` — both prove a labelled, non-raising stop with zero completed years and (for circuit_open) zero provider calls; matches the runbook's ~300s recovery-window wait-out contract documented in `backfill_cli.py`'s `--help` | Pass |
| State / tenancy / time | `test_zoning_republication_does_not_orphan_baseline` (a zone's own `scope_version` bump cannot orphan the baseline read, since the key structurally excludes it) | Pass |

### Workload / PR Boundary

- Mode: chained PR slice (`feature-branch-chain`, per tasks.md's Review Workload Forecast)
- Current work unit: Unit 1 — "Provider-asset baseline key (D1) + backfill orchestrator/CLI, `(AdapterError, CircuitOpen)` stop (D2)"
- Boundary: starts at the tracker branch (`feat/lluvia-insights`, SDD artifacts only), ends at this commit — slice 1 is a complete, independently mergeable, independently verifiable unit (365/365 rainfall+mutation tests, 1931/1931 full backend regression)
- Estimated review budget impact: ~380 production lines forecast (tasks.md); actual diff is source (`gee_client.py`, `compute.py`, `ports.py`, `repository.py`, `tasks.py`, `backfill_cli.py`) + 2 new test files — within the forecast slice budget

### Remaining Tasks (out of this batch's scope)

- [ ] Slice 2a: Metric Core — Normal, Percentile, Antecedents, Thresholds (2a.1-2a.15)
- [ ] Slice 2b: Summary Mechanism, Revision Bump, Cross-Source Caveat, Stale Requeue (2b.1-2b.12)
- [ ] Slice 3a: Series Module — Consistency Pin + `data_revision` Exposure (3a.1-3a.14)
- [ ] Slice 3b: xlsx Export + TS Contract + Consistency Exposure (3b.1-3b.11)
- [ ] Slice 4: Frontend Chart (4.1-4.10)
- [ ] Ops.1-3: real 1991-2020 backfill runbook execution (owner-run, explicitly NOT this agent's scope) — precondition: enable the `historical` role feature flag, then merge this slice
- [ ] Ops.4-6: doc-nit folds

### Status

17/17 slice-1 tasks complete (365/365 targeted tests pass, 1931/1931 full backend regression pass, ruff clean). Ready for review/PR of this work unit, then `sdd-apply` for slice 2a (or `sdd-verify` if the orchestrator wants a checkpoint first).

## Slice 1 review fix pass (2026-08-10)

Fixes 4 findings from `review-ledger.md`'s "Pre-PR review — slice 1 baseline" (review-reliability, standard tier): LI1-001 (CRITICAL), LI1-002/003/004 (WARNING/SUGGESTION, folded). Branch: `feat/lluvia-insights-01-baseline` (same slice-1 branch). Strict TDD: RED captured for every genuine RED (LI1-001, LI1-002, LI1-004); LI1-003 is a test-hygiene fix with no behavior change, so no RED exists for it.

### TDD Cycle Evidence

| Finding | Test | RED evidence | GREEN evidence |
|---|---|---|---|
| LI1-001 | `test_backfill_dedupes_shared_asset_one_fetch_per_year`, `test_backfill_resumes_after_interruption_no_refetch`, `test_backfill_stops_labelled_on_circuit_open`, `test_backfill_stops_labelled_on_adapter_error` | Standalone `pytest tests/new/geo/rainfall/test_rainfall_backfill.py -v` → 4 failed / 4 passed, `UndefinedTable: relation "rainfall_backfill_checkpoint" does not exist` (reproduced twice) | Added `db` fixture param ×4 (comment style matches `test_rainfall_materialization.py:461-464`). Surfaced an adjacent pre-existing landmine (see Deviations) fixed at `tests/new/conftest.py`. Final: 9/9 (8 + LI1-004's new test) standalone green |
| LI1-002 | `test_baseline_cumulatives_returns_per_year_totals` | Added a `1991-01-01T00:00Z` boundary row + `db.execute(text("SET TIME ZONE 'America/Argentina/Buenos_Aires'"))` before the call, run against unfixed `repository.py` → `KeyError: 1990` | `repository.py:293`: `year_expr` wraps `interval_start` in `.op("AT TIME ZONE")("UTC")`; verified emitted SQL via standalone compile probe (`date_part('year', ... AT TIME ZONE 'UTC')`); same test green after the fix |
| LI1-003 | `test_backfill_stops_labelled_on_adapter_error` | No genuine RED — behavior unchanged, this closes a real-Redis-write test-hygiene gap | Monkeypatches `resilience.RedisCircuitStore` to `_FakeCircuitStore(MemoryCircuitStore)` (fresh non-shared `_memory={}`, same call-time-import seam as its `circuit_open` sibling); still green, no Redis touched |
| LI1-004 | `test_backfill_cli_main_rejects_inverted_year_range` (new) | Against unfixed `backfill_cli.py` → `AttributeError: ... has no attribute 'EXIT_INVALID_RANGE'`, captured stdout showed the actual bug: `completed years: []`, exit 0 | `backfill_cli.py`: `EXIT_INVALID_RANGE = 2` + `main()` guard rejecting `start_year > end_year` with a stderr message before calling `backfill_baseline_range`; new test green |

### Files Changed (fix pass)

| File | Action | What |
|---|---|---|
| `gee-backend/app/domains/geo/rainfall/repository.py` | Modified | LI1-002: `baseline_cumulatives`'s `year_expr` pinned to `AT TIME ZONE 'UTC'` before `date_part` |
| `gee-backend/app/domains/geo/rainfall/backfill_cli.py` | Modified | LI1-004: `EXIT_INVALID_RANGE` constant + inverted-range guard in `main()` |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_backfill.py` | Modified | LI1-001: `db` fixture param ×4; LI1-003: `_FakeCircuitStore` substitution in the adapter_error test; LI1-004: new `test_backfill_cli_main_rejects_inverted_year_range` |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_baseline.py` | Modified | LI1-002: boundary row + non-UTC `SET TIME ZONE` demonstration in `test_baseline_cumulatives_returns_per_year_totals` |
| `gee-backend/tests/new/conftest.py` | Modified | Necessary adjacent fix (see Deviations): added `app.domains.geo.intelligence.models` to the eager-import block |
| `openspec/changes/lluvia-insights/review-ledger.md` | Modified | LI1-001 → fixed; LI1-002/003/004 → Addressed; fix-pass resolutions table added |

### Deviations (fix pass)

1. **`tests/new/conftest.py` eager-import list gained `app.domains.geo.intelligence.models` — not one of the 4 assigned findings, but load-bearing for LI1-001's own proof requirement.** Adding the `db` fixture param to the 4 tests (LI1-001's literal fix) makes `test_engine`'s session-scoped `create_all()` fire at the file's *second* test — but its *first* test (still `db`-free, runs first in file order) imports `tasks` → `repository` → `app.domains.geo.models` in its own body, registering `FloodLabel`'s FK to `zonas_operativas` (a table defined only in `app.domains.geo.intelligence.models`, never imported by this chain). `Base.metadata.create_all()`'s dependency sort then raised `NoReferencedTableError`, deterministically (testcontainers gives a fresh, empty container per session — confirmed not state leakage by 2 identical repro runs). This is a pre-existing crack in conftest's own documented eager-import mechanism (its comment already exists to prevent exactly this bug class for `EmailCode`), just never tripped before because no rainfall-backfill test file previously requested `db` standalone. Fixed at the root: one import line in `conftest.py`, matching the established pattern and its own stated rationale — not a per-test workaround. Verified against the full `tests/new/` suite (1933/1933 passed, no regressions) to confirm this doesn't collide with anything importing `intelligence.models` elsewhere.
2. **LI1-003 has no RED** (documented above) — included per the fix brief's literal instruction ("the adapter_error test substitutes MemoryCircuitStore exactly like its circuit_open sibling") even though it is a test-hygiene fix, not a behavior fix.

### Author Counterexample Self-Check (fix pass)

| Category | Evidence or N/A reason | Result |
|---|---|---|
| Null / absence | LI1-002's `expected_days_by_year[int(year)]` lookup is exactly the null/missing-key path the bug hit (`KeyError` on a year absent from the dict) — now unreachable since the group key can never diverge from the Python-side year | Pass |
| Boundaries | LI1-002 is itself a year-boundary (`1991-01-01T00:00Z`, exact midnight) probe; LI1-004 is itself a boundary probe (`start_year == end_year` still allowed — only `>` rejected, verified by the existing CLI tests still passing with equal/ascending ranges) | Pass |
| Concurrency / idempotency | LI1-003's fix specifically prevents cross-test circuit-state leakage (a concurrency/shared-state hazard) via a non-shared `_memory={}` dict instead of `MemoryCircuitStore`'s class-level `_shared` default | Pass |
| Malicious input / security | N/A — all 4 findings are backend test-infra/CLI-operator-input fixes; no new user-facing input surface | N/A (reason given) |
| Partial failure / recovery | LI1-004 guards a runbook misuse (inverted range) before any provider call is ever attempted — `called is False` asserted in the new test, so the fix fails fast before any partial work | Pass |
| State / tenancy / time | LI1-002 is exactly a time/TZ-state fix; verified the `SET TIME ZONE` scoping cannot leak into other tests (Postgres transactional `SET` semantics, confirmed via the full 260-test rainfall suite passing with no order-dependent failures) | Pass |

### Final Verification (fix pass)

```
pytest tests/new/geo/rainfall/test_rainfall_backfill.py -v   (standalone)
=> 9 passed (was 4 failed / 4 passed pre-fix)

pytest tests/new/geo/rainfall/ -v
=> 260 passed, 1 pre-existing unrelated warning (was 259 pre-fix-pass; +1 for LI1-004's new test)

pytest tests/new/ -q
=> 1933 passed, 5 skipped (pre-existing live-backend/Martin skips), 0 failed (was 1932 passed baseline; +1)

ruff check + ruff format --check on all 5 touched files: clean
```

### Status (fix pass)

4/4 findings addressed (1 fixed as CRITICAL, 3 addressed as folded WARNING/SUGGESTION). Ready for re-review or `sdd-verify`.

## Slice 2a: Metric Core — Normal, Percentile, Antecedents, Thresholds (D4 rows, D5, D6) — COMPLETE (15/15 tasks)

**Branch**: `feat/lluvia-insights-02a-metrics` (base: `feat/lluvia-insights-01-baseline`, tip `0ed4d70` verified present at branch time).
**Mode**: Strict TDD (RED → GREEN → REFACTOR), enforced via git-stash isolation per cycle (same protocol as slice 1).

### Baseline (before slice-2a changes, same branch, source at slice-1 tip)

```
pytest tests/new/geo/rainfall/ tests/test_mutation_targets_rainfall.py -q
=> 366 passed, 0 failed, 1 warning (pre-existing SAWarning, unrelated)
```

### Final (after slice-2a changes)

```
pytest tests/new/geo/rainfall/ tests/test_mutation_targets_rainfall.py -q
=> 378 passed, 0 failed, 1 warning (same pre-existing warning)
   (366 baseline + 12 new tests, 0 regressions)

pytest tests/new/ -q   (full backend regression, all domains)
=> 1936 passed, 5 skipped (pre-existing, live-backend/Martin-only skips), 0 failed
```

`ruff check` and `ruff format --check` both clean on every changed/created file.

### TDD Cycle Evidence

| Task | Test | RED evidence | GREEN evidence |
|---|---|---|---|
| 2a.1/2a.2 | `TestWeibullPercentile` (3 tests) | `ImportError: cannot import name 'weibull_percentile'` against slice-1 code | passes after `compute.py::weibull_percentile` + `MIN_BASELINE_YEARS` |
| 2a.3/2a.4/2a.5 | `TestNormalAndPercentileBaselineFloor` (3 tests, incl. the `selected_value=None` counterexample), `TestPercentileFeb29SmallSample` | `ImportError: cannot import name '_normal_and_percentile_metrics'` | pass after `compute.py::_normal_and_percentile_metrics` (per-year 0.95 completeness filter + `MIN_BASELINE_YEARS=20` floor); Feb-29 suppresses structurally (8 leap years < 20), no special-case code |
| 2a.6 | `TestAnnualNormalAndPercentileEnvelopeShape` | `KeyError: 'normal'` against slice-1 `build_snapshot` | passes: `provenance.source_id` fixed to `chirps-v3-final` regardless of the selected year's own source, `unit="percentil"`, interval bounds = the 1991-01-01→last-baseline-year+1d envelope |
| 2a.7 | `TestBuildSnapshotEnvelope::test_build_snapshot_envelope_contract` (updated) | `AssertionError: assert {'selected'} == {'normal', 'percentile', 'selected'}` against slice-1 code | passes after `build_snapshot` wires `_normal_and_percentile_metrics`; `baseline=None` → both suppress `baseline_scope_unmapped` |
| 2a.9 | `TestAntecedentCrossYearWindow` (2 tests) | `KeyError: 'antecedents'` | pass after `compute.py::_antecedent_metric` (`temporal.rolling_total` wired for the first time in production code) + the `_ANTECEDENT_WINDOWS` loop in `build_snapshot` |
| 2a.10 | (covered by 2a.9's production-path proof, task 2a.14 below) | N/A — pure `tasks.py` window-widen, proven via the real-PG cross-year test | `tasks.py::_persist_analysis_revision`'s read start moved to `year_start - timedelta(days=90)` |
| 2a.11 | `TestRainfallMetricPolicyConstants` (pre-existing, still green) + `test_no_metric_suppressed_as_policy_threshold_unset` (2a.12) | N/A — additive dict entries, proven by 2a.12's acceptance test | `policy.py::RAINFALL_METRIC_POLICY` gains 5 entries (`annual_normal`, `annual_percentile`, `d7`, `d30`, `d90`) |
| 2a.12/2a.13/2a.14 | `test_rainfall_insights_metrics.py` (3 new real-PG tests) | `KeyError: 'normal'` / `KeyError: 'antecedents'` — captured via `git stash push -u -- compute.py policy.py tasks.py`, running the new test file against the stashed-out (slice-1) source, then `git stash pop` | pass after the full slice-2a implementation; 2a.13 additionally caught and fixed a LEAP-YEAR bug in the test's OWN fixture (see Deviations) before reaching genuine green |

**RED verification method**: for 2a.1–2a.9 (pure, `test_mutation_targets_rainfall.py`), tests were written first and run against the untouched slice-1 source to capture the failure (`ImportError`/`AssertionError`/`KeyError`, recorded above), then the implementation was added and the suite re-run to confirm GREEN. For 2a.12–2a.14 (real-PG, new file `test_rainfall_insights_metrics.py`), the same git-stash isolation protocol slice 1 established was used: `git stash push -u -- app/domains/geo/rainfall/{compute,policy,tasks}.py` (keeping the new test file in the working tree), `pytest` run to capture the RED failure, `git stash pop` to restore, then the full suite re-run to confirm GREEN.

### Files Changed

| File | Action | What |
|---|---|---|
| `gee-backend/app/domains/geo/rainfall/compute.py` | Modified | `weibull_percentile` (pure, empirical Weibull plotting-position rank) + `MIN_BASELINE_YEARS=20` + `_BASELINE_YEAR_COMPLETENESS_THRESHOLD=0.95`; `_normal_and_percentile_metrics` (builds `annual.normal`/`annual.percentile` from the baseline dict alone, two-layer suppression); `_antecedent_metric` + `_ANTECEDENT_WINDOWS` (builds `antecedents.{d7,d30,d90}` via `temporal.rolling_total`, wired for the first time); `build_snapshot` now returns `annual.{selected,normal,percentile}` + `antecedents.{d7,d30,d90}` (was `annual.selected` only) |
| `gee-backend/app/domains/geo/rainfall/policy.py` | Modified | `RAINFALL_METRIC_POLICY` gains 5 threshold entries (`annual_normal`, `annual_percentile`, `d7`, `d30`, `d90`, all 0.9/0.8) — no `summary` entry (D4) |
| `gee-backend/app/domains/geo/rainfall/tasks.py` | Modified | `_persist_analysis_revision`'s resolved-interval read widened from `[year_start, year_end)` to `[year_start - 90d, year_end)` (D6); `annual.selected`'s own `in_window` filter inside `build_snapshot` is unaffected |
| `gee-backend/tests/test_mutation_targets_rainfall.py` | Modified | Updated `TestBuildSnapshotEnvelope::test_build_snapshot_envelope_contract` for the new envelope shape; added `TestWeibullPercentile`, `TestNormalAndPercentileBaselineFloor`, `TestPercentileFeb29SmallSample`, `TestAnnualNormalAndPercentileEnvelopeShape`, `TestAntecedentCrossYearWindow` (12 new tests total) |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_insights_metrics.py` | Created | 3 real-PG integration tests: 2a.12 (no `policy_threshold_unset`), 2a.13 (shared `comparison_end`, post-cutoff-tail non-leak), 2a.14 (cross-year `d90` suppression on a prior-year gap) |
| `openspec/changes/lluvia-insights/tasks.md` | Modified | Slice 2a (2a.1-2a.15) marked `[x]`, with inline deviation notes |

### Deviations from Design/Tasks

1. **Task literal test names implemented as test CLASSES with multiple focused tests, not single functions.** Every `test_mutation_targets_rainfall.py` addition (2a.1, 2a.3, 2a.4, 2a.6, 2a.9) follows the file's own established convention (e.g., `TestApplyMetricPolicy`, `TestRevisionWriteDecision`) of one class per concern with several small, precisely-named tests, rather than one monolithic test per literal task name. Every literal task's acceptance criterion is still covered; the extra tests are additional counterexample coverage (e.g., the exact 19-vs-20 boundary as two separate tests, not one).
2. **2a.3/2a.4 test the private `compute._normal_and_percentile_metrics` helper directly**, not the full `build_snapshot`. This matches the repo's own precedent (`repository._values_equal_at_6dp` is tested directly in the same file) and keeps the MIN_BASELINE_YEARS floor tests independent of unrelated `build_snapshot` machinery (batch evidence, cadence, etc.).
3. **`_BASELINE_SOURCE_ID = "chirps-v3-final"` is a NEW local constant in `compute.py`**, duplicating `service.py`'s existing `RAINFALL_HISTORICAL_SOURCE` string value rather than importing it. `compute.py`'s import graph currently points only at `policy.py`/`scope.py`/`temporal.py`/`adapters.manifests` (never at `service.py`, the orchestration layer above it); importing a constant from `service.py` would add a new, architecturally-backwards edge. The literal string is duplicated (documented inline) rather than the import boundary being crossed.
4. **2a.11 added 5 threshold entries, not the "4" the task line's own prose states** — the task's own body text explicitly names all 5 (`annual_normal`, `annual_percentile`, `d7`, `d30`, `d90`), and all 5 are required for 2a.12's "no metric suppressed as `policy_threshold_unset`" acceptance test to pass. Read as a minor miscount in the tasks doc, not a scope signal; no threshold was omitted.
5. **`RAINFALL_METRIC_POLICY_REVISION` was NOT bumped, and `router.py`'s stale-policy requeue was NOT touched in this slice**, even though the design.md D3 narrative (and the orchestrator's own context-recovery framing) discusses both. `tasks.md`'s own slice boundary is unambiguous: the revision bump is task 2b.6 and the requeue is 2b.7/2b.8, both explicitly under "## Slice 2b" — this batch's assigned task list is 2a.1-2a.15 only. Practically: every 2a/2a-integration-test build is a BRAND NEW revision (no pre-existing incumbent row for these fresh test fixtures), so `persist_revision`'s `ON CONFLICT DO NOTHING` never discards the enriched envelope in this slice's own tests — the load-bearing bump only matters for a REBUILD of an already-`done` key, which is 2b's concern.
6. **Own test-fixture bug caught and fixed before reaching genuine green (2a.13).** The first draft of `test_normal_and_percentile_share_selected_comparison_end` used a hand-rolled, YEAR-INVARIANT day-count (`cutoff_days=105`, intended as "Jan 1 through Apr 15 inclusive") to build both the "counted" and "must-not-leak" baseline windows for all 30 baseline years. This silently breaks for the 8 LEAP years in 1991-2020: a fixed 105-day offset from Jan 1 lands on Apr 14 in a leap year (the extra Feb 29 pushes everything back one day), so the "must-not-leak" tail (1000.0mm/day) actually STARTED on Apr 15 for those 8 years — squarely inside the intended `[Jan 1, Apr 16)` counted window — and its value leaked into `baseline_cumulatives`'s per-year totals for those years. First run of the test against the FINISHED implementation failed with `791.67 != 525.0 ± 0.0005` (not a `KeyError`/`ImportError` — a genuine wrong-number bug, in the test's own fixture, not the production code). Root-caused via the debugging-discipline loop (reproduce → trace → hypothesize → fix → verify): traced to the 8-leap-year subset, hypothesized the day-count/leap interaction, verified by recomputing the leap-contaminated total by hand. Fixed by moving the test's `comparison_end` to Jan 20 (before every possible Feb 29 in any calendar), making the day-count genuinely year-invariant across leap and non-leap baseline years alike — not a workaround, a correct fixture. Re-verified green; the identical scenario was ALSO re-run through the mandatory git-stash RED check to confirm it remains genuinely RED against slice-1 code (see TDD Cycle Evidence table).
7. **Locked in one additional counterexample regression test beyond the assigned task list**: `test_selected_value_unavailable_suppresses_only_percentile` (Author Counterexample Self-Check, Null/absence category) — proves that a RESOLVED, ELIGIBLE baseline still yields an `available` `annual.normal` even when the selected year's own value is `None` (only `annual.percentile` suppresses, with `reason="annual_selected_value_unavailable"`, a reason not named anywhere in tasks.md/design.md but structurally required — the rank needs a value to rank against, the baseline average does not). This code path was reachable but untested by the literal task list; verified first via an inline probe, then locked in as a permanent test per the self-check's "if a probe reveals real behavior, lock it in" spirit.

### Author Counterexample Self-Check

| Category | Evidence | Result |
|---|---|---|
| Null / absence | `baseline=None` → both metrics suppress `baseline_scope_unmapped` (`test_build_snapshot_envelope_contract`, updated); `selected_value=None` with a resolved, eligible baseline → `annual.normal` stays `available`, only `annual.percentile` suppresses (`test_selected_value_unavailable_suppresses_only_percentile`, new); an empty/absent baseline dict for a given year is never fabricated as a zero (falls out of `eligible_years` naturally via the `year in possible_years` + `expected > 0` guard) | Pass |
| Boundaries | `MIN_BASELINE_YEARS` exact 19-vs-20 boundary (`TestNormalAndPercentileBaselineFloor`, both directions); `weibull_percentile`'s lowest/highest rank bounds (i=1, i=N -- the 3.1/96.9 range at n=30); Feb-29's structural 8-leap-year boundary (`TestPercentileFeb29SmallSample`); `antecedents.d90`'s exact-window boundary (90 complete days available vs. one dropped day, real-PG `test_d90_suppressed_with_reason_when_prior_year_incomplete`) | Pass |
| Concurrency / idempotency | N/A — `_normal_and_percentile_metrics`/`_antecedent_metric`/`weibull_percentile` are pure functions with no shared or mutable state and no I/O; the only concurrency-relevant seam this slice touches (`tasks._persist_analysis_revision`'s read window) is a plain `SELECT`, already covered by `intervals_in_window`'s existing anti-join and the pre-existing per-fingerprint advisory lock upstream of it (both unchanged in this slice) | N/A (reason given) |
| Malicious input / security | N/A — no new HTTP route, no new user-facing input surface in this slice; every new function is fed exclusively by the caller's own resolved DB rows (`repository.baseline_cumulatives`, `repository.intervals_in_window`), never directly by request input | N/A (reason given) |
| Partial failure / recovery | A genuine data gap inside `antecedents.d90`'s window fails LOUD — suppressed with `reason="antecedent_window_incomplete"` — never a silently-short sum, proven at both the pure level (`TestAntecedentCrossYearWindow::test_d90_suppresses_on_a_gap_in_the_prior_year_tail`) and the real-PG production-path level (`test_d90_suppressed_with_reason_when_prior_year_incomplete`, with `d7` unaffected in the same build) | Pass |
| State / tenancy / time | `annual.normal`/`annual.percentile` genuinely share `annual.selected`'s own `comparison_end` cutoff end-to-end — proven by persisting data AFTER the cutoff and confirming it does NOT leak into the baseline average (`test_normal_and_percentile_share_selected_comparison_end`, real PG, after fixing the fixture's own leap-year bug, deviation 6); the D6-widened read window correctly crosses the calendar-year boundary in both directions (complete cross-year sum + gapped cross-year suppression) | Pass |

### Workload / PR Boundary

- Mode: chained PR slice (`feature-branch-chain`, per tasks.md's Review Workload Forecast)
- Current work unit: Unit 2a — "`annual.normal`/`percentile`/antecedents metrics + threshold entries (D4 rows, D5, D6)"
- Boundary: starts at `feat/lluvia-insights-01-baseline`'s tip (`0ed4d70`), ends at this commit — slice 2a is a complete, independently mergeable, independently verifiable unit (378/378 rainfall+mutation tests, 1936/1936 full backend regression)
- Estimated review budget impact: ~240 production lines forecast (tasks.md); actual diff is source (`compute.py`, `policy.py`, `tasks.py`) + 1 modified test file + 1 new test file — within the forecast slice budget. `summary`/cross-source-caveat/revision-bump/stale-requeue explicitly deferred to slice 2b, per tasks.md's own slice boundary.

### Remaining Tasks (out of this batch's scope)

- [ ] Slice 2b: Summary Mechanism, Revision Bump, Cross-Source Caveat, Stale Requeue (2b.1-2b.12)
- [ ] Slice 3a: Series Module — Consistency Pin + `data_revision` Exposure (3a.1-3a.14)
- [ ] Slice 3b: xlsx Export + TS Contract + Consistency Exposure (3b.1-3b.11)
- [ ] Slice 4: Frontend Chart (4.1-4.10)
- [ ] Ops.1-3: real 1991-2020 backfill runbook execution (owner-run, explicitly NOT this agent's scope)
- [ ] Ops.4-6: doc-nit folds

### Status

15/15 slice-2a tasks complete (378/378 targeted tests pass, 1936/1936 full backend regression pass, ruff clean). Ready for review/PR of this work unit, then `sdd-apply` for slice 2b (or `sdd-verify` if the orchestrator wants a checkpoint first).
