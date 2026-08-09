# Apply Progress: Rainfall v2 Materialization

## Scope covered by this artifact (cumulative across batches)

- Batch 1: Phase 1 (PR 1) — Persistence. Tasks 1.1-1.9. Strict TDD mode.
- Batch 2, Part 0: PR1 hardening (review-reliability findings R3-001..R3-004)
  on branch `feat/rainfall-materialization-01-persistence`.
- Batch 2, Part 1: Phase 2 (PR 2) — Compute. Tasks 2.1-2.14. Strict TDD mode,
  on branch `feat/rainfall-materialization-02-compute` (base: PR1 branch
  after Part 0's hardening commits).

## Git

- Tracker branch: `feat/rainfall-materialization` (commit `e2754bc` — SDD artifacts only, checked out from `main`)
- PR1 branch: `feat/rainfall-materialization-01-persistence` (checked out from the tracker)
  - Batch 1 (persistence): `f19a06e` .. `ef82d1a` (tasks 1.1-1.9, see table below)
  - Batch 2 Part 0 (R3 hardening): `7f892fc` (test+impl), `70bd040` (ledger annotation)
- PR2 branch: `feat/rainfall-materialization-02-compute` (checked out from PR1 branch, after `70bd040`)
  - Batch 2 Part 1 (compute): `0fb88fd` .. `3a8e0d2` (tasks 2.1-2.14, see table below)
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

## Next Recommended

`judgment-day` (post-sdd-phase trigger rule) on the PR2 diff
(`feat/rainfall-materialization-01-persistence...feat/rainfall-materialization-02-compute`), then
`sdd-apply` again for Phase 3 (PR 3 — Revisit, Finalization, Guards: tasks 3.1-3.19), base branch
`feat/rainfall-materialization-02-compute`, per the feature-branch-chain strategy. PR 3 is where
the advisory lock (`fingerprint_lock_key`/`acquire_fingerprint_lock`), the write gate
(`revision_write_decision`), and the latch land in `build_analysis` — PR2 deliberately does not
include them (see Deviations/Clarifications above).
