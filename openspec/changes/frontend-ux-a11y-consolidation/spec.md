# Specification: Frontend UX, Functional Consolidation & WCAG 2.1 AA Hardening (`consorcio-web`)

## 1. Wave 1 — Map 2D/3D, Viewport Layout & Elevation Profile (`TimeCompareBar`, `MAP-01`..`MAP-08`)

### 1.1. `TimeCompareBar` Removal & Dead Code Elimination

#### Requirements
- **REQ-TIME-01**: `TimeCompareBar.tsx`, `timeLayers.ts`, and `tests/unit/timeLayers.test.ts` MUST be removed from `consorcio-web`. Before/After satellite comparison MUST remain governed exclusively through `/admin/images` (`ImageExplorerPanel.tsx`) and `ViewModePanel.tsx`.
- **REQ-DEAD-01**: Dead map modules and branches (`PropuestasEtapasFilter.tsx`, `pointAlongLine.ts`, unused `InfoPanel` props and dead `showEmbeddedMapControls`/`showEmbeddedRasterLegend` branches in `MapUiPanels.tsx`, non-embedded branch in `InfoPanel.tsx`, and `showVectorSections` dead branch in `TerrainLayerTogglesPanel.tsx`) MUST be removed.

#### Scenarios
- **Scenario: Anonymous or authenticated user opens `/mapa`**
  - **GIVEN** a user navigates to `/mapa`
  - **WHEN** the 2D map workspace finishes loading
  - **THEN** `TimeCompareBar` is not rendered in the bottom-left corner, no unauthenticated GEE tile requests (`401/403`) are triggered from a timeline bar, and `baseLayer` / `viewMode` cannot be locked into a state where `ViewModePanel` disappears.

---

### 1.2. `MAP-01`, `MAP-02`, `MAP-03` — Measurement Toolbar & Personal Measurements Lifecycle

#### Requirements
- **REQ-MAP-01**: Every action button in `MeasurementToolbar.tsx` (`"Deshacer"`, `"Guardar"`, `"Limpiar"`, visibility toggle) MUST render a visible Tabler icon (`@tabler/icons-react`), an explicit `aria-label`, and a Mantine `<Tooltip>` so desktop (`pointer: fine`) users never see empty 29×29px white boxes when `.mapCtrlButtonLabel` has `display: none`.
- **REQ-MAP-02**: `MeasurementToolbar.tsx` and `personalMeasurements.ts` / `usePersonalMeasurementsLayer.ts` MUST provide UI controls to toggle visibility and clear saved personal measurements (`localStorage['cc-personal-measurements']`), and saved polygons MUST render with both a fill layer (`type: 'fill'` with translucent fill opacity) and an outline layer (`type: 'line'`).
- **REQ-MAP-03**: `undo()` in `useMeasurement.ts` MUST remove the last vertex both when `mode === 'measuring-distance'` (`LineString`) and when `mode === 'measuring-area'` (`Polygon`).

#### Scenarios
- **Scenario: Desktop user hovers and clicks measurement actions (`MAP-01`)**
  - **GIVEN** a desktop viewport (`pointer: fine`) with active measurement points
  - **WHEN** the user inspects the `"Deshacer"` and `"Guardar"` buttons in `MeasurementToolbar`
  - **THEN** each button displays a centered SVG icon (`IconArrowBackUp`, `IconDeviceFloppy`) and shows a descriptive `<Tooltip>` on hover/focus.
- **Scenario: User saves, hides, and clears personal measurements (`MAP-02`)**
  - **GIVEN** the user has saved at least one distance line and one area polygon to `cc-personal-measurements`
  - **WHEN** the saved measurements layer renders on the map
  - **THEN** the polygon displays both a semi-transparent interior fill and a stroke outline, and clicking `"Ocultar mediciones guardadas"` or `"Borrar mediciones guardadas"` hides or removes them from `localStorage` and the MapLibre canvas immediately.
- **Scenario: User undoes vertices while measuring an area polygon (`MAP-03`)**
  - **GIVEN** `mode === 'measuring-area'` and the user has placed 4 polygon vertices
  - **WHEN** the user clicks `"Deshacer"` (`undo()`)
  - **THEN** the 4th vertex is removed leaving a 3-vertex polygon; if only 1 vertex was placed, `undo()` resets the current draft geometry cleanly.

---

### 1.3. `MAP-04`, `MAP-05` — 3D Layer Fine Control, Presets & Unified Raster Controls

