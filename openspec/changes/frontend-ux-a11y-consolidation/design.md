# Design: Frontend UX, Functional Consolidation & WCAG 2.1 AA Hardening (`consorcio-web`)

## Technical Approach

Remediate the 29 audit findings across 4 orthogonal waves without backend DB migrations or new GEE algorithms. Every architectural decision below is anchored to the exact `file:line` locations verified in the 2026-11-03 audit (`HEAD` at `a8979b82`).

---

## Architecture & UI Layout Decisions

### 1. Viewport Collision Resolution: Top-Left & Bottom Chrome

#### 1.1. Top-Left Stack (`MapSearchBox`, `2D/3D` Toggle, `.workspaceBurger`, `HazardControls`)

**Current Defect (Audit §2.2):**
Four independent `position: absolute` elements compete for the top-left corner of `/mapa`:
- `.workspaceBurger` (`top: 12px, left: 12px, z-index: 1250` on mobile)
- `2D/3D` view toggle (`top: 8px, left: 72px, z-index: 25`)
- `MapSearchBox.tsx:23-186` + `MapShareLink.tsx:38-56` (`top: 12px, left: 12px, z-index: 12`)
- `HazardControls` (`top: 96px, left: 16px, z-index: 3`)

**Design Resolution:**
```
┌─────────────────────────────────────────────────────────────────────────┐
│ [☰ Burger (mobile)] [MapSearchBox (combobox) + Share/QR] [2D | 3D Pill] │ ← Top-Left Flex Bar (top: 12px, left: 12px, gap: 8px, z-index: 25)
├─────────────────────────────────────────────────────────────────────────┤
│ [HazardControls (positioned dynamically below Top-Left Bar)]            │
└─────────────────────────────────────────────────────────────────────────┘
```
1. **Single Top-Left Control Row**: Replace the colliding independent coordinates with a single flex container `.mapTopLeftBar` anchored at `top: 12px; left: 12px; z-index: 25; display: flex; align-items: flex-start; gap: 8px; pointer-events: none` (with `pointer-events: auto` on children).
2. **Mobile Burger Offset**: When `.workspaceBurger` is visible (`@media (max-width: 768px)`), `.mapTopLeftBar` shifts to `left: 60px` so the burger button (`40×40px` at `left: 12px`) never overlaps `MapSearchBox`.
3. **2D/3D Toggle Placement**: Move the `2D/3D` segmented control into `.mapTopLeftBar` immediately to the right of `MapSearchBox` (or docked in the top-right action cluster alongside `ViewModePanel`), eliminating the `top: 8px, left: 72px` collision over the search input border.
4. **HazardControls Flow**: Anchor `HazardControls` below `.mapTopLeftBar` with `z-index: 11` while `MapSearchBox` dropdown (`role="listbox"`) renders at `z-index: 30` so expanding search suggestions cleanly overlays `HazardControls` without permanent resting overlap.
5. **Single Permalink Action**: Remove the duplicate plain-text `"Copiar enlace"` button inside `MapActionsPanel.tsx:96-109` and keep `MapShareLink.tsx:38-56` (which includes both URL copy and QR generation) as the single canonical permalink control.

#### 1.2. Bottom Viewport Dock (`ElevationProfileDock`, `FichaTerritorialPanel`, `RoadFlowPanel`, `MapCursorReadout`)

**Current Defect (Audit §1.2, §2.2, `MAP-08`):**
Five surfaces collide along the bottom edge:
- `TimeCompareBar.tsx:1-217` (`bottom: 28px, left: 12px, z-index: 12`) — **DELETED in T1.1**
- `MapCursorReadout` (`bottom: 10px, left: 90px, z-index: 16`)
- `RoadFlowPanel` (`bottom: 16px, left: 16px, z-index: 1000`)
- `FichaTerritorialPanel` (`bottom: 16px, right: 56px, z-index: 1000`)
- `ElevationProfileDock` (`bottom: 0, left: 0, right: 0, height: 260px, z-index: 18`)

When `ElevationProfileDock` opens, `FichaTerritorialPanel` (`z-index: 1000`) covers the top-right close/minimize buttons of `ElevationProfileDock`, and `RoadFlowPanel` (`z-index: 1000`) covers the left chart axis.

