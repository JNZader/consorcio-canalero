# Delta Spec: Rainfall Analysis Cache Freshness

## Domain

`rainfall-analysis` (frontend cache-freshness behavior in `RainfallDetailPanel`)

## ADDED Requirements

### Requirement: Per-Parcel Rainfall Analysis Query Key

The `useRainfallAnalysis` hook MUST include the source parcel `nomenclatura` in the rainfall-analysis query key so that each parcel has an independent cache entry. The key MUST also carry the resolved scope (`kind`, `id`, `version`) and the selected `year`.

#### Scenario: Parcel A and parcel B with different scopes have independent cache entries

- GIVEN `useRainfallAnalysis` is called for parcel A with scope SA and year Y
- AND the result is cached
- WHEN `useRainfallAnalysis` is called for parcel B with scope SB and year Y
- THEN the query key for parcel B differs from parcel A's key
- AND a fresh network request is issued for parcel B

#### Scenario: Re-rendering the same parcel reuses the cached analysis

- GIVEN `RainfallDetailPanel` is rendered for parcel A with scope SA and year Y
- AND the analysis result is cached
- WHEN the panel re-renders with the same `nomenclatura`, scope, and year
- THEN no new rainfall-analysis network request is issued
- AND the cached result is served

#### Scenario: Scope or year change within the same parcel creates a new query

- GIVEN `RainfallDetailPanel` is rendered for parcel A with scope SA and year Y
- WHEN the user selects a different scope or year while staying on parcel A
- THEN the rainfall-analysis query key changes to reflect the new scope/year
- AND a new network request is issued for the new scope/year combination
- AND the result is cached independently under the parcel's key

### Requirement: No Production Cache Invalidation

The system MUST NOT call `queryClient.invalidateQueries` for the rainfall-analysis query prefix in `RainfallDetailPanel` or any related production code. Cache freshness across parcels is achieved exclusively through the per-parcel query key.

#### Scenario: Parcel change does not trigger invalidation

- GIVEN `RainfallDetailPanel` is rendered for parcel A
- WHEN the `nomenclatura` prop changes to parcel B
- THEN the system does NOT call `queryClient.invalidateQueries({ queryKey: ['rainfall-analysis'] })`
- AND a fresh analysis query for parcel B runs because the key differs

#### Scenario: Scope or year change does not trigger invalidation

- GIVEN `RainfallDetailPanel` is rendered for parcel A
- WHEN the user switches scope or year while staying on parcel A
- THEN the system does NOT call `queryClient.invalidateQueries` for the rainfall-analysis prefix
- AND the new query is created naturally by the key change

### Requirement: E2E Cache-Freshness Gate (Option A)

The multi-parcel E2E harness MUST accept that a repeat parcel selection inside the 60-second stale window may be served from the per-parcel cache without a new network request. For the final `C→A` transition in the `A→B→C→A` journey, the harness MUST treat the selection as fresh when the rendered card matches the target fixture exactly, even if the recorded analysis sequence or trace key is not newer than the previous transition.

#### Scenario: Final C→A is served from cache

- GIVEN the `A→B→C→A` multi-parcel journey has reached the final A selection
- AND parcel A's analysis is still within the 60-second stale window
- WHEN the user selects parcel A again
- THEN the E2E harness MAY observe that no new analysis network request was issued
- AND the harness MUST pass if the rendered identity, scope sentence, percentile, accumulation, and metric revision all match fixture A

#### Scenario: A→B and B→C still require a newer analysis sequence

- GIVEN the user transitions from parcel A to parcel B
- WHEN the harness waits for the target analysis
- THEN it MUST wait for a newer recorded analysis sequence than the previous transition
- AND the trace key, scope, and rendered values MUST all match fixture B

## MODIFIED Requirements

### Requirement: Supported Analysis Scope and Parcel Semantics

When the selected parcel changes, the system MUST fetch the analysis for the newly selected parcel instead of serving the cached snapshot from the previous parcel. The per-parcel query key guarantees this by construction.

(Previously: the requirement assumed the same query key and required invalidation; now the key itself includes the parcel identity.)

#### Scenario: Parcel switch no longer shows previous parcel's cached analysis

- GIVEN authorized staff viewed rainfall analysis for parcel A
- AND the 60-second stale window has not elapsed
- WHEN staff select parcel B
- THEN the system displays a loading or queued state for parcel B's analysis
- AND does not render parcel A's cached rainfall snapshot for parcel B

## REMOVED Requirements

- The requirement that `RainfallDetailPanel` call `queryClient.invalidateQueries({ queryKey: ['rainfall-analysis'] })` on parcel change is removed because the per-parcel query key makes it unnecessary.
- The requirement that `useRainfallAnalysis.ts` docstring state that the panel owns invalidation is removed; the docstring now states that the query key itself carries the parcel identity and that no production invalidation is used.

## Non-Functional Requirements

### Performance

The per-parcel cache key preserves the existing 60-second `staleTime` within a single parcel session. Scope or year changes within the same parcel create a new query for the new combination, but re-selecting the same scope/year for the same parcel reuses the cached entry.

There MUST be no production `invalidateQueries` calls for the rainfall-analysis prefix, avoiding unnecessary cache churn and refetch coordination.

### Testability

A regression unit test in `RainfallDetailPanel.test.tsx` MUST verify that changing `nomenclatura` creates a new `fetchRainfallAnalysis` call.

A regression unit test MUST verify that re-rendering with the same `nomenclatura` does not create a new `fetchRainfallAnalysis` call.

An optional unit test MAY verify that switching scope/year within the same parcel and reverting reuses the cached query without a new fetch.

The E2E multi-parcel journey in `rainfall-v2-detail.spec.ts` MUST report an 11/0/0/0 assertion gate.

## Acceptance Criteria

- [ ] `useRainfallAnalysis.ts` builds the rainfall-analysis query key with `scope.kind`, `scope.id`, `scope.version`, `year`, and `nomenclatura`.
- [ ] `RainfallDetailPanel.tsx` does NOT call `queryClient.invalidateQueries` for the rainfall-analysis prefix.
- [ ] `RainfallDetailPanel.tsx` passes `nomenclatura` to `useRainfallAnalysis`.
- [ ] A unit test in `RainfallDetailPanel.test.tsx` verifies that a `nomenclatura` change creates a new analysis fetch.
- [ ] A unit test verifies that a same-`nomenclatura` re-render does not create a new analysis fetch.
- [ ] An optional unit test verifies scope/year cache reuse within the same parcel.
- [ ] `rainfall-v2-detail.spec.ts` multi-parcel journey reports **11/0/0/0**.
- [ ] The E2E harness accepts the final `C→A` repeat selection as fresh when the rendered card matches fixture A, even without a newer analysis sequence.
- [ ] Within a single parcel session, the 60-second `staleTime` remains effective.

## Out of Scope

- Changing global TanStack Query `staleTime` or `refetchOnMount` defaults.
- Adding server-side cache headers or API-level invalidation.
- Refactoring the multi-parcel E2E harness fixture itself (owned by sibling change `rainfall-multi-parcel-e2e-harness`).
- Visual or UX changes to the Lluvia detail card (owned by parent `lluvia-ux-tarjeta` JDA-001).
- Backporting the per-parcel key pattern to other detail panels (NDVI, suelos) without an explicit request.
- Adding production invalidation logic to force refetches on parcel change.
