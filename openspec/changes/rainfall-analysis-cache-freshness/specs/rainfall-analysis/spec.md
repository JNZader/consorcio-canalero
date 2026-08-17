# Delta Spec: Rainfall Analysis Cache Freshness

## Domain

`rainfall-analysis` (frontend cache-freshness behavior in `RainfallDetailPanel`)

## ADDED Requirements

### Requirement: Parcel-Change Cache Invalidation for Rainfall Analysis

The system MUST invalidate all cached queries matching the `['rainfall-analysis']` query-key prefix whenever the `nomenclatura` prop passed to `RainfallDetailPanel` changes. The system MUST NOT trigger that invalidation on initial mount, on re-render with an unchanged `nomenclatura`, or on scope/year selection changes within the same parcel.

#### Scenario: Parcel change triggers rainfall-analysis invalidation (happy path)

- GIVEN `RainfallDetailPanel` is rendered for parcel A with a `QueryClient`
- AND the rainfall-analysis query for parcel A's resolved scope is cached
- WHEN the `nomenclatura` prop changes to parcel B
- THEN the system calls `queryClient.invalidateQueries({ queryKey: ['rainfall-analysis'] })`
- AND the active rainfall-analysis observer for parcel B issues a fresh network request

#### Scenario: Initial render and same-parcel re-render do not invalidate

- GIVEN `RainfallDetailPanel` is rendered for parcel A
- WHEN the component mounts or re-renders without a `nomenclatura` change
- THEN the system does NOT call `invalidateQueries` for the rainfall-analysis prefix

#### Scenario: Scope or year change within the same parcel does not invalidate

- GIVEN `RainfallDetailPanel` is rendered for parcel A
- AND the user switches scope or year while staying on parcel A
- WHEN the selection changes
- THEN the system does NOT call `invalidateQueries` for the rainfall-analysis prefix
- AND the existing 60-second `staleTime` cache for that parcel remains valid

#### Scenario: Returning to a previously selected parcel refetches fresh data

- GIVEN parcels A, B, and C were each selected within the 60-second stale window
- WHEN the user selects parcel A again
- THEN the rainfall-analysis cache entry for parcel A is stale
- AND a fresh network request is issued for parcel A

### Requirement: Cache-Freshness Contract Documentation

The system MUST document, in the `useRainfallAnalysis` hook docstring or adjacent code comment, that `RainfallDetailPanel` owns rainfall-analysis cache invalidation on parcel change and that the rainfall-analysis query key intentionally omits `nomenclatura`.

#### Scenario: Developer reads hook documentation

- GIVEN a developer inspects `useRainfallAnalysis.ts`
- WHEN they read the cache-freshness contract comment
- THEN they understand that parcel-switch invalidation is performed by the panel
- AND they understand why the query key does not include `nomenclatura`

## MODIFIED Requirements

### Requirement: Supported Analysis Scope and Parcel Semantics

When the selected parcel changes, the system MUST treat any cached rainfall-analysis result as stale and MUST refetch the analysis for the newly selected parcel instead of serving the cached snapshot from the previous parcel.

(Previously: the requirement defined scope resolution and regional-estimate labelling but did not address cache invalidation across parcel switches.)

#### Scenario: Parcel switch no longer shows previous parcel's cached analysis

- GIVEN authorized staff viewed rainfall analysis for parcel A
- AND the 60-second stale window has not elapsed
- WHEN staff select parcel B
- THEN the system displays a loading or queued state for parcel B's analysis
- AND does not render parcel A's cached rainfall snapshot for parcel B

## REMOVED Requirements

None.

## Non-Functional Requirements

### Performance

The rainfall-analysis cache invalidation logic SHOULD run only once per actual parcel transition and SHOULD NOT cause additional invalidations on scope/year changes or repeated mount/unmount of the same parcel.

Within a single parcel session, the existing 60-second `staleTime` for rainfall-analysis queries MUST remain in effect, preserving the current request-budgeting behavior.

### Testability

A regression unit test in `RainfallDetailPanel.test.tsx` MUST verify that changing `nomenclatura` calls `invalidateQueries({ queryKey: ['rainfall-analysis'] })`.

The unit test MUST fail if the invalidation logic is removed.

The E2E multi-parcel journey in `rainfall-v2-detail.spec.ts` MUST report an 11/0/0/0 gate (11 passing assertions, 0 expected, 0 unexpected, 0 failing).

## Acceptance Criteria

- [ ] `RainfallDetailPanel.tsx` invalidates `['rainfall-analysis']` whenever `nomenclatura` changes.
- [ ] No invalidation occurs on initial mount or re-render with the same `nomenclatura`.
- [ ] Scope/year changes within the same parcel do not trigger invalidation.
- [ ] A new unit test in `RainfallDetailPanel.test.tsx` fails if invalidation logic is removed.
- [ ] `useRainfallAnalysis.ts` docstring documents the cache-freshness contract.
- [ ] `rainfall-v2-detail.spec.ts` multi-parcel journey reports **11/0/0/0**.
- [ ] Within a single parcel session, the 60-second cache remains effective.

## Out of Scope

- Redesigning the rainfall-analysis query key to include `nomenclatura`.
- Changing global TanStack Query `staleTime` or `refetchOnMount` defaults.
- Adding server-side cache headers or API-level invalidation.
- Refactoring the multi-parcel E2E harness itself (owned by sibling change `rainfall-multi-parcel-e2e-harness`).
- Visual or UX changes to the Lluvia detail card (owned by parent `lluvia-ux-tarjeta` JDA-001).
- Backporting the invalidation pattern to other detail panels (NDVI, suelos) without an explicit request.
