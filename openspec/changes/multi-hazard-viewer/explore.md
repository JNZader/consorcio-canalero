# Exploration: Multi-Hazard Viewer

## Current State

The Consorcio Canalero platform already has most of the pieces a **Multi-Hazard Viewer** would need:

- **2D map shell**: `MapaPage` / `MapaMapLibre` render a MapLibre GL canvas with a responsive `MapWorkspace` sidebar/Drawer, a `LayerControlsPanel` accordion, a `LeyendaPanel`, and a `ViewModePanel`.
- **Layer state**: `mapLayerSyncStore` (Zustand + persist) owns visibility, per-layer opacity multipliers, and render order for the `map2d` and `map3d` views. New toggles should be registered in `layerRenderRegistry.ts` and `map2dDerived.ts`.
- **Risk zones**: the DEM pipeline produces `flood_risk` and `drainage_need` rasters served through the public tile proxy (`/api/v2/geo/layers/{id}/tiles/{z}/{x}/{y}.png`). The ficha overlay endpoint (`/api/v2/geo/ficha`) already returns clipped vector overlays for `suelos`, `flood_risk`, and `drainage_need`. `LAYER_LEGEND_CONFIG` (frontend) and `RANGE_CONFIGS` (backend) define class breaks/colors.
- **Soils**: `useSoilMap` fetches `/data/suelos_cu.geojson` and renders polygons by IDECOR capability class (`I–VIII`).
- **Channels**: `useCanales` loads `/capas/canales/{relevados,propuestas}.geojson` plus `index.json`; the UI has master toggles, per-canal sub-toggles, and the "Etapas propuestas" filter.
- **CHIRPS precipitation**: `generate_chirps_normals.py` registers 13 `precip_normal` GeoTIFFs in `geo_layers` (monthly + annual normals). They are **not** exposed in `useGeoLayers`/`PUBLIC_TILE_CAPABLE_TYPES`/`TILE_CAPABLE_TYPES` today, so they are invisible on the map. Daily/event rainfall lives in `RainfallIntervalValue` rows and is served as time-series analysis snapshots (`/api/v2/geo/rainfall/analyses`), not as map tiles.
- **Basin filtering**: `useBasins` queries `/api/v2/geo/basins` with optional `cuenca` and `bbox` filters.

In short: the **risk/soil/channel** layers are production-ready, while **CHIRPS precipitation as a map overlay** is the largest remaining gap.

## Affected Areas

| Path | Why it is affected |
|------|--------------------|
| `consorcio-web/src/components/MapaPage.tsx` | Page shell; may host a new hazard mode toggle or route entry. |
| `consorcio-web/src/components/MapaMapLibre.tsx` | Main 2D map wiring; new mode/filter controls and layer effects land here. |
| `consorcio-web/src/components/map2d/LayerControlsPanel.tsx` | Accordion for toggles; likely needs a new hazard section or filter bar integration. |
| `consorcio-web/src/components/map2d/LeyendaPanel.tsx` | Legend must include hazard-specific items (risk classes, precip ranges, channel etapas). |
| `consorcio-web/src/components/map2d/layerRenderRegistry.ts` | New/reused UI layer ids need registration for opacity/order controls. |
| `consorcio-web/src/components/map2d/map2dDerived.ts` | `buildVectorLayerItems` / `buildFamilyActiveCounts` must account for new hazard layers. |
| `consorcio-web/src/stores/mapLayerSyncStore.ts` | Visibility/opacity defaults and possibly a dedicated hazard view slice. |
| `consorcio-web/src/hooks/useGeoLayers.ts` | Catalog currently filters out `precip_normal`; must add it to tile-capable types. |
| `gee-backend/app/domains/geo/router_core.py` | `PUBLIC_TILE_CAPABLE_TYPES` must include `precip_normal` for public map exposure. |
| `gee-backend/app/domains/geo/tile_service_support.py` / `tile_service.py` | Need colormap, rescale, and legend config for precipitation rasters. |
| `gee-backend/app/domains/geo/models.py` | `TipoGeoLayer.PRECIP_NORMAL` already exists. |
| `consorcio-web/src/config/rasterLegend.ts` | Need precip legend/colors synced with backend tile service. |
| `consorcio-web/src/hooks/useRainfallAnalysis.ts` / `lib/api/rainfall.ts` | If daily/event precip is shown as a chart/sidecar rather than raster. |
| `gee-backend/app/domains/geo/rainfall/router.py` | May need endpoints for precipitation event windows or current-month overlays. |

## Approaches

### 1. Hazard mode inside the existing 2D map

Add a "Multi-riesgo" mode to `MapaPage`/`MapaMapLibre`. When active, the map pre-selects the hazard stack (`flood_risk`, `drainage_need`, `soil`, `canales_relevados`, `basins`, `precip_normal`) and renders a compact hazard filter bar (basin selector, date/range picker, risk-threshold selector). The existing `LayerControlsPanel` remains available so power users can refine the stack.

