# Exploration: rainfall-analysis-cache-freshness

## Current State

The Lluvia v2 detail uses two TanStack Query hooks in series:

1. `useRainfallScopes(nomenclatura)` resolves a parcel into regional scope choices. Its key includes the parcel nomenclatura, so each new parcel always fetches fresh scopes (`consorcio-web/src/hooks/useRainfallAnalysis.ts:43-60`).
2. `useRainfallAnalysis(scope, year)` fetches the snapshot. Its key is `['rainfall-analysis', scope.kind, scope.id, scope.version, year]` and it carries `staleTime: 60_000` (`useRainfallAnalysis.ts:77-79`, `:123-139`).

`RainfallDetailPanel` is mounted as long as the ficha is a single parcel (`FichaTerritorialPanel.tsx:581-588`). Its `nomenclatura` prop changes when the user clicks a different parcel, but the component instance survives; only the hook inputs change. Because the analysis key is derived from the resolved *scope*, not the parcel, clicking parcel A → B → C → A within 60 seconds returns to A's cached scope entry. TanStack serves the cached snapshot without a network request.

The E2E harness (`rainfall-v2-detail.spec.ts`) tracks every analysis response in `trace.analysisSequence` and `waitForTargetAnalysis` / `assertTargetReady` require the sequence to increase on each transition (`tests/e2e/helpers/rainfallMultiParcelHarness.ts:1004-1008`). The UI renders the correct parcel, but no new request means `analysisSequence` is stale and the gate fails.

Existing invalidation precedent lives in `consorcio-web/src/hooks/useApprovedZones.ts:137,145,153` and `consorcio-web/src/lib/query.ts:331-352`, which call `queryClient.invalidateQueries({ queryKey: ... })` after mutations or auth changes.

## Affected Areas

- `consorcio-web/src/hooks/useRainfallAnalysis.ts` — key design, `staleTime`; the hook itself may need no change, but its contract must be documented.
- `consorcio-web/src/components/map2d/rainfall/RainfallDetailPanel.tsx` — owns `nomenclatura` and the resolved `selected` scope; the natural place to detect a parcel change and invalidate/refetch.
- `consorcio-web/src/components/map2d/FichaTerritorialPanel.tsx` — passes `parcelaProps.nomenclatura` to the panel; could alternatively own invalidation, but the panel already isolates rainfall concerns.
- `consorcio-web/tests/e2e/rainfall-v2-detail.spec.ts` and `tests/e2e/helpers/rainfallMultiParcelHarness.ts` — the consumer that defines the freshness gate.
- `consorcio-web/tests/hooks/useRainfallAnalysis.test.tsx` / `tests/unit/RainfallDetailPanel.test.tsx` — may need a regression test.

## Approaches

### A. Invalidate the rainfall-analysis cache when the parcel changes

Implementation: in `RainfallDetailPanel`, track the previous `nomenclatura` in a ref; when it changes, call `queryClient.invalidateQueries({ queryKey: ['rainfall-analysis'] })`. Active observers automatically refetch stale entries, so the newly selected parcel's analysis always issues a fresh request. The previous parcel's cache is also marked stale, ensuring the C→A round-trip refetches.

- Pros:
  - Preserves caching *within* a parcel session (same parcel, switching year/scope still benefits from `staleTime`).
  - Minimal surface: one `useEffect` and one import in `RainfallDetailPanel`.
  - Follows the existing mutation invalidation pattern in `useApprovedZones`.
  - Directly satisfies the E2E freshness gate without altering the query key or `staleTime` defaults.
- Cons:
  - Slightly broader than necessary — invalidates the whole `rainfall-analysis` prefix rather than the exact previous scope.
  - Adds a runtime dependency on `useQueryClient` inside a presentational panel.
- Effort: Low

### B. Include the parcel nomenclatura in the analysis query key

Implementation: change `rainfallAnalysisQueryKey(scope, year)` to `['rainfall-analysis', scope.kind, scope.id, scope.version, year, nomenclatura]` or pass a `parcelId` into the hook.