**Design Resolution:**
1. **CSS Custom Property `--map-bottom-dock-offset`**: Set `--map-bottom-dock-offset: 268px` (or `48px` when minimized, `0px` when closed) on the map viewport root container (`MapaMapLibreView.tsx` and `TerrainViewer3D.tsx:938-1043`).
2. **Dynamic Bottom Offset for Floating Cards**: `FichaTerritorialPanel`, `RoadFlowPanel`, and `MapCursorReadout` bind `bottom: calc(16px + var(--map-bottom-dock-offset, 0px))` (and `max-height: calc(100vh - var(--map-bottom-dock-offset, 0px) - 96px)`), shifting cleanly above `ElevationProfileDock` whenever the dock is open.
3. **Single `<ElevationProfileChart>` Instance (`InfoPanel.tsx:546-568`)**: When `ElevationProfileDock` is open for a canal (`dockOpen === true`), `InfoPanel.tsx` collapses its inline `<ElevationProfileChart>` and renders a compact status pill (`"Mostrando perfil en el panel inferior"`), ensuring two `<ElevationProfileChart>` SVG instances never mount simultaneously.
4. **3D Dock Containment & `onOpenCanalProfile` (`MAP-08`)**:
   - In `TerrainViewer3DChrome.tsx:303-312`, pass `onOpenCanalProfile` down to `<InfoPanel>` so users in 3D can open the longitudinal profile directly from a clicked canal feature.
   - In `TerrainViewer3D.tsx:938-1043`, move `<ElevationProfileDock>` inside the relative `<Box pos="relative" ...>` viewport container so it stays bounded to the 3D canvas area.
5. **Hide Unbacked Profile Switches (`MAP-06`, `MAP-07`)**:
   - In `ElevationProfileChart.tsx:379-389` and `L454-L456`, render the `"Comparar relevamiento"` `<Switch>` only when `pairedSurvey != null && pairedSurvey.points.length > 0`.
   - In `ElevationProfileChart.tsx:180` (`useDemProfile.ts:16-21`), render the `"Terreno vs solera"` `<Switch>` only when `solera.ok === true`.

---

### 2. Unification of 3D Sidebar Controls (`MAP-04`, `MAP-05`, Dead Code)

**Current Defect (Audit §2.1, §2.2, §2.3):**
- `TerrainViewer3DChrome.tsx:465-505` mounts `<TerrainLayerTogglesPanel showVectorSections={false} />` and immediately below it mounts `<LayerControlsPanel variant="3d" />`. Both render DEM layer selection and raster opacity sliders.
- `TerrainViewer3DChrome.tsx:479-504` does not pass `layerFineControl` to `<LayerControlsPanel variant="3d" />`, so `LayerControlsPanel.tsx:84-93` falls back to `NOOP_FINE_CONTROL` — making every eye button (`active-layer-toggle-*`) and opacity slider (`active-layer-opacity-*`) under `"En el mapa"` a silent no-op.
- `LayerControlsPanel.tsx:456` (`MapPresetChips`) hardcodes `applyPreset('map2d', preset)` even when `variant === '3d'`.
- `TerrainLayerTogglesPanel.tsx:231-396` contains 165 lines of dead vector section JSX because `showVectorSections` is permanently passed as `false`.

**Design Resolution:**
1. **Wire Real `layerFineControl` in 3D (`TerrainViewer3DChrome.tsx:479-504`)**: Construct a memoized `layerFineControl: LayerFineControlContract` in `TerrainViewer3DChrome` backed by the 3D viewer's layer visibility state and per-layer opacity map (`useMapLayerSyncStore((s) => s.map3d)` + 3D terrain overlay opacity state), and pass it to `<LayerControlsPanel variant="3d" layerFineControl={layerFineControl} />`.
2. **Route Preset Chips by Variant (`LayerControlsPanel.tsx:456`)**: Update `MapPresetChips` to inspect `variant`:
   ```ts
   const targetStore = variant === '3d' ? 'map3d' : 'map2d';
   applyPreset(targetStore, preset.id);
   ```
