# Apply Progress: rainfall-analysis-cache-freshness

**Branch**: `verify/lluvia-rainfall-e2e`  
**Base**: `fix/rainfall-analysis-cache-freshness` / `origin/main` integration  
**Mode**: Standard  
**Status**: All phases completed. Production contract aligned with Approach B; E2E harness relaxed for Option A; unit tests green; CSS pointer-events guard refactored into `.panelCardBody` inner wrapper (R3-001/R3-002); E2E multi-parcel journey passed with an **11/0/0/0** gate.

---

## Completed Tasks

- [x] **1.1** Verified `useRainfallAnalysis.ts` query key includes `nomenclatura`:
  - Key is `['rainfall-analysis', scope.kind, scope.id, scope.version, year, nomenclatura]`.
  - `useRainfallAnalysis` accepts `nomenclatura` in options and forwards it.
  - `RainfallDetailPanel.tsx` passes `nomenclatura` to both primary and fallback `useRainfallAnalysis` calls.
  - Updated JSDoc on `useRainfallAnalysis` to state the key carries the parcel identity and that no production invalidation is used.
- [x] **1.2** Confirmed no `useQueryClient` / `invalidateQueries` scaffolding remains for rainfall analysis in production code.
  - `grep` for `invalidateQueries` in `RainfallDetailPanel.tsx` and `useRainfallAnalysis.ts` returned no matches.
- [x] **2.1** Updated `rainfallMultiParcelHarness.ts`:
  - Added exported `isRepeatSelection` helper.
  - Added `selectedAliases: ParcelAlias[]` to `TargetReadyEvidence`.
  - Modified `assertTargetReady` to skip strict trace-key and newer-sequence checks for repeat selections (final `C→A`), while keeping all rendered-card checks and auth/token checks.
  - `assertMobileReady` inherits the relaxation via `assertTargetReady`.
- [x] **2.2** Updated `rainfall-v2-detail.spec.ts`:
  - `collectReadyEvidence` now receives and returns `selectedAliases`.
  - `runContextJourney` maintains a `selectedAliases` array and passes it to the assertion helpers.
  - `waitForTargetAnalysis` keeps its existing fallback (headline match accepts cache-served response).
- [x] **3.1** Verified `RainfallDetailPanel.test.tsx` per-parcel query-key tests describe the Approach B contract:
  - `nomenclatura` change creates a new `fetchRainfallAnalysis` call.
  - Same-`nomenclatura` re-render does not create a new fetch.
  - No stale Approach A `invalidateQueries` assertions remain.
- [x] **3.2** Verification:
  - `npm --prefix consorcio-web run typecheck` → clean.
  - `npm --prefix consorcio-web run test -- --run tests/unit/RainfallDetailPanel.test.tsx` → 47/47 passing.
  - `npm --prefix consorcio-web run test -- --run tests/unit/rainfallMultiParcelHarness.test.ts` → 73/73 passing.
  - `npm --prefix consorcio-web run lint` → 3 pre-existing warnings, none in changed files.
- [x] **4.2** Sign off the review budget:
  - Total diff ~653 changed lines (405 insertions / 248 deletions), but only ~260 lines touch executable code; the orchestrator pre-approved an 800-line review budget.
  - Ran `review-reliability` inline; no BLOCKER/CRITICAL findings, two WARNING/SUGGESTION findings documented in the verify report.
- [x] **4.1** E2E multi-parcel journey passed with 11/0/0/0 (completed after the layout fix).
- [x] **5.1** Added CSS `pointer-events` guard to desktop `.infoPanel` / `.fichaPanel` floating cards in `map.module.css`, restoring `pointer-events: auto` for interactive children and SVG elements, and leaving `.panelSheet` untouched.
- [x] **5.2** Added `dismissDesktopPanel(page)` helper in `rainfall-v2-detail.spec.ts` and wired it after each non-final desktop selection in `runContextJourney`.
- [x] **5.3** Re-validated after the layout fix:
  - Rebuilt the RMEH frontend container so the new CSS was copied into the image.
  - CSS-related unit tests passed.
  - Typecheck and lint passed.
  - Python E2E driver produced a clean 11/0/0/0 run.
- [x] **6.1** Refactored desktop card pointer-events guard to fix R3-001/R3-002:
  - Removed `overflow-y: auto` from `.infoPanel` / `.fichaPanel` roots.
  - Added `.panelCardBody` inner wrapper with `overflow-y: auto` and `pointer-events: auto`.
  - Moved the sticky fade `::after` pseudo-element from the root to `.panelCardBody`.
  - Wrapped `{children}` and the minimize button inside `.panelCardBody` in `MapPanelShell.tsx`.
  - Removed the long interactive-descendant allowlist and the `.fichaPanel svg { pointer-events: none; }` rule.
