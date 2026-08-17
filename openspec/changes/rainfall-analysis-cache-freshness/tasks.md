# Tasks: Rainfall Analysis Cache Freshness

**Change name**: `rainfall-analysis-cache-freshness`  
**OpenSpec root**: `/tmp/opencode/consorcio-canalero-rainfall-pr2/openspec`  
**Goal**: close parent `lluvia-ux-tarjeta` JDA-001 by making the multi-parcel E2E harness reach an **11/0/0/0** assertion gate, using Approach B (per-parcel query key) and Option A (cache-served repeat selections are fresh).

## Acceptance Criteria (from spec)

- [x] `useRainfallAnalysis.ts` builds the rainfall-analysis query key with `scope.kind`, `scope.id`, `scope.version`, `year`, and `nomenclatura`.
- [x] `RainfallDetailPanel.tsx` does NOT call `queryClient.invalidateQueries` for the rainfall-analysis prefix.
- [x] `RainfallDetailPanel.tsx` passes `nomenclatura` to `useRainfallAnalysis`.
- [x] A unit test verifies that a `nomenclatura` change creates a new analysis fetch.
- [x] A unit test verifies that a same-`nomenclatura` re-render does not create a new analysis fetch.
- [ ] An optional unit test verifies scope/year cache reuse within the same parcel.
- [x] `rainfall-v2-detail.spec.ts` multi-parcel journey reports **11/0/0/0**.
- [x] The E2E harness accepts the final `C→A` repeat selection as fresh when the rendered card matches fixture A.
- [x] Within a single parcel session, the 60-second `staleTime` remains effective.

## First Slice / Batch Breakdown

This is a single fast-follow slice. The pivot from Approach A to Approach B means the production code already carries the per-parcel query key; the remaining work is to (1) align the docstring and remove any leftover invalidation, (2) relax the E2E harness for Option A, and (3) pin the behavior with focused unit tests. The work is intentionally ordered: **confirm the production contract first**, then **relax the E2E gate**, then **add unit tests**, and finally **run the E2E harness**.

## Dependency Graph

```text
1.1 (key contract) ──→ 2.1 (E2E harness relaxation) ──→ 4.1 (E2E verification)
         │
         └──→ 3.1 (unit tests) ──→ 4.1 (E2E verification)
```

- 1.1 must land before 2.1 and 3.1 can assume the production behavior.
- 2.1 and 3.1 are independent and can run in parallel.
- 4.1 depends on 1.1, 2.1, and 3.1.

## Phase 1: Align Production Code with Approach B (Foundation)

### 1.1 Verify the rainfall-analysis query key includes `nomenclatura`

- [x] **1.1.1** Open `consorcio-web/src/hooks/useRainfallAnalysis.ts` and confirm `rainfallAnalysisQueryKey(scope, year, nomenclatura)` returns `['rainfall-analysis', scope.kind, scope.id, scope.version, year, nomenclatura]`.
- [x] **1.1.2** Confirm `useRainfallAnalysis` accepts `nomenclatura` in `UseRainfallAnalysisOptions` and forwards it to the key builder.
- [x] **1.1.3** Confirm `RainfallDetailPanel.tsx` passes its `nomenclatura` prop to `useRainfallAnalysis` in the call options.
- [x] **1.1.4** Update the JSDoc on `useRainfallAnalysis` to state that the key carries the parcel `nomenclatura` and that no production invalidation is used; the key itself ensures per-parcel freshness.
- [x] **1.1.5** Confirm there is no `useQueryClient` import, no `queryClient.invalidateQueries` call, and no `invalidateQueries` reference in `RainfallDetailPanel.tsx` for the rainfall-analysis prefix.
- **Estimate**: 20 min
- **Verification**: Read the files; diff shows only docstring updates if already correct.
- **Risk**: Low — if the key already includes `nomenclatura`, this is mostly a docstring pass.

### 1.2 Remove any remaining Approach A invalidation scaffolding

- [x] **1.2.1** Search the production code for `invalidateQueries` with a `rainfall-analysis` key and remove any leftover.
- [x] **1.2.2** Run `npm --prefix consorcio-web run typecheck` to confirm no dangling `useQueryClient` or invalidation imports.
- [x] **1.2.3** Run `npm --prefix consorcio-web run lint` to confirm no unused imports.
- **Estimate**: 15 min
- **Verification**: Type-check and lint pass.
- **Risk**: Low — the source already reflects Approach B; this is a cleanup pass.

## Phase 2: Relax E2E Harness for Option A (Core Implementation)

### 2.1 Update `assertTargetReady` and `assertMobileReady` in `rainfallMultiParcelHarness.ts`