#### Requirements
- **REQ-MAP-04**: `TerrainViewer3DChrome.tsx` MUST pass a working `layerFineControl` adapter to `<LayerControlsPanel variant="3d">` bound to the 3D viewer's active vector/raster visibility and opacity state (never falling back to `NOOP_FINE_CONTROL`), and MUST eliminate duplicate DEM layer/opacity selectors between `TerrainLayerTogglesPanel` and `LayerControlsPanel`.
- **REQ-MAP-05**: `MapPresetChips` inside `LayerControlsPanel.tsx` MUST pass `'map3d'` (not hardcoded `'map2d'`) to `applyPreset(target, preset)` when `variant === '3d'`.

#### Scenarios
- **Scenario: User toggles layer visibility and adjusts opacity in 3D (`MAP-04`)**
  - **GIVEN** the 3D terrain viewer is active with active layers listed under `"En el mapa"`
  - **WHEN** the user clicks `active-layer-toggle-*` or drags `active-layer-opacity-*`
  - **THEN** the corresponding 3D layer visibility or opacity updates on the Three.js terrain mesh immediately, and only one DEM selector + raster opacity slider exists in the 3D sidebar.
- **Scenario: User selects a preset chip in 3D (`MAP-05`)**
  - **GIVEN** `<LayerControlsPanel variant="3d">` is rendered
  - **WHEN** the user clicks a preset chip
  - **THEN** `applyPreset('map3d', preset)` is invoked, updating the 3D layer configuration without mutating the 2D store slice.

---

### 1.4. `MAP-06`, `MAP-07`, `MAP-08` — Elevation Profile Truthfulness, Single-Instance Mounting & 3D Integration

#### Requirements
- **REQ-MAP-06**: `ElevationProfileChart.tsx` MUST only render the `"Comparar relevamiento"` switch when `pairedSurvey != null` and contains valid profile points.
- **REQ-MAP-07**: `ElevationProfileChart.tsx` MUST only render the `"Terreno vs solera"` toggle when at least one point in the profile dataset includes a finite `solera_m` value (`solera.ok === true`).
- **REQ-MAP-08**: `TerrainViewer3DChrome.tsx` MUST pass `onOpenCanalProfile` to `InfoPanel`, `TerrainViewer3D.tsx` MUST mount `ElevationProfileDock` inside the relative viewport container, and opening the bottom dock from `InfoPanel` (`"Abrir abajo"`) MUST close or collapse the inline sidebar chart so two `<ElevationProfileChart>` instances never remain mounted simultaneously.

#### Scenarios
- **Scenario: Canal profile opened without paired survey or solera data (`MAP-06`, `MAP-07`)**
  - **GIVEN** a canal profile returned by `useDemProfile` with `{ distance_m, elevation_m, lat, lon }` and `pairedSurvey === undefined`
  - **WHEN** `ElevationProfileChart` renders
  - **THEN** neither `"Comparar relevamiento"` nor `"Terreno vs solera"` is rendered in the chart toolbar, preventing dead switches and empty warning banners.
- **Scenario: User promotes sidebar profile to bottom dock or opens profile in 3D (`MAP-08`)**
  - **GIVEN** a selected canal in 2D or 3D `InfoPanel`
  - **WHEN** the user clicks `"Abrir abajo"` (or opens the canal profile in 3D)
  - **THEN** `ElevationProfileDock` opens inside the map container bounds and the inline `InfoPanel` chart unmounts, leaving exactly one `<ElevationProfileChart>` in the DOM.

---

### 1.5. Viewport Layout Collision Resolution (Top-Left & Bottom)

#### Requirements
- **REQ-LAYOUT-01 (Top-Left)**: `.workspaceBurger` (mobile), `2D/3D` toggle, `MapSearchBox` + `MapShareLink`, and `HazardControls` MUST be arranged in a non-overlapping top-left header/stack so no control covers another at any viewport width (`320px`–`1920px`). Duplicate permalink actions between `MapShareLink` and `MapActionsPanel` MUST be consolidated.
- **REQ-LAYOUT-02 (Bottom)**: When `ElevationProfileDock` is open (`height: 260px`), bottom-anchored floating panels (`RoadFlowPanel`, `FichaTerritorialPanel`, `MapCursorReadout`) MUST shift upward (via CSS custom property `--map-bottom-dock-offset` or flex container stacking) or dock cleanly so the close/minimize controls of `ElevationProfileDock` are never occluded.