3. **Eliminate Duplicate 3D Raster Controls & Dead Vector Code**:
   - Remove the duplicate DEM layer selector and raster opacity slider from `LayerControlsPanel` when `variant === '3d'` (or consolidate 3D-specific terrain exaggeration/lighting controls in `TerrainLayerTogglesPanel` while keeping DEM/vector layer selection in `LayerControlsPanel`).
   - Delete lines `231-396` (`showVectorSections` branch) from `TerrainLayerTogglesPanel.tsx`.
   - Delete dead files `PropuestasEtapasFilter.tsx:1-58` and `pointAlongLine.ts:1-60`, remove the 11 unused `InfoPanel` props and dead `showEmbeddedMapControls`/`showEmbeddedRasterLegend` blocks in `MapUiPanels.tsx:142-155, 525-605, 619-627`, and remove the dead non-embedded branch in `InfoPanel.tsx:642-667`.

---

### 3. `MeasurementToolbar.tsx` Icons/Tooltips, Polygon `undo()`, and Personal Measurements (`MAP-01`, `MAP-02`, `MAP-03`)

**Current Defect (Audit §2.1):**
- `MeasurementToolbar.tsx:224-238` renders `"Deshacer"` and `"Guardar"` with only `<span className={styles.mapCtrlButtonLabel}>`. Because `map.module.css:972-978` sets `.mapCtrlButtonLabel { display: none }` under `@media (pointer: fine)`, desktop users see two blank 29×29px white squares with no icon and no tooltip.
- `useMeasurement.ts:467-481` (`undo()`) checks only `LineString` features, ignoring `Polygon` features during `mode === 'measuring-area'`.
- `personalMeasurements.ts:27-44` and `usePersonalMeasurementsLayer.ts:10-34` persist up to 40 geometries in `localStorage['cc-personal-measurements']` with no UI button to hide or clear them, and polygons render only on a `type: 'line'` layer without interior fill.

**Design Resolution:**
1. **Desktop Icons & Tooltips (`MeasurementToolbar.tsx:224-238`)**:
   - Wrap `"Deshacer"`, `"Guardar"`, `"Ocultar/Mostrar guardadas"`, and `"Limpiar guardadas"` in Mantine `<Tooltip label="..." position="bottom" withArrow>`.
   - Add `<IconArrowBackUp size={16} aria-hidden="true" />` to `"Deshacer"` and `<IconDeviceFloppy size={16} aria-hidden="true" />` to `"Guardar"` alongside `<span className={styles.mapCtrlButtonLabel}>`.
2. **Polygon `undo()` Support (`useMeasurement.ts:467-481`)**:
   - In `undo()`, handle both `LineString` (`measuring-distance`) and `Polygon` (`measuring-area`):
     - For `Polygon`, inspect `ring = feature.geometry.coordinates[0]`. Recall GeoJSON polygons close the ring (`ring[0]` repeated at `ring[ring.length - 1]`). Removing the last placed vertex removes `ring[ring.length - 2]`. If fewer than 2 user vertices remain, clear the draft feature cleanly.
3. **Personal Measurements Visibility, Clear & Polygon Fill (`personalMeasurements.ts:27-44`, `usePersonalMeasurementsLayer.ts:10-34`)**:
   - Add a `personalMeasurementsfill` MapLibre layer (`type: 'fill'`, `filter: ['==', ['geometry-type'], 'Polygon']`, `paint: { 'fill-color': '#228be6', 'fill-opacity': 0.18 }`) beneath the existing line/label layers in `usePersonalMeasurementsLayer.ts`.
   - Expose `personalVisible: boolean`, `togglePersonalVisible()`, and `clearAllPersonalMeasurements()` in `MeasurementToolbar.tsx`, rendering `<IconEye>` / `<IconEyeOff>` (`"Ocultar/Mostrar mediciones guardadas"`) and `<IconTrash>` (`"Borrar mediciones guardadas"`) whenever `savedMeasurements.length > 0`.

---

### 4. `SuggestionGeometryControl.tsx` Race Condition, `LineString` Vertices & Touch Controls (`CIT-01`..`CIT-05`)

