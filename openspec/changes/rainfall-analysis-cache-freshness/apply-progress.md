# Apply Progress: rainfall-analysis-cache-freshness

**Branch**: `fix/rainfall-analysis-cache-freshness`  
**Base**: `feat/lluvia-ux-tarjeta`  
**Mode**: Standard (design.md was not present; explore.md served as the technical handoff)  
**Status**: Phase 1 and 2 complete; Phase 3.1 green; Phase 3.2 blocked by unseeded local environment.

---

## Completed Tasks

- [x] **1.1** Documented the cache-freshness contract in `useRainfallAnalysis.ts` as a JSDoc block on `useRainfallAnalysis`.
- [x] **1.2** Added parcel-change invalidation to `RainfallDetailPanel.tsx`:
  - Imported `useQueryClient` from `@tanstack/react-query`.
  - Added `useQueryClient()` before the `canAccess` early return.
  - Added a `useEffect` that tracks the previous `nomenclatura` and calls `queryClient.invalidateQueries({ queryKey: ['rainfall-analysis'] })` exactly once per parcel change.
  - Dependency array is `[nomenclatura, canAccess, queryClient]`; no dependency on `year`, `selectedKey`, or `selected`.
- [x] **2.1** Added regression unit test in `RainfallDetailPanel.test.tsx`:
  - `renderPanelWithClient(queryClient, props)` helper using `QueryClientProvider` + `MantineProvider` wrapper.
  - Test verifies no invalidation on initial mount, invalidation on parcel change, and no re-invalidation on same-parcel rerender.
  - Optional test verifies scope/year changes inside the same parcel do not invalidate.
  - Confirmed the test fails when the invalidation `useEffect` is removed.
- [x] **3.1** Verification:
  - `npm --prefix consorcio-web run test -- --run tests/unit/RainfallDetailPanel.test.tsx` → 24/24 passing.
  - `npm --prefix consorcio-web run typecheck` → no new errors.
  - `npm --prefix consorcio-web run lint` → no new lint errors (3 pre-existing warnings unchanged).
- [x] **3.3** Review-budget sign-off:
  - Source diff ≈ 20 lines, test diff ≈ 80 lines; total well under 400-line threshold.
  - Recommends one standard lens (`review-reliability`) because the change is a bounded TanStack Query pattern.
  - `staleTime: 60_000` and global query defaults are untouched.

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `consorcio-web/src/hooks/useRainfallAnalysis.ts` | Modified | Added JSDoc cache-freshness contract on `useRainfallAnalysis`. |
| `consorcio-web/src/components/map2d/rainfall/RainfallDetailPanel.tsx` | Modified | Imported `useQueryClient`; added parcel-change invalidation effect. |
| `consorcio-web/tests/unit/RainfallDetailPanel.test.tsx` | Modified | Added `renderPanelWithClient` helper and cache-freshness regression tests. |

## Discovered Patterns

- The parent branch `feat/lluvia-ux-tarjeta` carries an earlier version of `RainfallDetailPanel.tsx` (277 lines) than the `openspec/archive-rainfall-e2e` worktree snapshot (679 lines). The implementation was adapted to the parent-branch version, which is the correct fast-follow base.
- Existing tests wrap `RainfallDetailPanel` with `QueryClientProvider` + `MantineProvider`; the new helper reuses that pattern but accepts an external `QueryClient` so `invalidateQueries` can be spied on.
- `vi.spyOn(queryClient, 'invalidateQueries')` works directly against a `QueryClient` instance; no manual `jest.mock` of `@tanstack/react-query` is needed.
- The pre-commit hook rebuilds the frontend on every commit; `consorcio-web/public/version.json` changes but is left unstaged and uncommitted.

## Deviations from Design

- `design.md` was not present in the artifact store; `explore.md` served as the implementation guide. Approach A (invalidate in panel on parcel change) was implemented exactly as recommended.
- The parent branch does not yet include the Phase-3 answer-first hierarchy, one-step year fallback, or `CollapsibleSection` folds, so the regression test was written against the simpler panel surface that is actually on the base branch.

## Issues Found / Blockers

- **Phase 3.2 (E2E multi-parcel journey) could not be executed**:
  - `docker compose ps` fails with `required variable REDIS_PASSWORD is missing a value`.
  - The local stack (postgres, backend, martin, redis) is not running and is not seeded with `suelos_catastro`.
  - Running `npm --prefix consorcio-web run dev` would not have a reachable API, and the Playwright harness would soft-skip or fail on missing catastro tiles.
  - Per the spec, this E2E is intentionally not gated in CI and depends on the sibling `rainfall-multi-parcel-e2e-harness` slice being combined with this one for a full validation run.
  - **What is needed**: a `.env` with `REDIS_PASSWORD`, `docker compose up -d postgres backend`, seed `suelos_catastro`, `docker compose up -d martin`, a reachable `VITE_MARTIN_URL`, and `npm --prefix consorcio-web run dev` before running `npm --prefix consorcio-web run test:e2e:rainfall`.

## Remaining Tasks

- [ ] **3.2** Run `rainfall-v2-detail.spec.ts` multi-parcel journey once the local environment is seeded and report the 11/0/0/0 gate.
- [ ] **3.3.2** Apply the recommended `review-reliability` lens before merge.

## Next Recommended Steps

1. Merge this slice into the integration branch that already contains `lluvia-ux-tarjeta` and `rainfall-multi-parcel-e2e-harness`.
2. Run the E2E harness on the combined branch in a fully seeded environment.
3. Run the `review-reliability` lens on the final diff.
