# Specification: Map Performance, Network Latency & Render Loop Consolidation

## Requirements

### REQ-NET-01: Approved Zones History Isolation
* **Description:** `useApprovedZones.ts` MUST NOT fetch `/api/v2/geo/basins/approved-zones/history` when mounting the interactive map. The history query MUST be isolated into `useApprovedZonesHistory()` or gated with `enabled: false` by default, executing only when an authorized operator opens the zoning version restore modal.
* **Acceptance Criteria:** Loading `/mapa` performs 0 network requests to `/approved-zones/history`.

### REQ-NET-02: Earth Engine Comparison Deferral & Parallelization
* **Description:** `MapaMapLibre.tsx` MUST NOT call `useImageComparisonListener()` or request `/api/v2/public/map/gee/current-comparison` when `/mapa` is loaded in standard 2D view. The request MUST only fire when the operator switches to `viewMode === 'compare'`. In `gee-backend/app/domains/geo/public_map.py`, image projections MUST run concurrently via `asyncio.gather`.
* **Acceptance Criteria:** Booting `/mapa` initiates 0 calls to `current-comparison`. When triggered, backend processing resolves both images concurrently in $\le 4.5$ seconds instead of sequentially in ~9 seconds.

### REQ-NET-03: Deduplication of GEE Layer Requests
* **Description:** `useGEELayers` in `MapaMapLibre.tsx` MUST NOT request `/api/v2/public/map/gee/caminos` if `useCaminosColoreados` is also active.
* **Acceptance Criteria:** Network tab records exactly 1 request to `/api/v2/public/map/gee/caminos` during boot.

### REQ-NET-04: In-Memory Branding Cache
* **Description:** Backend endpoint `GET /api/v2/public/settings/branding` MUST cache its response in memory with a 10-minute TTL or eviction on setting update.
* **Acceptance Criteria:** Subsequent requests to `/api/v2/public/settings/branding` resolve in $< 15$ ms.

### REQ-NET-05: Tabler Icons Bundle Grouping
* **Description:** `vite.config.ts` code splitting MUST group all `@tabler/icons-react` and `src/components/ui/icons` imports into a single named chunk `vendor-icons`.
* **Acceptance Criteria:** Build output produces 0 micro-chunks $< 1$ KB for individual Tabler icons.

### REQ-NET-06: Elimination of Unwanted Chart Chunks on `/mapa`
* **Description:** `/mapa` route MUST set `hideFooter={true}` on `<RootLayout>`, and `AdminDashboard.tsx` MUST dynamically import `DashboardEstadisticas.tsx`. Links to `/admin` in Navigation/UserMenu MUST have `preload={false}`.
* **Acceptance Criteria:** Navigating to `/mapa` downloads 0 bytes of `vendor-mantine-charts` or `vendor-charts`.

### REQ-NET-07: Service Worker Caching for Public Geo Endpoints
* **Description:** `vite.config.ts` Workbox runtime caching MUST include a `StaleWhileRevalidate` rule for `/api/v2/geo/(basins|canales/publico|layers/public)`.
* **Acceptance Criteria:** Second visit to `/mapa` serves public basins and canals directly from cache in 0 ms network time.

### REQ-GEO-01: PMTiles for Waterways
* **Description:** `useWaterways.ts` and `mapLayerEffectHelpers.ts` MUST consume the compact PMTiles files in `/waterways/*.pmtiles` via `pmtilesProtocol` rather than fetching monolithic GeoJSON files.
* **Acceptance Criteria:** Waterway network payload is $\le 200$ KB total (reduced from 947 KB), and 0 waterways GeoJSON files are fetched in the JS main thread.

### REQ-GEO-02: Lazy IDECOR Layer Mounting
* **Description:** `syncIdecorHydroLayers.ts` MUST NOT add sources or layers to MapLibre for IDECOR layers whose visibility is `false`.
* **Acceptance Criteria:** Initial map load initiates 0 requests to `/capas/idecor/cuencas.geojson`, `/capas/idecor/cursos.geojson`, or `/capas/idecor/consorcios.geojson`.

### REQ-GEO-03: Fluid DEM Raster Tile Swap
* **Description:** In `mapRasterOverlayHelpers.ts:198-212`, when `params.demTileUrl` changes, `source.setTiles([params.demTileUrl])` MUST be called instead of destroying and re-adding the layer.
* **Acceptance Criteria:** Switching DEM visualization modes (e.g. MDE-Ar to Curvatura) produces 0 black flashes and maintains existing WebGL textures and layer ordering.

### REQ-GEO-04: Non-Destructive Selection Overlays
* **Description:** `fichaOverlayLayers.ts` and `canalCuencaLayer.ts` MUST NOT call `removeSource` and `removeLayer` on deselection. They MUST retain the existing source and update data with an empty FeatureCollection `setData(EMPTY_FEATURE_COLLECTION)`.
* **Acceptance Criteria:** Selecting and deselecting parcels or canal basins executes 0 shader recompilations or source registrations.

### REQ-UI-01: Decoupled Comparison Slider
* **Description:** Dragging the comparison slider in `useComparisonSlider.ts` MUST NOT update a root React state in `MapaMapLibre.tsx`. It MUST update a CSS variable `--comparison-slider-pos` on the container or set the `clipPath` directly on the overlay DOM element via ref.
* **Acceptance Criteria:** Dragging the slider maintains $\ge 58$ FPS without re-rendering `MapaMapLibreView`.

### REQ-UI-02: Scoped Comparison Stage Update
* **Description:** The `useEffect` updating `comparisonControllerRef.current` in `useMapaMapLibreStage.ts` MUST include an explicit dependency array (`[comparisonSyncInputs]`) instead of running on every render frame.
* **Acceptance Criteria:** Non-comparison state changes do not execute `syncComparisonVectorLayers`.

### REQ-UI-03: Throttled Profile Cursor with BBox Filter
* **Description:** `useMapProfileCursor.ts` MUST throttle `mousemove` events to $\le 20$ Hz via `requestAnimationFrame` and skip points outside an immediate bounding box filter. The computed distance MUST NOT be stored in `MapaMapLibreView` root state.
* **Acceptance Criteria:** Hovering over longitudinal traces produces 0 frame drops in MapLibre.

### REQ-UI-04: Memoized MapUiPanels
* **Description:** `MapaMapLibreView.tsx` MUST pass stable props to `MapUiPanels` to maintain `React.memo` effectiveness.
* **Acceptance Criteria:** Clicking tools or toggling non-panel layers causes 0 re-renders of `MapUiPanels`.