- **Pros**: Reuses all existing map infrastructure (`MapWorkspace`, layer store, tile proxy, legends, ordering, health banners); single canonical map page; easy to deep-link via URL params; no navigation/menu changes.
- **Cons**: `MapaMapLibre` is already ~1,200 lines; adding another mode increases its cognitive load; hazard filters are global and can interact unexpectedly with existing layer toggles; mobile layout is already tight.
- **Effort**: Medium.

### 2. Dedicated `/visor-multi-riesgo` page

Create a new route/page with its own simplified map wrapper focused exclusively on hazards. It can import the same sync helpers (`mapLayerEffectHelpers.ts`, `fichaOverlayLayers.ts`, etc.) but owns its own state, defaults, and a side-by-side summary card.

- **Pros**: Clear product boundary; own persistence slice avoids polluting general map settings; easier to tailor the mobile layout; lower regression risk to the main interactive map.
- **Cons**: Duplicates some map wiring and tile-loading hooks; needs a new navigation entry; can drift out of sync with main-map improvements.
- **Effort**: Medium-High.

### 3. New "Multi-riesgo" accordion section in the layer panel

Add a new accordion family to `LayerControlsPanel` that bundles the hazard toggles and exposes basin/date/threshold controls inline. No new page or mode.

- **Pros**: Smallest UI change; fits existing search/accordion; quick to validate.
- **Cons**: Limited space for date/range controls; does not solve mobile overflow; mixes operational layer controls with analytic filters; no dedicated summary card or legend real estate.
- **Effort**: Low-Medium.

## Recommendation

**Approach 1** is the best fit for the stated goal of a *unified map* that overlays the four layer families. The platform's existing map, store, and tile pipeline already support the core use case.

However, this should only be done after a **preliminary refactor** of `MapaMapLibre` into smaller coordinators (data wiring, map effects, UI shell) — the component is at its complexity ceiling. If the target audience is public/executive rather than operators, or if the UX needs a clearly distinct layout, **Approach 2** is safer.

A pragmatic path is:
1. Add a feature-flagged hazard mode to the existing map.
2. Wire `precip_normal` into the public tile catalog and legend.
3. Build the basin/date/threshold filter bar.
4. Defer dynamic daily CHIRPS raster to a follow-up change.

## Risks

- **`precip_normal` is not tile-capable today**: exposing it requires backend changes to `PUBLIC_TILE_CAPABLE_TYPES`/`TILE_CAPABLE_TYPES`, colormap/rescale definitions, and the frontend legend config. The existing normals rasters are also coarse (5 km), which may look underwhelming when overlaid on high-resolution soil/channel data.
- **Daily/event CHIRPS is time-series, not raster**: showing precipitation for an arbitrary date requires either on-the-fly GEE tile generation or pre-generated event rasters. This is the largest unresolved technical question.
- **Risk threshold semantics are class-based**: `flood_risk`/`drainage_need` use discrete classes (Bajo/Medio/Alto/Crítico). A single "risk threshold" slider must be mapped consistently to classes across datasets.
- **Visual clutter**: stacking soils, risk, channels, and precipitation semi-transparent fills can make the map unreadable. A clear default stack and opacity conventions are required.
- **Mobile real estate**: adding a filter bar to the existing panel/Drawer will likely overflow on small screens.
- **`MapaMapLibre` complexity**: adding hazard mode without decomposition risks breaking existing layer effects, ordering, or the ficha overlay interactions.

## Open Product Questions

Answering these is required before moving to `sdd-propose`:

1. **Target users**: operators planning works, or public/executive dashboard consumers?
2. **Default active layers** on entry: e.g., `flood_risk` + `canales_relevados` + `basins` + `precip_normal`?
3. **Date granularity** for CHIRPS: monthly normals only, daily/event rainfall, rolling windows, or a combination?
4. **Basin selector behavior**: single selection that zooms and scopes precipitation/risk, multi-select filter, or just a highlight?
5. **Risk threshold scope**: apply to `flood_risk` only, or also `drainage_need`/`terrain_class`? Class toggle vs. numeric threshold?
6. **CHIRPS representation**: raster overlay on the map, or a rainfall-analysis card sidecar? If raster, what temporal aggregations (month, year, custom window)?
7. **Mobile layout**: filters inside the existing Drawer, a bottom sheet, or a dedicated mobile hazard panel?
8. **Interaction with ficha**: should the hazard view coexist with parcel click → ficha, or replace it?
9. **Persistence**: should hazard-mode settings be saved separately from the general map state?

## Ready for Proposal

**Yes, with caveats.** The technical groundwork is in place, but the product definition around precipitation granularity, risk thresholds, and mobile layout needs to be settled first. The recommendation is to proceed with a feature-flagged **Approach 1** and treat dynamic daily CHIRPS raster as a separate, later change.
