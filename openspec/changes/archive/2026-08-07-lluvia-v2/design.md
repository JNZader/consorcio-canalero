# Design: Rainfall v2 Technical Analysis

## Technical approach

Add a bounded `geo/rainfall` capability; keep `POST /geo/analisis-zona` and `PrecipChart` unchanged.

```
Celery adapters -> canonical intervals -> immutable store -> policy/derivation -> revision snapshot
                                              ^                 |
ficha -> authenticated rainfall router -> scope resolver --------+-> JSON/CSV -> detail panel
```

Routers authorize/validate. Services own scope, policy, temporal rules and serialization; repositories use SQLAlchemy; adapters implement ports, never reaching routers.

## Canonical contracts

| Contract | Shape |
|---|---|
| `ScopeRef` | `{kind: zone|basin,id,version}` or `{kind: parcel,nomenclature}` or `{kind: geometry,geometry}`; only resolved zone/basin are executable. |
| `MetricResult` | `{metric,value?,unit,state,reason?,interval,coverage,completeness,quality,temporal_state,revision,provenance,fallback,discrepancies}`; states are `available|partial|suppressed|unavailable`, temporal state `provisional|final`. Null never means zero; values retain source-supported precision. |
| Provenance | `{source_id,source_class,method,nominal_resolution,aggregation,spatial_scope,freshness,available_through}`; classes remain `observed_station|estimated_radar|estimated_satellite`. |
| Analysis request/result | Request is `{scope,year,event_window?}`; `event_window` is required only for peak/duration. Result is `{analysis_revision_id,scope,regional_estimate,year,comparison_end,baseline:1991-2020,annual:{selected,normal,percentile},antecedents:{d7,d30,d90},intensity:{p30,p60,p3h,p24h,i30,i60,peak,duration,event_window?},summary,source_health}`. |

`POST /geo/rainfall/scopes:resolve`, `POST /geo/rainfall/analyses`, and `GET /geo/rainfall/analyses/{revision}.csv` require `require_admin_or_operator`, Origin/content-type CSRF middleware and rate limiting. POST bodies use the shared streamed bounded-JSON parser before Pydantic validation. The server derives the request fingerprint from `{scope,year,event_window?}` and selects the newest immutable snapshot by creation time; policy/data revision keys are never client inputs, while CSV revision URLs retain explicit historical retrieval. JSON/CSV share one validated canonical envelope and metric-row traversal; unauthorized or malformed snapshots reveal no values.

## Decisions

