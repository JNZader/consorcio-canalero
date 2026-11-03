# Proposal: Map Performance, Network Latency & Render Loop Consolidation (`consorcio-web` & `gee-backend`)

## Intent

Remediate critical performance, network payload, and frame-rate bottlenecks in `consorcio-web` and `gee-backend` identified during the 2026-11-03 exhaustive audit. The interactive map currently triggers 14 concurrent API calls on startup (including an 8.7-second blocking Earth Engine image projection and a 1.5-second unused historical zoning query), downloads 1.7 MB of unneeded static GeoJSON files that already have compact PMTiles or vector equivalents, fractures icons into 17 micro-chunks, and drops render loops from 60 FPS to 15–20 FPS due to un-throttled high-frequency React state cascades and destructive WebGL texture rebuilds.

## Scope

### In Scope (3 Execution Waves)

| Wave | Slug | Deliverable Summary |
|---|---|---|
| **Wave 1** | `Wave 1: Network, Bundling & API Boot Optimization` | Remove unneeded `approved-zones/history` query from `useApprovedZones.ts`; defer `current-comparison` to active compare mode and parallelize backend projections via `asyncio.gather`; deduplicate `caminos` requests; add in-memory caching to `/api/v2/public/settings/branding`; consolidate Tabler icons into `vendor-icons` in `vite.config.ts`; prevent unwanted `vendor-mantine-charts` download by hiding footer on `/mapa` and lazy-loading `DashboardEstadisticas`; add `StaleWhileRevalidate` service worker caching for public `/api/v2/geo/` endpoints. |
| **Wave 2** | `Wave 2: Geospatial Pipeline & WebGL Render Loop` | Connect existing `public/waterways/*.pmtiles` via `pmtilesProtocol` and eliminate duplicate GeoJSON fetch in `useWaterways.ts`; lazy-mount IDECOR layers in `syncIdecorHydroLayers.ts` only when toggled on; invert bug in `syncDemRasterLayer` to call `setTiles` on URL change and eliminate black screen texture destruction; replace destructive `removeSource` with `setData(EMPTY_FC)` in ephemeral selection overlays (`fichaOverlayLayers.ts`, `canalCuencaLayer.ts`); optimize `queryRenderedFeatures` click testing to avoid querying heavy polygon fill layers. |
| **Wave 3** | `Wave 3: React Lifecycle & 60 FPS Event Decoupling` | Decouple comparison slider position from root React state (use CSS variable `--slider-pos` / direct DOM ref); add dependency array to `useMapaMapLibreStage.ts` comparison update effect to prevent 21 syncs per mouse move; throttle `useMapProfileCursor` with `requestAnimationFrame` and isolate distance updates from `MapaMapLibreView`; throttle `useMeasurement.ts` Turf calculations during drawing; stabilize inline JSX props in `MapaMapLibreView` to restore `React.memo(MapUiPanels)`; replace monolithic Zustand subscriptions in `TerrainViewer3D.tsx` with primitive selectors and debounce exaggeration slider state. |

### Out of Scope / NON-goals

- Altering database schemas with Alembic migrations.
- Rewriting MapLibre GL core shaders.
- Removing legitimate user-visible features or map layers.
- Changing cartographic symbology rules.

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| PMTiles waterways break line styling or clicks | Low | Keep same layer IDs and style definitions in `mapLayerEffectHelpers.ts` targeting source layer `'waterways'`. |
| Comparison slider CSS variable breaks mobile touch | Low | Implement fallback style update on DOM element reference during pointermove events. |
| Service Worker caching serves stale GeoJSON | Medium | Use `StaleWhileRevalidate` with 24-hour expiration so user gets instant offline/cached render while revalidating fresh data in background. |