- [x] **2.1.1** Add a way to detect a repeat selection (e.g., pass a flag from `runContextJourney` or derive from the transition order that A appears at index 0 and again at index 3).
- [x] **2.1.2** For repeat selections (final `C→A`), skip the `analysisSequence > previous.analysisSequence` check and the `evidence.traces.analysisCacheKey !== wantTraceKey` check.
- [x] **2.1.3** Keep the strict newer-sequence and trace-key checks for non-repeat selections (`A→B` and `B→C`).
- [x] **2.1.4** Keep all rendered-card checks (identity, scope sentence, percentile, accumulation, metric revision) regardless of repeat status.
- [x] **2.1.5** Ensure `assertMobileReady` inherits the same relaxation via `assertTargetReady`.
- **Estimate**: 30 min
- **Verification**: The harness compiles; the helper unit tests pass if any exist.
- **Risk**: Medium — if the repeat detection is wrong, every transition could skip the freshness gate.

### 2.2 Update `waitForTargetAnalysis` in `rainfall-v2-detail.spec.ts`

- [x] **2.2.1** Keep the newer-sequence wait for `A→B` and `B→C`.
- [x] **2.2.2** For the final `C→A` transition, accept the cached response when either:
  - `trace.latest.analysisCacheKey === target.rainfall.effectiveCacheKey` and `trace.analysisSequence > previousSequence`, OR
  - the rendered card matches the target fixture (headline percentile, accumulation text, scope sentence, identity, metric revision) even if the sequence did not advance.
- [x] **2.2.3** Reuse the existing `collectReadyEvidence` helper to read the rendered values, or extract a small helper to avoid duplicating the DOM reads.
- [x] **2.2.4** Do not add production invalidation; the relaxation lives only in the test harness.
- **Estimate**: 30 min
- **Verification**: The spec type-checks and the `A→B→C→A` test can reach the assert gate.
- **Risk**: Medium — the DOM selectors used to detect the cache-served state must match the actual rendered card.

## Phase 3: Unit Tests for Per-Parcel Query Key (Testing)

### 3.1 Add/update per-parcel query-key tests in `RainfallDetailPanel.test.tsx`

- [x] **3.1.1** Keep or rewrite the existing test: changing `nomenclatura` from `parcel-a` to `parcel-b` calls `fetchRainfallAnalysis` exactly once (new query).
- [x] **3.1.2** Keep or rewrite the existing test: re-rendering with the same `nomenclatura` does not call `fetchRainfallAnalysis` again (cache hit).
- [ ] **3.1.3** Add an optional test: within the same parcel, switch to a different scope/year via the UI, then switch back to the original scope/year; the second selection reuses the cached query (no new fetch) because the key includes scope/year.
- [x] **3.1.4** Remove any tests that assert `queryClient.invalidateQueries` is called for rainfall analysis, since production does not perform invalidation.
- **Estimate**: 45 min
- **Verification**: `npm --prefix consorcio-web run test -- --run tests/unit/RainfallDetailPanel.test.tsx` passes.
- **Risk**: Low — the test scaffold already wraps with `QueryClientProvider`.

### 3.2 Run the RainfallDetailPanel unit suite

- [x] **3.2.1** Run `npm --prefix consorcio-web run test -- --run tests/unit/RainfallDetailPanel.test.tsx` and confirm all tests pass.
- [x] **3.2.2** Run `npm --prefix consorcio-web run typecheck` and confirm no new errors.
- [x] **3.2.3** Run `npm --prefix consorcio-web run lint` and confirm no new errors.
- **Estimate**: 15 min
- **Verification**: CI-green unit output.
- **Risk**: Low — the change is small.

## Phase 4: Verification

### 4.1 Run the E2E multi-parcel journey

- [x] **4.1.1** Set up the declared local environment from design D13 of `lluvia-ux-tarjeta`:
  - `FICHA_ENABLED=true docker compose up -d postgres backend`
  - `docker compose exec backend python -m app.domains.geo.etl.load_suelos_catastro`
  - `docker compose up -d martin` (with a reachable `VITE_MARTIN_URL`)
  - `npm --prefix consorcio-web run dev`
- [x] **4.1.2** Execute the dedicated rainfall E2E script:
  ```bash
  E2E_APP_URL=http://localhost:5173 E2E_API_BASE=http://localhost:8000 \
    npm --prefix consorcio-web run test:e2e:rainfall
  ```
- [x] **4.1.3** Confirm the `A→B→C→A` multi-parcel test reaches the harness assertion gate.
- **Estimate**: 30 min
- **Verification**: Test passes and the harness report shows 11/0/0/0.
- **Risk**: High — the local environment must be fully seeded.
- **Status**: COMPLETED — the Python disposable-stack driver produced a clean `11/0/0/0` run. The canonical ports (`8011/3011/5184`) were blocked by a stale docker-proxy, so the final run used alternative ports (`8013/3012/5185`) and still passed.
- **Evidence**: `/tmp/rainfall-e2e-evidence8/manifest.json`, `/tmp/rainfall-e2e-evidence8/playwright-results.json`, `/tmp/rainfall-e2e-evidence8/events.jsonl`.

