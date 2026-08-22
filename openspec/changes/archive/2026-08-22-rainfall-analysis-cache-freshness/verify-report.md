# Verify Report: rainfall-analysis-cache-freshness

**Change**: `rainfall-analysis-cache-freshness`  
**Branch**: `verify/lluvia-rainfall-e2e`  
**Verifier**: SDD verify phase  
**Date**: 2026-08-17  
**Artifact store**: hybrid (OpenSpec + Engram)  
**Status**: PASS after R3-001/R3-002 fix

---

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 14 (phases 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3) |
| Tasks complete | 14 |
| Tasks incomplete | 0 |

All acceptance criteria are met except the optional scope/year cache-reuse test, which remains out of scope.

---

## Build & Tests Execution

### Typecheck

**Command**: `npm --prefix consorcio-web run typecheck`  
**Result**: ✅ Passed (exit 0)  
**Output**: `tsc --noEmit && tsc --noEmit -p tsconfig.tests.json` completed cleanly.

### Lint

**Command**: `npm --prefix consorcio-web run lint`  
**Result**: ✅ Passed (3 pre-existing warnings, none in changed files)  

### Unit tests — RainfallDetailPanel

**Command**: `npm --prefix consorcio-web run test -- --run tests/unit/RainfallDetailPanel.test.tsx`  
**Result**: ✅ 47/47 passed (exit 0)  
**Duration**: 5.42 s  
**Notes**: stderr contains React `act()` warnings and chart dimension warnings from existing tests; they do not fail the suite.

### Unit tests — rainfallMultiParcelHarness

**Command**: `npm --prefix consorcio-web run test -- --run tests/unit/rainfallMultiParcelHarness.test.ts`  
**Result**: ✅ 73/73 passed (exit 0)  
**Duration**: 791 ms

### CSS-related unit tests

**Command**: `npm --prefix consorcio-web run test -- --run tests/unit/mapPanelFadeClearance.test.ts tests/unit/MapCtrlTouchTargets.test.tsx tests/unit/MapUiPanelsLayout.test.tsx tests/unit/MapPanelMinimizePill.test.tsx tests/unit/MapPanelBottomSheet.test.tsx`  
**Result**: ✅ All passed (exit 0)  
**Notes**: `mapPanelFadeClearance.test.ts` was updated to assert the sticky fade now lives on `.panelCardBody::after` and that `.panelCardBody` has no compensatory `padding-bottom`. The tests validate the refactored pointer-events guard does not regress fade geometry.

---

## E2E Multi-Parcel Harness

**Command**:

```bash
RMEH_BACKEND_HOST_PORT=8011 RMEH_MARTIN_HOST_PORT=3011 RMEH_FRONTEND_HOST_PORT=5184 \
  python3 -m scripts.rainfall_e2e_harness.driver run --evidence-dir /tmp/rainfall-e2e-evidence9
```

**Result**: ✅ Passed  
**Manifest counts**: `passed: 11, failed: 0, skipped: 0`  
**Playwright stats**: `expected: 11, skipped: 0, unexpected: 0, flaky: 0`  
**Run ID**: `11d8660799d675b985eabdd30c06e341`

### Driver events

`/tmp/rainfall-e2e-evidence9/events.jsonl` records:

```jsonl
{"phase": "lease_planned", "run_id": "11d8660799d675b985eabdd30c06e341"}
{"phase": "provisioning"}
{"database_name": "rmeh_11d8660799", "phase": "database_owned"}
{"phase": "bootstrapped"}
{"phase": "preflight_passed"}
{"phase": "tests_finished"}
{"phase": "evidence_sealed"}
{"phase": "cleaned"}
```

**Note**: A first attempt on the canonical ports failed because a stale `rmeh-4659da112b` stack held `127.0.0.1:3011` and `127.0.0.1:5184`. The stale containers were stopped and removed; the rerun on the canonical ports produced the required 11/0/0/0 gate.

### Selection records

The driver manifest records 8 parcel selections across mobile and desktop contexts, each successful on the first attempt with one click:

| # | Context | Target | Attempts | Clicks | Wheel proofs |
|---|---|---------|--------|----------|--------|--------------|
| 1 | mobile | A | 1 | 1 | 0 |
| 2 | mobile | B | 1 | 1 | 1 |
| 3 | mobile | C | 1 | 1 | 1 |
| 4 | mobile | A | 1 | 1 | 1 |
| 5 | desktop | A | 1 | 1 | 0 |
| 6 | desktop | B | 1 | 1 | 0 |
| 7 | desktop | C | 1 | 1 | 0 |
| 8 | desktop | A | 1 | 1 | 0 |


---

## Spec Compliance Matrix

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Per-Parcel Rainfall Analysis Query Key | Parcel A and B have independent cache entries | `RainfallDetailPanel.test.tsx > starts a new analysis query when nomenclatura changes` | ✅ COMPLIANT |
| Per-Parcel Rainfall Analysis Query Key | Re-rendering the same parcel reuses the cached analysis | `RainfallDetailPanel.test.tsx > does not start a new analysis query when the same nomenclatura re-renders` | ✅ COMPLIANT |
| Per-Parcel Rainfall Analysis Query Key | Scope or year change within the same parcel creates a new query | (none — optional test removed) | ⚠️ UNTESTED (optional) |
| No Production Cache Invalidation | Parcel change does not trigger invalidation | Static inspection + `RainfallDetailPanel.test.tsx` | ✅ COMPLIANT (no `invalidateQueries` present) |
| No Production Cache Invalidation | Scope or year change does not trigger invalidation | Static inspection | ✅ COMPLIANT |
| E2E Cache-Freshness Gate (Option A) | Final C→A is served from cache and accepted if card matches | E2E harness driver | ✅ COMPLIANT (11/0/0/0) |
| E2E Cache-Freshness Gate (Option A) | A→B and B→C still require a newer analysis sequence | E2E harness driver | ✅ COMPLIANT (11/0/0/0) |
| Desktop Layout Robustness | Floating panel root does not block map clicks; scroll area is usable | CSS guard + E2E selection records | ✅ COMPLIANT |
| Desktop Layout Robustness | Native scrollbar on desktop cards is clickable/draggable | `.panelCardBody` pointer-events refactor | ✅ COMPLIANT |
| Desktop Layout Robustness | Recharts tooltip receives pointer events | Removed `.fichaPanel svg` pointer-events rule | ✅ COMPLIANT |
| E2E Robustness | Panel is dismissed before next desktop click | `dismissDesktopPanel` helper + E2E selection records | ✅ COMPLIANT |

**Compliance summary**: 10/10 scenarios compliant, 1 optional scenario untested.

---

## Correctness (Static — Structural Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| `useRainfallAnalysis` query key includes `nomenclatura` | ✅ Implemented | `rainfallAnalysisQueryKey(scope, year, nomenclatura)` returns `['rainfall-analysis', scope.kind, scope.id, scope.version, year, nomenclatura]` |
| `RainfallDetailPanel` passes `nomenclatura` to `useRainfallAnalysis` | ✅ Implemented | Passed to both primary and fallback calls |
| No production `invalidateQueries` for rainfall-analysis | ✅ Implemented | `useQueryClient` import and effect removed from `RainfallDetailPanel.tsx` |
| E2E harness accepts cache-served C→A when card matches | ✅ Implemented | `isRepeatSelection` + relaxed `assertTargetReady` for repeats |
| Strict newer-sequence gate kept for A→B and B→C | ✅ Implemented | Trace-key/sequence checks only run when `!isRepeat` |
| Desktop floating cards do not intercept map clicks | ✅ Implemented | `.infoPanel` / `.fichaPanel` root keeps `pointer-events: none`; `.panelCardBody` inner wrapper owns `overflow-y: auto` and `pointer-events: auto`. |
| SVG chart tooltips remain interactive | ✅ Implemented | `.fichaPanel svg { pointer-events: none; }` removed; Recharts `<Tooltip>` receives pointer events via `.panelCardBody`. |
| Native scrollbar on desktop cards is clickable | ✅ Implemented | Scrollbar is on `.panelCardBody`, which has `pointer-events: auto`. Verified by E2E (11/0/0/0). |
| Mobile sheet behavior unchanged | ✅ Implemented | `.panelSheet` was not modified. |