#### Scenarios
- **Scenario: Opening ElevationProfileDock while FichaTerritorialPanel or RoadFlowPanel is active**
  - **GIVEN** `FichaTerritorialPanel` or `RoadFlowPanel` is open on the map
  - **WHEN** `ElevationProfileDock` is opened at the bottom of the viewport
  - **THEN** the close and minimize buttons of `ElevationProfileDock` remain 100% clickable and unobstructed.

---

## 2. Wave 2 — Citizen Participation & Field Geometry UX (`CIT-01`..`CIT-05`)

### 2.1. `CIT-01` — Touch-Compatible Geometry Drawing & Point Click Race Fix

#### Requirements
- **REQ-CIT-01a**: `SuggestionGeometryControl.tsx` MUST stop propagation / guard map-level `click` when `handlePointClick` deletes or selects an existing vertex on `suggestion-point-layer`, preventing `handleClick` from immediately re-creating the deleted point at the same coordinates.
- **REQ-CIT-01b**: The vertex circle layer (`suggestion-point-layer`) MUST render vertices for both `Point` and `LineString` geometries (using a dedicated vertices GeoJSON FeatureCollection or multi-geometry filter) so users see every placed vertex as they draw a canal line.
- **REQ-CIT-01c**: `SuggestionGeometrySection.tsx` / `SuggestionGeometryControl.tsx` MUST expose explicit, touch-accessible `"Deshacer último punto"` and `"Limpiar dibujo"` buttons alongside the map canvas, removing reliance on desktop-only right-click (`contextmenu`).

#### Scenarios
- **Scenario: Mobile user draws a multi-point canal suggestion and undoes/clears vertices (`CIT-01`)**
  - **GIVEN** a citizen on a touch device (`pointer: coarse`) in `FormularioSugerencia`
  - **WHEN** the user taps 3 points on `SuggestionGeometryControl`
  - **THEN** all 3 vertices remain visible as circular handles along the `LineString`, tapping `"Deshacer último punto"` reverts to 2 points, tapping an existing vertex removes it without re-adding it at the same tap location, and tapping `"Limpiar dibujo"` clears the geometry to empty.

---

### 2.2. `CIT-02`, `CIT-03`, `CIT-04`, `CIT-05` — Citizen Form Parity, Conditional Map, OAuth Photo Guard & Unified Step UI

#### Requirements
- **REQ-CIT-02**: `SuggestionGeometrySection.tsx` MUST offer a `"Mi ubicación (GPS)"` center/locate action so field users can center the suggestion map on their current position just like `FormularioReporte`.
- **REQ-CIT-03**: When the citizen selects a non-spatial category in `FormularioSugerencia.tsx` (e.g., `"Temas administrativos"`), `SuggestionGeometrySection` MUST collapse by default behind an optional `"¿Querés marcar una ubicación en el mapa? (Opcional)"` toggle instead of demanding a canal trace.
- **REQ-CIT-04**: In `FormularioReporte.tsx` and `useReportFormSubmission.ts`, if the user is unauthenticated and triggers Google OAuth login redirect, the UI MUST either gate Step 2 photo selection behind authentication OR persist a small Base64/IndexedDB preview / display an explicit warning before redirect so a selected `File` is never silently lost after OAuth return.
- **REQ-CIT-05**: `StepHeader.tsx` and `SuggestionStepIndicator.tsx` MUST share a single consistent step-header visual component, and post-submission feedback across `/participacion` tabs MUST follow a unified pattern.

#### Scenarios
- **Scenario: Citizen selects an administrative suggestion category (`CIT-03`)**
  - **GIVEN** the citizen is on `/participacion?tab=sugerencias`
  - **WHEN** they select `"Temas administrativos"` as the category
  - **THEN** the satellite canal-drawing canvas is hidden by default and replaced by a non-intrusive optional toggle.
- **Scenario: Unauthenticated citizen logs in with Google during report creation (`CIT-04`)**
  - **GIVEN** an unauthenticated citizen on `/participacion?tab=reportes`
  - **WHEN** they authenticate via Google OAuth redirect and return to the restored draft
  - **THEN** either the photo step was unlocked only after login or the restored draft explicitly informs/restores the attachment state so no silent data loss occurs.

---

## 3. Wave 3 — Admin Workflow Cohesion & State Fixes (`ADM-01`..`ADM-09`)

### 3.1. `ADM-01` — Server-Backed Filtering & True KPI Totals in `ReportsPanel` and `SugerenciasPanel`

