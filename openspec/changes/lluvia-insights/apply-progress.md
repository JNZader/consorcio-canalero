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

## Slice 2a review fix pass (2026-08-10)

Fixes the 2 CRITICAL findings from `review-ledger.md`'s "Slice 2a — reliability lens + general refuter" (both survived the general refuter). Branch: `feat/lluvia-insights-02a-metrics` (same slice-2a branch). LI2A-003/004/005/006 are `info` (WARNING/SUGGESTION) — reported, not fixed, per the severity floor. Task list unchanged: all 15 slice-2a tasks were already `[x]`; this is a fix round on committed work, not new task scope.

### TDD Cycle Evidence

| Finding | Test | RED evidence | GREEN evidence |
|---|---|---|---|
| LI2A-002 | `test_rainfall_insights_metrics.py::test_antecedents_clip_to_last_available_interval_under_provider_lag` (new, real PG) | Written first, run against unfixed `compute.py`: `AssertionError: ('d7', {'metric': 'd7', 'value': None, ..., 'state': 'suppressed', ...})` / `assert 'suppressed' == 'available'` — the 3-day provider lag (data through Apr 12, `comparison_end` Apr 15) suppressed every antecedent, exactly the predicted steady-state failure. 1 failed / 120 passed in that same run | `build_snapshot` passes `end=window_end` (the existing `min(comparison_end_exclusive, last_interval_end)` clip) into `_antecedent_metric`; test green, d7/d30/d90 = 14.0/60.0/180.0 mm over the clipped window with `available_through == 2025-04-13T00:00:00+00:00` |
| LI2A-002 (counterexample) | `test_rainfall_insights_metrics.py::test_antecedent_gap_inside_the_clipped_window_still_suppresses` (new, real PG) | No genuine RED — it passes both before and after by design; its job is to prove the clip did NOT soften `rolling_total`'s exact-slot-set check (a hole at Apr 9, inside the clipped d7 window) | Green after the fix: all three antecedents suppress `antecedent_window_incomplete`, no short sum |
| LI2A-001 | `TestAntecedentCrossYearWindow::test_d90_sums_across_the_year_boundary_when_complete`, `::test_d90_suppresses_on_a_gap_in_the_prior_year_tail`, `test_d90_suppressed_with_reason_when_prior_year_incomplete` (assertions added to 3 existing tests) | No RED by construction — the refuter classified this as a coverage gap on CORRECT code; all three assertion blocks passed on first run against unfixed source. That pass IS the evidence D6's "annual.selected provably unaffected" claim held, and the same three then re-passed after the LI2A-002 fix, proving the anchor change did not disturb `annual.selected` | Green in both runs; `annual.selected.value == 20.0` and `completeness == 1.0` in all three |

**Expected-value derivation (not assumed).** `test_d90_*` (mutation file): `_COMPARISON_END_EXCLUSIVE = 2025-01-21`, so the 90-row fixture starts `2025-01-21 − 90d = 2024-10-23`; of those, only `2025-01-01 .. 2025-01-20` (20 rows × 1.0 mm) clear `build_snapshot`'s `in_window` filter → `value = 20.0`. `window_end = min(2025-01-21, last_interval_end = 2025-01-21) = 2025-01-21`, so `expected_slots = 20 = matched_slots` → `completeness = 1.0`. The gapped sibling drops index 30 = `2024-11-22`, a PRIOR-year slot, so both numbers are identical there. Integration test 2a.14: 20 current-year rows × 1.0 mm, same window arithmetic → `20.0` / `1.0`. Lagged-tail test: `days_persisted = (2025-04-12 − 2025-01-01).days + 1 = 102` (asserted in the test itself), × 2.0 mm → `annual.selected = 204.0`; `end_effective = 2025-04-13T00:00Z`, so d7/d30/d90 = `2.0 × 7/30/90` = `14.0`/`60.0`/`180.0`.

### Files Changed (fix pass)

| File | Action | What |
|---|---|---|
| `gee-backend/app/domains/geo/rainfall/compute.py` | Modified | LI2A-002: `build_snapshot` passes `end=window_end` (was `comparison_end_exclusive`) into `_antecedent_metric`, reusing `annual.selected`'s own clip; `_antecedent_metric`'s docstring restated (clipped anchor, honest `available_through`); the call-site comment documents the rationale and the no-in-window-intervals fallback |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_insights_metrics.py` | Modified | LI2A-002: 2 new real-PG tests (lagged-tail steady state, gap inside the clipped window); LI2A-001: `annual.selected` value + completeness assertions in the 2a.14 cross-year test |
| `gee-backend/tests/test_mutation_targets_rainfall.py` | Modified | LI2A-001: `annual.selected` value + completeness assertions in both `TestAntecedentCrossYearWindow` tests |
| `openspec/changes/lluvia-insights/design.md` | Modified | D6 anchor amendment: the clip, its rationale (provider lag as steady state), `available_through` honesty tied to the owner's `comparison_end` deferral decision, unchanged in-window suppression, year-boundary degradation |
| `openspec/changes/lluvia-insights/review-ledger.md` | Modified | New "Slice 2a — reliability lens + general refuter" section: 6 rows + resolutions + final verification |

### Deviations (fix pass)

1. **`end_effective` is not a new variable.** The brief asked for `end_effective = min(comparison_end_exclusive, last_interval_end)` derived from the same resolved-interval data `annual.selected` uses. That value already exists as `window_end` (`compute.py:394`), so the fix passes it through rather than introducing a second name for the same quantity — the brief's own "do not invent a second derivation" constraint, taken literally.
2. **The year-boundary reasoning in the brief was verified and corrected in the design note.** The brief predicted `last_interval_end < year_start` would push the clipped window's head slots outside the D6 read window. Checked against the code: `window_end` is derived from `in_window`, which only holds slots with `year_start <= interval_start`, so the anchor can never land before `year_start`. The real year-boundary-lag path is `in_window` being EMPTY, which falls the clip back to `comparison_end_exclusive` and suppresses because the current-year head slots do not exist. Both paths end in suppression, never a wrong value; D6 documents the actual mechanism and keeps the brief's variant as the outer bound.
3. **A `git stash pop` was issued against a pre-existing, unrelated stash and aborted safely.** While measuring the pre-fix targeted baseline, a `git stash push` failed on a path-prefix error (wrong `cwd`), so the chained `git stash pop` targeted `stash@{0}` from an unrelated branch. Git refused it (`consorcio-web/public/version.json` would have been overwritten) and aborted; `git stash list` and the working tree were verified unchanged immediately afterwards. No further stash operations were attempted. The baseline was instead established by arithmetic on the diff (`git diff -U0 | rg -c '^\+\s*def test_'` → exactly 2 new test functions, both under `tests/new/`), corroborated by the full suite moving 1936 → 1938.

### Author Counterexample Self-Check (fix pass)

| Category | Evidence or N/A reason | Result |
|---|---|---|
| Null / absence | No in-window intervals at all → `window_end` falls back to `comparison_end_exclusive` and every antecedent suppresses (reasoned from the code and covered by `test_build_snapshot_with_no_data_in_window_is_unavailable`'s envelope, which still builds all three antecedents); a missing slot inside the clipped window still yields `value=None` + `antecedent_window_incomplete` (`test_antecedent_gap_inside_the_clipped_window_still_suppresses`) | Pass |
| Boundaries | The clip itself is the boundary under test: `comparison_end_exclusive` vs `last_interval_end`, exercised on both sides — equal (`test_d90_sums_across_the_year_boundary_when_complete`, no clipping) and strictly lagging (`test_antecedents_clip_to_last_available_interval_under_provider_lag`, 3-day clip). Year-boundary lag traced explicitly (see Deviation 2) | Pass |
| Concurrency / idempotency | N/A — `_antecedent_metric` and `build_snapshot` stay pure functions over their inputs; the fix moves no I/O and adds no state. The only shared-state seam nearby (`intervals_in_window`'s anti-join, the per-fingerprint advisory lock) is untouched | N/A (reason given) |
| Malicious input / security | N/A — no new route, no new user-facing input; the changed argument is a datetime already derived from resolved DB rows inside the same function | N/A (reason given) |
| Partial failure / recovery | Exactly the finding's subject: a lagging provider is the partial-failure steady state, and the metric now degrades to a shorter-but-honest window instead of blanket suppression, while a genuine hole still fails loud rather than short-summing (both proven by the two new tests) | Pass |
| State / tenancy / time | `available_through` and `interval_end` now report the clipped end (`2025-04-13T00:00:00+00:00`), asserted per metric; `comparison_end` stays the calendar date, asserted in the same test, so the owner's "calendar `comparison_end` + `available_through` disclosure" decision is preserved rather than silently reinterpreted | Pass |

### Final Verification (fix pass)

```
pytest tests/new/geo/rainfall/ tests/test_mutation_targets_rainfall.py -q
=> 381 passed, 1 pre-existing SAWarning, 0 failed   (379 pre-fix + 2 new tests)