| Area | Decision and rationale |
|---|---|
| Persistence | Add `rainfall_source_eligibility`, `rainfall_interval_value`, and immutable `rainfall_analysis_revision`. Uniqueness covers source/scope/version/interval/provider revision and analysis request/policy/data revision; idempotent upserts append changed revisions. This is zonal rainfall history plus audit snapshots—not the removed one-row-per-zone/day table or a generic observation platform. Final intervals/eligibility remain; superseded revisions retain two years; raw payloads are not DB records. Backfills are source/scope/year batches with checkpoints. |
| Scope | Zone = approved-zoning feature stable id + zoning version; basin = `ZonaOperativa.id` + geometry hash. Missing stable identity is ineligible. Parcel PostGIS intersections return ordered zone/basin choices; no match is unavailable, ambiguous overlaps require selection. Every parcel result is regional. Geometry/direct parcel compute is rejected. |
| Time and events | Policy timezone is `America/Argentina/Buenos_Aires`; adapters declare UTC half-open intervals, converted once to local calendar dates. Historical/current comparison ends Dec-31 or `available_through`; baseline years end on the same month/day. Feb-29 uses leap baseline years only and is never imputed. Antecedents are the N local dates ending at comparison end across years. P30/P60/P3h/P24h are rolling sums; I30=P30/0.5h and I60=P60/1h. An event request supplies local, half-open `[start,end)` `event_window`; it is required for peak/duration and Rainfall v2 never discovers, catalogs, or auto-selects events. For the chosen source, boundaries must align to its cadence and expected intervals are every cadence interval wholly inside the window. Wet means per-interval rainfall at or above the versioned duration threshold; that rainfall cutoff is never compared with the final duration-in-time value. Dry or missing intervals break contiguity. Exactly one contiguous wet run is required: no run, multiple runs, boundary misalignment, unsupported cadence, incomplete expected-interval coverage (`verified/expected` must be 100%), or failed quality suppresses both metrics with a specific reason; the user must submit a narrower window. Duration is wet-run interval count × cadence. Peak is the maximum supported rolling sum wholly inside that same window (earliest start wins ties). Unset coverage/quality/duration policy suppresses the paired peak/duration disclosure, never permits it. The domain technical lead approves policy; platform operations activates it. |
| Sources | `RainfallSourceAdapter.fetch(request)->SourceBatch`; no SDK escapes adapters. A versioned metric-role policy considers only audit-passed access, licence, units, boundaries, cadence, completeness, revisions, corridor, quality and known events, chooses one ordered source, records failures/discrepancies, never blends. Evidence-gated candidates: baseline CHIRPS v3; daily SQPE-OBS/CHIRPS; intensity SINARAME RQPE→IMERG V07→PERSIANN; accessible gauges validate/observe. Disabled until evidence passes; rendered-image access fails. |
| Spike | Versioned manifests, representative corridor scopes/events, provider fixtures/checksums and golden reports prove conversions, boundaries, coverage, discrepancy and provisional->final behavior. Eligibility rows contain every criterion and evidence revision. Passed subsets enable independent metrics/fallbacks while others stay unavailable. |
| Execution | Beat/outbox Celery jobs ingest daily, revisit provisional windows and batch backfills. Requests read DB/Redis only; missing work is queued and labelled. Per-provider timeout, quota, bounded retry/circuit and stale-labelled cache prevent ficha blocking; metric failures are isolated. Cache key includes scope, geometry, year, policy and data revisions; structured metrics log latency, gaps, fallbacks and revisions. |

## Frontend and testing

`FichaTerritorialPanel` keeps the public compact chart and conditionally mounts an authenticated `RainfallDetailPanel`. TanStack Query owns resolve/analysis; component state owns selected scope/year. Summary, comparison/antecedent/intensity charts, source-health disclosure and CSV expose all states, badges, reasons and regional labels. Controls are keyboard-labelled, status announcements use live regions, charts have textual equivalents, and layouts collapse for the sheet. React 19 components use named imports, strict flat TypeScript contracts and no new manual memoization.

TDD maps R1-R13 and all 38 scenarios: policy/time/scope/serializer units; adapter contract fakes and spike goldens; PostgreSQL migration/revision/auth/CSV integrations; Vitest state/accessibility; Playwright ficha authorization/switch/export. Replace stale `rainfall-api.spec.ts`; mutation targets cover policy, suppression, temporal windows and CSV parity.

## Rollout, files and traceability

Migrate tables/IDs, run spike, backfill validated sources, then enable provider, API and UI flags progressively. Rollback disables flags/jobs and keeps audits; the public normal is untouched. Replays use idempotency keys and checkpoints.

Files: create `gee-backend/app/domains/geo/rainfall/{models,schemas,repository,ports,policy,scope,temporal,service,router,tasks,adapters/}`, migration and tests; register router/outbox/Beat/config. Create `consorcio-web/src/{lib/api/rainfall.ts,hooks/useRainfallAnalysis.ts,components/map2d/rainfall/}`; modify panel/query keys and replace the stale E2E.

| Requirements | Components |
|---|---|
| R1-R2 | auth router, panel, resolver |
| R3-R7 | temporal/derivation, contracts, revisions |
| R8-R10 | policy, eligibility, adapters |
| R11-R12 | interval engine, shared JSON/CSV serializer |
| R13 | bounded reusable rainfall snapshots; exclusions enforced |

Rejected: provider logic in routers, silent blending, scrape-only sources, arbitrary geometry, unchanged removed table, and synchronous provider fan-out. Risks: scientific misrepresentation, access/licence loss, sparse validation, volume/quotas, drift/revisions, authorization and unclear operations; mitigations are evidence gates, labels, quotas, immutable revisioning, deny-by-default auth and named policy/data owners.

## Open questions

- Which named people fill the technical-lead, data-operations and validation-approval roles?
- Which representative events/gauges are approved for the spike?