- [x] **6.2** Updated `mapPanelFadeClearance.test.ts` to assert the fade lives on `.panelCardBody::after` and that `.panelCardBody` has no compensatory `padding-bottom`.
- [x] **6.3** Re-verified after the R3-001/R3-002 fix:
  - `npm --prefix consorcio-web run typecheck` → clean.
  - `npm --prefix consorcio-web run lint` → 3 pre-existing warnings, none in changed files.
  - Targeted unit suites → 212/212 passing.
  - E2E harness on canonical ports `8011/3011/5184` → 11/0/0/0.

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `consorcio-web/src/hooks/useRainfallAnalysis.ts` | Modified | Updated JSDoc to explicitly state no production invalidation is used; per-parcel key is the freshness mechanism. |
| `consorcio-web/tests/e2e/helpers/rainfallMultiParcelHarness.ts` | Modified | Added `isRepeatSelection` helper; added `selectedAliases` to `TargetReadyEvidence`; relaxed trace-key/sequence checks in `assertTargetReady` for repeat selections only. |
| `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts` | Modified | `collectReadyEvidence` and `runContextJourney` now carry `selectedAliases` through to the assertion helpers; added `dismissDesktopPanel` helper and wired it after non-final desktop selections. |
| `consorcio-web/tests/unit/rainfallMultiParcelHarness.test.ts` | Modified | Updated `readyEvidence` helper for new field; added tests for `isRepeatSelection`, cache-served repeat acceptance, repeat-with-mismatched-card rejection, and strict first-time gate. |
| `consorcio-web/src/styles/components/map.module.css` | Modified | Refactored desktop floating-card pointer-events guard: root stays `pointer-events: none`; new `.panelCardBody` owns `overflow-y: auto` and `pointer-events: auto`; sticky fade moved to `.panelCardBody::after`; removed allowlist and `.fichaPanel svg` pointer-events rule. |
| `consorcio-web/src/components/map2d/MapPanelShell.tsx` | Modified | Desktop branch now wraps `{children}` and the minimize button in `.panelCardBody`; existing `data-testid`s and classes preserved. |
| `consorcio-web/tests/unit/mapPanelFadeClearance.test.ts` | Modified | Updated fade selector from `.infoPanel::after, .fichaPanel::after` to `.panelCardBody::after`; added assertion that `.panelCardBody` has no compensatory `padding-bottom`. |

## Discovered Patterns

- The existing `TargetReadyEvidence` type is the natural place to carry repeat-selection context; making `selectedAliases` required keeps every caller explicit.
- For cache-served repeat selections, all three trace fields (`analysisCacheKey`, `scopeNomenclature`, `seriesScopeId`) may remain stale because no new network request is issued. Skipping the entire trace-key block for repeats (not just `analysisCacheKey`) is necessary for the final `C→A` to pass when the rendered card matches.
- The auth/token checks remain active for repeats because they validate the last observed request's bearer against the currently active token, not against the transition order.
- The previous-only stale-value check does not need relaxing for `A→B→C→A` because fixture values are pairwise distinct.
- Mantine `SegmentedControl` tab labels are rendered as plain `<label>` elements, so they must live inside a pointer-events-enabled container; wrapping the whole card body in `.panelCardBody { pointer-events: auto }` removes the need for an exhaustive descendant allowlist.
- CSS `pointer-events: none` on a scroll container disables the native scrollbar because scrollbars are pseudo-elements of the container, not matched by descendant selectors. The fix is to move scrolling to an inner wrapper that has `pointer-events: auto`.
- Recharts `<Tooltip>` inside an SVG stops working when the SVG root has `pointer-events: none` because the property is inherited by SVG children. Removing the broad SVG rule restores hover tooltips.
- The frontend Dockerfile copies source at build time, so a container rebuild is required to pick up CSS changes; a host bind-mount is not used in the harness stack.

## Deviations from Design

- None in the core cache-freshness implementation. The layout guard (Phases 5 and 6) was added as an additional robustness measure after the E2E journey revealed the ficha panel was blocking map clicks on desktop; it was not part of the original design but is required for the acceptance gate to be deterministic.

## Issues Found / Blockers

- None remaining.
- The canonical harness ports (`8011/3011/5184`) were initially blocked by a stale `rmeh-4659da112b` stack holding `127.0.0.1:3011` and `127.0.0.1:5184`. The stale containers were stopped and removed, after which a clean run on the canonical ports produced the required 11/0/0/0 gate.

## Remaining Tasks

- None. The change is ready for verify/archive.

## E2E Verification Result (Verify Phase)

- **Command**:
  ```bash
  RMEH_BACKEND_HOST_PORT=8011 RMEH_MARTIN_HOST_PORT=3011 RMEH_FRONTEND_HOST_PORT=5184 \
    python3 -m scripts.rainfall_e2e_harness.driver run --evidence-dir /tmp/rainfall-e2e-evidence9
  ```
- **Exit**: driver completed and wrote `manifest.json` and `playwright-results.json`.
- **Manifest counts**: `passed: 11, failed: 0, skipped: 0`.
- **Playwright stats**: `expected: 11, skipped: 0, unexpected: 0, flaky: 0`.
- **Evidence**: `/tmp/rainfall-e2e-evidence9/manifest.json`, `/tmp/rainfall-e2e-evidence9/playwright-results.json`, `/tmp/rainfall-e2e-evidence9/events.jsonl`.
- **Note**: First attempt failed because ports 3011/5184 were held by a stale `rmeh-4659da112b` stack; containers were stopped/removed, then the canonical-port rerun passed cleanly.
- **Full report**: `openspec/changes/rainfall-analysis-cache-freshness/verify-report.md`.
