# Tasks: Rainfall Analysis Cache Freshness

**Change name**: `rainfall-analysis-cache-freshness`  
**OpenSpec root**: `/tmp/opencode/consorcio-canalero-rainfall-pr2/openspec`  
**Goal**: close parent `lluvia-ux-tarjeta` JDA-001 by making the multi-parcel E2E harness reach an **11/0/0/0** assertion gate.

## Acceptance Criteria (from spec)

- [ ] `RainfallDetailPanel.tsx` invalidates `['rainfall-analysis']` whenever `nomenclatura` changes.
- [ ] No invalidation occurs on initial mount or re-render with the same `nomenclatura`.
- [ ] Scope/year changes within the same parcel do not trigger invalidation.
- [ ] A new unit test in `RainfallDetailPanel.test.tsx` fails if the invalidation logic is removed.
- [ ] `useRainfallAnalysis.ts` docstring documents the cache-freshness contract.
- [ ] `rainfall-v2-detail.spec.ts` multi-parcel journey reports **11/0/0/0**.
- [ ] Within a single parcel session, the 60-second `staleTime` remains effective.

## First Slice / Batch Breakdown

This is a single, small fast-follow slice. It only touches the rainfall panel, the hook contract, and one regression test. The work is intentionally ordered: **document the contract first** so the implementation is motivated, then **add the invalidation**, then **pin it with a regression test**, and finally **verify the E2E harness gate**.

## Dependency Graph

```text
1.1 (docstring) ──→ 1.2 (invalidation effect) ──→ 2.1 (regression test)
                        │
                        └──→ 3.1 (unit suite) ──→ 3.2 (E2E multi-parcel run) ──→ 3.3 (gate sign-off)
```

- 1.1 can be done in parallel with 2.1 scaffolding, but the docstring text must match the chosen invalidation behavior before the slice is merged.
- 1.2 must land before 2.1 can assert the behavior.
- 3.1 and 3.2 depend on 1.2 and 2.1.
- 3.3 is the final readiness gate.

## Phase 1: Cache-Freshness Contract (Foundation)

### 1.1 Document the cache-freshness contract in `useRainfallAnalysis.ts`

- [x] **1.1.1** Add a code comment / docstring in `consorcio-web/src/hooks/useRainfallAnalysis.ts` that explains:
  - `RainfallDetailPanel` is the owner of rainfall-analysis cache invalidation on parcel change.
  - The rainfall-analysis query key intentionally omits `nomenclatura` so that the same resolved scope + year stays cached for 60 seconds while the user is viewing a single parcel.
  - Parcel-switch invalidation is performed in the panel, not in the hook, because the hook only sees scope + year and cannot know when the underlying parcel changes.
- **Estimate**: 15 min
- **Verification**: Read the comment and confirm it matches the exact invalidation logic added in 1.2.
- **Risk**: Low — pure documentation; must be kept in sync with the actual implementation or it becomes misleading.

### 1.2 Add parcel-change invalidation to `RainfallDetailPanel.tsx`

- [ ] **1.2.1** Import `useQueryClient` from `@tanstack/react-query` in `consorcio-web/src/components/map2d/rainfall/RainfallDetailPanel.tsx`.
- [ ] **1.2.2** Call `const queryClient = useQueryClient();` inside `RainfallDetailPanel`, placed **before** the `if (!canAccess) return null;` early return to keep the hook order stable.
- [ ] **1.2.3** Add a `useEffect` that tracks the previous `nomenclatura` prop and, when it changes (and `canAccess` is true), calls:
  ```ts
  queryClient.invalidateQueries({ queryKey: ['rainfall-analysis'] });
  ```
- [ ] **1.2.4** Ensure the effect does **not** run on initial mount: initialize the previous-value ref to the current `nomenclatura` and compare inside the effect.
- [ ] **1.2.5** Ensure the effect does **not** depend on `year`, `selectedKey`, or `selected` scope changes, so scope/year changes within the same parcel do not trigger invalidation.
- **Estimate**: 30 min
- **Verification**:
  - The new unit test in 2.1 passes.
  - `useEffect` dependency array is exactly `[nomenclatura, canAccess, queryClient]` or equivalent, and does not include `year`/`selected`.
- **Risk**: Medium — if the dependency list is wrong, every scope/year change will throw away the 60-second cache and defeat the request-budgeting behavior.

## Phase 2: Regression Test

### 2.1 Add a regression unit test in `RainfallDetailPanel.test.tsx`

- [ ] **2.1.1** Add a test-specific helper `renderPanelWithClient(queryClient, props)` in `consorcio-web/tests/unit/RainfallDetailPanel.test.tsx` that wraps `RainfallDetailPanel` with the provided `QueryClient` and the standard `MantineProvider`.
- [ ] **2.1.2** Spy on `queryClient.invalidateQueries` with `vi.spyOn(queryClient, 'invalidateQueries')`.
- [ ] **2.1.3** Write a test that:
  - Mounts the panel with `nomenclatura="parcel-a"` and asserts `invalidateQueries` was **not** called for `['rainfall-analysis']` (initial mount is safe).
  - Rerenders to `nomenclatura="parcel-b"` and asserts `invalidateQueries` was called **once** with `{ queryKey: ['rainfall-analysis'] }`.
  - Rerenders again to `nomenclatura="parcel-b"` and asserts the call count stays at one (same-parcel re-render is safe).