**Current Defect (Audit §3.1):**
- In `SuggestionGeometryControl.tsx:96-206`:
  1. When a single point exists (`Point`), clicking on `suggestion-point-layer` triggers `handlePointClick` (which deletes the point) AND simultaneously triggers the map-level `click` listener `handleClick` (which immediately adds a new point at `e.lngLat`), resulting in a race condition where the point cannot be deleted by clicking it.
  2. `suggestion-point-layer` uses filter `['==', '$type', 'Point']`. As soon as a 2nd vertex is added, the geometry becomes a `LineString` and all vertex circles disappear.
  3. Deletion relies on desktop right-click (`contextmenu`), which is unavailable/unusable on mobile field devices (`SuggestionGeometrySection.tsx:134-135`).

**Design Resolution:**
1. **Eliminate Click Race Condition (`SuggestionGeometryControl.tsx:96-145`)**:
   - In `handleClick(e: MapMouseEvent)`, check `map.queryRenderedFeatures(e.point, { layers: ['suggestion-point-layer'] })`. If a rendered vertex feature exists under `e.point` (or if `e.originalEvent.defaultPrevented`), return early from `handleClick` so `handlePointClick` exclusively owns vertex removal.
2. **Dedicated Vertex FeatureCollection for `Point` and `LineString` (`SuggestionGeometryControl.tsx:150-206`)**:
   - Derive a separate `verticesGeoJson` `FeatureCollection<Point>` from the current coordinates array `coords.map((coord, idx) => ({ type: 'Feature', properties: { index: idx }, geometry: { type: 'Point', coordinates: coord } }))` and bind `suggestion-point-layer` to that vertices source (or include multi-point features in the single source with a `feature_role: 'vertex'` property filter `['==', ['get', 'feature_role'], 'vertex']`). Every vertex remains visible as a styled circle whether 1 point or N points are placed.
3. **Touch-Accessible Controls (`SuggestionGeometryControl.tsx` & `SuggestionGeometrySection.tsx:134-135`)**:
   - Add an action bar above/below the map canvas with:
     - `"Mi ubicación (GPS)"` (`navigator.geolocation.getCurrentPosition` → `map.flyTo`, matching `FormularioReporte.tsx` — fixes `CIT-02`)
     - `"Deshacer último punto"` (`coords.slice(0, -1)`)
     - `"Limpiar dibujo"` (`coords = []`)
   - Update helper copy from desktop-only *"Clic derecho para borrar"* to touch-inclusive instructions.
4. **Conditional Map on Administrative Categories (`CIT-03`)**:
   - In `FormularioSugerencia.tsx:217` and `SuggestionGeometrySection.tsx:126`, when `categoria === 'administrativo'` (or non-spatial category), collapse the map inside a Mantine `<Collapse>` toggled by an optional `<Button variant="subtle">` (`"Agregar ubicación en el mapa (opcional)"`).
5. **OAuth Redirect Photo Guard (`CIT-04`) & Unified Step Header (`CIT-05`)**:
   - In `FormularioReporte.tsx:200-204` and `useReportFormSubmission.ts:52-65`, serialize small attached photos (`≤ 2 MB`) as a data URL in `sessionStorage['cc-report-draft-photo']` before triggering Google OAuth redirect (or warn if oversized), restoring the `File` via `fetch(dataUrl).then(r => r.blob())` on return.
   - Extract a shared `<ParticipacionStepHeader>` used by both `StepHeader.tsx:14-46` and `SuggestionStepIndicator.tsx:13-57`.

---

### 5. Admin Workflow & State Cohesion (`ADM-01`..`ADM-09`)

1. **`ProfilePanel.tsx:70-75` Render-Phase Mutation Fix (`ADM-02`)**:
   - Remove the synchronous `if (profile?.nombre && !profileForm.values.nombre) { profileForm.setFieldValue('nombre', profile.nombre); }` block from the component render body.
   - Replace it with a `useEffect` that initializes `profileForm.setValues({ nombre: profile.nombre })` only once when `profile?.nombre` first loads or when the user clicks `"Cancelar"`.