- Pros:
  - Different parcels get distinct cache entries even if they resolve to the same regional scope.
  - No manual invalidation logic.
- Cons:
  - Does **not** solve the C→A re-selection problem by itself: parcel A's cache entry is still fresh 60 seconds later, so returning to A is still a cache hit.
  - Would need to be paired with Approach A, C or D to satisfy the E2E gate, increasing complexity.
  - Increases cache cardinality; fixtures already produce unique scopes per parcel, so this adds little value here.
- Effort: Low-Medium

### C. Lower / conditional `staleTime` or enable `refetchOnWindowFocus` / `refetchOnMount`

Implementation: set `staleTime: 0`, `refetchOnMount: 'always'`, or similar in `useRainfallAnalysis`.

- Pros:
  - Conceptually simple.
- Cons:
  - TanStack Query only auto-refetches stale queries when there is a *trigger* (mount, window focus, invalidation). `RainfallDetailPanel` does not remount when the parcel changes, so `refetchOnMount` does not fire.
  - Lowering `staleTime` globally would force refetches on every observer mount even during normal single-parcel use, increasing server load.
  - `refetchOnWindowFocus` is irrelevant for the E2E harness and would produce noisy refetches in production.
- Effort: Low, but ineffective without a remount or invalidation trigger.

### D. Manual refetch trigger tied to the selection event

Implementation: expose a `refetch` or `onSelectionChange` callback from `RainfallDetailPanel` and have the parent call `query.refetch()` when `fichaSelectionKey` changes; or imperatively call `queryClient.refetchQueries({ queryKey: rainfallAnalysisQueryKey(...) })` in a `useEffect`.

- Pros:
  - Very explicit: the caller decides when freshness matters.
  - Can be scoped to the exact previous scope/key.
- Cons:
  - Requires wiring through `FichaTerritorialPanel` or `MapUiPanels`, leaking rainfall concerns up the tree.
  - `refetchQueries` forces an immediate fetch even for inactive observers; `invalidateQueries` is the more idiomatic TanStack pattern for "data is stale, refetch when observed again".
  - More files touched for no material gain over A.
- Effort: Medium

## Recommendation

**Adopt Approach A**, implemented inside `RainfallDetailPanel`.

Track the previous `nomenclatura` prop and, when it changes, call `queryClient.invalidateQueries({ queryKey: ['rainfall-analysis'] })`. This keeps the fix local to the rainfall detail surface, reuses the established TanStack invalidation idiom, and satisfies the E2E gate while still allowing legitimate 60-second caching during a single parcel session.

First-slice scope:
1. Add the invalidation `useEffect` to `RainfallDetailPanel.tsx`.
2. Add a regression test in `RainfallDetailPanel.test.tsx` proving that rendering the panel with a new `nomenclatura` invalidates `['rainfall-analysis']` (use `queryClient.isFetching` or a spy on `invalidateQueries`).
3. Run `rainfall-v2-detail.spec.ts` and confirm the multi-parcel journey reaches 11/0/0/0.
4. Update the docstring in `useRainfallAnalysis.ts` to note that the panel invalidates on parcel change; the hook itself can remain unchanged.

## Risks

- **Extra network requests in production**: a user rapidly switching between parcels will refetch each analysis. This is the intended tradeoff for fresher per-parcel data and matches the E2E contract.
- **Test leakage**: `invalidateQueries` needs a real `QueryClient`. `RainfallDetailPanel.test.tsx` already wraps with `QueryClientProvider`, so no new test infrastructure is required.
- **Scope-within-parcel churn**: if the user switches between zone and basin inside the same parcel, `nomenclatura` does not change, so no invalidation occurs. That is correct — the query key already changes and fetches the other scope.
- **Mobile sheet unmounts**: on narrow viewports the panel may unmount when the sheet is minimized. The invalidation is tied to `nomenclatura`, not mount state, so repeated open/close of the same parcel does not over-invalidate.

## Ready for Proposal

Yes. The root cause is clear, the fix surface is small, and Approach A is the lowest-risk way to make the E2E gate pass without disabling legitimate caching.
