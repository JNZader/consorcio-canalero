# map-ux-perf-01

First implementable slice of audit v5 **PERF-01** (`/mapa` mobile Lighthouse 49). Onto `origin/main` (`e89b11c3`).

Audit already shipped elsewhere: PERF-02 lazy ficha charts, PERF-03 glyphs, PERF-04 CARTO, soil/catastro fetch gated until on.

## In

- [x] InfoPanel: `lazy()` ElevationProfileChart so recharts is not on `/mapa` first paint
- [x] Measurement: do not statically import `@mapbox/mapbox-gl-draw` until the user starts measuring
- [x] `index.html`: dns-prefetch CARTO (`basemaps.cartocdn.com`), drop `tile.openstreetmap.org`
- [x] Source-guard tests (same pattern as PERF-02)

## Out

- Full Lighthouse rewrite / splitting `MapaMapLibre`
- CODE-02 reconciler
- Soil/catastro GeoJSON → pmtiles (follow-up: tiles when the layer is ON, not first paint)
- Favicon.ico swap (PNG/maskable icons in `public/icons` are larger than the 77k ico)
- Claiming a new Lighthouse score without a measured run
- New map libraries
