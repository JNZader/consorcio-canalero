# Tasks: Map Performance, Network Latency & Render Loop Consolidation

## Wave 1: Network, Bundling & API Boot Optimization

- [x] **T1.1 (Frontend)**: Isolate `approved-zones/history` in `useApprovedZones.ts` into a separate hook `useApprovedZonesHistory()` with `enabled: false` by default, so `/mapa` does not fetch historical zoning on mount.
- [x] **T1.2 (Frontend & Backend)**: Defer `current-comparison` in `MapaMapLibre.tsx` so it only fetches when `viewMode === 'compare'`; in `gee-backend/app/domains/geo/public_map.py:380`, run image projections concurrently with `asyncio.gather`.
- [x] **T1.3 (Frontend)**: Remove `'caminos'` from `GEE_LAYER_NAMES` in `useGEELayers` in `MapaMapLibre.tsx` to eliminate the duplicate request (since `useCaminosColoreados` already manages this layer).
- [x] **T1.4 (Backend)**: Add in-memory TTL caching (10 min) to `/api/v2/public/settings/branding` in `gee-backend/app/domains/settings/service.py`.
- [x] **T1.5 (Frontend)**: Add `vendor-icons` grouping rule in `vite.config.ts` (`rolldownOptions.output.codeSplitting.groups`) to consolidate the 17 micro-chunks of `@tabler/icons-react`.
- [x] **T1.6 (Frontend)**: Hide footer on `/mapa` (`hideFooter={true}` in `routeTree.gen.tsx`), add `preload={false}` to admin links, and dynamically import `DashboardEstadisticas` in `AdminDashboard.tsx`.
- [x] **T1.7 (Frontend)**: Add `StaleWhileRevalidate` rule in `vite.config.ts` Workbox runtime caching for `/api/v2/geo/(basins|canales/publico|layers/public)`.

## Wave 2: Geospatial Pipeline & WebGL Layer Lifecycle

- [x] **T2.1 (Frontend)**: Decouple waterways GeoJSON from React memory boot, enabling only on KMZ export (`exportIntent`).
- [x] **T2.2 (Frontend)**: Update `syncIdecorHydroLayers.ts` to only add sources and layers to MapLibre when `visible[layer.id]` is `true` (lazy-mount).
- [x] **T2.3 (Frontend)**: Fix inverted logic bug in `mapRasterOverlayHelpers.ts` (`syncDemRasterLayer`) so `source.setTiles()` is called on URL changes, avoiding texture destruction.
- [x] **T2.4 (Frontend)**: Verify 3D terrain hillshade source exclusive cloning without WebGL texture duplication.
- [x] **T2.5 (Frontend)**: Filter `buildClickableLayers` in `useMapInteractionEffects.ts` to only query visible layers and use refs for mutable state arrays.

## Wave 3: React Lifecycle & 60 FPS Event Decoupling

- [x] **T3.1 (Frontend)**: Decouple `sliderPosition` from React state in `useComparisonSlider.ts` and `MapaMapLibre.tsx` by using direct DOM `clipPath` styling via a ref or CSS variable `--slider-pos`.
- [x] **T3.2 (Frontend)**: Add dependency array to `useEffect` in `useMapaMapLibreStage.ts:674` so `comparisonController.update()` is not called on every render.
- [x] **T3.3 (Frontend)**: Throttle `useMapProfileCursor.ts` with `requestAnimationFrame` and BBox pre-filtering, eliminating heavy point-by-point projections.
- [x] **T3.4 (Frontend)**: Keep Turf measurement calculations debounced and prevent event loop re-entrancy in `useMeasurement.ts`.
- [x] **T3.5 (Frontend)**: Add `willChange: left, top` and optimize DOM styles in `MeasurementLabels.tsx`.
- [x] **T3.6 (Frontend)**: Ensure stable references to eliminate unnecessary cascading updates to `MapUiPanels`.
- [x] **T3.7 (Frontend)**: Refactor `TerrainViewer3D.tsx` to subscribe to primitive Zustand properties (`opacityByLayer`, `orderByLayer`, etc.) instead of the whole `map3d` slice.

## Wave 4: Verification & Performance Regression Gates

- [x] **T4.1 (Verification)**: Run `npm run typecheck` and `npm run lint`.
- [x] **T4.2 (Verification)**: Run full Vitest suite in `consorcio-web` (426 test suites passed).
- [x] **T4.3 (Verification)**: Run backend checks (`ruff check`).
- [ ] **T4.4 (Verification)**: Local build verification (requires explicit user authorization).
