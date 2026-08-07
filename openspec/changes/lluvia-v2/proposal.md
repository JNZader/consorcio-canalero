# Proposal: Rainfall v2 Technical Analysis

## Intent

Technical staff currently see only an on-demand CHIRPS v2 1991–2020 monthly normal. They need trustworthy calendar-year analysis for zones and basins without presenting regional estimates as parcel measurements or hiding uncertainty, gaps, and source substitution.

## Scope

### In Scope
- Preserve the compact public normal; add authenticated technical detail within the ficha.
- Contract scopes: `zone | basin | parcel | geometry`. V1 executes stable zones/basins. Parcels resolve and switch between their zone/basin and remain labelled regional estimates. Direct parcel/free-geometry computation is deferred.
- Compare a calendar year with the fixed 1991–2020 normal: same-date current-year comparison, totals, percentile, 7/30/90-day antecedent rainfall, report summary, and CSV.
- Expose provenance, nominal resolution, freshness, `available_through`, coverage, completeness, provisional/final state, revision, source, fallback, discrepancies, and quality.
- Validate CHIRPS v3 and metric-specific source ladders through an early known-event spike across radar, IMERG, PERSIANN, SQPE/CHIRPS, and available gauges. Never silently average.
- Show partial data, but suppress completeness-sensitive metrics when quality rules fail; event peak/duration requires every expected interval.

### Out of Scope
- Return periods, event catalog/polygons, Sentinel-1, intervention comparisons, SPI/ENSO, community gauges, soil moisture, groundwater, agricultural campaigns, arbitrary-geometry execution, and generic observation-schema migration.

## Capabilities

### New Capabilities
- `rainfall-analysis`: Technical comparison, provenance, quality states, fallbacks, and export.

### Modified Capabilities
- None; no published main specs exist.

## Approach

Validate scientific quality and access before source selection. Produce regional zonal results with metric-specific priorities and auditable fallbacks. Preserve `observed_station`, `estimated_radar`, and `estimated_satellite`; nominal resolution never implies local accuracy.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `gee-backend/app/domains/geo/` | Modified/New | Analysis, provenance, quality, scope |
| `consorcio-web/src/components/map2d/` | Modified | Detail, comparison, states, export |
| Geo operations | Modified | Sources, monitoring, revision, fallback audit |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| No stable API/archive/licence | High | Evidence gates; validated fallback; never scrape images |
| Sparse/biased observations | High | Event validation; estimation labels |
| Partial/provisional data misread | Medium | Visible state, coverage, suppression, revisions |

## Rollback Plan

Disable technical detail and new analysis paths; retain the compact normal and audit records.

## Dependencies

- Confirmed access, terms, coverage, archives, time windows, and quality.
- Representative corridor events and accessible gauges.

## Success Criteria

- [ ] Staff obtain every scoped output for a stable zone/basin, or an explicit unavailable/suppressed state.
- [ ] Every displayed/exported metric identifies source class, interval, status, resolution, coverage, quality, and fallback use.
- [ ] Parcel flows never claim parcel measurement or accuracy from nominal resolution.
- [ ] Preferred-source failure uses an audited validated fallback without blocking independent valid outputs.