2. **Server-Backed Filtering & True KPI Counts (`ADM-01`)**:
   - In `ReportsPanel.tsx:55-173` (`reportsPanelUtils.tsx:18-41`) and `SugerenciasPanel.tsx:117-124`, forward `status`, `category`, and `search` parameters to the query hook and reset `page` to `1` on filter change.
   - Compute KPI badge counters (`pendientes`, `en_revision`, `resueltos`) from an unfiltered summary query or total counts returned by the API so filtering the table by `"Resuelto"` never turns the `"Pendientes"` badge into `0`.
3. **Remove Dead Suggestion History & Wire Meetings (`ADM-03`, `ADM-04`)**:
   - Remove the dead `"Historial de Gestión — Mostrar (0)"` UI and fake history toast from `SugerenciasPanel.tsx:153-216` and `SuggestionDetailModal.tsx:179-243`.
   - Extend `fetchReferrables` in `useReunionesController.ts:85-110` and `AgendaModal.tsx:72-188` to include `/sugerencias` (filtered to `en_agenda` / `pendiente`) so scheduled suggestions can be linked into meeting agendas.
4. **Basemap Parity & Report Map Link (`ADM-05`)**:
   - Switch `SugerenciaGeometryMap.tsx:105-113` default raster tile source from OpenStreetMap to Esri World Imagery (`https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`).
   - Add a `"Ver en el mapa"` `<Link to="/mapa" search={{ lat, lng, zoom: 16 }}>` button and coordinate preview inside `ReportDetailModal.tsx:144-161`.
5. **Role Visibility, CRUD Completeness, Duplicate 3D Viewer & `<Link>` (`ADM-06`..`ADM-09`)**:
   - In `AdminLayout.tsx:59, 170-183`, restrict `/admin/conocimiento` nav item to `roles: ['admin']` and render the dynamic role label (`userRole === 'admin' ? 'Administrador' : 'Operador'`).
   - In `PadronPanel.tsx:193-225`, add `email`, `telefono`, and edit/delete action buttons; in `EditGastoModal.tsx:25-44`, bind inputs for `descripcion`, `monto`, `fecha`, and `categoria`; in `FinanzasSummaryTab.tsx:24-34`, render the budget vs execution summary cards.
   - In `MapaPage.tsx:267-288`, remove the below-the-fold KPI cards so `/mapa` stays a clean `100dvh` workspace; in `DemPipelinePanel.tsx:161-174`, replace the embedded `<TerrainViewer3D>` with a direct link/action to open `/mapa` in 3D mode.
   - Replace `<a href>` internal navigation in `UserMenu.tsx:71-232` and `HomePage.tsx:219-456` with TanStack Router `<Link>`, and consolidate status badge helpers into `StatusBadge.tsx:11-18`.

---

### 6. `<LiveRegionProvider>` Hoisting, Keyboard/ARIA Fixes & Authenticated `a11y.spec.ts` (`A11Y-01`..`A11Y-07`)

#### 6.1. Hoisting `<LiveRegionProvider>` to `RootLayout.tsx` (`A11Y-01`)

**Current Defect (Audit §4 `A11Y-01`):**
- `liveRegion.tsx:64-71` returns a silent no-op fallback when `LiveRegionContext` is missing.
- `ParticipacionPage.tsx:43` calls `useLiveRegion()` with no `<LiveRegionProvider>` ancestor at all.
- `ReportsPanel.tsx:46` and `SugerenciasPanel.tsx:86` call `useLiveRegion()` at the top of the component function and then render `<LiveRegionProvider>` in their own JSX return — meaning the hook executes *above* the provider it creates, so `context` is always `null` across 100% of the app.

**Design Resolution:**
1. Mount `<LiveRegionProvider>` once inside `RootLayout.tsx` directly inside `<MantineProvider>` wrapping the entire router `<Outlet />`.
2. Remove the redundant local `<LiveRegionProvider>` JSX wrappers from `ReportsPanel.tsx` and `SugerenciasPanel.tsx`.
3. Every call to `useLiveRegion()` in `ParticipacionPage`, `ReportsPanel`, `SugerenciasPanel`, `ElevationProfileChart`, and `MapSearchBox` now resolves the root context and writes to the single polite/assertive ARIA live regions.

