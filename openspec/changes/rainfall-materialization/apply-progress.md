# Apply Progress: Rainfall v2 Materialization

## Scope of this batch

Phase 1 (PR 1) — Persistence. Tasks 1.1-1.9. Strict TDD mode.

## Git

- Tracker branch: `feat/rainfall-materialization` (commit `e2754bc` — SDD artifacts only, checked out from `main`)
- PR1 branch: `feat/rainfall-materialization-01-persistence` (checked out from the tracker)
- No push, no PR created — local branches only, per protocol.

## Baseline (before any code change)

- `pytest tests/new/geo/rainfall/ -v` → **182 passed**, 1 warning, exit 0 (clean; no pre-existing failures).
- `pytest tests/test_mutation_targets_rainfall.py -v` → **71 passed**, exit 0 (clean).

## Test infrastructure note

The prescribed harness resolves `DATABASE_URL` via testcontainers (Docker available in this
environment) or `TEST_DATABASE_URL`. For iteration speed across ~9 TDD RED/GREEN cycles, a
disposable local PostGIS container (`rainfall-test-pg`, port 55433, `postgis/postgis:16-3.4`)
was started and used via `TEST_DATABASE_URL` for the RED/GREEN loop — this avoids spinning a
fresh testcontainer (~5-10s) on every single-test pytest invocation. The container was **removed
after this batch's work** (`docker rm -f rainfall-test-pg`). The final validation runs (see
below) were re-executed with `TEST_DATABASE_URL` unset, exercising the default testcontainers
path, and produced identical results (191 passed) — confirming the scratch DB shortcut did not
mask anything testcontainers-specific.

## TDD Cycle Evidence