#### Requirements
- **REQ-ADM-01**: `ReportsPanel.tsx` (`reportsPanelUtils.tsx`) and `SugerenciasPanel.tsx` MUST pass active filters (`status`, `category`, `search`) to the backend query / API hook rather than filtering only the 10 items of the current client page, and KPI summary badges (`pendientes`, `en_revision`, etc.) MUST display global totals across all pages (from backend summary/stats metadata or dedicated count queries) independent of the currently selected status filter or page index.

#### Scenarios
- **Scenario: Admin filters reports by status `"Resuelto"` on page 2 (`ADM-01`)**
  - **GIVEN** 45 total reports exist in the database (12 `pendiente`, 8 `en_revision`, 25 `resuelto`)
  - **WHEN** the admin selects status filter `"Resuelto"` or searches by text
  - **THEN** the API is queried with the filter parameters returning matching records across the entire dataset, and the header KPI badge for `"Pendientes"` still reads `12` (not `0`).

---

### 3.2. `ADM-02` — Render-Phase State Mutation Fix in `ProfilePanel`

#### Requirements
- **REQ-ADM-02**: `ProfilePanel.tsx` MUST NOT call `profileForm.setFieldValue('nombre', ...)` inside the component render body. Form initialization from `profile.nombre` MUST occur inside a `useEffect` keyed on `profile?.nombre` (or when entering edit mode) so clearing the input field during editing does not overwrite the user's keystrokes.

#### Scenarios
- **Scenario: User clears the name input in `ProfilePanel` to type a new name (`ADM-02`)**
  - **GIVEN** an authenticated user with `profile.nombre === "Juan Pérez"` opens `/perfil`
  - **WHEN** the user selects all text in the `"Nombre"` input and presses `Backspace`
  - **THEN** the input value becomes `""` (empty string) and stays empty until the user types a new name or cancels.

---

### 3.3. `ADM-03`, `ADM-04` — Suggestion Scheduling Integration & Removal of Dead History UI

#### Requirements
- **REQ-ADM-03**: Scheduling a suggestion for a meeting in `SugerenciasPanel.tsx` / `SuggestionDetailModal.tsx` MUST integrate with the `/admin/reuniones` workflow (`useReunionesController.ts` / `AgendaModal.tsx` `fetchReferrables` MUST include suggestions alongside `/denuncias` and `/tramites`, or link directly to a meeting agenda item).
- **REQ-ADM-04**: The dead `"Historial de Gestión — Mostrar (0)"` section and the misleading toast claiming an entry was recorded in history MUST be removed from `SugerenciasPanel.tsx` and `SuggestionDetailModal.tsx` until a real backend history endpoint is implemented.

#### Scenarios
- **Scenario: Operator schedules a suggestion and opens Reuniones agenda (`ADM-03`, `ADM-04`)**
  - **GIVEN** an operator updates a suggestion status or schedules it in `SuggestionDetailModal`
  - **WHEN** the modal renders and the action completes
  - **THEN** no dead `"Historial de Gestión (0)"` accordion or fake history toast is shown, and the scheduled suggestion appears as a referrable item when building a meeting agenda in `/admin/reuniones`.

---

### 3.4. `ADM-05`, `ADM-06`, `ADM-07`, `ADM-08`, `ADM-09` — Admin Maps, Role Guards, CRUD Completeness & Router Links

#### Requirements
- **REQ-ADM-05**: `SugerenciaGeometryMap.tsx` MUST use Esri World Imagery satellite tiles (matching the citizen drawing basemap) with an optional OSM toggle, and `ReportDetailModal.tsx` MUST render an embedded mini-map or a `"Ver en el mapa"` `<Link>` that centers `/mapa` on the report's `lat`/`lon`.
- **REQ-ADM-06**: `AdminLayout.tsx` MUST hide the `/admin/conocimiento` sidebar entry when the logged-in user role is not in `['admin']` (matching `ConocimientoPanel.tsx`), and the sidebar role badge MUST display the actual user role (`"Administrador"` vs `"Operador"`) instead of hardcoded `"Admin"`.
- **REQ-ADM-07**: `PadronPanel.tsx` MUST display `email` and `telefono` columns and provide edit/delete actions wired to the consorciostas API; `EditGastoModal.tsx` MUST allow editing `descripcion`, `monto`, `fecha`, and `categoria` (not just `categoria`); `FinanzasSummaryTab.tsx` MUST surface the budget execution summary.
- **REQ-ADM-08**: `MapaPage.tsx` MUST NOT render duplicate KPI cards below the full-viewport map canvas that cause vertical page scrolling, and `DemPipelinePanel.tsx` MUST link to `/mapa?view=3d` instead of mounting a duplicate embedded `<TerrainViewer3D>` instance.
- **REQ-ADM-09**: Internal navigation in `UserMenu.tsx`, `HomePage.tsx`, and admin panels MUST use TanStack Router `<Link>` instead of full-reload `<a href>`, and all 5 duplicate status badge helpers MUST delegate to the canonical `src/components/ui/StatusBadge.tsx`.