pytest tests/new/ -q
=> 1938 passed, 5 skipped (pre-existing live-backend/Martin skips), 0 failed
   (was 1936 passed + 5 skipped; +2, exactly the two new tests)

ruff check .   => All checks passed!        (exit 0)
ruff format .  => 400 files left unchanged  (exit 0)
```

Bookkeeping note: this document's slice-2a section records the targeted baseline as 378; the measured pre-fix figure is 379. The full-suite baseline (1936) reconciles exactly with +2, so the 378 is a one-test slip in the record, not a regression.

### Status (fix pass)

2/2 CRITICAL findings fixed; 4 WARNING/SUGGESTION reported as `info` (never blocking, never re-reviewed). Ready for the scoped re-review of this fix diff against the ledger, then `sdd-verify`.

## Slice 2b: Summary Mechanism, Revision Bump, Cross-Source Caveat, Stale Requeue (D3, D4, D5) — COMPLETE (12/12 tasks + 3 amendments)

**Branch**: `feat/lluvia-insights-02b-summary` (base: `feat/lluvia-insights-02a-metrics`, tip `7677327` verified present at branch time).
**Mode**: Strict TDD (RED → GREEN → REFACTOR). RED captured by running each new test against the untouched source before writing the implementation; where the source change was a single line, it was disabled in place and restored rather than stashed (see Deviations 5).

### Baseline (before slice-2b changes, same branch, source at slice-2a tip)

```
pytest tests/new/geo/rainfall/ tests/test_mutation_targets_rainfall.py -q
=> 381 passed, 1 warning (pre-existing SAWarning, unrelated)
```

### Final (after slice-2b changes)

```
pytest tests/new/geo/rainfall/ tests/test_mutation_targets_rainfall.py -q
=> 401 passed, 0 failed, 1 warning (same pre-existing warning)
   (381 baseline + 20 new tests, 0 regressions)

pytest tests/new/ -q   (full backend regression, all domains)
=> 1945 passed, 5 skipped (pre-existing live-backend/Martin skips), 0 failed
   (was 1938 + 5; +7 -- the new tests that live UNDER tests/new/. The other
    13 new tests are in tests/test_mutation_targets_rainfall.py, which sits
    outside that tree and is therefore not counted by this command.)

pytest tests/new/geo/rainfall/test_backend_api.py -q   (standalone)
=> 52 passed
   (LI1-001's collection-order rule re-checked on purpose: this slice makes
    that file request the `db` fixture for the first time.)