| Task | Test(s) | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR | Commit |
|------|---------|-------|------------|-----|-------|-------------|----------|--------|
| 1.2 | `tests/test_mutation_targets_rainfall.py::TestRevisionFamilyAndCorrectionRevision` (4 tests) | Unit (pure) | ✅ 71/71 (module didn't exist) | ✅ `ModuleNotFoundError` confirmed | ✅ 4/4 passed | ✅ bare-family + ordinal-1/2 + reject-non-positive | ✅ clean, no further extraction needed | `f19a06e` |
| 1.1 | `tests/new/geo/rainfall/test_rainfall_materialization.py::test_reingest_is_idempotent` | Integration (real PG) | ✅ 182/182 (function didn't exist) | ✅ `ImportError` confirmed | ✅ 1/1 passed | ➖ single scenario (idempotency) — minimal ON CONFLICT DO NOTHING bulk insert | ✅ clean | `c8df247` |
| 1.3 | `..._materialization.py::test_persist_intervals_inserts_absent_slot` | Integration (real PG) | ✅ 183/183 | ✅ `ImportError` on `intervals_in_window` confirmed | ✅ 2/2 passed (incl. 1.1 regression) | ➖ single scenario (absent-slot classify) | ✅ clean | `6af414e` |
| 1.4 | `..._materialization.py::test_persist_intervals_unchanged_slot_writes_nothing` + `test_mutation_targets_rainfall.py::TestSixDecimalEqualityBoundary` (2 tests) | Unit (pure) + Integration | ⚠️ see note below | ✅ pure test: `ImportError` on `_values_equal_at_6dp` confirmed | ✅ 3+2 passed | ✅ symmetric-boundary case + a change large enough to move the 6th decimal | ✅ inline comparison extracted into `_values_equal_at_6dp`, wired into `persist_intervals` | `7b1baf5` |
| 1.5 | `..._materialization.py::test_persist_intervals_changed_slot_appends_correction_and_lifecycle_row` | Integration (real PG) | ✅ 4/4 prior | ✅ `assert 0 == 1` (no correction/lifecycle logic yet) confirmed | ✅ 4/4 passed | ➖ single scenario (this task); chaining is 1.6's triangulation | ✅ clean | `adf8791` |
| 1.6 | `..._materialization.py::test_second_correction_chains_off_first` | Integration (real PG) | ✅ 5/5 prior | ⚠️ see note below | ✅ 6/6 passed | ✅ this test IS the triangulation for 1.5's ordinal-parsing generalization | ➖ none needed | `7ad4acb` |
| 1.7 | `..._materialization.py::test_intervals_in_window_excludes_superseded_rows` | Integration (real PG) | ✅ 6/6 prior | ⚠️ see note below | ✅ 7/7 passed | ✅ two slots (corrected + untouched), explicit ordering assertion | ➖ none needed | `0c5acd9` |
| 1.8 | `..._materialization.py::test_ingest_source_scope_writes_without_commit_when_given_db` + `::test_ingest_source_scope_opens_own_session_and_commits_when_db_is_none` | Integration (real PG) | ✅ 7/7 prior + `test_provider_adapters.py:436-456` contract test unmodified | ✅ `TypeError: got an unexpected keyword argument 'db'` confirmed | ✅ 9/9 passed | ✅ given-db branch + None branch (own session + commit) | ✅ extracted `_batch_result()` helper for the JSON-safe evidence dict | `2ad9912` |
| 1.9 | `..._materialization.py::test_backfill_missing_shares_transaction_with_ingest` | Integration (real PG) | ✅ 9/9 prior | ✅ `TypeError: failing_ingest() missing 1 required keyword-only argument: 'db'` confirmed | ✅ 10/10 passed | ➖ single scenario (transaction-sharing, proven via all-or-nothing rollback) | ➖ one-line change, no refactor needed | `2210bb8` |

**Notes on Safety Net for 1.4/1.6/1.7 (RED honesty disclosure):** for these three tasks, the
*repository-level* real-PG test happened to already pass against the code left by the prior
commit, because the prior commit's classify step already distinguished "absent" from "present"
(1.4) or already implemented ordinal parsing generically rather than hardcoding ordinal=1 (1.6),
or already anti-joined superseded rows correctly for a single slot (1.7). This is disclosed
per the Strict TDD "real GREEN" rule rather than glossed over:
- **1.4**: the *pure* test (`test_six_decimal_equality_boundary`, importing the not-yet-existing
  `_values_equal_at_6dp`) was genuinely RED (`ImportError`) and is the task's true new-behavior
  proof. The repository-level test was written and run defensively (a real regression guard,
  calling real production code with a specific expected value) but did not itself require new
  production code — extracting the named function and wiring it into `persist_intervals` was
  the REFACTOR half of this task, executed in the same commit.
- **1.6** and **1.7**: both tests are the TRIANGULATION cases for the general algorithm already
  written in 1.5/1.3 respectively (ordinal parsing was written generically, not hardcoded to
  ordinal=1; `intervals_in_window`'s anti-join was written as a set-based SQL predicate, not
  special-cased to one row). Both were run and passed on the first try — confirmed by actual
  execution, not claimed from code inspection. No production code changed in these two commits;
  they are test-only commits that prove the general implementation already covers the scenario
  the task describes, which is a legitimate and expected outcome of triangulation done correctly
  one step earlier.

## Deviations / Deferrals

- **Migration task (2.1, `lluvia_v2_005`)**: NOT part of this batch. Per `tasks.md`, it belongs
  to Phase 2 (PR2 — Compute), not Phase 1 (PR1 — Persistence). The orchestrator's launch prompt
  included a generic migration-verification instruction that appears templated across batches;
  it does not apply to PR1's assigned task list (1.1-1.9), which touches only `repository.py`,
  `compute.py` and `tasks.py` — no model/migration changes. Deferred to the PR2 batch, where the
  assigned executor should read `alembic.ini`/`app/db/session.py` for the dev DB URL and decide
  whether a disposable DB is safe for the `upgrade head / downgrade -1 / upgrade head` check.
- **No other deviations.** Implementation matches `design.md` decisions 2, 2c (partially —
  per-row claim/commit is PR2 scope per the PR table; PR1 only threads the `db` parameter),
  3, 3b (not touched — `data_revision_for` is PR2), 3c (fully implemented), and the "NRT
  Correction Supersession" write algorithm exactly as specified (classify-then-append,
  `ON CONFLICT DO NOTHING` + `RETURNING`, lifecycle rows only for landed ids).

## Author Counterexample Self-Check

| Category | Evidence | Result |
|----------|----------|--------|
| Null / absence | `persist_intervals([])` returns the zero dict early (guarded); `intervals_in_window` over an empty window returns `[]`; `served_state`-style absence not applicable to PR1 | Pass |
| Boundaries | 6dp equality boundary tested both directions (`test_six_decimal_equality_boundary`, `test_six_decimal_equality_is_symmetric`); ordinal chaining tested to depth 2 (`+r1` → `+r2`) | Pass |
| Concurrency / idempotency | `test_reingest_is_idempotent` proves identical re-ingest is a no-op; classification read is documented as non-locking ("a lost race degrades to a skipped write") matching design.md's explicit statement — no new concurrency primitive introduced in PR1 (advisory lock is PR3 scope) | Pass |
| Malicious input / security | N/A — PR1 has no new external input surface (no new endpoint/schema); `provider_revision` shape is adapter-controlled, not user input | N/A — no new input surface in this batch |
| Partial failure / recovery | `test_backfill_missing_shares_transaction_with_ingest` proves a mid-transaction failure leaves BOTH the checkpoint and the interval row absent (all-or-nothing), not a partially-committed state | Pass |
| State / tenancy / time | Not applicable to PR1 (no tenancy dimension in rainfall intervals; `comparison_end`/temporal logic is PR2/PR3 scope) | N/A — out of this batch's scope |

## Final Suite Counts

- `pytest tests/new/geo/rainfall/ -v` (testcontainers, default path): **191 passed**, 1 warning, exit 0 (182 baseline + 9 new test functions across tasks 1.1, 1.3, 1.4, 1.5, 1.6, 1.7, 1.9 = 1 each, plus 1.8 = 2 → 9 new; confirmed by direct run).
- `pytest tests/test_mutation_targets_rainfall.py -v`: **77 passed**, exit 0 (71 baseline + 6 new: 4 from task 1.2 + 2 from task 1.4).
- `pytest tests/new/ -v` (full cross-domain regression): **1864 passed, 5 skipped** (pre-existing skips requiring a live backend/Martin tile server — unrelated to this change), exit 0. No failures.
- `ruff check` / `ruff format --check` on all touched files: clean (verified via the `javi-forge ci --quick` pre-commit hook on every commit).

## Task Status

- [x] 1.1 through [x] 1.9 — all complete, all committed individually on `feat/rainfall-materialization-01-persistence`.

## Files Changed (PR1 branch, cumulative)

| File | Action |
|------|--------|
| `gee-backend/app/domains/geo/rainfall/compute.py` | Created — `revision_family`, `correction_revision` |
| `gee-backend/app/domains/geo/rainfall/repository.py` | Modified — `persist_intervals`, `intervals_in_window`, `record_supersession`, `_values_equal_at_6dp`, `_next_correction_ordinal` |
| `gee-backend/app/domains/geo/rainfall/tasks.py` | Modified — `ingest_source_scope(db=...)`, `_batch_result()`, `backfill_missing` shares transaction |
| `gee-backend/tests/new/geo/rainfall/test_rainfall_materialization.py` | Created — 10 test functions across tasks 1.1-1.9 |
| `gee-backend/tests/test_mutation_targets_rainfall.py` | Modified — `TestRevisionFamilyAndCorrectionRevision`, `TestSixDecimalEqualityBoundary` |

## Next Recommended

`sdd-apply` again for Phase 2 (PR2 — Compute), base branch `feat/rainfall-materialization-01-persistence`, per the feature-branch-chain strategy. Before starting PR2: run `judgment-day` (post-sdd-phase trigger rule) on this PR1 diff.
