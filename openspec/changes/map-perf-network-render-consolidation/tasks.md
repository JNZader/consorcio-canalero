# Tasks: Map Performance, Network Latency & Render Loop Consolidation

## Wave 1: Network, Bundling & API Boot Optimization

- [ ] **T1.1 (Frontend)**: Isolate `approved-zones/history` in `useApprovedZones.ts` into a separate hook `useApprovedZonesHistory()` with `enabled: false` by default, so `/mapa` does not fetch historical zoning on mount.
- [ ] **T1.2 (Frontend & Backend)**: Defer `current-comparison` in `MapaMapLibre.tsx` so it only fetches when `viewMode === 'compare'`; in `gee-backend/app/domains/geo/public_map.py:380`, run image projections concurrently with `asyncio.gather`.
- [ ] **T1.3 (Frontend)**: Remove `'caminos'` from `GEE_LAYER_NAMES` in `useGEELayers` in `MapaMapLibre.tsx` to eliminate the duplicate request (since `useCaminosColoreados` already manages this layer).
- [ ] **T1.4 (Backend)**: Add in-memory TTL caching (10 min) to `/api/v2/public/settings/branding` in `gee-backend/app/domains/settings/service.py`.
- [ ] **T1.5 (Frontend)**: Add `vendor-icons` grouping rule in `vite.config.ts` (`rolldownOptions.output.codeSplitting.groups`) to consolidate the 17 micro-chunks of `@tabler/icons-react`.
- [ ] **T1.6 (Frontend)**: Hide footer on `/mapa` (`hideFooter={true}` in `routeTree.gen.tsx`), add `preload={false}` to admin links, and dynamically import `DashboardEstadisticas` in `AdminDashboard.tsx`.
- [ ] **T1.7 (Frontend)**: Add `StaleWhileRevalidate` rule in `vite.config.ts` Workbox runtime caching for `/api/v2/geo/(basins|canales/publico|layers/public)`.

## Wave 2: Geospatial Pipeline & WebGL Layer Lifecycle

- [ ] **T2.1 (Frontend)**: Wire `public/waterways/*.pmtiles` in `useWaterways.ts` and `mapLayerEffectHelpers.ts` using `pmtilesProtocol` instead of raw GeoJSONs.
- [ ] **T2.2 (Frontend)**: Update `syncIdecorHydroLayers.ts` to only add sources and layers to MapLibre when `visible[layer.id]` is `true`.
- [ ] **T2.3 (Frontend)**: Fix inverted logic bug in `mapRasterOverlayHelpers.ts` (`syncDemRasterLayer`) so `source.setTiles()` is called on URL changes, avoiding texture destruction.
- [ ] **T2.4 (Frontend)**: Replace destructive `removeSource` with `setData(EMPTY_FEATURE_COLLECTION)` in `fichaOverlayLayers.ts` and `canalCuencaLayer.ts`.
- [ ] **T2.5 (Frontend)**: Filter `buildClickableLayers` in `useMapInteractionEffects.ts` to only query visible layers and skip heavy polygon fills (`soil-fill`).

## Wave 3: React Lifecycle & 60 FPS Event Decoupling

- [ ] **T3.1 (Frontend)**: Decouple `sliderPosition` from React state in `useComparisonSlider.ts` and `MapaMapLibre.tsx` by using direct DOM `clipPath` styling via a ref or CSS variable `--slider-pos`.
- [ ] **T3.2 (Frontend)**: Add dependency array `[comparisonSyncInputs]` to `useEffect` in `useMapaMapLibreStage.ts:674`.
- [ ] **T3.3 (Frontend)**: Throttle `useMapProfileCursor.ts` with `requestAnimationFrame` and BBox pre-filtering, moving `mapCursorDistance` to an isolated context.
- [ ] **T3.4 (Frontend)**: Throttle `useMeasurement.ts` `draw.render` Turf updates with `requestAnimationFrame`.
- [ ] **T3.5 (Frontend)**: Update `MeasurementLabels.tsx` to position label elements via `transform: translate3d()` refs directly on map `move` events.
- [ ] **T3.6 (Frontend)**: Memoize inline control elements and callbacks in `MapaMapLibreView.tsx` to restore `React.memo(MapUiPanels)` functionality.
- [ ] **T3.7 (Frontend)**: Refactor `TerrainViewer3D.tsx` to subscribe to primitive Zustand properties and debounce the exaggeration slider state.

## Wave 4: Verification & Performance Regression Gates

- [ ] **T4.1 (Verification)**: Run `npm run typecheck` and `npm run lint`.
- [ ] **T4.2 (Verification)**: Run full Vitest suite in `consorcio-web`.
- [ ] **T4.3 (Verification)**: Run backend pytest suite in `gee-backend`.
- [ ] **T4.4 (Verification)**: Verify build output (`npm run build` once authorized, or audit chunks via tests).