### 4.2 Sign off the review budget

- [x] **4.2.1** Estimate the final diff size: source changes ~15 lines (docstring + minor cleanup), test changes ~80 lines, total well under 400 lines.
- [x] **4.2.2** Forecast review workload: one standard lens (`review-reliability`) because the diff is small and does not touch auth/security/payments.
- [x] **4.2.3** Confirm that no global `staleTime` or `refetchOnMount` defaults were modified.
- **Estimate**: 10 min
- **Verification**: Diff review shows only the intended changes.
- **Risk**: Low.

## Phase 5: Layout + E2E Robustness Fix (Ficha Panel Overlay)

This batch was added to eliminate a flaky desktop failure: the ficha-territorial panel's floating card was intercepting map clicks on desktop, so the second/third desktop parcel selections could not click through to the canvas. The fix mixes a minimal CSS `pointer-events` guard with a test helper that explicitly dismisses the panel between selections.

### 5.1 Add CSS pointer-events guard to desktop floating cards

- [x] **5.1.1** Open `consorcio-web/src/styles/components/map.module.css` and add `pointer-events: none` to the desktop `.infoPanel` and `.fichaPanel` card rules only.
- [x] **5.1.2** Restore `pointer-events: auto` for interactive children: close buttons, action icons, pills, buttons, links, inputs, selects, textareas, `label` elements, and elements with ARIA roles such as `button`, `tab`, `radio`, `listbox`, `switch`, `option`.
- [x] **5.1.3** Add `.fichaPanel svg { pointer-events: none; }` to prevent the Recharts SVG from stealing clicks from the map canvas.
- [x] **5.1.4** Confirm the mobile sheet class `.panelSheet` is NOT modified; mobile behavior must remain unchanged.
- **Estimate**: 20 min
- **Verification**: CSS-related unit tests pass; the desktop panel buttons and tab labels remain clickable; the map can be clicked behind the panel.
- **Risk**: Medium — `pointer-events: none` can accidentally disable all panel interactions if children are not correctly restored.

### 5.2 Add a dismiss helper to the E2E multi-parcel spec

- [x] **5.2.1** Add `dismissDesktopPanel(page)` in `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts` that clicks the close button with aria-label `"Cerrar ficha territorial"` and waits for the panel to disappear or the pill to appear.
- [x] **5.2.2** Wire `dismissDesktopPanel` after each non-final desktop selection in `runContextJourney` so the canvas is clear before the next click.
- [x] **5.2.3** Keep the mobile path unchanged; mobile uses the bottom sheet, not the floating panel.
- **Estimate**: 25 min
- **Verification**: The `A→B→C→A` desktop journey reaches the assertion gate in one attempt.
- **Risk**: Low — the helper is a test-only change.

### 5.3 Re-validate the E2E harness after the layout fix

- [x] **5.3.1** Rebuild the RMEH frontend container so the new CSS is copied into the image.
- [x] **5.3.2** Run the CSS-related unit tests and confirm no regressions.
- [x] **5.3.3** Run `npm --prefix consorcio-web run typecheck` and `npm --prefix consorcio-web run lint`.
- [x] **5.3.4** Run the Python E2E driver and confirm the harness gate is `11/0/0/0`.
- **Estimate**: 35 min
- **Verification**: `manifest.json` reports `"passed": 11, "failed": 0, "skipped": 0` and `playwright-results.json` shows `expected: 11, unexpected: 0, flaky: 0`.
- **Risk**: Low — the fix is additive and test-only beyond the CSS rule.

## Chained-PR Implications

- This change is a fast-follow PR to `lluvia-ux-tarjeta` (JDA-001). It assumes the panel, the card hierarchy, and the E2E harness from that change are already on the integration branch.
- The diff is small and should be delivered as one PR against the parent branch.
- The E2E harness and the 11/0/0/0 gate are owned by the sibling `rainfall-multi-parcel-e2e-harness` change; this change must be validated on a branch that includes both slices.
- No backend, contract, migration, or route changes are required.

## Out-of-Scope Reminders

- Do NOT add `queryClient.invalidateQueries` in production code.
- Do NOT change the rainfall-analysis query key to omit `nomenclatura`.
- Do NOT change global TanStack Query `staleTime` or `refetchOnMount` defaults.
- Do NOT add server-side cache headers or API-level invalidation.
- Do NOT refactor the multi-parcel E2E harness fixture itself (owned by `rainfall-multi-parcel-e2e-harness`).
- Do NOT touch visual or UX changes to the Lluvia detail card (owned by `lluvia-ux-tarjeta`).
- Do NOT backport the per-parcel key pattern to NDVI or suelos panels without an explicit request.