ruff check .          => All checks passed!            (exit 0)
ruff format --check . => 400 files already formatted   (exit 0)
```

### TDD Cycle Evidence

| Task | Test | RED evidence | GREEN evidence |
|---|---|---|---|
| A1 (LI2A-101) | `test_rainfall_insights_metrics.py::test_baseline_is_cut_at_the_effective_end_not_the_calendar_comparison_end` (new, real PG) | `assert 3144.0 == 144.0 ± 1.4e-04` against unfixed `compute.py` — a 3-day lag admitted 3 × 1000.0 mm of post-cutoff baseline tail into every one of the 30 baseline years | `compute._disclosure_window` + `compute.baseline_cutoff_for`, consumed by `tasks._persist_analysis_revision` for `temporal.baseline_dates(...)`; normal = 144.0, percentile = 50.0 (was 3.125 — the measured bias), envelope end 2020-02-18 |
| A1 (no-regression half) | `::test_baseline_cutoff_equals_the_calendar_comparison_end_when_there_is_no_lag` (new, real PG) | No RED by construction — with the provider caught up `window_end == comparison_end_exclusive`, so the effective cutoff IS the calendar date; it passed against unfixed source, which IS the proof the amendment changes nothing without lag | Still green after the change: normal = 3144.0 (tail counted), percentile = 3.125, envelope end 2020-02-21 |
| A1 (pure) | `TestNormalAndPercentileBaselineFloor` / `TestPercentileFeb29SmallSample` (4 call sites) | N/A — keyword rename `comparison_end_date` → `baseline_cutoff` | Same assertions, renamed keyword; the parameter can no longer be read as the calendar date |
| A2 (LI2A-003) | `TestBaselineFloorBindsAtDisclosure` (5 tests, pure end-to-end through `normalize_snapshot`) | `assert 'coverage_below_threshold' != 'coverage_below_threshold'` at 21 eligible years; `assert 0.9 == 0.6666666666666666` on the drift test | `policy._BASELINE_SAMPLE_FRACTION = 20 / 30` on BOTH the coverage and quality entries; 19 → `baseline_years_below_minimum`, 20 → available (float boundary), 21 → available |
| A2 (intermediate probe) | — | After changing ONLY coverage, an executed probe returned `normal -> suppressed quality_below_threshold \| completeness 0.7 \| quality 0.7` — the same band, a different label | Quality entry moved too; see Deviations 1 |
| A3 (LI2A-005) | `test_rainfall_baseline.py::test_baseline_cumulatives_raises_on_a_duplicated_interval_slot` (new, real PG) | `Failed: DID NOT RAISE ValueError`; a temporary probe of the same fixture returned `{1991: (20.0, 2, 122)}` for a single 10.0 mm slot — total AND matched_days inflated together, so the year still looked complete | `count(DISTINCT interval_start)` vs `count()` per year → `ValueError` naming source/asset/year and both counts |
| 2b.1/2b.2/2b.4 | `TestRainfallSummary` (4 tests) | `ImportError: cannot import name 'rainfall_summary' from 'app.domains.geo.rainfall.service'` (and the same for `SUMMARY_AVAILABLE_PREFIX`/`SUMMARY_METRIC_LABELS`); the stale-summary case additionally showed the old narrative passing through untouched | `service.rainfall_summary(...)` + `normalized["summary"] = rainfall_summary(normalized)` at the end of `normalize_snapshot` |
| 2b.3 | `TestBuildSnapshotEnvelope::test_build_snapshot_emits_no_summary_key` | No RED — already true; an assert-only pin in the same sense as tasks 1.6/1.12, and now a regression guard against a future build-time narrative | Green on first run, before and after the service change |
| 2b.5 | `test_backend_api.py::test_summary_disagrees_from_build_time_completeness_end_to_end` (new, real PG) | `KeyError: 'summary'` with the single `normalize_snapshot` assembly line disabled in place | Stored envelope says `available` / 33.0; served JSON says `suppressed` / `coverage_below_threshold`; the narrative agrees with the served state and never prints 33.0 |
| 2b.6 | `test_backend_api.py::test_revision_bump_lands_enriched_envelope_not_conflict_skipped` (new, real PG) | `assert 'rainfall-v2-2026-08' != 'rainfall-v2-2026-08'` — the bump itself was missing, and without it the rest collides by construction | `RAINFALL_METRIC_POLICY_REVISION = "rainfall-v2-2026-08-insights"`; 2 rows for one fingerprint, ONE data_revision, two policy revisions, enriched envelope in the new row |
| 2b.7/2b.8 | `test_backend_api.py::test_stale_policy_revision_served_and_requeued` (new, real PG) | `assert 0 == 1` — the row was already served (200), but no refresh was enqueued | `router.read_analysis` serves the row and enqueues `policy_revision_stale`; second poll adds nothing (pending pre-check), and a `done` refresh inside the cooldown window adds nothing either |
| 2b.8 (counterexample) | `::test_current_policy_revision_serves_without_enqueueing_anything` (new, real PG) | No RED — pins that the trigger is the revision DIFFERING, not every 200 | Zero outbox rows for a current-revision key |
| 2b.9/2b.10/2b.11 | `TestCrossSourceBaselineCaveat` (3 tests) | `AssertionError: ('normal', [])` — no caveat emitted for an NRT selected year | `cross_source_baseline=chirps-v3-final_vs_chirps-v3-sat` on normal + percentile; absent when both sides are Final; survives `_normalize_metric` into `metric_rows` |

### Files Changed

| File | Action | What |
|---|---|---|
| `gee-backend/app/domains/geo/rainfall/compute.py` | Modified | A1: `_DisclosureWindow`/`_disclosure_window` (the single derivation, extracted from `build_snapshot`'s inline math) + public `baseline_cutoff_for` + `_cutoff_date`; `_normal_and_percentile_metrics`'s `comparison_end_date` → `baseline_cutoff`, and the envelope end follows it. 2b.11: `selected_source_id` parameter + the fixed `cross_source_baseline=...` discrepancy entry on both baseline metrics |
| `gee-backend/app/domains/geo/rainfall/policy.py` | Modified | 2b.6: `RAINFALL_METRIC_POLICY_REVISION` bumped to `rainfall-v2-2026-08-insights` with the load-bearing rationale inline. A2: `_BASELINE_SAMPLE_FRACTION = 20 / 30` on `annual_normal`/`annual_percentile`'s coverage AND quality entries; every other metric untouched |
| `gee-backend/app/domains/geo/rainfall/service.py` | Modified | 2b.4: `SUMMARY_METRIC_LABELS`/`SUMMARY_STATE_LABELS`/the three bucket prefixes, pure `_summary_entry` + `rainfall_summary`, and the one assembly line at the end of `normalize_snapshot` |
| `gee-backend/app/domains/geo/rainfall/router.py` | Modified | 2b.8: `read_analysis` reads the row's fields into locals first (the enqueue commits and would otherwise expire the ORM instance), emits `rainfall.analysis.policy_revision_stale`, and enqueues the labelled refresh before normalizing |
| `gee-backend/app/domains/geo/rainfall/repository.py` | Modified | A3: `baseline_cumulatives` gained `count(DISTINCT interval_start)` and the loud duplicate-slot guard |
| `gee-backend/app/domains/geo/rainfall/tasks.py` | Modified | A1: the baseline dates now come from `compute.baseline_cutoff_for(year, now, intervals=resolved)` instead of the calendar `comparison_end_date` |
| `gee-backend/tests/test_mutation_targets_rainfall.py` | Modified | +13 tests: `TestRainfallSummary` (4), `TestBaselineFloorBindsAtDisclosure` (5), `TestCrossSourceBaselineCaveat` (3), `test_build_snapshot_emits_no_summary_key` (1); 4 keyword renames; LI2A-102 docstring fold |
| `gee-backend/tests/new/geo/rainfall/test_backend_api.py` | Modified | +4 real-PG tests (2b.5/2b.6/2b.7/2b.8 counterexample) + local helpers; first `db`-fixture tests in this file |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_insights_metrics.py` | Modified | +2 real-PG tests (A1 lagged + no-lag) and the shared A1 baseline fixture |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_baseline.py` | Modified | +1 real-PG test (A3 duplicate-slot guard) |
| `gee-backend/tests/new/geo/rainfall/test_prepr_contract_fixes.py` | Modified | Route-contract fixture moved onto the CURRENT policy revision (see Deviations 3) |
| `openspec/changes/lluvia-insights/design.md` | Modified | D5 "Same-date anchor amendment" (A1); D4 threshold note + table rows (A2); D4 mechanism reason 3 corrected (2b.12/LIA-102); File Changes rows for `repository.py` and `policy.py` |
| `openspec/changes/lluvia-insights/review-ledger.md` | Modified | LI2A-003/LI2A-005 → `fixed`; new LI2A-101 row; "Slice 2b" section with resolutions and verification |
| `openspec/changes/lluvia-insights/tasks.md` | Modified | 2b.1-2b.12 marked `[x]` with inline deviation notes; a new amendments block (A1/A2/A3) |

### Deviations from Design/Tasks

1. **A2 moved BOTH thresholds, not only coverage.** The brief said "set the coverage threshold ... to 20/30". Applying that alone leaves the exact 20-26 band suppressed as `quality_below_threshold`, because `quality["score"]` for these two metrics IS `completeness` (design.md D4's own convention) — verified by executed probe, recorded in the ledger. The brief's own acceptance criterion ("21 years → available") is unreachable without moving the quality entry too, so both moved and D4's threshold note states why.
2. **The threshold is written `20 / 30`, not `0.6667`.** `completeness` is `len(eligible_years) / len(possible_years)`, the identical float division, so the boundary case (exactly 20 eligible years) compares EQUAL and passes. A hand-rounded `0.6667` would suppress it, which is a silently wrong floor. Pinned by `test_exactly_the_floor_is_served_at_the_float_equality_boundary` and by a drift test tying the entries to `MIN_BASELINE_YEARS / len(baseline_years_for(...))`.
3. **`test_prepr_contract_fixes.py::test_analysis_route_server_resolves_fingerprint_and_revision` needed a fixture update.** It injects `object()` as the session and a fake revision on `policy_revision="v1"`, which after 2b.8 is a STALE revision and now takes a DB-touching enqueue branch (`AttributeError: 'object' object has no attribute 'scalar'`). The test's subject is fingerprint resolution + `analysis_revision_id` injection, not stale serving, so its fake row was moved onto the current policy revision (restamping `metric_policy.revision` and the metric's own `revision` together, as a real row does). The stale branch has its own real-PG coverage. The feature was not weakened to keep a fake-session test green.
4. **`build_snapshot` had no `summary` emission to remove** (task 2b.4's literal wording). It never emitted one — slice 2a's envelope is `annual`/`antecedents` only — so 2b.3 is an assert-only pin (same shape as tasks 1.6/1.12) that now guards against a future build-time narrative rather than removing an existing one.
5. **RED for single-line changes was captured by disabling the line in place, not by `git stash`.** Slice 2a's fix pass recorded a stash mishap against an unrelated pre-existing stash (its Deviation 3). For `normalized["summary"] = rainfall_summary(normalized)` the line was replaced with `pass  # TEMP`, the test run captured (`KeyError: 'summary'`), and the line restored in the same command — no stash, no cross-branch risk. The multi-line REDs (A1, A3, A2, the caveat) needed no isolation at all: the tests were written before the implementation existed.
6. **`rainfall_summary` reads `unit` in addition to `state`/`reason`/`value`** (task 2b.4 says "reads only `state`/`reason`/`value`"). D4's coherence invariant is about STATES: `unit` is static disclosure metadata that `apply_metric_policy` never rewrites and `_normalize_metric` passes through untouched, so it cannot make the narrative disagree with a badge. Without it the same sentence would print "204.0" for millimetres and "50.0" for a percentile with nothing to tell them apart. Guarded: a missing or non-string unit degrades to the bare number rather than printing `None`.
7. **The caveat is built inside `_normal_and_percentile_metrics`, not bolted onto `build_snapshot`'s return value** (task 2b.11 names `build_snapshot`). Both metrics are constructed in one place; emitting the entry there keeps a single construction site instead of mutating returned dicts, and `build_snapshot` still owns the decision by passing `selected_source_id` in.
8. **2b.5's disagreement comes from real evidence, not hand-tuned thresholds** (the task says "thresholds chosen so build-time and post-policy state disagree"). A gapped fixture (10 days, a 21-day hole, then 1 day) produces `completeness = 11/32` under the REAL shipped policy while `build_snapshot` still reports `available` — a genuine end-to-end disagreement rather than a fixture-only one, and one that survives future threshold edits as long as `annual` stays above 0.34.
9. **`policy.py` defines its own `20 / 30` literal instead of importing `compute.MIN_BASELINE_YEARS`.** `compute.py` imports `policy.py`, so the reverse import would be circular. The drift risk this creates (LI2A-004's bug class) is closed by a test asserting the two are equal, not by a comment.

### Author Counterexample Self-Check

| Category | Evidence | Result |
|---|---|---|
| Null / absence | `rainfall_summary({})` returns the explicit "no metrics disclosed" sentence rather than an empty string; a metric with `value=None` in an `available`-like state falls to the "sin dato" bucket via `_is_finite_metric_value`; a missing/non-string `unit` degrades to the bare number; `baseline=None` still suppresses `baseline_scope_unmapped` (unchanged, `test_build_snapshot_envelope_contract`) | Pass |
| Boundaries | A2's float-equality boundary at exactly `MIN_BASELINE_YEARS` (20 → available, 19 → suppressed with the DISTINCT reason, 21 → available); A1's zero-lag boundary (`window_end == comparison_end_exclusive` ⇒ the effective cutoff IS the calendar date, own test); the A1 fixtures are deliberately confined to Jan 1 - Feb 20 so the day count is identical in leap and non-leap years (the leap-year fixture bug slice 2a hit in its own 2a.13, avoided by construction here) | Pass |
| Concurrency / idempotency | The stale requeue is idempotent under repeated polls, asserted in both directions: a second poll hits `pending_row_for_key` and adds nothing, and a `done` refresh inside `RAINFALL_RECOMPUTE_COOLDOWN` hits `recent_done` and adds nothing — one refresh per key per cooldown window, never one per poll. 2b.6 asserts the bump produces exactly ONE new row (not a duplicate per rebuild) since a third build would collide on the same (fingerprint, policy_revision, data_revision) | Pass |
| Malicious input / security | No new route, no new request field, no widened auth: the requeue reuses the router-level `require_admin_or_operator` and the SAME server-derived fingerprint the read used, so a caller cannot steer which key gets enqueued beyond the scope/year it may already request. The enqueue is bounded by the pre-existing cooldown, so a poll loop cannot turn into a GEE-quota amplifier | Pass |
| Partial failure / recovery | The stale refresh is enqueued BEFORE normalization, so a stale row that ALSO fails its contract still gets its healing refresh instead of only a 503; `queue_missing_analysis` commits, so the row's fields are read into locals first and no post-commit ORM refresh can fail mid-response. A3's guard turns a corrupted (duplicated-slot) baseline read into a loud failure instead of a quietly biased normal | Pass |
| State / tenancy / time | A1 is itself a time-boundary fix, asserted on both sides of the lag; the disclosed `comparison_end` stays the CALENDAR date (the owner's decision) while only the comparison cutoff follows the evidence, asserted in the same test. Old snapshot rows keep their own `policy_revision` and are still served self-consistently after the bump (2b.7), so the bump is not a retroactive rewrite | Pass |

### Workload / PR Boundary

- Mode: chained PR slice (`feature-branch-chain`, per tasks.md's Review Workload Forecast)
- Current work unit: Unit 2b — "disclosure-time `summary` + revision bump + cross-source caveat + stale requeue (D3, D4, D5)", plus the three ledger-driven amendments the orchestrator folded in
- Boundary: starts at `feat/lluvia-insights-02a-metrics`'s tip (`7677327`), ends at this commit — independently mergeable and independently verifiable (401 targeted, 1945 full-suite, ruff clean)
- Estimated review budget impact: ~210 production lines forecast for the slice; actual production diff is 6 files, with the amendments adding roughly 60 further production lines (the `_disclosure_window` extraction, the policy fraction, the SQL guard). Test and doc lines carry the rest.

### Remaining Tasks (out of this batch's scope)

- [ ] Slice 3a: Series Module — Consistency Pin + `data_revision` Exposure (3a.1-3a.14)
- [ ] Slice 3b: xlsx Export + TS Contract + Consistency Exposure (3b.1-3b.11)
- [ ] Slice 4: Frontend Chart (4.1-4.10)
- [ ] Ops.1-3: real 1991-2020 backfill runbook execution (owner-run, explicitly NOT this agent's scope)
- [ ] Ops.4-6: doc-nit folds

### Status

12/12 slice-2b tasks complete + 3 ledger amendments (LI2A-101/003/005) fixed. 401/401 targeted, 1945/1945 full backend regression (5 pre-existing skips), ruff check + format clean. Ready for review/PR of this work unit, then `sdd-apply` for slice 3a (or `sdd-verify` if the orchestrator wants a checkpoint first).

## Slice 2b resilience fix round (2026-08-10) — COMPLETE (5/5 findings)

Branch `feat/lluvia-insights-02b-summary`, base `592a57a`. Surgical round over the slice-2b diff: `review-resilience` + 1 general refuter produced LI2B-001 (CRITICAL, adjudicated WARNING after refutation) and LI2B-002..005 (WARNING, promoted rather than deferred). Ledger rows and full evidence: `review-ledger.md`, section "Slice 2b — resilience lens + general refuter".

### Baseline (before fix-round changes, same branch)

- `pytest tests/new/ -q` → **1944 passed, 6 skipped** (measured on this environment; the slice-2b entry records 1945/5 — `tests/new/test_martin_reader_grants.py` skips here for lack of an isolated superuser DB, so both totals are 1950 collected)
- `pytest tests/new/geo/rainfall/ tests/test_mutation_targets_rainfall.py -q` → **401 passed**

### Final (after fix-round changes)

- `pytest tests/new/ tests/test_mutation_targets_rainfall.py -q` → **2081 passed, 6 skipped**, 0 failed
- `pytest tests/new/ -q` → **1952 passed, 6 skipped** (+8 = exactly the eight new tests)
- `pytest tests/new/geo/rainfall/ tests/test_mutation_targets_rainfall.py -q` → **409 passed** (+8)
- `ruff check .` → All checks passed · `ruff format .` → 401 files left unchanged

### TDD Cycle Evidence

| Finding | RED (executed, against unfixed source) | GREEN | REFACTOR |
|---|---|---|---|
| LI2B-001 | `assert [<app.domains...RainfallOutbox>] == []` — a key whose retries were exhausted seconds earlier enqueued a fresh full-year work item on the next poll | 3-rung cooldown ladder; both the in-cooldown and cooldown-expired tests pass | `_requeue_cooldown` extracted so `queue_missing_analysis` reads as one guard, and both `pending_row_for_key` call sites now share the one `key` dict instead of re-spelling six kwargs |
| LI2B-002 | `sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedTable)` propagating out of `read_analysis` (500 on a read whose snapshot was in memory) | 200 + `requeue_failed` event + a working `SELECT 1` on the same session | enqueue extracted to `router._requeue_stale_revision`, keeping `read_analysis` linear |
| LI2B-003 | `ImportError: cannot import name 'outcome_label'` (marker vocabulary did not exist); the behavioral gap is pinned by the CONTROL half — an unmarked same-age `done` row still enqueues | marker stamped, stripped on carry-over, 24-h read-path backoff | marker vocabulary (`outcome_label`/`carryover_labels`/`non_write_outcome`) centralized in `service.py` so `tasks.py` has no literal `outcome:` strings |
| LI2B-004 | `ValueError: baseline_cumulatives received duplicated interval_start slots (... year=1991: 2 rows over 1 slots)` aborting the entire build | build lands, `annual.selected` available at 153.0 mm, only normal/percentile suppress | reason strings promoted to `BASELINE_SCOPE_UNMAPPED`/`BASELINE_EVIDENCE_INVALID` constants so the caller cannot typo an undocumented reason |
| LI2B-005 | `AssertionError: rainfall.analysis.policy_revision_stale missing from the event catalogue` | all three events + marker semantics catalogued; test green | cooldown reasons documented as one table rather than three prose mentions |

### Files Changed

| File | Action | What |
|---|---|---|
| `gee-backend/app/domains/geo/rainfall/repository.py` | Modified | `DuplicateBaselineSlotError` (carries source/asset/year/counts); `baseline_cumulatives` raises it; new `latest_terminal_attempt` read |
| `gee-backend/app/domains/geo/rainfall/service.py` | Modified | `RAINFALL_FAILED_REQUEUE_COOLDOWN` (6 h) + `RAINFALL_REFUSED_REQUEUE_COOLDOWN` (24 h); `outcome:` marker vocabulary; `_requeue_cooldown` ladder; `rainfall.outbox.cooldown` gains `reason`/`cooldown_seconds` |
| `gee-backend/app/domains/geo/rainfall/router.py` | Modified | `_requeue_stale_revision` (manual SAVEPOINT + `rainfall.analysis.requeue_failed`); corrected bounded-cost comment covering all four states |
| `gee-backend/app/domains/geo/rainfall/tasks.py` | Modified | non-write decision stamps the `done` row; `carryover_labels` in both sweep stages; `DuplicateBaselineSlotError` degradation + `rainfall.baseline.duplicate_slots` |
| `gee-backend/app/domains/geo/rainfall/compute.py` | Modified | `baseline_unavailable_reason` threaded through `build_snapshot` → `_normal_and_percentile_metrics`; two named reason constants |
| `gee-backend/tests/new/geo/rainfall/test_slice2b_resilience_fixes.py` | Created | 8 real-PG regressions, one per finding (LI2B-001 gets two: in-cooldown and cooldown-expired; LI2B-004 gets two: task degradation and repository boundary) |
| `gee-backend/tests/test_mutation_targets_rainfall.py` | Modified | `_FakeSession` models the third `scalar()` read (`latest_terminal_attempt`) |
| `docs/lluvia-v2-observability-workbook.md` | Modified | 3 new event rows, the cooldown-ladder table, the `outcome:` marker section |
| `openspec/changes/lluvia-insights/specs/rainfall-analysis/spec.md` | Modified | `MODIFIED` "GEE Quota Guards on Request-Path Re-enqueue and Poll" + 4 new scenarios |
| `openspec/changes/lluvia-insights/design.md` | Modified | D3 "Cooldown ladder amendment" + the best-effort-refresh paragraph |
| `openspec/changes/lluvia-insights/review-ledger.md` | Modified | Slice 2b resilience section: 5 rows, resolutions, cleared surfaces |

### Deviations

1. **Constant naming** — briefed as `FAILED_REQUEUE_COOLDOWN`, shipped as `RAINFALL_FAILED_REQUEUE_COOLDOWN` to match the module's existing `RAINFALL_RECOMPUTE_COOLDOWN` convention.
2. **Manual SAVEPOINT instead of `with db.begin_nested():`** (LI2B-002) — forced by evidence, not preference: `queue_missing_analysis` rolls back internally to recover the `IntegrityError` race, and inside the context-manager form the next statement raises `InvalidRequestError: Can't operate on closed transaction inside context manager`. Probed before choosing; the manual form was verified against all three callee paths.
3. **`latest_terminal_attempt` instead of a `failed`-only `recent_terminal_attempt`** — the brief suggested a `status='failed'` sibling; one read that returns the NEWEST terminal row (`done` OR `failed`) serves both LI2B-001 and LI2B-003, and is what makes "a key healed after a failure is not suppressed by its own history" true by construction rather than by a second query.
4. **`baseline_evidence_invalid` reason added** (LI2B-004) — beyond the brief. Reusing `baseline_scope_unmapped` for a duplicate would ship a knowingly-false reason on a suppressed metric, the same defect class LI2A-003 fixed. Verified no consumer enumerates reason strings.
5. **`rainfall.outbox.cooldown` extended rather than split** — three reasons on one event (`reason` + `cooldown_seconds`) instead of three event names, so existing dashboards keep working and the ladder reads as one thing.

### Author Counterexample Self-Check

| Category | Evidence | Result |
|---|---|---|
| Null / absence | `latest_terminal_attempt` returns `None` for a key with no terminal history → ladder falls through to the pending pre-check (the default path every pre-existing test exercises); `non_write_outcome` handles `work_labels` being `None` or empty; `build_analysis` returning `None`/no `decision` is tolerated by `(built or {}).get(...)` | Pass |
| Boundaries | Both cooldown-expiry directions asserted for LI2B-001 (inside → zero enqueues; backdated past the window → exactly one); the `_backdate` helper asserts the timestamp actually moved, so an expiry test cannot pass vacuously; the daily rung is paired with a same-age unmarked CONTROL row that still enqueues | Pass |
| Concurrency / idempotency | The `IntegrityError` race recovery (decision 8) is preserved through the savepoint — the exact reason the context-manager form was rejected — and the pending pre-check still makes repeated polls idempotent (asserted in the cooldown-expired test's second poll); marker stamping is idempotent (`if marker not in row.work_labels`) | Pass |
| Malicious input / security | No new route, field or auth surface. The new cooldowns only ever REDUCE work a caller can trigger; a poll loop is now bounded in every terminal state instead of two of three | Pass |
| Partial failure / recovery | This round IS the partial-failure work: enqueue failure degrades to a served 200 + event with the session verifiably usable afterwards (`SELECT 1` asserted); a corrupt baseline degrades to two suppressed metrics instead of an unbuildable key; a terminal `failed` key still SERVES its stored revision while its retries back off | Pass |
| State / tenancy / time | The failed rung is dated by `updated_at` (advances on the final retry) not `next_attempt_at` (failure instant + backoff, i.e. the future); `latest_terminal_attempt` orders by `COALESCE(completed_at, updated_at)` so `done` and `failed` rows are comparable; `outcome:` markers are stripped on carry-over so a stale refusal cannot leak into a new attempt's state; the test key is derived from `resolve_missing_work_source` rather than hardcoded, so it does not rot when the real clock rolls over | Pass |

### Status (fix round)

5/5 findings fixed with executed RED evidence for every genuine RED. 2081/2081 (6 pre-existing skips), ruff clean. Next: `sdd-verify`, or a scoped re-review of this fix diff against the ledger.

## Slice 3a: Series Module — Consistency Pin + `data_revision` Exposure (D3, LIB-101 fold) — COMPLETE (14/14 tasks + 1 addition)

**Branch**: `feat/lluvia-insights-03a-series` (base: `feat/lluvia-insights-02b-summary`, tip `3314c83` verified present at branch time).
**Mode**: Strict TDD (RED → GREEN → REFACTOR). Every RED was executed against the untouched source before the implementation existed; for the two single-line source changes (3a.10/3a.12) the line was disabled in place and restored in the same command, per slice 2b's Deviation 5 protocol (no `git stash`, no cross-branch risk).

### Baseline (before slice-3a changes, same branch, source at slice-2b tip)

```
pytest tests/new/geo/rainfall/ tests/test_mutation_targets_rainfall.py -q
=> 409 passed, 1 warning (pre-existing SAWarning, unrelated)

pytest tests/new/ tests/test_mutation_targets_rainfall.py -q
=> 2081 passed, 6 skipped   (the 6th skip is test_martin_reader_grants, which
   needs an isolated superuser DB on this environment)
```

### Final (after slice-3a changes)

```
pytest tests/new/geo/rainfall/test_rainfall_series_consistency.py -q
=> 16 passed   (the new file: 11 task tests + 5 counterexample probes)

pytest tests/new/ tests/test_mutation_targets_rainfall.py -q
=> 2098 passed, 6 skipped, 0 failed   (2081 + 17 new tests, 0 regressions)

pytest tests/new/ -q
=> 1969 passed, 6 skipped, 0 failed   (was 1952 + 6)

ruff check .   => All checks passed!         (exit 0)
ruff format .  => 2 files reformatted, 401 files left unchanged (the 2 are this
                  slice's own new files; re-run after: 403 unchanged)

consorcio-web: npm run typecheck => exit 0
consorcio-web: npx vitest run tests/unit/rainfallApi.test.ts => 9 passed
consorcio-web: full vitest run => see Final Verification below
```

### TDD Cycle Evidence

| Task | Test | RED evidence (executed, against unfixed source) | GREEN evidence |
|---|---|---|---|
| 3a.1-3a.4, 3a.8 | `test_rainfall_series_consistency.py` (8 tests) | `ModuleNotFoundError: No module named 'app.domains.geo.rainfall.series'` — the whole file, 8 failures, before `series.py` existed | All pass after `repository.daily_series_rows`/`baseline_curve_rows` + `series.py`. 3a.8's equality (`curve last point == annual.normal.value`) passed on the FIRST run, which is the evidence the curve is `baseline_cumulatives`' own aggregate at daily resolution rather than a second derivation that happens to agree |
| 3a.13 (route) | `test_series_route_serves_the_pin_and_404s_on_an_unknown_revision` | `assert 404 == 200` — the path did not exist | 200 with the pin fields, the three echoes and 20 points; an unknown revision still 404s |
| 3a.13 (auth) | `test_series_route_requires_authentication` | `assert 404 == 401` — with no route registered, FastAPI 404s BEFORE any router dependency, so the auth claim was unprovable | 401 once the route exists: the router-level `require_admin_or_operator` runs before the handler, exactly as it does for the CSV export |
| 3a.15 (workbook) | `test_series_served_event_is_documented_in_the_observability_workbook` | `assert '`rainfall.series.served`' in <workbook text>` failed | Catalogue row added to `docs/lluvia-v2-observability-workbook.md` §2.1 |
| 3a.12 | `test_backend_api.py::test_analyses_response_discloses_data_revision` | `KeyError: 'data_revision'` with `normalized["data_revision"] = ...` replaced by `pass  # TEMP RED probe` and restored in the same command | Served JSON carries the row's own column value |
| 3a.10 | same test's `assert set(body) <= SNAPSHOT_ROOT_KEYS` | `AssertionError: assert {'analysis_re...evision', ...} <= {...}` with the `"data_revision"` entry removed from `SNAPSHOT_ROOT_KEYS` and restored in the same command | The declared disclosure envelope names every field the router injects |
| 3a.14 | `rainfallApi.test.ts::"snapshot type carries data_revision"` | `tsc` probe: `tests/unit/rainfallApi.test.ts(44,5): error TS2353: Object literal may only specify known properties, and 'data_revision' does not exist in type 'RainfallAnalysisSnapshot'` + `(147,19): error TS2339` | Both errors gone after the interface gains the field; `npm run typecheck` exit 0; vitest 9/9 |
| counterexample (TZ) | `test_series_dates_do_not_shift_under_a_non_utc_session_timezone` | Guard removed (`_utc_day` → bare `.date()`), test re-run: `assert False` — under `SET TIME ZONE 'America/Argentina/Buenos_Aires'` every UTC-midnight row buckets into the previous day | Restored: dates unchanged, all 20 days `available` |
| counterexample (clamp) | `test_a_runaway_disclosure_window_is_clamped_to_the_analysis_year` | Clamp removed, test re-run: `AssertionError: assert 356111 == 365` — a corrupt `available_through` produced 356,111 points from one GET | Restored: exactly 365, last point `2025-12-31` |

**RED verification method**: the new test file was written and executed in full against the slice-2b source before any implementation existed (`ModuleNotFoundError`, captured). For the two single-line source changes and for the two defensive guards, the line was disabled in place, the targeted test re-run to capture the failure, and the source restored in the SAME command — verified afterwards by `rg "TEMP probe"` returning no matches and by the full suite passing.

### Files Changed

| File | Action | What |
|---|---|---|
| `gee-backend/app/domains/geo/rainfall/series.py` | Created | The one series contract (3a.6/3a.9): `build_series(db, revision)` → echoes + `consistent_with_snapshot`/`consistency_reason` + daily points. ONE read (`daily_series_rows` over the D6-widened window) backs both the pin and the displayed points; `_pin` (family rule then digest compare, one-directional); `_normal_curve` (per-year cumulative keyed by `(month, day)`, Feb-29 skipped as a KEY but still accumulated); `_points` (clipped window, `null` never `0.0`, cumulative carried across gaps); `_as_utc`/`_utc_day` (session-TZ-proof day bucketing) |
| `gee-backend/app/domains/geo/rainfall/repository.py` | Modified | 3a.5: `daily_series_rows` (delegates to `intervals_in_window`, projects to ORM-free tuples + `provider_revision`) and `baseline_curve_rows` (the daily rows behind `baseline_cumulatives`, same key, same anti-join, same per-year windows) |
| `gee-backend/app/domains/geo/rainfall/router.py` | Modified | 3a.12: `data_revision` read into a local with the other row fields (before the enqueue that expires the ORM instance) and injected post-normalize; 3a.13: `GET /analyses/{revision}/series` + the `rainfall.series.served` event |
| `gee-backend/app/domains/geo/rainfall/service.py` | Modified | 3a.10: `"data_revision"` added to `SNAPSHOT_ROOT_KEYS` with the reason inline |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_series_consistency.py` | Created | 16 real-PG tests: 3a.1-3a.4, 3a.8 + same-source, lagged-tail, suppressed-baseline, route, auth, workbook + 5 counterexample probes |
| `gee-backend/tests/new/geo/rainfall/test_backend_api.py` | Modified | +1 real-PG test (3a.11 + 3a.10's allow-list half) |
| `gee-backend/tests/new/geo/rainfall/test_prepr_contract_fixes.py` | Modified | Test double updated, not weakened (see Deviations 3) |
| `consorcio-web/src/lib/api/rainfall.ts` | Modified | 3a.14: `data_revision: string` on `RainfallAnalysisSnapshot`, with the cross-check rationale in TSDoc |
| `consorcio-web/tests/unit/rainfallApi.test.ts` | Modified | 3a.14: `snapshot()` annotated `: RainfallAnalysisSnapshot` (so an undeclared field is a compile error) + the new test |
| `docs/lluvia-v2-observability-workbook.md` | Modified | 3a.15: `rainfall.series.served` catalogue row incl. what each `consistency_reason` means and what to do when each dominates |
| `openspec/changes/lluvia-insights/design.md` | Modified | 3a.7: D3 step 2 asymmetry note (extended with the zero-family case and the parity-not-normalization rule); D3 curve-points paragraph gained the read-only and clipped-window statements |
| `openspec/changes/lluvia-insights/tasks.md` | Modified | 3a.1-3a.14 marked `[x]` with inline deviation notes; 3a.15 added |

### Deviations from Design/Tasks

1. **`daily_series_rows` DELEGATES to `intervals_in_window` instead of re-expressing its anti-join** (task 3a.5 says "both anti-joined on supersession (pattern of `intervals_in_window`)"). Following the *pattern* would produce a second, independently-maintained copy of the read whose entire job is to prove that a chart shows the same evidence a stored revision was built from — the one shape that could make that claim quietly false as the two copies drift. The delegation makes "same resolved set as the build" true by construction rather than by review vigilance; the only difference is the projection (ORM-free tuples plus `provider_revision`, which the pin needs and the build took from the adapter batch). `baseline_curve_rows` IS a new query, because no existing read returns per-day baseline rows.
2. **ONE read backs both the pin and the displayed points.** tasks.md describes them as separate concerns. Reading twice would admit a window where a correction lands between the two reads and the chart shows data the pin declared untouched. `build_series` reads the D6-widened set once; the display window is a filter over it. Pinned by `test_series_points_and_pin_read_the_same_resolved_set`, which plants a row into a gap and asserts BOTH halves move.
3. **`test_prepr_contract_fixes.py::test_analysis_route_server_resolves_fingerprint_and_revision` needed its double updated** — the same fixture slice 2b already had to restamp (its Deviation 3). It injects a `SimpleNamespace` revision carrying only `id`/`policy_revision`/`snapshot`; `data_revision` is a NOT NULL column on every real row, so once the route discloses it the double raised `AttributeError`. Added the field AND an assertion that the served body carries it — the double gained coverage rather than a silencer. This was the only regression in the full suite.
4. **The series window is the analysis' own CLIPPED disclosure window**, taken from `annual.selected.provenance.available_through`, not the calendar `comparison_end` and not a live re-derivation. Consequence, asserted: under a 5-day provider lag the series stops at the last published day (20 points, ending Jan 20) instead of trailing 5 empty days a chart would read as a dry spell, and the last cumulative equals `annual.selected.value` exactly. One field, one meaning: the same string is echoed as `available_through` and used as the window bound, so the two cannot drift.
5. **`consistency_reason` was NOT extended for the zero-rows case.** With nothing left to read, the build's family cannot be reconstructed at all. The design fixes the enum at three values, so rather than adding a fourth the exactly-one-family rule is read as written — "not exactly one" covers zero as well as two — and `interval_family_ambiguous` is reported. Documented in both the design note (3a.7) and `_pin`'s docstring, and pinned by `test_no_resolved_rows_report_ambiguous_rather_than_guessing_a_family`.
6. **Feb-29 is omitted from the CURVE, not from the data.** Design says "Feb-29 is omitted from the curve". Implemented as: no curve KEY at `(2, 29)` — that day's point carries `normal_accumulated: null` — while the leap years' own Feb-29 rain still accumulates into their running totals. Any other reading breaks the design's own acceptance rule, since `baseline_cumulatives` (the source of `annual.normal.value`) sums whole `[Jan 1, cutoff]` windows including Feb 29. Proven at both ends by 3a.8: the last point matches `annual.normal.value`, AND the Feb-28 → Mar-1 step is larger than one day's mean, which is exactly the 8 leap years' extra day showing up.
7. **A new event, `rainfall.series.served`, is catalogued in the observability workbook (3a.15, not in tasks.md).** LI2B-005 established the rule that an event firing in production must appear in its own contract document, and pinned it with a test. Rather than extend slice 2b's test file, this slice pins its own event in its own file — same rule, no cross-slice edit.
8. **Two counterexample guards were added beyond the task list and then PROVEN load-bearing by removing them**: UTC-normalized day bucketing (removing it: `assert False` under a Buenos Aires session TZ — the LI1-002 defect class) and a clamp of the day loop to the analysis year (removing it: 356,111 points from one GET on a corrupt `available_through`).

### Observation for a later slice (NOT fixed here — no assigned task, and a fix needs its own RED)

`compute._cutoff_date` and `compute._disclosure_window` call `.date()` / compare against datetimes that come back from `psycopg2` rendered in the **session's** `TimeZone`, so under a non-UTC session TZ `baseline_cutoff_for` can pick a cutoff one day off (the LI1-002 defect class, on the slice-2b code path rather than this one). It is latent today because the deployment's Postgres `TimeZone` is UTC and both the worker and the API inherit it, and because the pin deliberately does NOT normalize (parity with the build is what keeps the digests comparable — Deviation/design note above). Series-side code is defended (`_as_utc`, with an executed proof); the compute-side path is untouched by this slice and is left to a slice that can give it its own RED.

### Author Counterexample Self-Check

| Category | Evidence | Result |
|---|---|---|
| Null / absence | A day with no evidence is `mm: null` + `state: "unavailable"`, never `0.0`, and the cumulative carries across it (`test_series_points_and_pin_read_the_same_resolved_set`); a window opening before the first published day carries NO cumulative at all (`test_window_before_the_first_published_day_has_no_cumulative`); a suppressed `annual.normal` yields no curve rather than a mean over the empty set (`test_no_normal_curve_when_the_baseline_is_suppressed`); zero resolved rows report ambiguous rather than guessing a family (`test_no_resolved_rows_report_ambiguous_rather_than_guessing_a_family`) | Pass |
| Boundaries | The exclusive `window_end` boundary (last point is `window_end − 1 day`, asserted on both the untouched and the lagged fixtures); the leap-year boundary (Feb-29 point present with a null normal, curve continuous across it, 3a.8); the D6 window's own boundary — a row at `year_start − 17d` moves the pin and does NOT enter the display (`test_pin_uses_d6_widened_read_window`); the runaway-window clamp, measured at 356,111 points without it | Pass |
| Concurrency / idempotency | N/A — the route is strictly READ-ONLY: no INSERT, no enqueue, no commit, no marker. `build_series` is a pure function of (the immutable revision row, the rows resolved at read time), so two concurrent calls on the same state return the same answer, and unlike `read_analysis` no polling loop can create work. That is also why LI2B-001's cooldown ladder has nothing to bound here | N/A (reason given) |
| Malicious input / security | Route sits under the router-level `require_admin_or_operator` and returns 401 without it (`test_series_route_requires_authentication`, the ONLY new HTTP surface in this slice); `{revision}` is typed `UUID`, so a non-UUID is rejected at validation and nothing user-controlled reaches SQL — every other query input is derived from the server-built snapshot and bound as a parameter; the response is bounded to at most one year of daily points by the clamp (proven above), so a corrupt row cannot be turned into an unbounded response | Pass |
| Partial failure / recovery | A snapshot too broken to describe itself raises `SnapshotContractError` and the route maps it to **503**, not a 500 — the same refusal the CSV export already makes (`test_a_snapshot_too_broken_to_describe_itself_is_refused_not_charted`, asserted at both the function and the HTTP level). Note the deliberate asymmetry with LI2B-002: there the failing operation was a SIDE EFFECT while the answer was already in memory, so it degraded to a 200; here the read IS the answer, so a failed read must not be dressed up as a chart | Pass |
| State / tenancy / time | Day bucketing is UTC-normalized and proven session-TZ-proof by removing the guard (`assert False` under `SET TIME ZONE 'America/Argentina/Buenos_Aires'`); the pin deliberately does NOT normalize its hashed rows, because parity with the build — not normalization — is what keeps the two digests comparable, and the residual risk is bounded to a false *inconsistent* (design note 3a.7); the displayed window follows the evidence (clipped) while `comparison_end` stays the calendar date, so the owner's disclosure decision is preserved rather than reinterpreted | Pass |

### Workload / PR Boundary

- Mode: chained PR slice (`feature-branch-chain`, per tasks.md's Review Workload Forecast)
- Current work unit: Unit 3a — "series module + consistency pin + `data_revision` exposure (D3)"
- Boundary: starts at `feat/lluvia-insights-02b-summary`'s tip (`3314c83`), ends at this commit — independently mergeable and independently verifiable. Slice 3b (xlsx + TS series/hook contract) consumes `series.build_series` and adds nothing to it
- Estimated review budget impact: ~240 production lines forecast; the actual production diff is 1 new module (~290 lines including its docstrings), 2 repository reads, 3 router lines + one route, 1 service allow-list entry and 1 TS field. Tests and docs carry the rest

### Remaining Tasks (out of this batch's scope)

- [ ] Slice 3b: xlsx Export + TS Contract + Consistency Exposure (3b.1-3b.11)
- [ ] Slice 4: Frontend Chart (4.1-4.10)
- [ ] Ops.1-3: real 1991-2020 backfill runbook execution (owner-run, explicitly NOT this agent's scope)
- [ ] Ops.4-6: doc-nit folds

### Status

14/14 slice-3a tasks complete + 1 addition (3a.15). 2098/2098 backend (6 pre-existing skips), 16/16 in the new file, ruff check + format clean, frontend typecheck exit 0 and vitest green. Ready for review/PR of this work unit, then `sdd-apply` for slice 3b.

## Slice 3a reliability fix round (2026-08-10) — COMPLETE (5/5 findings)

**Branch**: `feat/lluvia-insights-03a-series` (base for this round: slice-3a tip `903ab9a`).
**Mode**: Strict TDD (RED → GREEN). Every RED was executed against the untouched source; for the two "remove the guard and watch it break" proofs (LI3A-003's split read, LI3A-004's interface field) the change was applied in place, the targeted check re-run to capture the failure, and the source restored — verified afterwards by `rg "TEMP RED probe"` returning no matches and by `git diff` on the restored file being empty.

### Baseline (before fix-round changes, same branch)

```
pytest tests/new/ -q
=> 1969 passed, 6 skipped            (exit 0)

pytest tests/new/ tests/test_mutation_targets_rainfall.py -q
=> 2098 passed, 6 skipped            (matches slice-3a apply-progress)

consorcio-web: npx vitest run        => 276 files, 3633 passed
consorcio-web: npm run typecheck     => exit 0 (src only — the LI3A-004 gap itself)
```

### Final (after fix-round changes)

```
pytest tests/new/geo/rainfall/test_rainfall_series_consistency.py -q
=> 20 passed                         (16 pre-round + 4 new)

pytest tests/new/ tests/test_mutation_targets_rainfall.py -q
=> 2102 passed, 6 skipped, 0 failed  (exit 0; +4, exactly the new tests)

ruff check .   => All checks passed!  (exit 0)
ruff format .  => 1 file reformatted (this round's own test file), 402 unchanged

consorcio-web: npm run typecheck     => exit 0, now compiling tests/ as well
consorcio-web: npx vitest run        => 276 files, 3633 passed (unchanged — both
                                        frontend edits are type-level)
```

### TDD Cycle Evidence

| Finding | Test / check | RED evidence (executed, against unfixed source) | GREEN evidence |
|---|---|---|---|
| LI3A-001 (a+b) | `test_a_duplicated_baseline_slot_refuses_the_curve_instead_of_inflating_it`, `test_a_curve_that_disagrees_with_the_stored_normal_is_refused`, + 2 extended | 4 × `KeyError: 'normal_curve_state'`. Plus a deleted throwaway probe that measured the defect itself against the unfixed `_normal_curve`: `PROBE: stored annual.normal.value=61.266666666666666 \| curve last point=77.93333333333334 \| delta=16.66666666666667` — one duplicated 500.0 mm baseline slot, silently averaged into the curve | Refused with `normal_curve_state == "integrity_refused"`, event `rainfall.series.normal_curve_refused` carrying its reason, and the pin/points/stored value all asserted untouched |
| LI3A-002 | `test_series_served_event_is_documented_in_the_observability_workbook` (extended) | `assert 'Zero resolved rows' in <workbook text>` failed | The `consistency_reason` shape table added under §2.1 |
| LI3A-003 | `test_build_series_reads_the_interval_store_exactly_once` (new) | With `build_series` split into two `daily_series_rows` calls: `AssertionError: ['SELECT rainfall_interval_value...', 'SELECT rainfall_interval_value...']` on `assert len(scoped) == 1` — **while `test_series_points_and_pin_read_the_same_resolved_set` passed unchanged in the same run**, which is the finding executed rather than argued | Split restored; 1 scoped SELECT + 1 baseline SELECT, both asserted |
| LI3A-004 | `npm run typecheck` (the command `.github/workflows/frontend.yml`'s `Typecheck` job runs) | With `data_revision` removed from `RainfallAnalysisSnapshot`: exit **2**, `tests/unit/rainfallApi.test.ts(44,5): error TS2353` + `(147,19): error TS2339` + `RainfallDetailPanel.test.tsx(88,5): TS2353`, and **zero `src` errors** — the proof the pre-round gate was blind to all three | Field restored → exit 0. The gate also surfaced two real pre-existing defects, both fixed (see Files Changed) |
| LI3A-005 | `test_baseline_cutoff_does_not_shift_under_a_non_utc_session_timezone` (new) | `assert 60.266666666666666 == 61.266666666666666 ± 6.1e-05` under `SET TIME ZONE 'America/Argentina/Buenos_Aires'` set BEFORE the build, with a 3-day provider lag — the baseline cut at Mar 1 instead of Mar 2 | Both paths cut at Mar 2; the pre-existing series-side TZ test still passes |

### Files Changed

| File | Action | What |
|---|---|---|
| `gee-backend/app/domains/geo/rainfall/temporal.py` | Modified | LI3A-005: `as_utc` / `utc_day` — THE one UTC normalization, next to `buenos_aires_date`, so `compute` and `series` cannot drift apart again |
| `gee-backend/app/domains/geo/rainfall/compute.py` | Modified | LI3A-005: `_cutoff_date` returns `temporal.utc_day(window_end - 1d)` instead of a bare `.date()` |
| `gee-backend/app/domains/geo/rainfall/series.py` | Modified | LI3A-001: `_NormalCurve` NamedTuple (points + state + refusal reason), the slot-duplicate guard, the `math.isclose` acceptance cross-check, `normal_curve_state` in the response, the refusal event; LI3A-005: private TZ helpers deleted in favour of `temporal`'s; `consistent_with_snapshot`'s selected-scope-only meaning documented in place |
| `gee-backend/app/domains/geo/rainfall/router.py` | Modified | `normal_curve_state` added to the `rainfall.series.served` event fields |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_series_consistency.py` | Modified | +4 tests, 3 extended, 1 docstring corrected to claim only what it proves; `_fake_revision` gained a `data_revision` parameter |
| `docs/lluvia-v2-observability-workbook.md` | Modified | LI3A-001: `rainfall.series.normal_curve_refused` catalogue row with a per-reason repair procedure; LI3A-002: the `consistency_reason` shape table; `rainfall.series.served` updated for `normal_curve_state` and for the pin's selected-scope-only meaning |
| `consorcio-web/tsconfig.tests.json` | Created | LI3A-004: the typecheck project for the rainfall contract test surface, with its scope decision documented inline |
| `consorcio-web/package.json` | Modified | LI3A-004: `typecheck` = `tsc --noEmit && tsc --noEmit -p tsconfig.tests.json` |
| `consorcio-web/tests/unit/RainfallDetailPanel.test.tsx` | Modified | Defect the new gate caught: `snapshot()` built a `RainfallAnalysisSnapshot` with no `data_revision` — a fixture the server cannot produce |
| `consorcio-web/tests/hooks/useRainfallAnalysis.test.tsx` | Modified | Defect the new gate caught: `.mock` reached on the unmocked function type (line 129 was the only site missing `vi.mocked(...)`) |
| `openspec/changes/lluvia-insights/design.md` | Modified | D3 "Normal-curve integrity amendment": the acceptance rule promoted to a runtime check, both guards, the tolerance rationale, and the three-valued `normal_curve_state` |
| `openspec/changes/lluvia-insights/review-ledger.md` | Modified | Slice 3a lens + refuter section, the 5 rows, the cleared surfaces, and the resolutions |

### Deviations

1. **`normal_curve_state` is a NEW response field**, not in tasks.md or the pre-round design. Without it a refused curve and a structurally absent one are byte-identical on the wire (`normal_accumulated: null` everywhere), so the fix would have been unobservable by the very operator it exists for. design.md D3 amended.
2. **The refusal REASON is on the event, not in the response.** A chart only needs to know there is no line to draw; an operator needs to know which invariant broke. Keeping the reason off the wire avoids widening a client contract that slice 3b and slice 4 will consume.
3. **A third refusal reason exists beyond the two briefed**: `stored_normal_unreadable`, for a snapshot marking `annual.normal` available with a non-numeric value. Returning `"suppressed"` there would be a lie (nothing suppressed it — the check could not run), and the whole point of the state field is that absence and refusal are different facts.
4. **The duplicate guard keys on `interval_start`, not on the day.** The brief said "detects >1 row per (year, day)". That mirrors nothing: `baseline_cumulatives` guards `COUNT` vs `COUNT DISTINCT interval_start`, and a per-day rule would falsely refuse a legitimately sub-daily baseline while claiming to be its sibling. Detection is in the bucket loop rather than SQL — no extra round trip, and it sees every row the curve consumes, so it cannot miss.
5. **The LI3A-004 gate is scoped to the rainfall contract surface, not to all of `tests/`.** Measured: compiling the whole tests tree reports pre-existing errors in 62 other files, none related to this contract. The tsconfig documents this and says to add files as their errors clear. Shipping a real gate over the contract this SDD owns beats shipping none until an unrelated backlog is paid — which is precisely how the gap survived.
6. **`test_series_points_and_pin_read_the_same_resolved_set` was kept, not deleted or renamed.** Its behavioral assertions (the gap contract) retain value and are referenced from tasks.md 3a.6; what was wrong was its docstring's claim, which now points at the counting test for the structural half.

### Author Counterexample Self-Check

| Category | Evidence | Result |
|---|---|---|
| Null / absence | A suppressed baseline still yields `normal_curve_state: "suppressed"` with no curve (asserted); an `annual.normal` marked available with a non-numeric value refuses rather than pretending to suppress; the zero-resolved-rows pin shape is now documented as a distinct, benign operator case (LI3A-002) | Pass |
| Boundaries | The cross-check's tolerance is bounded from both sides and argued in the code: `rel_tol=1e-9` sits ~6 orders above accumulated float noise (30 years × 62 daily doubles, PostgreSQL `SUM` vs Python accumulation) and ~11 below the measured 16.7 mm defect; a missing last key (structurally impossible outside a Feb-29 cutoff, which suppresses `annual.normal` long before) is treated as unverifiable and refused, not as a pass | Pass |
| Concurrency / idempotency | The route stays strictly READ-ONLY — the guards add no write, no enqueue, no commit. The one-read property they sit beside is now actually measured (LI3A-003), which is the concurrency-relevant half: a split read would admit a correction landing between the two queries | Pass |
| Malicious input / security | No new HTTP surface, no new user-controlled input: every query input still derives from the server-built snapshot. The refusal event logs only ids and enum reasons, no row values, so a corrupt baseline cannot exfiltrate itself through the log | Pass |
| Partial failure / recovery | Both guards refuse the WHOLE curve rather than serving a partial one — a baseline line wrong anywhere is a comparison the reader cannot trust — and refusal degrades the chart, never the response: points, pin and echoes are asserted untouched in the duplicate test. LI3A-004's gate additions (`vite-env.d.ts`, `tests/setup.ts`) were driven by executed failures, so the gate reports defects and not missing-ambient noise | Pass |
| State / tenancy / time | LI3A-005 closes the third appearance of the LI1-002 class and closes it in ONE place both modules import, so a fourth cannot be introduced by copy-drift. Proven by a build executed under a Buenos Aires session zone WITH provider lag — the only combination that reaches it — and the pre-existing series-side TZ test still passes | Pass |

### Status (fix round)

5/5 findings fixed. 2102/2102 backend (6 pre-existing skips), 20/20 in the series file, ruff check + format clean, frontend typecheck exit 0 **with `tests/` compiled for the first time**, vitest 3633 unchanged. Ready for the scoped re-review of this fix diff, then slice 3b.