#### Scenarios
- **Scenario: Operator logs into `/admin` (`ADM-06`)**
  - **GIVEN** a user with role `operador` opens `/admin`
  - **WHEN** `AdminLayout` renders
  - **THEN** the role badge reads `"Operador"` and the restricted `"Consultas normativas"` (`/admin/conocimiento`) link is not shown in the sidebar.
- **Scenario: Admin reviews a report and a suggestion geometry (`ADM-05`)**
  - **GIVEN** an admin opens `SuggestionDetailModal` and `ReportDetailModal`
  - **WHEN** the geometry views render
  - **THEN** `SugerenciaGeometryMap` displays the drawn geometry over Esri satellite imagery, and `ReportDetailModal` provides a mini-map / `"Ver en el mapa"` deep link to the report coordinates.

---

## 4. Wave 4 — WCAG 2.1 AA Hardening & Authenticated a11y E2E Suite (`A11Y-01`..`A11Y-07`)

### 4.1. `A11Y-01` — Root `<LiveRegionProvider>` Hoisting

#### Requirements
- **REQ-A11Y-01**: `<LiveRegionProvider>` (`liveRegion.tsx`) MUST be mounted once near the root of the application in `RootLayout.tsx`, and duplicate/child `<LiveRegionProvider>` wrappers inside `ReportsPanel.tsx` and `SugerenciasPanel.tsx` (where `useLiveRegion()` was called in the same component above the provider return) MUST be removed.

#### Scenarios
- **Scenario: Screen reader announcement triggered in `ParticipacionPage`, `ReportsPanel`, or `SugerenciasPanel` (`A11Y-01`)**
  - **GIVEN** any page in `consorcio-web` calls `const { announce } = useLiveRegion()`
  - **WHEN** `announce("Reporte enviado correctamente", "polite")` is invoked
  - **THEN** the root `[ role="status" ][ aria-live="polite" ]` DOM node in `RootLayout` updates its text content with the announcement message (never hitting the fallback no-op warning).

---

### 4.2. `A11Y-02` — Authenticated Playwright + Axe E2E Coverage

#### Requirements
- **REQ-A11Y-02**: `tests/accessibility/a11y.spec.ts` MUST seed an authenticated admin/citizen session before visiting protected routes (`/perfil`, `/admin`, `/admin/reports`, `/admin/sugerencias`, `/admin/reuniones`), MUST assert that `page.url()` did not redirect to `/login`, and MUST also scan `/participacion?tab=sugerencias` and `/mapa` with interactive panels open.

#### Scenarios
- **Scenario: Running `npx playwright test tests/accessibility/a11y.spec.ts` (`A11Y-02`)**
  - **GIVEN** the Playwright accessibility suite runs against `consorcio-web`
  - **WHEN** Axe scans `/perfil` and `/admin/*`
  - **THEN** the browser remains on `/perfil` and `/admin/*` (not `/login`) and reports 0 `critical` or `serious` WCAG 2.1 A/AA violations.

---

### 4.3. `A11Y-03`, `A11Y-04` — Keyboard & Screen Reader Support for `ElevationProfileChart` and `MapSearchBox`

#### Requirements
- **REQ-A11Y-03**: The `<svg>` in `ElevationProfileChart.tsx` MUST have `tabIndex={0}`, `role="group"` (or `role="application"` with instructions), an accessible `aria-label` summarizing canal name, total length, min/max elevation, and slope, and `onKeyDown` handlers for `ArrowLeft` / `ArrowRight` (step 1 sample), `PageUp` / `PageDown` (step 10 samples), `Home`, and `End` that move the active cursor and announce/update the readout.
- **REQ-A11Y-04**: `MapSearchBox.tsx` MUST implement the WAI-ARIA 1.2 Combobox pattern (`role="combobox"`, `aria-expanded`, `aria-controls`, `aria-activedescendant` on the input; `role="listbox"` on the results container; `role="option"` and `aria-selected` on each result) with `ArrowDown`, `ArrowUp`, `Enter`, and `Escape` keyboard navigation.