#### 6.2. Keyboard Navigation, ARIA Integrity & Colorblind-Safe Slope Ramp (`A11Y-03`..`A11Y-07`)
- **`ElevationProfileChart.tsx:579-592` (`A11Y-03`)**: Add `tabIndex={0}`, `role="group"`, `aria-label` with profile summary metrics, and `onKeyDown` handling `ArrowLeft`/`ArrowRight` (±1 vertex), `PageUp`/`PageDown` (±10 vertices), `Home` (index 0), and `End` (last index), updating the active sample and announcing milestones via `useLiveRegion()`.
- **`MapSearchBox.tsx:96-182` (`A11Y-04`)**: Add `role="combobox"`, `aria-expanded={isOpen}`, `aria-controls="map-search-listbox"`, and `aria-activedescendant` to the `<TextInput>` input element; add `id="map-search-listbox"` and `role="listbox"` to the dropdown container; add `id={optionId}`, `role="option"`, and `aria-selected={idx === activeIndex}` to each item; handle `ArrowDown`, `ArrowUp`, `Enter`, and `Escape`.
- **Broken ARIA Attributes (`A11Y-05`)**:
  - `SugerenciasFilters.tsx:24-49`: Add `aria-label="Filtrar por estado"`, `aria-label="Filtrar por categoría"`, and `aria-label="Buscar sugerencias"` to the 3 filter controls.
  - `ReportDetailModal.tsx:104`: Remove dangling `aria-labelledby="modal-title-detail"` (Mantine `<Modal title="...">` automatically wires its own header `aria-labelledby`).
  - `coordinates.tsx:110`: Render `<Text id="lng-format-help" srOnly>...</Text>` (or only set `aria-describedby="lng-format-help"` when the element with `id="lng-format-help"` is mounted in the DOM).
- **Interactive Semantics & Dark-Mode Contrast (`A11Y-06`)**:
  - `MapPanelShell.tsx:242-250` & `ProximaReunionSection.tsx:36-45`: Add `role="button"`, `tabIndex={0}`, and `onKeyDown` (`Enter`/`Space`) to interactive headers/cards.
  - `radioGroup.tsx:76, 124`: Scope `[role="radio"]` focus queries to `groupRef.current?.querySelector(...)` instead of global `document.querySelector`, and replace hardcoded `bg="blue.0"` with `var(--mantine-color-blue-light)` so dark-mode text contrast passes WCAG 2.1 AA (≥ 4.5:1).
- **Colorblind-Safe Slope Palette (`A11Y-07`)**:
  - `slopeColor.ts:17-21` & `MapaMapLibreView.tsx:427-445`: Replace the red-yellow-green ramp (`#2b8a3e` → `#f59f00` → `#e03131`) with a colorblind-safe sequential/diverging ramp (`#0072B2` low / `#E69F00` moderate / `#D55E00` steep, Okabe-Ito aligned) paired with a text label (`"Baja"`, `"Media"`, `"Alta"`) and legend entry.

#### 6.3. Authenticating `tests/accessibility/a11y.spec.ts` (`A11Y-02`)

**Current Defect (Audit §4 `A11Y-02`):**
`consorcio-web/tests/accessibility/a11y.spec.ts:4-11` iterates over `['/login', '/perfil', '/admin', '/admin/reports', '/admin/sugerencias']` with an unauthenticated browser context. Protected routes redirect to `/login`, so Axe scans `/login` 4 times in a row while never testing `ProfilePanel` or `AdminLayout`.

**Design Resolution:**
1. **Split Public vs Protected Route Suites in `a11y.spec.ts`**:
   - **Public Suite**: Scans `/`, `/login`, `/mapa` (with `LayerControlsPanel` and `MapSearchBox` open), `/participacion?tab=reportes`, and `/participacion?tab=sugerencias`.
   - **Authenticated Suite**: In `test.beforeEach`, inject a valid mock session into `localStorage` (Supabase auth token key + mocked `/api/v2/auth/me` and `/api/v2/admin/*` route handlers via `page.route(...)`, matching existing Playwright E2E auth fixtures in `tests/e2e/`).
   - **Redirect Guard**: Before calling `new AxeBuilder({ page }).analyze()`, assert `await expect(page).not.toHaveURL(/\/login/)` so any auth regression fails the test loudly instead of silently scanning `/login`.
