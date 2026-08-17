# Design: Rainfall Analysis Cache Freshness

## Change

`rainfall-analysis-cache-freshness` — fast-follow to `lluvia-ux-tarjeta` JDA-001.

## Goal

Make the multi-parcel E2E harness reach the **11/0/0/0** assertion gate while preserving the 60-second per-parcel cache for rainfall analysis.

## Decision Log

| Decision | Option A | Option B | Selected |
|----------|----------|----------|----------|
| Cache strategy | Invalidate `['rainfall-analysis']` on parcel change | Include `nomenclatura` in the analysis query key | **B** |
| E2E freshness gate for C→A | Require newer sequence + trace key | Accept cache-served response if rendered card matches fixture | **A** |

## Approach B: Per-Parcel Query Key

The `useRainfallAnalysis` hook builds the query key as:

```ts
['rainfall-analysis', scope.kind, scope.id, scope.version, year, nomenclatura]
```

This makes each parcel's analysis independent. Selecting a different parcel always produces a new query and a fresh network request. Re-selecting the same parcel within the 60-second `staleTime` reuses the cached entry, which is the intended TanStack Query behavior.

The query key also continues to carry the resolved scope and year, so scope/year changes within the same parcel naturally create new queries without any production invalidation.

## Option A: Cache-Served Repeat Selections Are Fresh

Owner decision #15286 resolved the W9 contradiction: for the final `C→A` transition inside the stale window, React Query may serve parcel A's cached entry without a new network request. The E2E harness treats this as fresh when the rendered card matches the target fixture exactly:

- `renderedIdentity` equals the target's `nomenclature`
- `renderedScopeSentence` matches the prettified scope sentence
- `renderedPercentile` equals the target's percentile
- `renderedAccumulationMm` equals the target's accumulation
- `renderedMetricRevision` equals the target's metric revision

The stricter newer-sequence gate is kept only for `A→B` and `B→C`, where a new parcel selection always produces a new request because the per-parcel key differs.

## Production Files

- `consorcio-web/src/hooks/useRainfallAnalysis.ts`: defines the query key, `staleTime`, and `nomenclatura` option.
- `consorcio-web/src/components/map2d/rainfall/RainfallDetailPanel.tsx`: passes `nomenclatura` to the hook; no `invalidateQueries`.

## Test Files

- `consorcio-web/tests/unit/RainfallDetailPanel.test.tsx`: per-parcel query-key regression tests.
- `consorcio-web/tests/e2e/helpers/rainfallMultiParcelHarness.ts`: `assertTargetReady` / `assertMobileReady` cache-served repeat logic.
- `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts`: `waitForTargetAnalysis` accepts the final `C→A` cache hit.

## Risks

- The fixture's `effectiveCacheKey` does not include `nomenclatura`, but the E2E trace is internally consistent because both sides use the fixture value. If the harness is later reused to assert the exact real cache key, the fixture will need updating.
- A user rapidly switching between parcels will issue more requests than the old shared-key approach, but each parcel still benefits from the 60-second cache if revisited within the window.
- The `assertTargetReady` relaxation must be scoped to repeat selections only; otherwise the strict freshness gate for `A→B` and `B→C` would be lost.