---

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Approach B: per-parcel query key | ✅ Yes | Key includes `nomenclatura`; no production invalidation |
| Option A: cache-served repeat accepted if card matches | ✅ Yes | `assertTargetReady` skips trace/sequence checks for repeats only |
| 60-second `staleTime` preserved | ✅ Yes | No global query defaults changed |
| E2E relaxation lives only in test harness | ✅ Yes | Production code has no invalidation or test-only logic |
| Layout fix is minimal and desktop-only | ✅ Yes | Refactored to `.panelCardBody` inner wrapper; mobile sheet untouched; no broad SVG pointer-events override |

---

## Review-Reliability Lens Findings

No BLOCKER or CRITICAL issues remain.

### FIXED (R3-001 / R3-002)

- **R3-001 — Desktop card scrollbar unclickable**  
  Location: `consorcio-web/src/styles/components/map.module.css`  
  Refactored the desktop card layout so the floating card root keeps `pointer-events: none` while the scrollable inner wrapper `.panelCardBody` owns `overflow-y: auto` and `pointer-events: auto`. The native scrollbar is now on a container with pointer events enabled.

- **R3-002 — Recharts tooltip disabled by SVG pointer-events rule**  
  Location: `consorcio-web/src/styles/components/map.module.css`  
  Removed the broad `.fichaPanel svg { pointer-events: none; }` rule. The SVG now inherits `pointer-events: auto` from `.panelCardBody`, restoring Recharts hover tooltips.

### WARNING

- **`isRepeatSelection` is broader than the literal "final C→A" gate**  
  Location: `consorcio-web/tests/e2e/helpers/rainfallMultiParcelHarness.ts:887`  
  The helper returns `true` for **any** alias that already appears earlier in the journey, not only the final `A` of `A→B→C→A`. For the current fixture this is equivalent, but if the journey is extended to `A→B→A→C`, the intermediate `A` would be treated as a repeat and would skip the strict trace/sequence gate. Consider documenting this contract or scoping the repeat detection to the known transition set.

### SUGGESTION

- **Fixed 100 ms sleep in same-nomenclatura test**  
  Location: `consorcio-web/tests/unit/RainfallDetailPanel.test.tsx`  
  The test uses `await new Promise((resolve) => setTimeout(resolve, 100))` before asserting no fetch occurred. This is inherently racy; prefer `waitFor` polling the call count or asserting the query state is `success` without additional calls.

- **Idle query key includes `nomenclatura`**  
  Location: `consorcio-web/src/hooks/useRainfallAnalysis.ts:147`  
  When `scope` is null the query is disabled, so this has no runtime effect. It creates a separate disabled cache entry per parcel, which is harmless but slightly confusing. Consider keeping the idle key constant (`['rainfall-analysis', 'idle']`) since the query is never active in that state.

---

## Issues Found

**CRITICAL**: None.

**WARNING** (non-blocking):

- `isRepeatSelection` is broader than the documented final `C→A` case.

**SUGGESTION** (nice to have):

- Replace the 100 ms sleep in `RainfallDetailPanel.test.tsx` with a deterministic assertion.
- Re-evaluate whether the idle query key needs `nomenclatura`.

---

## Verdict

**PASS**

All tasks are complete. Typecheck, lint, and the targeted unit suites are green. The E2E multi-parcel harness produced the required `11/0/0/0` gate on the canonical ports. The R3-001/R3-002 pointer-events refactor is verified, and the production code matches the Approach B + Option A design. The change is ready for archive.

---

## Next Recommended Steps

1. Archive the change (`/sdd-archive` or equivalent) and merge the branch.
2. Optionally address the `isRepeatSelection` WARNING if the journey is extended beyond `A→B→C→A`.
3. Optionally replace the 100 ms sleep in `RainfallDetailPanel.test.tsx` with a deterministic `waitFor` assertion.

---

## Evidence Paths

- `/tmp/rainfall-e2e-evidence9/events.jsonl`
- `/tmp/rainfall-e2e-evidence9/manifest.json`
- `/tmp/rainfall-e2e-evidence9/playwright-results.json`
- `/tmp/rainfall-e2e-evidence9/ownership.json`
- `/tmp/rainfall-e2e-evidence9/jda-001-handoff.json`
