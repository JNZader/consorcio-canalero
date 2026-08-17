# Archive Report — `rainfall-multi-parcel-e2e-harness`

## Final Status

**MERGED** ✅

- **PR:** [#187](https://github.com/JNZader/consorcio-canalero/pull/187)
- **Merge commit:** `a888583182ad079d57e78ec46007e53d9d09da8b`
- **Merged to:** `main`
- **Remote branch:** `test/rainfall-multi-parcel-e2e-execution` (deleted)
- **Archive date:** 2026-08-16
- **Artifact store mode:** openspec

## What Was Implemented

This change delivered a deterministic, operator-only Chromium E2E harness that proves same-tab rainfall continuity and fact freshness while selecting three distinct parcels (A → B → C → A) through the production interaction path. The harness runs against an isolated, disposable PostGIS/backend/Martin/frontend stack and provides follow-up evidence for parent change `lluvia-ux-tarjeta` without modifying production behavior.

### Major Components Delivered

| Component | Files | Responsibility |
|---|---|---|
| Python lifecycle runner | `scripts/rainfall_e2e_harness/` package (8 modules) | Disposable identity, ownership marker, Compose lifecycle, bootstrap, preflight, accounting, cleanup, evidence |
| Safety/taxonomy tests | `scripts/tests/test_rainfall_e2e_harness.py`, `scripts/tests/test_rainfall_e2e_config.py` | 141 pytest cases covering safety, cleanup, lifecycle, failure taxonomy, compose env parity |
| TS fixture + helper | `consorcio-web/tests/e2e/fixtures/rainfall-multi-parcel.fixture.json`, `consorcio-web/tests/e2e/helpers/rainfallMultiParcelHarness.ts` | Strict validator, Web Mercator CSS projection, occlusion, one-click policy, auth/cache contracts |
| Vitest unit tests | `consorcio-web/tests/unit/rainfallMultiParcelHarness.test.ts` | 69 tests for fixture/projection/cache/bearer/geometry |
| Playwright spec | `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts` | One new `test()` with mobile + desktop contexts (11 total tests) |
| Harness config | `consorcio-web/tests/e2e/playwright.rainfall-harness.config.ts` | Chromium, one worker, retries 0, JSON reporter |
| Compose / Martin | `scripts/tests/rainfall-e2e.compose.yml`, `scripts/tests/fixtures/martin-rainfall-e2e.yaml` | Isolated stack with generated project/volume/network and loopback-only ports |
| Optional workflow | `.github/workflows/rainfall-multi-parcel-e2e.yml` | `workflow_dispatch`-only, serialized, no secrets, artifact retention + cleanup |
| Runbook | `docs/testing/rainfall-multi-parcel-e2e.md` | Operator command, statuses, evidence layout, JDA-001 boundary, rollback |

### Verification Summary

| Layer | Result |
|---|---|
| Python harness + config tests | **141 passed** |
| TypeScript helper unit tests | **69 passed** |
| TypeScript typecheck | **0 errors** |
| Playwright collection gate | **11 tests discovered** ✅ |
| Playwright live-stack result | **10 passed, 1 failed** ⚠️ |
| Docker cleanup after run | **verified empty** ✅ |

### Constraints Preserved

- **0 production lines touched** — no changes under `consorcio-web/src/` or `gee-backend/app/`.
- Parent change `lluvia-ux-tarjeta` review ledger and Engram topic were not mutated.
- Workflow remains optional (`workflow_dispatch`-only) and unreferenced by required CI gates.
- Rollback boundary is limited to 13 created files + 2 test-config enrolments.

## Specs Synced

| Domain | Action | Details |
|---|---|---|
| `rainfall-multi-parcel-e2e-harness` | Created | 14 requirements (RMEH-001..014) and 46 scenarios copied from delta spec to main spec source of truth |

The main spec now lives at:

- `openspec/specs/rainfall-multi-parcel-e2e-harness/spec.md`

## Known Caveats and Deferred Work

### 1. A→B→C→A final C→A freshness gate

The multi-parcel journey passes A→B and B→C on both mobile and desktop viewports. The final C→A re-selection fails the test's strict freshness gate because `useRainfallAnalysis` has `staleTime: 60_000`; within 60 seconds of the initial A selection, TanStack Query returns the cached A analysis, so the fixture router observes no new request. The UI correctly renders parcel A's data.

**Impact:**
- Result gate reports **10 passed / 1 failed** instead of **11/0/0/0**.
- `jda-001-handoff.json` is **not emitted** because it requires a full `PASSED` run.
- Parent change `lluvia-ux-tarjeta` JDA-001 remains pending.

**Candidate remediation paths** (outside this change):
- Product-side: expose a `staleTime` option on `useRainfallAnalysis` and opt into `0` for the harness.
- Product-side: invalidate the analysis query on scope selection change in the map selection handler.
- Test-side: add a fourth distinct parcel to the fixture and avoid repeating a parcel within 60 s.
- Test-side: relax `assertTargetReady` to accept a cached repeat selection when UI evidence matches the target.

### 2. Bootstrap idempotency on second pass

`test_bootstrap_twice_same_owned_db_is_stable` reports `create` on the first pass and `recreate` on the second pass, indicating the migration-owned view is recreated instead of treated as stable. This is unit-covered but not fully resolved on the real stack.

### 3. Real-stack negative scenarios (5.2 / 5.7)

The bounded-rebuild and relation-drift negative paths are unit-covered. Manually corrupting migration-owned views in a live stack and observing the bounded rebuild + explicit abort was not executed.

## Parent Change Handoff Status

| Parent | Finding | Status | Reason |
|---|---|---|---|
| `lluvia-ux-tarjeta` | JDA-001 | **Pending** | The child change did not reach the required 11/0/0/0 pass gate. The `A→B→C→A` final transition fails the strict freshness/sequence gate due to `useRainfallAnalysis` `staleTime: 60_000`. Browser evidence is partial (10/11 tests pass). A full green run is required before `jda-001-handoff.json` can be emitted and JDA-001 can be closed.

The runner and workflow continue to **not** write parent artifacts or declare the parent APPROVED. Any future remediation must occur in a separate review transaction.

## Archive Contents

All artifacts are moved to:

```text
openspec/changes/archive/2026-08-16-rainfall-multi-parcel-e2e-harness/
```

- [x] `proposal.md`
- [x] `specs/rainfall-multi-parcel-e2e-harness/spec.md`
- [x] `design.md`
- [x] `tasks.md`
- [x] `apply-progress.md`
- [x] `verify-report.md`
- [x] `review-ledger.md`
- [x] `explore.md`
- [x] `archive-report.md` (this file)

## Source of Truth Updated

The following main spec now reflects the new behavior:

- `openspec/specs/rainfall-multi-parcel-e2e-harness/spec.md`

## SDD Cycle Complete

This change has been planned, implemented, verified, and archived. The merged code is in `main` via PR #187. The remaining caveat is documented and does not affect the test-only nature of the change.

## Next Recommended Phase

1. **Immediate:** `sdd-compact` on `rainfall-multi-parcel-e2e-harness` to extract learnings and free session context.
2. **Follow-up (separate transaction):** Decide how to resolve the C→A cached-repeat freshness gate so the parent `lluvia-ux-tarjeta` JDA-001 handoff can be completed.
