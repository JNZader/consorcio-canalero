# Proposal: Ficha Territorial (territorial report card)

## Intent

Inspired by the INTA territorial app: produce an integrated, on-demand report for any
area of interest — soil capability classes, flood risk, drainage need, area in hectares,
BPA/forestación membership and monthly precipitation — as percentages of that area.

Today the platform shows those datasets as **separate map layers the user must read by
eye**. Nobody can answer "how much of this parcel is class VI soil AND high drainage
need?" without a manual QGIS session. The consorcio's core decision is **drainage
prioritization**: which parcels/canal corridors get intervention first. That decision
needs one number per area, not four visual layers.

## Scope

### In Scope (phases 0-5, chained PRs)

| Phase | Deliverable |
|---|---|
| 0 | ETL populating `suelos_catastro` from `suelos_cu.geojson`; migration DROPping dead twins `canales_geo` + `mv_canales_por_zona` (rainfall_records precedent) |
| 1 | `POST /api/v2/geo/analisis-zona` `tipo=parcela`: soils % via PostGIS `ST_Intersection`/32720, flood_risk + drainage_need % via class-binned zonal stats, hectares, BPA/forestación join by `nro_cuenta`; `FichaTerritorialCard` fetched by a container (not InfoPanel — it is pure) |
| 2 | `tipo=poligono` — free polygon via existing `DrawControl` |
| 3 | `tipo=canal_buffer` — canal selection + `ST_Buffer` influence zone in EPSG:32720 |
| 4 | CHIRPS precomputed monthly-normal rasters + recharts monthly bar chart (same zonal-stats path) |
| 5 | `tipo=canal_cuenca` — real drainage catchment via `flow_dir` + WBT `watershed`; caller chooses natural vs relevado variant |

Cross-cutting, phase 1 onward: **public** endpoint (all joined data is already public via
tiles and static geojson) with NON-NEGOTIABLE mitigations — `DistributedRateLimiter`
(first geo consumer), polygon area cap + vertex cap, `audit_log` entry per request
(Ley 25.326).

### Out of Scope / NON-goals

- Reviving `canales_geo` — `canal_network` is the real table; the twin is dropped.
- Live GEE `reduceRegion` per click. Precomputed normals only.
- Fixing the 2 latent bugs found in exploration (`zonal_stats.py:89` nodata `-32768` vs
  composites' `-9999.0`; WBT `watershed` fed a DEM instead of a D8 pointer at
  `intelligence/tasks.py:353`). **Backlog tickets, fixed BETWEEN SDDs.** Phase 5 is
  blocked on the D8 fix landing first.
- Named scenarios, saved comparisons, delta maps, PDF export.
- Reviving the orphaned `Afectados*` schemas.
- Authenticated/PII-widening variants (nothing beyond what tiles already expose).

## Capabilities

`openspec/specs/` does not exist in this repo; all capabilities are new.

### New Capabilities
- `territorial-analysis-api`: single `POST /geo/analisis-zona` with discriminated-union
  body (`parcela | poligono | canal_buffer | canal_cuenca`) → one uniform response schema;
  public + rate-limited + audited.
- `soils-catastro-etl`: idempotent load of soil polygons into `suelos_catastro`; dead
  schema removal.
- `precipitation-normals`: CHIRPS monthly-normal raster generation + registration.
- `territorial-report-ui`: ficha card, draw/canal selection entry points, monthly chart.

### Modified Capabilities
- None.

## Approach