#### Scenarios
- **Scenario: Keyboard-only user explores the elevation profile (`A11Y-03`)**
  - **GIVEN** `ElevationProfileChart` is rendered with 50 profile points
  - **WHEN** the user focuses the `<svg>` via `Tab` and presses `ArrowRight` 3 times
  - **THEN** the hovered/selected profile index advances to index 3, the map cursor syncs to that coordinate, and the distance/elevation readout updates.
- **Scenario: Keyboard-only user searches for a canal in `MapSearchBox` (`A11Y-04`)**
  - **GIVEN** the user types `"Canal"` in `MapSearchBox`
  - **WHEN** they press `ArrowDown` twice and press `Enter`
  - **THEN** the second option in the `listbox` receives `aria-selected="true"`, `aria-activedescendant` updates accordingly, and pressing `Enter` centers the map on that feature and closes the listbox.

---

### 4.4. `A11Y-05`, `A11Y-06`, `A11Y-07` — Valid ARIA Labels/IDs, Interactive Semantics, Dark Mode Contrast & Colorblind-Safe Slope Ramp

#### Requirements
- **REQ-A11Y-05**: Every input/select in `SugerenciasFilters.tsx` MUST have an explicit `aria-label` or visible `label`; `ReportDetailModal.tsx` MUST remove or bind `aria-labelledby` to an existing heading ID; `coordinates.tsx` MUST render the element with matching `id="lng-format-help"` (or omit the dangling `aria-describedby` when `showFormatHelp={false}`).
- **REQ-A11Y-06**: Clickable containers in `MapPanelShell.tsx` (mobile bottom-sheet header) and `ProximaReunionSection.tsx` (meeting cards) MUST use semantic `<button>` / `<UnstyledButton>` or `role="button"` + `tabIndex={0}` + `onKeyDown` (`Enter`/`Space`); `radioGroup.tsx` MUST scope focus queries to a local `useRef` container (not `document.querySelector`) and use theme-aware selection colors that satisfy 4.5:1 contrast in both light and dark modes.
- **REQ-A11Y-07**: `slopeColor.ts` MUST use a colorblind-safe palette (distinguishable under deuteranopia/protanopia, e.g. Viridis / YlOrBr / Okabe-Ito ramp instead of pure green-yellow-red) and expose a legend / secondary textual severity label in the 2D map and profile chart.

#### Scenarios
- **Scenario: Screen reader & Axe audit on `SugerenciasFilters`, `ReportDetailModal`, and `coordinates.tsx` (`A11Y-05`)**
  - **GIVEN** `SugerenciasFilters`, `ReportDetailModal`, and `CoordinateInput` are rendered
  - **WHEN** `@axe-core/playwright` or Vitest accessibility checks run
  - **THEN** every form control has a non-empty accessible name and every `aria-labelledby` / `aria-describedby` attribute resolves to a non-null DOM element ID.
- **Scenario: Dark-mode radio selection and keyboard navigation (`A11Y-06`)**
  - **GIVEN** two `<AccessibleRadioGroup>` instances on the same page in dark mode
  - **WHEN** the user presses `ArrowDown` inside the second radio group
  - **THEN** focus moves within the second radio group's ref container only, and the selected option's background/foreground combination meets ≥ 4.5:1 contrast ratio.

---

## 5. Edge Cases & Invariants

1. **Empty `cc-personal-measurements` storage**: When 0 personal measurements are saved, the `"Borrar mediciones guardadas"` and `"Ocultar mediciones guardadas"` buttons MUST be hidden or disabled so the toolbar stays compact.
2. **Simultaneous 2D/3D mode switch with open `ElevationProfileDock`**: Switching between 2D and 3D views while a canal profile is open MUST either preserve the single dock instance inside the active container or cleanly close it without leaving orphaned DOM portals.
3. **Rapid double-tap on `SuggestionGeometryControl` mobile canvas**: Tapping an existing vertex twice in <300ms MUST delete the vertex on the first tap and only create a new vertex if a subsequent tap occurs on empty canvas after the deletion event finishes propagating.
4. **Pagination boundary when changing server filters in `ReportsPanel` / `SugerenciasPanel`**: Changing any filter (`status`, `category`, `search`) MUST reset `page` to `1` so a user on page 4 is not stranded on an empty page when the filtered result set has only 1 page.