- [ ] **2.1.4** (Optional but recommended) Write a second test that changes the year/scope select within the same `nomenclatura` and asserts `invalidateQueries` is not called again.
- [ ] **2.1.5** Confirm the test **fails** if the `useEffect` from 1.2 is removed (regression guard).
- **Estimate**: 45 min
- **Verification**: Run `npm --prefix consorcio-web run test -- --run tests/unit/RainfallDetailPanel.test.tsx` and the new test passes; temporarily comment out the invalidation and confirm it fails.
- **Risk**: Low — test scaffolding is straightforward; the main risk is a stale `QueryClient` between tests if not reset in `afterEach`.

## Phase 3: Verification

### 3.1 Run the RainfallDetailPanel unit suite

- [ ] **3.1.1** Run `npm --prefix consorcio-web run test -- --run tests/unit/RainfallDetailPanel.test.tsx` and confirm all tests pass.
- [ ] **3.1.2** Run `npm --prefix consorcio-web run typecheck` (or the relevant package script) and confirm no new type errors.
- [ ] **3.1.3** Run `npm --prefix consorcio-web run lint` (Biome) and confirm no new lint errors.
- **Estimate**: 15 min
- **Verification**: CI-green unit output; no new errors.
- **Risk**: Low — the change is small, but Biome may complain about unused imports if the spy helper is not cleaned up.

### 3.2 Run the E2E multi-parcel journey

- [ ] **3.2.1** Set up the declared local environment from design D13 of `lluvia-ux-tarjeta`:
  - `FICHA_ENABLED=true docker compose up -d postgres backend`
  - `docker compose exec backend python -m app.domains.geo.etl.load_suelos_catastro`
  - `docker compose up -d martin` (with a reachable port / `VITE_MARTIN_URL` as documented in D13)
  - `npm --prefix consorcio-web run dev`
- [ ] **3.2.2** Execute the dedicated rainfall E2E script:
  ```bash
  E2E_APP_URL=http://localhost:5173 E2E_API_BASE=http://localhost:8000 \
    npm --prefix consorcio-web run test:e2e:rainfall
  ```
  (Script defined in `consorcio-web/package.json` as `test:e2e:rainfall`.)
- [ ] **3.2.3** Confirm the `A→B→C→A` multi-parcel test reaches the harness assertion gate.
- **Estimate**: 30 min (mostly environment warm-up)
- **Verification**: The test passes and the harness report shows the expected 11/0/0/0 assertion gate.
- **Risk**: High — if the local environment is not fully seeded (catastro tiles, Martin reachable, `FICHA_ENABLED`, `suelos_catastro` populated), the spec will skip or fail. This is a known operational risk; the E2E is intentionally not gated in CI.

### 3.3 Sign off the review budget and gate

- [ ] **3.3.1** Estimate the final diff size:
  - Source changes: ~15 lines in `RainfallDetailPanel.tsx` + ~10 lines in `useRainfallAnalysis.ts` = ~25 lines.
  - Test changes: ~35 lines in `RainfallDetailPanel.test.tsx`.
  - **Estimated total changed lines**: ~60 lines (well under the 400-line threshold for full 4R review).
- [ ] **3.3.2** Forecast review workload: one standard lens (`review-reliability` or `review-readability`) because the diff is small, does not touch auth/security/payments, and the behavior change is a TanStack Query pattern. If the slice is merged into a larger branch that already exceeds 400 changed lines, the combined diff must be reviewed at the full 4R tier.
- [ ] **3.3.3** Confirm that `staleTime: 60_000` in `useRainfallAnalysis.ts` is unchanged and that no global `refetchOnMount`/`staleTime` defaults were modified.
- **Estimate**: 10 min
- **Verification**: Diff review shows only the intended lines; no `staleTime` or global query-config changes.
- **Risk**: Low — the change is bounded, but a mis-merge into the parent branch could accidentally drag in unrelated changes.

## Chained-PR Implications

- This change is a **fast-follow PR** to `lluvia-ux-tarjeta` (JDA-001). It assumes the panel, the card hierarchy, and the E2E harness from that change are already on the integration branch.
- The diff is too small to justify its own chain; it should be delivered as **one PR** against the parent branch / after the parent merges.
- Because the E2E harness and the `11/0/0/0` gate are owned by the sibling `rainfall-multi-parcel-e2e-harness` change, this change must be validated on a branch that includes both the UX card slice and the harness slice.
- No backend, contract, migration, or route changes are required.

## Out-of-Scope Reminders

- Do NOT change the rainfall-analysis query key to include `nomenclatura`.
- Do NOT change global TanStack Query `staleTime` or `refetchOnMount` defaults.
- Do NOT add server-side cache headers or API-level invalidation.
- Do NOT refactor the multi-parcel E2E harness itself (owned by `rainfall-multi-parcel-e2e-harness`).
- Do NOT touch visual or UX changes to the Lluvia detail card (owned by `lluvia-ux-tarjeta`).
- Do NOT backport the invalidation pattern to NDVI or suelos panels without an explicit request.