Collapse the whole ficha into **"N rasters × 1 geometry" + "1 vector overlay × 1
geometry"**. Standardize every raster read on `extract_composite_zonal_stats`
(`composites.py:258`) — it reads nodata from the raster and already computes
`pixel_area_ha`; add class binning instead of the single `_HIGH_RISK_THRESHOLD`. Reuse
the `mv_suelos_por_zona` SQL from migration `0015:94-113` verbatim for the vector half.
Precipitation becomes 12 small rasters, so it enters the same code path — no second
implementation. Endpoint lives in `router_analysis.py` unless it exceeds ~300 lines.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `gee-backend/app/db/migrations/` | New | Drop `canales_geo` + `mv_canales_por_zona`; soils ETL support |
| `gee-backend/app/domains/geo/router_analysis.py` | Modified | New `analisis-zona` endpoint |
| `gee-backend/app/domains/geo/composites.py` | Modified | Class-binning zonal variant |
| `gee-backend/app/domains/geo/gee_service.py` | Modified | CHIRPS normals export |
| `gee-backend/app/core/rate_limit.py` | Modified (use) | First geo consumer |
| `gee-backend/app/shared/audit_log.py` | Modified (use) | New action for zone analysis |
| `consorcio-web/src/components/map/` | New/Modified | `FichaTerritorialCard`, container fetch, DrawControl wiring |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `suelos_catastro` empty dead schema — biggest hidden cost | High | Phase 0 is a standalone prerequisite PR with its own verification |
| `parcelas_catastro` may be empty in target env | Med | Phase 0 verifies population in prod; ficha returns explicit "sin datos" |
| nodata mismatch `-32768` vs `-9999.0` | High | Ban `compute_zonal_stats` for composites; standardize on `extract_composite_zonal_stats` |
| Zones fully in raster nodata are SKIPPED silently (`composites.py:361`) | Med | Response MUST distinguish `0%` from `sin cobertura` |
| `all_touched=True` overestimates on sub-pixel parcels (30 m UTM) | High | Report pixel count + a low-confidence flag for tiny parcels |
| Burned (relevado) vs natural DEM defaults | Med | Phase 5 exposes the variant to the caller; default documented |
| WBT `watershed` D8-pointer bug | High | Phase 5 blocked until the backlog fix lands; do NOT copy the existing call |
| Public endpoint = amplification vector | High | Rate limit + area cap + vertex cap, enforced before any raster read |
| Ley 25.326 surface from per-parcel BPA + `nro_cuenta` | Med | `audit_log` on every request; expose nothing beyond current tile properties |
| Large-polygon payload/latency | Med | Area cap; percentages only, no geometry echo |
| CHIRPS normals refresh drift | Low | Normals are static; regenerate on demand, version in `metadata_extra` |

## Rollback Plan

Per-phase, since each phase is its own PR. Phase 0 migration is reversible for the soils
load (`DELETE FROM suelos_catastro`); the twin DROP follows the `rainfall_records`
precedent (downgrade unsupported, documented). Phases 1-5: revert the PR — the endpoint
is additive and the UI card is behind a feature-flagged panel, so removing it restores
current behavior. No existing endpoint contract changes.

## Dependencies

- `suelos_cu.geojson` as ETL source (provenance/rebuild path is an open question).
- Google Earth Engine credentials for the one-time CHIRPS normals export.
- Backlog fix for the WBT D8-pointer bug — blocks Phase 5 only.
- Redis available for `DistributedRateLimiter`.

## Success Criteria

- [ ] Click-to-ficha p95 latency ≤ 1.5 s for a parcel (no live GEE call in the path).
- [ ] Soils and risk percentages for one known parcel match a manual QGIS computation
      within ±2 percentage points.
- [ ] Rate limit demonstrably returns HTTP 429 past the configured threshold; area and
      vertex caps reject oversized polygons with 422.
- [ ] One `audit_log` row per `analisis-zona` request, verified in an integration test.
- [ ] `canales_geo` and `mv_canales_por_zona` no longer exist; `suelos_catastro` row
      count > 0 and its ha total matches the source geojson within 1%.
- [ ] Ficha renders "sin cobertura" (not "0%") for an area outside raster extent.

## Open Questions

1. Provenance of `suelos_cu.geojson` — is there an upstream source to rebuild from, or is
   the file the canonical artifact?
2. Refresh strategy for `mv_suelos_por_zona` once populated (on-write trigger, cron, or
   manual admin action)?
3. Rate-limit numbers: requests/minute per IP, max polygon area (ha), max vertices?
4. Does `afectados.spec.ts` currently pass, and does that reverted feature overlap here?
