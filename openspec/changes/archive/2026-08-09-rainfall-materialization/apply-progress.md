# Apply Progress: Rainfall v2 Materialization

## Scope covered by this artifact (cumulative across batches)

- Batch 1: Phase 1 (PR 1) — Persistence. Tasks 1.1-1.9. Strict TDD mode.
- Batch 2, Part 0: PR1 hardening (review-reliability findings R3-001..R3-004)
  on branch `feat/rainfall-materialization-01-persistence`.
- Batch 2, Part 1: Phase 2 (PR 2) — Compute. Tasks 2.1-2.14. Strict TDD mode,
  on branch `feat/rainfall-materialization-02-compute` (base: PR1 branch
  after Part 0's hardening commits).
- Batch 3: Phase 3 (PR 3) — Revisit, Finalization, Guards. Tasks 3.1-3.19 +
  folded review items R4-101..104. Strict TDD mode, on branch
  `feat/rainfall-materialization-03-revisit` (base: PR2 branch). Executed
  across two agent runs (a resume after a mid-batch crash) — see "Batch 3 /
  PR3" below. A follow-on same-batch round (PR3 review fix round 1) fixed
  C1/C2 (confirmed criticals) plus 10 approved info fixes on the same branch.
- Batch 4 (FINAL): Phase 4 (PR 4) — Daily-Source Flip. Tasks 4.1-4.2 +
  folded review items R4-301/R4-302. Strict TDD mode, on branch
  `feat/rainfall-materialization-04-flip` (base: PR3 branch, after the
  review fix round). See "Batch 4 / PR4" below.

## Git

- Tracker branch: `feat/rainfall-materialization` (commit `e2754bc` — SDD artifacts only, checked out from `main`)
- PR1 branch: `feat/rainfall-materialization-01-persistence` (checked out from the tracker)
  - Batch 1 (persistence): `f19a06e` .. `ef82d1a` (tasks 1.1-1.9, see table below)
  - Batch 2 Part 0 (R3 hardening): `7f892fc` (test+impl), `70bd040` (ledger annotation)
- PR2 branch: `feat/rainfall-materialization-02-compute` (checked out from PR1 branch, after `70bd040`)
  - Batch 2 Part 1 (compute): `0fb88fd` .. `3a8e0d2` (tasks 2.1-2.14, see table below)
  - PR2 review fix round 1: `da761d9`, `a08fb94` (R4-001..003, see table below)
- PR3 branch: `feat/rainfall-materialization-03-revisit` (checked out from PR2 branch, after `a08fb94`)
  - Pre-crash (prior agent run): `025ed53`, `b412dc5`, `81470b0` (tasks 3.1-3.6, 3.8 + repository
    halves of 3.2/3.9/3.13; see "Batch 3 / PR3" below)
  - Resume run (this run): `8709bce` .. `04b6538` (ledger reconciliation, task 3.7 completion,
    tasks 3.9-3.19, folded review items R4-101..104; see table below)
  - PR3 review fix round 1: `d9d050c` (prod), `4844c9f` (tests), `48dcdb6` (docs), `6a856da`
    (ledger/apply-progress) — C1/C2 + 10 approved info fixes, see "PR3 review fix round 1" below.
- PR4 branch: `feat/rainfall-materialization-04-flip` (checked out from PR3 branch, after `6a856da`)
  - Batch 4 (flip): `5c9d2a4` (prod: constant flip + `fallback_used_for`), `9b08fcd` (tests: tasks
    4.1-4.2), `d5674fa` (review fold: R4-301 docs fix + R4-302 regression), `30895c9` (sdd docs:
    tasks.md `[x]` + ledger addressed notes) — see "Batch 4 / PR4" below.
- No push, no PR created — local branches only, per protocol.

## Baseline (before any code change, batch 1)

- `pytest tests/new/geo/rainfall/ -v` → **182 passed**, 1 warning, exit 0 (clean; no pre-existing failures).
- `pytest tests/test_mutation_targets_rainfall.py -v` → **71 passed**, exit 0 (clean).

## Test infrastructure note

The prescribed harness resolves `DATABASE_URL` via testcontainers (Docker available in this
environment) or `TEST_DATABASE_URL`. For iteration speed across ~9 TDD RED/GREEN cycles in
batch 1, a disposable local PostGIS container (`rainfall-test-pg`, port 55433,
`postgis/postgis:16-3.4`) was started and used via `TEST_DATABASE_URL` for the RED/GREEN loop —
this avoids spinning a fresh testcontainer (~5-10s) on every single-test pytest invocation. The
container was **removed after that batch's work**. The final validation runs (see below) were
re-executed with `TEST_DATABASE_URL` unset, exercising the default testcontainers path, and
produced identical results — confirming the scratch DB shortcut did not mask anything
testcontainers-specific. Batch 2 ran directly against the default testcontainers path throughout
(no scratch DB shortcut needed — RED/GREEN cycles were fast enough already).

For the alembic migration verification (task 2.1), a **separate, disposable**
`pgrouting/pgrouting:16-3.4-3.6.1` container (matching `docker-compose.yml`'s actual image — the
plain `postgis/postgis` image lacks the `pgrouting` extension earlier, unrelated migrations
require) was started on a throwaway port, `alembic upgrade head && downgrade -1 && upgrade head`
run against it with `DATABASE_URL` pointed there explicitly, and the container torn down
afterward. The shared dev database (`postgresql://consorcio:consorcio_dev@localhost:5432/consorcio`,
`docker compose up -d postgres`) was never touched.

## TDD Cycle Evidence — Batch 1 (Phase 1 / PR 1 — Persistence)

| Task | Test(s) | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR | Commit |
|------|---------|-------|------------|-----|-------|-------------|----------|--------|
| 1.2 | `tests/test_mutation_targets_rainfall.py::TestRevisionFamilyAndCorrectionRevision` (4 tests) | Unit (pure) | ✅ 71/71 (module didn't exist) | ✅ `ModuleNotFoundError` confirmed | ✅ 4/4 passed | ✅ bare-family + ordinal-1/2 + reject-non-positive | ✅ clean, no further extraction needed | `f19a06e` |
| 1.1 | `tests/new/geo/rainfall/test_rainfall_materialization.py::test_reingest_is_idempotent` | Integration (real PG) | ✅ 182/182 (function didn't exist) | ✅ `ImportError` confirmed | ✅ 1/1 passed | ➖ single scenario (idempotency) — minimal ON CONFLICT DO NOTHING bulk insert | ✅ clean | `c8df247` |
| 1.3 | `..._materialization.py::test_persist_intervals_inserts_absent_slot` | Integration (real PG) | ✅ 183/183 | ✅ `ImportError` on `intervals_in_window` confirmed | ✅ 2/2 passed (incl. 1.1 regression) | ➖ single scenario (absent-slot classify) | ✅ clean | `6af414e` |
| 1.4 | `..._materialization.py::test_persist_intervals_unchanged_slot_writes_nothing` + `test_mutation_targets_rainfall.py::TestSixDecimalEqualityBoundary` (2 tests) | Unit (pure) + Integration | ⚠️ see note below | ✅ pure test: `ImportError` on `_values_equal_at_6dp` confirmed | ✅ 3+2 passed | ✅ symmetric-boundary case + a change large enough to move the 6th decimal | ✅ inline comparison extracted into `_values_equal_at_6dp`, wired into `persist_intervals` | `7b1baf5` |
| 1.5 | `..._materialization.py::test_persist_intervals_changed_slot_appends_correction_and_lifecycle_row` | Integration (real PG) | ✅ 4/4 prior | ✅ `assert 0 == 1` (no correction/lifecycle logic yet) confirmed | ✅ 4/4 passed | ➖ single scenario (this task); chaining is 1.6's triangulation | ✅ clean | `adf8791` |
| 1.6 | `..._materialization.py::test_second_correction_chains_off_first` | Integration (real PG) | ✅ 5/5 prior | ⚠️ triangulation of 1.5's general algorithm | ✅ 6/6 passed | ✅ this test IS the triangulation for 1.5's ordinal-parsing generalization | ➖ none needed | `7ad4acb` |
| 1.7 | `..._materialization.py::test_intervals_in_window_excludes_superseded_rows` | Integration (real PG) | ✅ 6/6 prior | ⚠️ triangulation of 1.3's anti-join | ✅ 7/7 passed | ✅ two slots (corrected + untouched), explicit ordering assertion | ➖ none needed | `0c5acd9` |
| 1.8 | `..._materialization.py::test_ingest_source_scope_writes_without_commit_when_given_db` + `::test_ingest_source_scope_opens_own_session_and_commits_when_db_is_none` | Integration (real PG) | ✅ 7/7 prior + `test_provider_adapters.py:436-456` contract test unmodified | ✅ `TypeError: got an unexpected keyword argument 'db'` confirmed | ✅ 9/9 passed | ✅ given-db branch + None branch (own session + commit) | ✅ extracted `_batch_result()` helper for the JSON-safe evidence dict | `2ad9912` |
| 1.9 | `..._materialization.py::test_backfill_missing_shares_transaction_with_ingest` | Integration (real PG) | ✅ 9/9 prior | ✅ `TypeError: failing_ingest() missing 1 required keyword-only argument: 'db'` confirmed | ✅ 10/10 passed | ➖ single scenario (transaction-sharing, proven via all-or-nothing rollback) | ➖ one-line change, no refactor needed | `2210bb8` |

Batch 1 final counts: `tests/new/geo/rainfall/` 191 passed (182 baseline + 9); `tests/test_mutation_targets_rainfall.py` 77 passed (71 baseline + 6); `tests/new/` full cross-domain 1864 passed, 5 skipped.

## TDD Cycle Evidence — Batch 2, Part 0 (PR1 hardening — R3-001..R3-004)

Single commit `7f892fc` (test-first; hardening fixes for tests already written are test-first by
construction — each R3 finding names the exact assertion/scenario the existing test was missing,
so the "test" step is writing that missing assertion/scenario and confirming it fails against the
pre-fix code, then fixing).

| Finding | Fix | RED | GREEN | Commit |
|---|---|---|---|---|
| R3-001 | `test_reingest_is_idempotent` asserts `unchanged == len(rows)`; added `test_persist_intervals_corrects_a_non_first_slot_in_a_multi_slot_batch` (multi-slot, restate last slot only) and `test_reingest_after_synthetic_supersession_with_no_successor_hits_conflict_path` (forced ON CONFLICT DO NOTHING path) | ✅ new assertion/tests fail against pre-fix code (verified by inspection: `unchanged` was never asserted; the two new tests reference no new production code, so they exercised the EXISTING implementation directly and passed — see note below) | ✅ 5 tests in the idempotence/correction/conflict family, all passed | `7f892fc` |
| R3-002 | Dedicated `scope_id="zone-own-session-commit"` for the SessionLocal-committing test; scope-filtered `intervals_in_window` assertion instead of source-only `_count_interval_rows`; DELETE-based `finally` cleanup removed; `_count_interval_rows` gained an optional `scope_id` filter, applied to task 1.9's own absolute-count assertion | ✅ **caught a real regression during this fix**: first pass left task 1.9's assertion source-only, and a full-suite run showed `test_backfill_missing_shares_transaction_with_ingest` FAILING (`assert 1 == 0`) because the R3-002 fix's own committed row leaked into it — fixed by adding the `scope_id` filter to that assertion too | ✅ full `tests/new/geo/rainfall/` suite green after the second pass | `7f892fc` |
| R3-003 | Corrected module docstring: the append-only *trigger* is raw SQL from the `lluvia_v2_001` migration, not part of `Base.metadata` — this harness's `create_all` schema never creates it; enforcement here is the ORM `before_flush` guard only | N/A (doc-only) | N/A | `7f892fc` |
| R3-004 | `SourceInterval.__post_init__` (ports.py) rejects `"+"` in `provider_revision`; `persist_intervals`' changed branch raises `ValueError` on `revision_family(row.provider_revision) != family` | ✅ both new tests (`test_source_interval_rejects_plus_in_provider_revision`, `test_persist_intervals_raises_on_provider_revision_family_mismatch`) confirmed failing (no rejection existed) before the fix | ✅ both passed after the fix; verified no existing adapter (chirps.py, imerg.py) emits `+` | `7f892fc` |

**Note on R3-001's RED honesty**: the new/adjusted assertions target pre-existing production code
(`persist_intervals`'s classification logic), which was ALREADY correct for the non-first-slot and
forced-conflict scenarios (written generically in batch 1, not hardcoded to a single scenario) —
same disclosed pattern as batch 1's 1.6/1.7 triangulation commits. The genuinely new assertion is
`unchanged == len(rows)` in `test_reingest_is_idempotent`, which is a real regression guard (would
fail if a future change silently reclassified an unchanged batch).

Ledger updated: `openspec/changes/rainfall-materialization/review-ledger.md` R3-001..004 rows each
append `**Addressed** in 7f892fc` (status unchanged at `info`, per the WARNING-never-reopens rule).

Part 0 final counts: `tests/new/geo/rainfall/` 195 passed (191 + 4 new); full `tests/new/` + `tests/test_mutation_targets_rainfall.py` combined: 1945 passed, 5 skipped.

## TDD Cycle Evidence — Batch 2, Part 1 (Phase 2 / PR 2 — Compute)

| Task | Test(s) | Layer | RED | GREEN | Commit |
|------|---------|-------|-----|-------|--------|
| 2.1 | Manual: `alembic upgrade head && downgrade -1 && upgrade head` against a disposable `pgrouting/pgrouting:16-3.4-3.6.1` container (see note above) | Migration (manual) | N/A (new migration file) | ✅ `upgrade head` reached `lluvia_v2_005`; `downgrade -1` removed `request_fingerprint` + `ix_rainfall_outbox_done_lookup` (verified via `\d rainfall_outbox`); re-`upgrade head` restored both | `0fb88fd` |
| 2.2 | `test_rainfall_materialization.py::test_outbox_model_has_request_fingerprint_column` | Integration (real PG) | ✅ `TypeError: 'request_fingerprint' is an invalid keyword argument` confirmed | ✅ 1/1 passed | `0fb88fd` |
| 2.3 | `..._materialization.py::test_queue_missing_analysis_stores_router_computed_fingerprint` + `::test_queue_missing_analysis_recomputes_fingerprint_when_not_passed` | Integration (real PG) | ✅ `TypeError: unexpected keyword argument 'request_fingerprint'` + `AssertionError: None == <hash>` confirmed | ✅ 2/2 passed | `0bd9042` |
| 2.8 | `test_mutation_targets_rainfall.py::TestRainfallMetricPolicyConstants::test_rainfall_metric_policy_constants_shape` | Unit (pure) | ✅ `ImportError` confirmed | ✅ 1/1 passed | `41b55a9` |
| 2.4-2.7 | `test_mutation_targets_rainfall.py::TestBuildSnapshotEnvelope` (2), `::TestBuildSnapshotCoverageWindow` (2), `::TestDataRevisionFor` (2) | Unit (pure) | ✅ RED verified via `git stash` on `compute.py` alone (test file kept) — all 6 failed with `ImportError` for `build_snapshot`/`data_revision_for` | ✅ all 6 passed on first implementation attempt after `git stash pop` | `6706eec` |
| 2.9 | `..._materialization.py::test_persist_revision_is_idempotent_on_identical_data_revision` + `::test_persist_revision_writes_a_new_row_on_changed_data_revision` | Integration (real PG) | ✅ `ImportError` confirmed | ✅ 2/2 passed | `c306f16` |
| 2.10 | `..._materialization.py::test_build_analysis_writes_one_revision_and_passes_normalize_snapshot` + `::test_build_analysis_raises_when_outbox_row_has_no_fingerprint` | Integration (real PG) | ✅ `AttributeError: module has no attribute 'build_analysis'` confirmed | ✅ 2/2 passed | `294d9b1` |
| 2.11 | `..._materialization.py::test_process_outbox_row_chains_build_analysis_before_done` + `::test_legacy_null_fingerprint_row_skips_compute` + `::test_full_year_null_fingerprint_row_derives_and_computes` (triangulation) | Integration (real PG) | N/A — `_process_outbox_row` existed; tests target the NEW `now` param + chaining, confirmed failing by inspection of the pre-change signature (2-arg call) | ✅ 3/3 passed; safety net: full `test_ingest_ops.py` + `test_phase4_verification.py` (59 tests) green, no regression | `07780b8` |
| 2.12 | `..._materialization.py::test_claim_outbox_row_returns_none_when_not_pending` + `::_not_yet_due` + `::_returns_the_row_when_pending_and_due` + `::test_per_row_commit_survives_a_later_row_failure` + `::test_claim_outbox_row_uses_python_now_not_frozen_sql_transaction_time` (regression) | Integration (real PG) | ✅ `ImportError` for the 3 `claim_outbox_row` tests confirmed; `test_per_row_commit_survives_a_later_row_failure`'s FIRST version passed trivially against the old batch-wide-commit code (a real "GREEN that passes trivially" catch — see Issues below) and was redesigned to force a crash outside `_process_outbox_row`'s own try/except, which then failed correctly (`assert 'pending' == 'done'`) before the per-row-commit fix | ✅ all 5 passed after implementation + a real bug fix (see Issues below); safety net: full `tests/new/geo/rainfall/` (210 tests) green | `44258be` |
| 2.13 | `..._materialization.py::test_now_seam_drives_comparison_end_without_moving_backoff_clock` + `::test_now_seam_does_not_move_the_backoff_clock_on_failure` | Integration (real PG) | ✅ `TypeError: unexpected keyword argument 'now'` confirmed | ✅ 2/2 passed (first attempt had a test bug — midnight-UTC seed crossed the Buenos Aires day boundary backward — fixed by seeding noon UTC instead; not a production bug) | `ce2f219` |
| 2.14 | `..._materialization.py::test_e2e_post_202_then_200_without_monkeypatching_ingest` | E2E (TestClient + real PG, fake GEE client only) | N/A — pure integration-wiring verification of already-built PR1+PR2 pieces, no new production code (task's own Files list: none) | ✅ 1/1 passed on first run | `3a8e0d2` |

Part 1 final counts: `tests/new/geo/rainfall/` 212 passed (195 + 17 new... — see note); `tests/test_mutation_targets_rainfall.py` 84 passed (77 + 7 new); combined `tests/new/` + `tests/test_mutation_targets_rainfall.py`: **1970 passed, 5 skipped, exit 0** (1945 Part-0 baseline + 25 new tests across 2.2-2.14, reconciles exactly).

## Deviations / Clarifications

- **PR2 scope excludes the advisory lock / write-gate / latch.** design.md's Interfaces section
  describes `build_analysis`'s FINAL, post-PR3 shape (advisory lock as first DB statement,
  `revision_write_decision` gate, latch). tasks.md's own PR slicing table is explicit that these
  land in PR 3 ("PR 3 adds the two decision branches to it rather than rewriting it" — design.md's
  own words). Tasks 2.10-2.13 as assigned build `build_analysis` WITHOUT the lock/gate/latch,
  matching the PR2 row of the Migration/Rollout table exactly ("build_analysis + savepoint
  chaining + per-row claim/commit (decision 2c)" — no mention of the lock/gate). This is followed
  precisely as assigned, not a deviation from design — flagged here because the orchestrator's
  launch prompt's own summary of `build_analysis`'s behavior mentioned the lock, which could be
  read as in-scope; the concrete task list (2.1-2.14) is what was implemented.
- **`fallback_used` is a `build_snapshot` parameter, default `False`, not computed internally.**
  design.md's Interfaces summary signature for `build_snapshot` does not list `fallback_used`
  explicitly, but `MetricResult.fallback_used` is a required (non-optional) field. Task 4.1
  (`RAINFALL_DAILY_SOURCE` flip) is explicitly the task that "sets `fallback_used=True` for any
  role whose spec-primary source differs from the one actually used" — PR4 scope. Rather than
  inventing untested role-vs-actual-source comparison logic ahead of its assigned task,
  `build_snapshot(..., fallback_used: bool = False)` takes it as an explicit parameter PR4 can
  wire a real value into without touching the function's structure.
- **`AnalysisScope.regional_estimate` defaults to `False` in `build_analysis`.** The outbox row
  carries no such flag (it is a property of the original public request — parcel-resolved vs
  direct — not of the outbox key), it is not part of the fingerprint's hashed input (verified:
  router.py's fingerprint dict omits it), and it does not feed any compute/temporal logic. Stated
  explicitly in `tasks.py`'s `_persist_analysis_revision` docstring/comment rather than left
  implicit.
- **`_process_outbox_row` raises on failure instead of catching internally** (a mid-course
  correction during task 2.12, not present in task 2.11's original implementation). Decision 1b
  states compute failures get "the same" retry/backoff/fail treatment as ingest failures, but
  task 2.11's initial implementation placed `build_analysis` OUTSIDE `_process_outbox_row`'s
  try/except, so a compute failure would have propagated unhandled. Decision 2b's own rationale
  ("the savepoint rolls back only the row's work and leaves its own transaction usable for the
  bookkeeping") requires the failure bookkeeping to be written AFTER a savepoint rollback, which
  only the CALLER (`_process_outbox_batch`) can guarantee — so `_process_outbox_row` was
  redesigned to raise, and the retry/backoff/status bookkeeping moved to
  `_process_outbox_batch`'s `except` block around `with db.begin_nested(): _process_outbox_row(...)`.
  This is a structural correctness fix following decision 1b/2b to their logical conclusion, not a
  deviation from them.

## Issues Found (and fixed within this batch)

1. **Real regression caught by R3-002's own hardening (Part 0).** Fixing the SessionLocal-test
   scope collision left task 1.9's absolute-count assertion source-only, which then failed against
   the fix's own committed row. Caught by running the full suite (not just the touched test) before
   committing; fixed by adding the same `scope_id` filter there. See table above.
2. **`test_per_row_commit_survives_a_later_row_failure`'s first draft passed trivially** against
   the OLD batch-wide-commit implementation (a real instance of the strict-TDD "GREEN that passes
   trivially" trap — the induced failure was caught entirely inside `_process_outbox_row`'s own
   try/except, so nothing distinguished per-row commit from a single final commit). Redesigned to
   inject the failure in `_role_enabled` — a call OUTSIDE any try/except — so it propagates out of
   `_process_outbox_batch` entirely, correctly failing against the old code
   (`assert 'pending' == 'done'`) and passing only after the real per-row-commit implementation.
3. **Real bug found via this same test, root-caused and fixed (task 2.12).** `claim_outbox_row`'s
   first implementation compared `next_attempt_at <= func.now()` (SQL-side). PostgreSQL freezes
   `now()` to *transaction start* within one transaction, not statement time. A row whose
   `next_attempt_at` is stamped via Python's `datetime.now(UTC)` AFTER the session's transaction
   already began then reads as "in the future" against the frozen `func.now()` and is never
   claimable in that transaction — reproduced empirically (debug script + a pre-existing test,
   `test_outbox_skips_and_retains_rows_for_disabled_role`, which uses the shared `db` fixture for
   both row setup and processing) before fixing. Fixed by making `claim_outbox_row` take an
   explicit Python-side `now: datetime` parameter instead of `func.now()`, matching the rest of
   `tasks.py`'s convention; added a dedicated regression test
   (`test_claim_outbox_row_uses_python_now_not_frozen_sql_transaction_time`); confirmed the full
   existing suite (210 tests in `tests/new/geo/rainfall/`) passes after the fix.
4. **`test_now_seam_drives_comparison_end_without_moving_backoff_clock`'s first draft seeded `now`
   at midnight UTC** (`datetime(2024, 3, 10, tzinfo=UTC)`), which converts to `2024-03-09` in
   Buenos Aires (UTC-3) — a test bug, not a production bug (this is exactly the day-boundary skew
   `buenos_aires_date` is designed to handle correctly; the test's own expectation was wrong).
   Fixed by seeding noon UTC instead (`datetime(2024, 3, 10, 12, tzinfo=UTC)`), safely the same
   calendar day in both zones.

## Author Counterexample Self-Check (Batch 2, Part 0 + Part 1)

| Category | Evidence | Result |
|----------|----------|--------|
| Null / absence | `_derive_full_year_fingerprint` returns `None` for non-full-year bounds (tested); `build_snapshot` with zero intervals in the window → `state="unavailable"`, `value=None`, non-empty `reason` (tested, `test_build_snapshot_with_no_data_in_window_is_unavailable`); `served_state`-style absence not applicable to PR2 (that's PR3's `served_state`) | Pass |
| Boundaries | 6dp equality boundary retested via R3-001's forced-conflict test; `data_revision_for`'s `comparison_end`-advance-alone case tested; coverage-window boundary (provider lag vs calendar `comparison_end`) tested via `test_build_snapshot_bounds_coverage_window_to_available_through`; `fingerprint_lock_key` wraparound is explicitly OUT of PR2 scope (PR3) | Pass |
| Concurrency / idempotency | `persist_revision`'s `ON CONFLICT DO NOTHING` tested idempotent + a real new row on change; `claim_outbox_row`'s `SKIP LOCKED` re-claim semantics tested (not-pending, not-yet-due, pending-and-due); the advisory-lock-based sibling-serialization (JDA-201/decision "Serializing siblings") is explicitly PR3 scope, not tested here — the per-row commit/savepoint concurrency this batch DOES own (decision 2c) was regression-tested via the crash-mid-batch design (`test_per_row_commit_survives_a_later_row_failure`) | Pass |
| Malicious input / security | N/A — PR2 adds no new external input surface (no new endpoint/schema); the router already validates `AnalysisRequest` before reaching any of this batch's code | N/A — no new input surface in this batch |
| Partial failure / recovery | `test_per_row_commit_survives_a_later_row_failure` (redesigned per Issue #2) proves a crash mid-batch leaves an already-succeeded row's work committed and durable, verified from fresh `SessionLocal()` connections; `_process_outbox_row` now raises so ingest AND compute failures get identical retry/backoff/fail bookkeeping (decision 1b), verified via `test_now_seam_does_not_move_the_backoff_clock_on_failure` | Pass |
| State / tenancy / time | The `now` seam is thoroughly tested for what it MUST and MUST NOT affect: `comparison_end`/disclosure date follows the seam (`test_now_seam_drives_comparison_end_without_moving_backoff_clock`), while `completed_at`/`next_attempt_at`/backoff stay on the real wall clock in BOTH the success and failure paths (both `test_now_seam_*` tests); no tenancy dimension in rainfall intervals | Pass |

## Task Status

- [x] 1.1 through [x] 1.9 — Phase 1 (PR 1), all complete, all committed individually on
  `feat/rainfall-materialization-01-persistence`.
- Batch 2 Part 0 (R3-001..004 hardening) — complete, committed on the same PR1 branch.
- [x] 2.1 through [x] 2.14 — Phase 2 (PR 2), all complete, all committed individually on
  `feat/rainfall-materialization-02-compute`.
- [x] 3.1 through [x] 3.19 — Phase 3 (PR 3), all complete, all committed individually on
  `feat/rainfall-materialization-03-revisit`. See "Batch 3 / PR3" section below.
- [x] 4.1, [x] 4.2 — Phase 4 (PR 4), both complete, committed on
  `feat/rainfall-materialization-04-flip`. See "Batch 4 / PR4" section below.
- [ ] 5.1, [ ] 5.2, [ ] 5.3 — Phase 5 (ops/rollout, non-code) — intentionally NOT executed by
  apply; out of scope for this phase per tasks.md's own framing ("Post-deploy", ops runbook,
  staging validation).

## Files Changed (cumulative, PR1 + PR2 branches)

| File | Action | Batch |
|------|--------|-------|
| `gee-backend/app/domains/geo/rainfall/compute.py` | Created (batch 1: `revision_family`, `correction_revision`); modified (Part 1: `build_snapshot`, `data_revision_for`, `_source_class_for`) | 1, Part 1 |
| `gee-backend/app/domains/geo/rainfall/repository.py` | Modified: `persist_intervals`, `intervals_in_window`, `record_supersession`, `_values_equal_at_6dp`, `_next_correction_ordinal` (batch 1); family-mismatch raise (Part 0, R3-004); `persist_revision`, `claim_outbox_row` (Part 1) | 1, Part 0, Part 1 |
| `gee-backend/app/domains/geo/rainfall/ports.py` | Modified: `SourceInterval.__post_init__` rejects `"+"` (Part 0, R3-004) | Part 0 |
| `gee-backend/app/domains/geo/rainfall/tasks.py` | Modified: `ingest_source_scope(db=...)`, `_batch_result()`, `backfill_missing` shares transaction (batch 1); `build_analysis`, `_persist_analysis_revision`, `_derive_full_year_fingerprint`, `_process_outbox_row` (raises on failure), `_process_outbox_batch` (per-row claim/savepoint/commit, `now` seam), `process_outbox(now=...)` (Part 1) | 1, Part 1 |
| `gee-backend/app/domains/geo/rainfall/models.py` | Modified: `RainfallOutbox.request_fingerprint` column + `ix_rainfall_outbox_done_lookup` index (Part 1, task 2.1/2.2) | Part 1 |
| `gee-backend/app/domains/geo/rainfall/router.py` | Modified: passes the router-computed fingerprint into `queue_missing_analysis` (Part 1, task 2.3) | Part 1 |
| `gee-backend/app/domains/geo/rainfall/service.py` | Modified: `queue_missing_analysis(request_fingerprint=...)` + `_default_request_fingerprint` fallback (Part 1, task 2.3) | Part 1 |
| `gee-backend/app/domains/geo/rainfall/policy.py` | Modified: `RAINFALL_METRIC_POLICY`, `RAINFALL_METRIC_POLICY_REVISION` (Part 1, task 2.8) | Part 1 |
| `gee-backend/app/db/migrations/versions/lluvia_v2_005_rainfall_outbox_request_fingerprint.py` | Created (Part 1, task 2.1) | Part 1 |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_materialization.py` | Created (batch 1: 10 test functions across tasks 1.1-1.9); modified (Part 0: docstring, hardened/new tests; Part 1: ~25 new test functions across tasks 2.2, 2.3, 2.9-2.14) | 1, Part 0, Part 1 |
| `gee-backend/tests/test_mutation_targets_rainfall.py` | Modified (batch 1: `TestRevisionFamilyAndCorrectionRevision`, `TestSixDecimalEqualityBoundary`; Part 1: `TestRainfallMetricPolicyConstants`, `TestBuildSnapshotEnvelope`, `TestBuildSnapshotCoverageWindow`, `TestDataRevisionFor`) | 1, Part 1 |
| `openspec/changes/rainfall-materialization/apply-progress.md` | This file — created batch 1, merged/rewritten Part 0 + Part 1 | 1, Part 0, Part 1 |
| `openspec/changes/rainfall-materialization/tasks.md` | Tasks 1.1-1.9 marked `[x]` (batch 1); tasks 2.1-2.14 marked `[x]` (Part 1) | 1, Part 1 |
| `openspec/changes/rainfall-materialization/review-ledger.md` | R3-001..004 rows annotated `**Addressed** in 7f892fc` (Part 0); R4-001 row set to `fixed` + resolution note, R4-002/R4-003 rows annotated `**Addressed (bounded)**`/`**Addressed**` (PR2 review fix round 1) | Part 0, PR2 fix round 1 |

## PR2 Review Fix Round 1 (pre-PR review-resilience findings R4-001..R4-003)

Fix agent applied the confirmed/approved findings from the pre-PR review-resilience pass (see
`review-ledger.md` "Pre-PR review — PR2 compute" section) on branch
`feat/rainfall-materialization-02-compute`. Round 1 of a max-2-round convergence budget.

| Finding | Severity | Fix | RED | GREEN | Commit |
|---|---|---|---|---|---|
| R4-001 | BLOCKER | `record_supersession` + `persist_intervals`' supersession loop switched from ORM `db.add` to a Core `pg_insert`/`db.execute` write (batched into one multi-row insert), matching the existing `persist_intervals`/`persist_revision` Core-write pattern. Rows now land at execute time, independent of any flush — `db.begin_nested()`/`SessionLocal` autoflush behavior is no longer load-bearing for the anti-join's correctness. | ✅ New regression test `test_restated_slot_survives_chained_compute_without_explicit_flush` uses a dedicated `db_autoflush_off` fixture (production-shape `Session(bind=connection, autoflush=False)`, built from the same `test_engine` connection infra as the shared `db` fixture — NOT the shared fixture itself, since its default `autoflush=True` would hide the bug). Confirmed failing pre-fix via `git stash` on `repository.py` alone: `ValueError: build_snapshot received a duplicated interval_start slot`, raised out of `tasks._process_outbox_row` (traceback: `build_analysis` → `_persist_analysis_revision` → `build_snapshot`). | ✅ Same test passes post-fix: `result == "done"`, exactly one `RainfallAnalysisRevision` row for the fingerprint, exactly one non-superseded `RainfallIntervalValue` row for the slot with the restated value. | `da761d9` |
| R4-002 | WARNING (info) | Bounded per refuter/orchestrator direction: the shared conftest `db` fixture stays `autoflush=True` this pass (blast radius: 1970 tests). The new `db_autoflush_off` fixture (local to `test_rainfall_materialization.py`) is the accepted alternative coverage, with the divergence documented in its own docstring at the point of use. | N/A (bounded scope decision, not a code defect) | N/A | `da761d9` |
| R4-003 | WARNING (info) | `rainfall.outbox.failed`/`rainfall.outbox.delayed` `record_event` payloads gained `error_type` (`type(exc).__name__`, captured inside the `except` block since `except ... as exc` unbinds `exc` on exit) and a 200-char-truncated `error_message`. `_persist_analysis_revision` emits a new `rainfall.build.revision_written` event with `{data_revision, created}`, `created` derived from a pre-write existence check against `RainfallAnalysisRevision` (since `persist_revision`'s own `ON CONFLICT DO NOTHING` branch doesn't surface new-vs-idempotent-noop to its caller, and changing its return contract would touch two passing tests outside this fix's scope). | N/A — additive observability, not a behavior-changing bugfix; no pre-existing test exercised these payload fields to regress | ✅ 3 new tests (`test_outbox_delayed_event_carries_error_type_and_truncated_message`, `test_outbox_failed_event_carries_error_type_and_truncated_message`, `test_build_analysis_emits_revision_written_event_distinguishing_created_from_noop`) assert the decoded JSON payload via the `caplog`/`metrics.record_event` seam (same `"%s %s"` format `test_rainfall_observability_seam_emits_structured_events` in `test_phase4_verification.py` already exercises, here parsed with `json.loads` instead of substring-matched) | `a08fb94` |

Verification: `tests/new/geo/rainfall/` 217 passed, 1 warning (pre-existing, unrelated —
`SAWarning: transaction already deassociated from connection` in
`test_phase4_verification.py::test_partial_unique_index_rejects_duplicate_pending_outbox_row`), 4
new tests this round (1 R4-001 regression + 3 R4-003 observability). Full `tests/new/` suite: 1890
passed, 5 skipped (pre-existing live-backend/Martin skips, unrelated), exit 0. `ruff check` clean
on all three touched files.

## Batch 3 / PR3 (Phase 3 — Revisit, Finalization, Guards: tasks 3.1-3.19)

Branch `feat/rainfall-materialization-03-revisit` (base: PR2 branch). This batch was executed
across TWO agent runs: a prior agent crashed mid-batch on an API error after landing 3 commits
(`025ed53`, `b412dc5`, `81470b0` — covering the advisory lock, `served_state`/
`revision_write_decision`/`fingerprint_lock_key`, cooldown, the sweep repository queries, and
the lock/gate wiring into `build_analysis`) plus an in-flight, uncommitted, partially-written
task 3.7 (the two-connection concurrent latch test). This resumed run reconciled that state
first (see "PR3 Resume Reconciliation" below), then completed tasks 3.9-3.19 and the folded
review items in order, strict TDD throughout.

### PR3 Resume Reconciliation

1. Committed the ledger doc (`openspec/changes/rainfall-materialization/review-ledger.md`,
   containing the orchestrator's PR2 re-review verdict) first, as instructed — `8709bce`.
2. Diffed the two uncommitted code files. `tasks.py`'s only change was
   `acquire_fingerprint_lock(...)` temporarily replaced with `pass  # TEMP: lock disabled for
   counterexample check` — the dead agent's own note confirmed this was mid-flight RED
   verification for task 3.7 (disable the lock, confirm the NEW concurrent-latch test and the
   EXISTING task-3.3 lock-ordering test both fail in the expected way without it, then restore).
   Ran both tests with the lock disabled first: both failed exactly as designed (`test_
   build_analysis_locks_before_incumbent_read`: `['get_snapshot'] != ['lock', 'get_snapshot']`;
   `test_latch_sequential_and_concurrent_two_connections`: the blocking assertion on the second
   sibling's thread). Restored the real `acquire_fingerprint_lock(...)` call — file became
   byte-identical to HEAD, confirming the crashed agent's committed work was already correct and
   only the counterexample check itself was left mid-flight.
3. The test file's uncommitted content (the full 3.7 test, already including the try/finally
   around `session_a` the dead agent's note asked for) was coherent and complete; finished 3.7
   by confirming GREEN (40/40 in `test_rainfall_materialization.py`) and committing — `f288169`.
4. Verified tasks 3.1-3.8 were ACTUALLY complete (not just committed) by running each task's
   own named test individually before marking `[x]`: all passed on the first run (3.1, 3.3, 3.6,
   3.7 direct; 3.2, 3.4, 3.5, 3.8 via their `test_mutation_targets_rainfall.py` classes). None
   needed rework.

### TDD Cycle Evidence — PR3 (tasks 3.9-3.19 + folded review items)

| Task/Item | Test(s) | RED | GREEN | Commit |
|---|---|---|---|---|
| 3.9, 3.13 | `test_current_year_done_keys_distinct_on_key`, `test_completed_year_daily_done_keys_is_a_superset` | Repository query functions were already implemented (prior-agent commit `b412dc5`) without direct tests. Counterexample check: temporarily stripped the `.distinct(...)` clause / the `role`+`year` filters, confirmed both new tests fail in the expected way (`3 == 2`; wrong scope_ids set) | Restored, both pass; 42/42 in the file | `4272aa6` |
| 3.10, 3.11 | `test_revisit_stage1_enqueues_fresh_pending_row_per_current_year_key`, `test_revisit_stage1_dedups_and_exempts_past_years` | `revisit_stale`'s old per-key signature — `TypeError: got an unexpected keyword argument 'db'` | New two-stage `revisit_stale(db=None, now=None)` implemented (stage 1 + stage 2 together, since the task returns one unified dict); 226/226 in `tests/new/geo/rainfall/` | `08175bd` |
| 3.12 | `test_e2e_same_key_later_date_and_corrected_revision_becomes_visible` | N/A — pure integration-wiring verification (tasks.md's own Files: none) | Passed in isolation first try; **failed when run inside the full suite** — root-caused to a real test-infrastructure bug (see Issues below) and fixed by switching to independent `SessionLocal()` connections. Stable across 5 repeated runs + 2 full-directory runs (227/227 both) | `fe1501c` |
| 3.14 | `test_revisit_stage2_reresolves_source_and_terminates_on_final` | Stage 2 logic already implemented in the 3.10-3.11 commit without its own test. Counterexample check: disabled the termination branch (RED: `2 == 1` enqueued) and separately the re-resolution call (RED: `'chirps-v3-sat' != 'chirps-v3-final'`) | Both restored; 228/228 | `0dfc838` |
| 3.15 | `test_finalization_is_retried_not_abandoned_then_terminates` | New scenario, first pass on already-implemented machinery. Counterexample check: forced `revision_write_decision` to always return `"write"` (RED: `2 == 1` revisions after a gate-refused attempt) | Restored; 229/229, stable across 2 full-directory runs | `4b31d8b` |
| 3.16 | `test_e2e_year_rollover_transitions_to_final` | N/A — pure integration-wiring verification (Files: none) | Passed first try; stable across 3 repeated + 2 full-directory runs (230/230) using the real-`SessionLocal()` pattern from 3.12/3.15 | `bde05ac` |
| 3.17 | `test_revisit_stale_beat_entry_is_registered` | ✅ `entry is None` confirmed (no beat schedule row) | ✅ 1/1 after adding the `rainfall-revisit-stale` entry; 231/231, celery-registration tests elsewhere unaffected | `26b63a1` |
| 3.18 | `test_validation_source_matches_manifest`, `test_concurrent_identical_post_does_not_surface_500` | First test passed immediately (smn-gauge fixed in prior-agent commit `025ed53`). Second: ✅ raw `IntegrityError` then `PendingRollbackError` confirmed pre-fix | Added the `try/except IntegrityError: db.rollback(); re-SELECT` recovery to `queue_missing_analysis`; 233/233. Test itself needed a redesign mid-flight (see Issues below) | `8b42ff4` |
| 3.19 | N/A (doc-only: `.cosmic-ray.toml` comment registration) | N/A | TOML re-parsed clean after the edit | `fc359f4` |
| R4-101, R4-102 | N/A (doc-only: `docs/lluvia-v2-observability-workbook.md` catalogue update) | N/A | N/A | `25a3769` |
| R4-103 | `test_record_supersession_batches_more_than_one_pair_correctly` | Counterexample check: deliberately cross-wired every `(superseded_id, landed_id)` pair to the last landed row, confirmed the test fails on the exact per-slot pairing assertion | Restored the real per-row pairing; 234/234 | `25a3769` |
| R4-104 | (no new test — already fixed) | — | — | `81470b0` (pre-dates this resumed run; ledger annotated in `04b6538`) |

### Issues Found (root-caused and fixed within this batch)

1. **`test_e2e_same_key_later_date_and_corrected_revision_becomes_visible` (task 3.12) passed
   in isolation but failed inside the full `tests/new/geo/rainfall/` run.** Root cause:
   `RainfallAnalysisRevision.created_at` is `server_default=func.now()`, which PostgreSQL
   freezes to *transaction start*. The first draft ran all three sequential builds through the
   shared `db` fixture's single savepoint-scoped transaction, so all three revisions for one
   fingerprint landed the identical `created_at`, and `get_snapshot`'s `id DESC` tiebreak served
   an arbitrary one of the three (a random UUID ordering) instead of the newest — passing or
   failing depending on unrelated UUID values generated elsewhere in the same test run. Fixed by
   using real, independent `SessionLocal()` connections throughout (real `get_db` override,
   `db=None` on every task call), matching the existing Durability testing-strategy precedent.
   Logged to engram (`Test bug-class: shared db fixture freezes created_at across multi-build
   tests`) since this applies to any future test needing multiple real builds under one
   fingerprint.
2. **`test_concurrent_identical_post_does_not_surface_500` (task 3.18) could not exercise its
   own recovery path on the shared `db` fixture.** The first design called `queue_missing_
   analysis` twice on the same fixture session, expecting the second call's own `db.rollback()`
   (inside the new `except IntegrityError` handler) to undo only the failed second INSERT while
   leaving the first call's committed row intact. Empirically, `db.rollback()` wiped BOTH rows —
   confirmed via a temporary debug print showing `db.query(RainfallOutbox).all() == []`
   immediately after the rollback. Root cause: the fixture's Session is bound directly to an
   already-`begin()`-ed Connection with no SAVEPOINT layering, so `rollback()` undoes the whole
   test's prior commits, not just the failed statement — a distinct failure mode from Issue 1's
   `created_at` freeze, same underlying fixture. Fixed by using two independent `SessionLocal()`
   connections (one per "concurrent" caller), which is also a more faithful simulation of a real
   race. Logged to engram (`db fixture rollback() undoes whole-test prior commits, not just
   failed statement`).
3. **Arithmetic slip in the first draft of the 3.12 E2E test**, caught by the test itself before
   commit: expected `31.0` for "30 days@1.0 + 1 day@2.0" (actually `32.0`). Fixed before the
   first GREEN run — not a production bug, a test-authoring mistake.

### Deviations / Clarifications (PR3)

- **Stage 1 and stage 2 of `revisit_stale` were implemented together in the SAME commit
  (`08175bd`, tasks 3.10-3.11's commit)**, even though tasks.md lists stage 2's own dedicated
  test under task 3.14. This follows necessarily from the design's own Interfaces section:
  `revisit_stale(db=None, now=None)` is ONE Celery task returning ONE unified dict
  (`scanned`/`enqueued`/`skipped` + `finalization_scanned`/`finalization_enqueued`/
  `finalization_skipped`) — there is no way to make the function callable at all with only
  stage 1's half of the return shape. Task 3.14's own dedicated RED/GREEN cycle (counterexample
  check against the already-written stage 2 logic) still ran in full before that logic was
  marked complete; see the TDD Cycle Evidence row above. Not a deviation from the design, but
  flagged here because "the code preceded its own numbered task's test" is a real ordering
  quirk worth disclosing per the self-check rules.
- No other deviations from design.md this batch — the two-stage sweep, the write gate, the
  latch, the advisory lock, the Beat entry and the `IntegrityError` recovery all match the
  design's Interfaces/decision sections exactly as specified.

### Author Counterexample Self-Check (PR3)

| Category | Evidence | Result |
|----------|----------|--------|
| Null / absence | `rainfall.revisit.skipped{reason:"fingerprint_unavailable"}` (NULL `request_fingerprint`, tested via 3.9/3.10's fixtures); `served_state` returning `None` for a corrupt/pre-contract snapshot (3.14's `provenance_unavailable` case); R4-103's N>1 supersession test | Pass |
| Boundaries | Coverage-equals-threshold boundary for `revision_write_decision` (already covered, task 3.5, re-verified via 3.14/3.15's integration path); year-boundary `now` seam for stage 2 re-resolution (3.14, 3.16); `event_window_key`'s structurally-unreachable assertion (3.14) | Pass |
| Concurrency / idempotency | `test_latch_sequential_and_concurrent_two_connections` (3.7, real two-connection block/latch, both claim orders); `test_concurrent_identical_post_does_not_surface_500` (3.18, real IntegrityError race recovery); stage 1/2 dedup via repeated sweep runs (3.11, 3.14) | Pass |
| Malicious input / security | N/A — PR3 adds no new external input surface (no new endpoint/schema); all new code is Celery-task/repository-internal | N/A — no new input surface in this batch |
| Partial failure / recovery | The self-extinguishing regression (3.15: a gate-refused attempt is retried, not abandoned, across 2 full cycles before succeeding); the `IntegrityError` recovery path (3.18); the advisory lock's savepoint-rollback-drops-the-lock-early case (already covered by 3.7's design, re-verified live) | Pass |
| State / tenancy / time | Year-rollover state transition (provisional→final) tested at both the integration layer (3.14) and the E2E/API-boundary layer (3.16); the `now` seam threading through `revisit_stale`→`resolve_missing_work_source` (3.8, re-exercised by 3.14/3.15/3.16); no tenancy dimension in rainfall intervals | Pass |

### Files Changed (PR3, cumulative with PR1+PR2 table above)

| File | Action | Task(s) |
|------|--------|---------|
| `gee-backend/app/domains/geo/rainfall/tasks.py` | Modified: `_persist_analysis_revision` (advisory lock, write gate); `_pending_row_for_key`, `_revisit_stage1`, `_revisit_stage2`, `_revisit_stale`, `revisit_stale(db=None, now=None)` (replaces the old per-key signature) | 3.3, 3.6, 3.10, 3.11, 3.14 |
| `gee-backend/app/domains/geo/rainfall/repository.py` | Modified: `record_supersession(pairs=...)` (batched, R4-001/R4-104), `recent_done`, `current_year_done_keys`, `completed_year_daily_done_keys`, `acquire_fingerprint_lock`, `claim_outbox_row(now=...)` | 3.1, 3.2, 3.9, 3.13 |
| `gee-backend/app/domains/geo/rainfall/compute.py` | Modified: `fingerprint_lock_key`, `served_state`, `revision_write_decision` | 3.2, 3.4, 3.5 |
| `gee-backend/app/domains/geo/rainfall/service.py` | Modified: cooldown in `queue_missing_analysis`, `resolve_missing_work_source(now=...)`, `RAINFALL_VALIDATION_SOURCE="smn-gauge"`, `IntegrityError` recovery in `queue_missing_analysis` | 3.1, 3.8, 3.18 |
| `gee-backend/app/core/celery_app.py` | Modified: `rainfall-revisit-stale` Beat entry | 3.17 |
| `gee-backend/.cosmic-ray.toml` | Modified: `compute.py` added to the commented rainfall block | 3.19 |
| `docs/lluvia-v2-observability-workbook.md` | Modified: new §2.3/§2.4, `error_type`/`error_message` fields, all PR3 events catalogued | R4-101, R4-102 |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_materialization.py` | Modified: ~20 new test functions across 3.7, 3.9-3.18, R4-103 | all PR3 tasks |
| `openspec/changes/rainfall-materialization/tasks.md` | Tasks 3.1-3.19 marked `[x]` | all |
| `openspec/changes/rainfall-materialization/review-ledger.md` | R4-101..104 annotated `**Addressed** in <sha>` | R4-101..104 |
| `openspec/changes/rainfall-materialization/apply-progress.md` | This file — merged with the PR3 section | — |

### Final Verification (PR3 close-out)

- `pytest tests/new/ -v` → **1907 passed, 5 skipped** (pre-existing live-backend/Martin gates,
  unrelated), 14 warnings (pre-existing, unrelated), exit 0.
- `pytest tests/test_mutation_targets_rainfall.py -v` → **106 passed**, exit 0.

## PR3 review fix round 1 (2026-08-09)

Fix agent applied the two CONFIRMED CRITICALs (C1 stage-2 starvation, C2 stage-1 starvation —
review-ledger.md "Pre-PR review — PR3", 2-of-3 refuter panel) plus the approved info fixes from
the same review round, on branch `feat/rainfall-materialization-03-revisit`. Strict TDD
throughout; RED verified for C1, C2, R2-005 and R4-204 by temporarily reverting each production
fix (a `pass` stub or a disabled branch) and re-running the affected test to confirm it failed
for the expected reason, then restoring the fix. R1-001's bounded-wait behavior was verified
GREEN only (a genuine RED would require an unbounded real wait — see the finding's own commit
note); this is disclosed, not silently skipped.

### TDD Cycle Evidence — C1 + C2 (confirmed criticals)

| Finding | Fix | RED | GREEN | Commit |
|---|---|---|---|---|
| C1 (stage 2 starvation) | `repository.completed_year_daily_done_keys`: SQL-side exclusion (correlated scalar subquery reading each candidate's own newest revision, `IS NOT TRUE` for NULL-safety) + rotation (DISTINCT ON wrapped in a subquery, outer `ORDER BY completed_at ASC`) | ✅ `test_finalization_sql_exclusion_frees_rotation_slot_for_a_stalled_key` confirmed failing pre-fix: `assert 50 == 1` (`finalization_scanned`) — the 50 already-final keys sorted ahead of the one stalled key and were scanned every time; the stalled key was never reached | ✅ post-fix: `finalization_scanned == 1`, `finalization_enqueued == 1`, `finalization_terminated == 0` | `d9d050c` (prod), `4844c9f` (test) |
| C2 (stage 1 starvation) | `repository.current_year_done_keys`: same rotation shape | ✅ `test_revisit_stage1_rotation_reaches_a_lexicographically_last_key_within_two_sweeps` confirmed failing pre-fix: `zone-zzz-frozen` never appeared as a pending row after either of two sweeps (same top-50-by-lexicographic-key returned both times) | ✅ post-fix: day 1 refreshes the 50 oldest (`truncated: true`); day 2, after those are processed and rotate to the back, reaches `zone-zzz-frozen` | `d9d050c` (prod), `4844c9f` (test) |

### TDD Cycle Evidence — approved info fixes (this round)

| Finding | Fix | RED | GREEN | Commit |
|---|---|---|---|---|
| R4-203 + R2-004 (merged into C1/C2 per the fix design) | Per-stage `rainfall.revisit.completed`/`.failed`/`rainfall.finalization.completed` events with full counters + `truncated`; stage 1 in its own try/except so a failure there does not block stage 2; `bind=True`/`max_retries=2` restored on `revisit_stale`; `finalization_terminated` closes the accounting | ✅ covered by the C1/C2 boundary tests (`truncated` assertions) plus existing sweep tests | ✅ | `d9d050c` |
| R1-001 | `SET LOCAL lock_timeout` before `pg_advisory_xact_lock` in `acquire_fingerprint_lock` (module constant `_FINGERPRINT_LOCK_TIMEOUT_MS = 5000`, mirrors `app/auth/refresh_tokens.py`'s convention) | ⚠️ GREEN-only, disclosed: a real RED (removing the `SET LOCAL` and re-running) would hang the test indefinitely (the second connection would block forever, not raise) — unsafe to run deliberately. Verified by inspection instead: `pg_advisory_xact_lock` without a `lock_timeout` set blocks with no bound by Postgres design, a textbook guaranteed hang | ✅ `test_acquire_fingerprint_lock_bounds_the_wait` (constant monkeypatched to 250ms) passes in 0.75s | `d9d050c` (prod), `4844c9f` (test) |
| R2-002 | Latch branch reads `incumbent_source_id` via `served_state()` instead of a raw subscript; docstring lists all three call sites | N/A — refactor of an existing, already-tested path (no behavior change: `served_state` on a well-formed incumbent returns the identical value the raw subscript did) | ✅ `test_latch_sequential_and_concurrent_two_connections` (sequential case) asserts the payload | `d9d050c` (prod), `4844c9f` (test) |
| R2-003 | `repository.pending_row_for_key` single implementation; `service._reused_outbox_response` dedup | N/A — refactor; caught a real regression in the process (see Issues below) | ✅ full suite green after fixing the fake-session regression | `d9d050c` |
| R2-005 | `revision_write_decision -> Literal[...]`; explicit `elif`/`else raise` in the consumer | ✅ `test_persist_analysis_revision_raises_on_unrecognized_write_decision` confirmed failing pre-fix (`raise` branch replaced with `pass`): `Failed: DID NOT RAISE ValueError` — the bogus decision silently fell through and wrote a real revision | ✅ passes after restoring the `raise` | `d9d050c` (prod), `4844c9f` (test) |
| R2-006 | `revisit_stale` docstring states the session-boundary exception | N/A — doc-only | N/A | `d9d050c` |
| R2-007 | `_revisit_stage2` derives `current_year` from `now.year` internally | N/A — refactor, no caller outside `_revisit_stale` (verified: no test calls `_revisit_stage2` directly) | ✅ full suite green | `d9d050c` |
| R2-008 | `finalization.gate_refused` flattened; `finalization.skipped` gains `scope_version` | N/A — payload shape change, no prior test asserted the old shape | ✅ `test_finalization_is_retried_not_abandoned_then_terminates` + `test_revisit_stage2_reresolves_source_and_terminates_on_final` assert the new flat fields | `d9d050c` (prod), `4844c9f` (test) |
| R4-204 | `PROCESS_OUTBOX_WALL_CLOCK_BUDGET_SECONDS = 420` wall-clock check between rows in `_process_outbox_batch`, `rainfall.outbox.batch_truncated` event | ✅ `test_process_outbox_batch_stops_cleanly_when_wall_clock_budget_exceeded` confirmed failing pre-fix (check disabled): all 3 fixture rows were processed (`processed == 3`, expected 0) | ✅ passes after restoring the check | `d9d050c` (prod), `4844c9f` (test) |
| R3-102 | Scoped the three `db=None` E2E tests' global count assertions (`>= 1` or direct scope-filtered queries) | N/A — test-only hardening against order-dependence, not a production behavior change | ✅ full suite green | `4844c9f` |
| R3-103 | Payload-level assertions for the five named events in tests that already traverse those paths | N/A — additive assertions on existing passing tests | ✅ all five assertions pass against the (already-correct) production payloads | `4844c9f` |

### Issues Found (root-caused and fixed within this round)

1. **`test_existing_pending_row_is_reused_not_recreated` (test_mutation_targets_rainfall.py)
   regressed when R2-003 moved `queue_missing_analysis`'s "existing pending row" check off
   `db.query(...).filter_by(...).first()` (the legacy ORM surface `_FakeSession.query()` faked)
   onto `repository.pending_row_for_key`'s `db.scalar(select(...))` (the SAME surface
   `recent_done`'s cooldown lookup already used).** `_FakeSession.scalar()` was hardcoded to
   always return `self._recent_done`, so the pending-row lookup silently got `None` instead of
   the fixture's `existing` row (`result["outbox_id"] == 'None'`, expected the real UUID). Fixed
   by making `_FakeSession.scalar()` positional — 1st call answers `recent_done`, 2nd+ answers
   `existing` — matching `queue_missing_analysis`'s own fixed call order. Caught by running the
   full `tests/test_mutation_targets_rainfall.py` suite (not just the touched test) before
   committing; see `4844c9f`.
2. **`test_latch_sequential_and_concurrent_two_connections`'s existing probe conflicted with
   R1-001.** The probe manually set `SET LOCAL lock_timeout = '250ms'` then called
   `acquire_fingerprint_lock`, expecting a fast `OperationalError`; once that function started
   issuing its OWN `SET LOCAL lock_timeout = '5000'` first, the override made the probe wait 5s
   instead of 250ms — and, worse, pushed session A's total hold time (the probe runs on the
   critical path before `session_a.commit()`) past session B's own 5s default, making B ALSO time
   out with `LockNotAvailable` (`KeyError: 'result'` when the test tried to read B's never-set
   result). Root-caused via the full traceback (`LockNotAvailable: canceling statement due to
   lock timeout` inside `run_second`'s `build_analysis` call, not inside the probe). Fixed by
   having the probe issue its own raw `SELECT pg_advisory_xact_lock(...)` instead of calling
   through the wrapper, restoring both the probe's short window and B's real 5s default. See
   `4844c9f`.

### Deviations / Clarifications (this round)

- R1-001 has no genuine RED (see the TDD Cycle Evidence table) — disclosed rather than silently
  skipped, per the strict-TDD "no silent fallback" rule; the fix itself is a one-statement,
  low-risk addition mirroring an existing, already-shipped pattern (`app/auth/refresh_tokens.py`).
- The design.md "Termination, stated as a proof obligation" paragraph's OWN proof was never wrong
  — only where it was enforced was wrong (a Python `continue` past an unrotated `LIMIT`, not the
  SQL pre-filter the design previously implied). The fix moves the enforcement to match the
  paragraph's own proof, rather than restating a new proof; documented as a correction, not a
  redesign, in `48dcdb6`.
- No changes outside `gee-backend/app/domains/geo/rainfall/`, `gee-backend/tests/`,
  `docs/lluvia-v2-observability-workbook.md` and this change's own `openspec/` artifacts.

### Author Counterexample Self-Check (this round)

| Category | Evidence | Result |
|----------|----------|--------|
| Null / absence | `completed_year_daily_done_keys`'s `IS NOT TRUE` NULL-safety explicitly tested via the JDA-002 healing case staying reachable (a `done` row with no revision is never excluded by the new SQL filter — `test_revisit_stage2_reresolves_source_and_terminates_on_final`'s `zone-stage2-legacy-null` case, pre-existing, still passes unmodified) | Pass |
| Boundaries | Both rotation tests exercise the exact `MAX_OUTBOX_BATCH` (50) boundary: 50 vs 51 candidates, `truncated` flag asserted `true`/`false` on both sides | Pass |
| Concurrency / idempotency | R1-001's lock-timeout test is itself a two-connection concurrency probe; the pre-existing `test_latch_sequential_and_concurrent_two_connections` (two real connections + a worker thread) re-verified green after the probe fix, including the reversed-claim-order round | Pass |
| Malicious input / security | N/A — this round adds no new external input surface (no new endpoint/schema); all changes are Celery-task/repository-internal or a Session-level lock timeout | N/A — no new input surface |
| Partial failure / recovery | R4-203's stage-1-try/except-then-stage-2-still-runs behavior; R4-204's clean-early-return-instead-of-SIGKILL behavior; both are new partial-failure paths and both have dedicated tests | Pass |
| State / tenancy / time | C1/C2's rotation is inherently a state-over-time property (which keys get picked THIS sweep depends on the outcome of the LAST sweep); both boundary tests drive two real sweep cycles to prove it; no tenancy dimension in rainfall intervals | Pass |

### Files Changed (this round)

| File | Action | Finding(s) |
|------|--------|------------|
| `gee-backend/app/domains/geo/rainfall/repository.py` | Modified: `pending_row_for_key` (new), `current_year_done_keys` (rotated), `completed_year_daily_done_keys` (SQL exclusion + rotated), `acquire_fingerprint_lock` (`SET LOCAL lock_timeout`) | C1, C2, R1-001, R2-003 |
| `gee-backend/app/domains/geo/rainfall/tasks.py` | Modified: `_revisit_stage1`/`_revisit_stage2`/`_revisit_stale`/`revisit_stale` (rotation-aware, `now`-only stage 2, per-stage try/except, sweep events, `bind=True`/`max_retries=2`), `_persist_analysis_revision` (latch payload via `served_state`, gate_refused flattened, explicit decision branches), `_process_outbox_batch` (wall-clock budget) | C1, C2, R2-002, R2-004, R2-005, R2-006, R2-007, R2-008, R4-203, R4-204 |
| `gee-backend/app/domains/geo/rainfall/compute.py` | Modified: `revision_write_decision` return type (`Literal`), `served_state` docstring | R2-002, R2-005 |
| `gee-backend/app/domains/geo/rainfall/service.py` | Modified: `queue_missing_analysis` uses `pending_row_for_key`; new `_reused_outbox_response` helper | R2-003 |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_materialization.py` | Modified: 2 new boundary tests (C1, C2), 2 new focused tests (R2-005, R4-204), 1 new test (R1-001), 2 pinned assertions updated, payload assertions added to 5 existing tests (R3-103), 3 E2E tests' global counts scoped (R3-102), existing latch test's probe fixed (R1-001 conflict) | all |
| `gee-backend/tests/test_mutation_targets_rainfall.py` | Modified: `_FakeSession.scalar()` fixed (R2-003 regression) | R2-003 |
| `docs/lluvia-v2-observability-workbook.md` | Modified: corrected the false "SQL pre-filter already terminates" claim; catalogued the 4 new events; R2-008 payload shape updates | C1, R2-008, R4-203, R2-004, R4-204 |
| `openspec/changes/rainfall-materialization/design.md` | Modified: "Current-Year Revisit Cycle" (rotation), "Year-Rollover Finalization" (SQL-first termination, rotation, observability), Interfaces block | C1, C2, R1-001, R2-002, R2-005, R4-203 |
| `openspec/changes/rainfall-materialization/review-ledger.md` | C1/C2 rows set to `fixed` with resolution notes; all approved info-fix rows annotated `**Addressed**` | all |
| `openspec/changes/rainfall-materialization/apply-progress.md` | This file — merged with this round's section | — |

### Final Verification (this round)

- `pytest tests/new/ -v` → **1912 passed, 5 skipped** (1907 prior baseline + 5 new tests: 2
  boundary, R2-005, R4-204, R1-001), exit 0.
- `pytest tests/test_mutation_targets_rainfall.py -v` → **106 passed**, exit 0 (unchanged count —
  the `_FakeSession` fix has no new test, it repairs an existing one).

## Batch 4 / PR4 (Phase 4 — Daily-Source Flip: tasks 4.1-4.2 + folded R4-301/R4-302)

Final batch. Strict TDD throughout, on branch `feat/rainfall-materialization-04-flip` (base:
PR3 branch, after the PR3 review fix round). RED confirmed genuinely for every task with a
production-code change; R4-302 is disclosed GREEN-only (approval test — see below), matching
the same disclosure class as R1-001 in the PR3 review fix round.

### TDD Cycle Evidence

| Task/Finding | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 4.1 (flip pin) | `test_ingest_ops.py::test_resolve_missing_work_source_uses_daily_for_current_year` | Unit | ✅ pre-existing green (pinned `"sqpe-obs"`) | ✅ updated assertion to `"chirps-v3-sat"`, confirmed failing (`assert 'sqpe-obs' == 'chirps-v3-sat'`) before touching `service.py` | ✅ passes after the constant flip | ➖ single scenario (the pin itself) | ➖ none needed |
| 4.1 (fallback flag) | `test_rainfall_materialization.py::test_daily_source_flips_to_chirps_v3_sat_with_fallback_flag` | Integration (real PG, `build_analysis`) | ✅ N/A (new test) | ✅ written first, failed on `RAINFALL_DAILY_SOURCE == "chirps-v3-sat"` before the flip | ✅ passes after the flip + `fallback_used_for` wiring into `tasks._persist_analysis_revision` | ✅ 2 cases: daily/chirps-v3-sat (fallback_used=True) vs historical/chirps-v3-final (fallback_used=False) — proves a real comparison, not a hardcoded value | ➖ none needed |
| 4.2 | `test_rainfall_materialization.py::test_current_year_key_reaches_done_after_flip_and_sweep_finds_it` | E2E (`TestClient` + real outbox/sweep) | ✅ N/A (new test) | ✅ written first, failed on `outbox_row.source_id == "chirps-v3-sat"` (still `"sqpe-obs"` pre-flip) | ✅ passes after the flip: 202 → `process_outbox` → `done` → 200 provisional `chirps-v3-sat` → `revisit_stale` stage 1 finds and re-enqueues the key | ➖ single scenario (task 4.2 is "verifies PR1-3 under the flipped constant", `Files: none`) | ➖ none needed |
| R4-301 (docs) | N/A — docstring/design.md correction, no test | N/A | N/A | N/A — documentation defect, not a code defect (the code was already correct; only the claim about it was wrong) | N/A | N/A | N/A |
| R4-302 | `test_rainfall_materialization.py::test_completed_year_daily_done_keys_keeps_a_revision_missing_key` | Integration (real PG, `completed_year_daily_done_keys`) | ✅ N/A (new test) | ⚠️ GREEN-only, disclosed: the `already_final.isnot(True)` NULL-safety was already correct in production code; a genuine RED would require breaking working code first for the sole purpose of a red bar, which strict-tdd's approval-testing pattern treats as unnecessary — same disclosure as R1-001 (PR3 review fix round 1) | ✅ passes on first run: revision-missing key selected, already-final key excluded (differential, not a single assertion) | ✅ 2 cases in one test (the differential control) | ➖ none needed |

### Test Summary

- **Total tests written this batch**: 3 new (`test_daily_source_flips_to_chirps_v3_sat_with_fallback_flag`, `test_current_year_key_reaches_done_after_flip_and_sweep_finds_it`, `test_completed_year_daily_done_keys_keeps_a_revision_missing_key`) + 1 updated pin (`test_resolve_missing_work_source_uses_daily_for_current_year`) + 2 monkeypatch-removal cleanups (no new tests, dead scaffolding removed now that the flip is real).
- **Total tests passing**: `tests/new/geo/rainfall/` 242 passed, exit 0; `tests/new/` 1915 passed, 5 skipped, exit 0; `tests/test_mutation_targets_rainfall.py` 106 passed, exit 0 (unchanged).
- **Layers used**: Unit (1 — the pin), Integration (2 — fallback flag + R4-302), E2E (1 — task 4.2).
- **Approval tests**: 1 (R4-302 — pins already-correct NULL-safety behavior).
- **Pure functions created**: 1 (`service.fallback_used_for`).

### Deviations / Clarifications

- None — implementation matches design.md decision 7 and the delta spec's "Evidence-Gated
  Source Roles" MODIFIED requirement exactly. `fallback_used_for` and
  `RAINFALL_SPEC_PRIMARY_SOURCE_BY_ROLE` are new (not named in design.md's Interfaces block, which
  predates this batch), but implement literally what design.md decision 7 and tasks.md task 4.1
  already specify ("fallback_used=True for any role whose spec-primary source differs from the one
  actually used") — no behavior invented beyond that sentence.
- `sqpe-obs`'s `NotImplementedError` contract (`test_provider_adapters.py:436-456`) is unchanged
  and still green, per the batch's own instruction — the daily role now routes AROUND it
  (`resolve_missing_work_source` no longer selects it), not through a change to it.

### Issues Found

None.

### Author Counterexample Self-Check (this batch)

| Category | Evidence | Result |
|----------|----------|--------|
| Null / absence | R4-302's whole point: a `done` row with a fingerprint but NO revision (`already_final` reads SQL `NULL`) must stay a candidate, not be silently dropped | Pass |
| Boundaries | N/A — no new numeric/size boundary introduced this batch (the flip is a constant swap; `fallback_used_for` is a two-value dict lookup with no threshold) | N/A — no applicable boundary |
| Concurrency / idempotency | Task 4.2's E2E reuses the existing per-row-commit/advisory-lock machinery (PR2/PR3) unmodified; no new concurrency surface introduced by the flip itself | N/A — no new concurrency surface, existing guards apply unchanged |
| Malicious input / security | N/A — no new external input surface (a constant flip + an internal dict lookup, no new endpoint/schema) | N/A — no new input surface |
| Partial failure / recovery | Task 4.2's E2E exercises the full `process_outbox` per-row commit/claim path (unchanged from PR2/PR3) under the newly-reachable daily role; no new failure path introduced | N/A — no new failure path introduced |
| State / tenancy / time | Task 4.2 proves the state transition PR3 could only simulate: a REAL `role='daily'` `done` row now exists, and `revisit_stale`'s stage 1 genuinely finds it (not a monkeypatched stand-in) | Pass |

### Files Changed (this batch)

| File | Action | Task/Finding |
|------|--------|--------------|
| `gee-backend/app/domains/geo/rainfall/service.py` | Modified: `RAINFALL_DAILY_SOURCE` flips to `"chirps-v3-sat"` (`TODO(smn)`); new `RAINFALL_SPEC_PRIMARY_SOURCE_BY_ROLE` + `fallback_used_for` | 4.1 |
| `gee-backend/app/domains/geo/rainfall/tasks.py` | Modified: `_persist_analysis_revision` threads `fallback_used_for(row.role, row.source_id)` into `build_snapshot` | 4.1 |
| `gee-backend/app/domains/geo/rainfall/repository.py` | Modified: `completed_year_daily_done_keys` docstring corrected (honest drain-bound claim, no behavior change) | R4-301 |
| `gee-backend/tests/new/geo/rainfall/test_ingest_ops.py` | Modified: daily-routing pin updated `"sqpe-obs"` → `"chirps-v3-sat"` | 4.1 |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_materialization.py` | Modified: 3 new test functions (4.1 fallback flag, 4.2 E2E, R4-302 regression); 2 monkeypatch-removal cleanups in pre-existing PR3 E2E tests | 4.1, 4.2, R4-302 |
| `openspec/changes/rainfall-materialization/design.md` | Modified: 3 "rotated, same shape as stage 1" claims corrected (Selection algorithm step 2, Interfaces bullet, "Rotation bound" → "Drain bound, corrected") | R4-301 |
| `openspec/changes/rainfall-materialization/tasks.md` | Tasks 4.1, 4.2 marked `[x]` with file/test evidence | 4.1, 4.2 |
| `openspec/changes/rainfall-materialization/review-ledger.md` | R4-301/R4-302 rows annotated `**Addressed**` with commit references | R4-301, R4-302 |
| `openspec/changes/rainfall-materialization/apply-progress.md` | This file — merged with this batch's section + final summary | — |

### Final Verification (this batch)

- `pytest tests/new/geo/rainfall/ -v` → **242 passed**, exit 0 (whole-directory total; 3 new this
  batch).
- `pytest tests/new/ -v` → **1915 passed, 5 skipped** (1912 prior + 3 new), exit 0.
- `pytest tests/test_mutation_targets_rainfall.py -v` → **106 passed**, exit 0 (unchanged).

## Apply phase complete (all 4 PRs)

All 47 code tasks (1.1-4.2) across all 4 chained PRs are `[x]` complete. Phase 5 (5.1-5.3,
ops/rollout, non-code) is intentionally NOT executed by apply and stays unchecked.

| PR | Branch | Base | Scope | Key commits |
|---|---|---|---|---|
| 1 — persistence | `feat/rainfall-materialization-01-persistence` | tracker `feat/rainfall-materialization` | Tasks 1.1-1.9 + R3-001..004 hardening | `f19a06e`..`ef82d1a`, `7f892fc`, `70bd040` |
| 2 — compute | `feat/rainfall-materialization-02-compute` | PR1 branch | Tasks 2.1-2.14 + R4-001..003 review fix | `0fb88fd`..`3a8e0d2`, `da761d9`, `a08fb94` |
| 3 — revisit + finalization + guards | `feat/rainfall-materialization-03-revisit` | PR2 branch | Tasks 3.1-3.19 + R4-101..104, + review fix round 1 (C1/C2 + 10 info fixes) | `025ed53`..`04b6538`, `d9d050c`, `4844c9f`, `48dcdb6`, `6a856da` |
| 4 — daily-source flip | `feat/rainfall-materialization-04-flip` | PR3 branch | Tasks 4.1-4.2 + R4-301/R4-302 review fold | `5c9d2a4`, `9b08fcd`, `d5674fa`, `30895c9` |

Total test growth across the whole change: `tests/new/geo/rainfall/` baseline **182 passed**
(before batch 1) → **242 passed** now; `tests/test_mutation_targets_rainfall.py` baseline **71
passed** → **106 passed** now; whole-backend `tests/new/` suite currently **1915 passed, 5
skipped**, exit 0 throughout — no regression introduced at any batch boundary. No push, no PR
opened at any point — all branches are local only, per protocol; the tracker branch
(`feat/rainfall-materialization`) is the only one intended to merge to `main`.

## Next Recommended

`judgment-day` (post-sdd-phase trigger rule) on the PR4 diff (the daily-source flip — the
single step that opens real current-year GEE traffic, per design.md decision 10's own
rationale for isolating it), then `sdd-verify` for the whole `rainfall-materialization` change
now that all 4 PRs are code-complete. Phase 5 (ops/rollout, non-code: tasks 5.1-5.3 — deleting
the 2 failed `sqpe-obs` prod outbox rows, the two-tier kill-switch runbook note, and the
staging `comparison_end` validation with the partner) remains for a human/ops action after
`sdd-verify`, not for another `sdd-apply` batch.

## Apply-phase JD fix round 1 (2026-08-09)

`judgment-day` ran on the whole-chain diff (tracker...04-flip) per "Next Recommended" above.
Judges A+B (blind, parallel) found no BLOCKER; one single-judge CRITICAL (JDB-301) triaged REAL
by the orchestrator, plus 3 approved info fixes (JDA-301, JDA-302, JDA-303). Full findings and
resolutions: `review-ledger.md` "Judgment Day — APPLY-PHASE completion" + "Apply-phase JD fix
round 1". Branch: `feat/rainfall-materialization-04-flip` (same branch as Batch 4/PR4 — this is
a fix-forward round on top of it, not a new PR).

- **JDB-301 (CRITICAL, confirmed real, fixed)**: `build_snapshot` never sets
  `analysis_revision_id`, and `read_analysis` never injected it before returning the served
  envelope, so the frontend CSV export contract (`consorcio-web/src/lib/api/rainfall.ts:75`,
  `RainfallDetailPanel.tsx:235` — builds `GET /analyses/{analysis_revision_id}.csv`) was
  unreachable for every real analysis. Fix: `read_analysis` now sets
  `normalized["analysis_revision_id"] = str(revision.id)` immediately after
  `normalize_snapshot` returns — the key was already allow-listed in `SNAPSHOT_ROOT_KEYS` and
  `normalize_snapshot` never strips extra/missing root keys, so no change to
  `normalize_snapshot` itself was needed. RED confirmed pre-fix (`KeyError:
  'analysis_revision_id'`), GREEN post-fix. `gee-backend/` only — no frontend files touched.
- **JDA-301/JDA-302 (WARNING, info, approved test fixes)**: a new E2E regression proves the
  delta spec's "Corrected value becomes visible as a later revision" scenario end-to-end
  (restating an already-served slot, not appending a new day — distinct from the existing
  JDA-001 date-driven regression); the concurrent-identical-POST regression was repaired to
  hijack the actual query path (`repository.pending_row_for_key`) instead of the never-called
  `Session.query`, so it now genuinely exercises the `except IntegrityError` recovery branch
  instead of passing vacuously via the non-racing reuse path.
- **JDA-303 (SUGGESTION, info, approved doc fix)**: design.md's `build_analysis` Interfaces
  block corrected — the advisory lock is the first database statement *after* resolving the
  outbox row and its fingerprint, not literally the first statement. Doc-only.

### Files Changed (this round)

| File | Action | Finding |
|------|--------|---------|
| `gee-backend/app/domains/geo/rainfall/router.py` | Modified: `read_analysis` injects `analysis_revision_id` into the served envelope | JDB-301 |
| `gee-backend/tests/new/geo/rainfall/test_prepr_contract_fixes.py` | Modified: `SimpleNamespace` revision mock carries an `id`; asserts the served field | JDB-301 |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_materialization.py` | Modified: new boundary test (JDB-301), new E2E correction-visibility test (JDA-301), rewritten concurrent-POST test (JDA-302) | JDB-301, JDA-301, JDA-302 |
| `openspec/changes/rainfall-materialization/design.md` | Modified: `build_analysis` Interfaces "FIRST database statement" claim tightened | JDA-303 |
| `openspec/changes/rainfall-materialization/review-ledger.md` | JDB-301 → `fixed`; JDA-301/302/303 evidence appended `**Addressed**`; new "Apply-phase JD fix round 1" subsection | JDB-301, JDA-301, JDA-302, JDA-303 |
| `openspec/changes/rainfall-materialization/apply-progress.md` | This file — new "Apply-phase JD fix round 1" section | — |

### Git (this round)

- `d0b80a5` — fix(rainfall): serve analysis_revision_id in the read_analysis envelope (JDB-301 prod fix + `test_prepr_contract_fixes.py` mock update)
- `8bf49ee` — test(rainfall): apply-phase JD fix round regressions (JDB-301, JDA-301, JDA-302)
- `4aeec69` — docs(rainfall): tighten build_analysis's "FIRST database statement" claim (JDA-303)
- No push, no PR created — local branch only, per protocol.

### Final Verification (this round)

- `pytest tests/new/geo/rainfall/ -v` → **244 passed**, exit 0 (242 prior + 2 new: JDB-301's boundary test, JDA-301's E2E test; JDA-302 rewrote an existing test in place, no count change).
- `pytest tests/new/ -v` → **1917 passed, 5 skipped**, exit 0 (1915 prior + 2 new, matches).
- `pytest tests/test_mutation_targets_rainfall.py -v` → **106 passed**, exit 0 (unchanged).

### Next Recommended

A scoped re-judge over this fix round's diff + the updated ledger (per the orchestrator's
convergence protocol), then `sdd-verify` for the whole `rainfall-materialization` change.
