# Tasks: Frontend UX, Functional Consolidation & WCAG 2.1 AA Hardening (`consorcio-web`)

## Overview & Wave Dependencies

| Wave | Name | Depends On | Primary Verification |
|---|---|---|---|
| **Wave 1** | `Wave 1: Map 2D/3D & Elevation Profile UX/Cleanup` | — | `npx tsc --noEmit` + focused `npx vitest run` on map2d/terrain |
| **Wave 2** | `Wave 2: Citizen Participation & Field Geometry UX` | — (independent of Wave 1) | `npx tsc --noEmit` + focused `npx vitest run` on suggestion/report forms |
| **Wave 3** | `Wave 3: Admin Workflow Cohesion & State Fixes` | — (independent of Wave 1/2) | `npx tsc --noEmit` + focused `npx vitest run` on admin panels |
| **Wave 4** | `Wave 4: WCAG 2.1 AA Hardening & Authenticated a11y E2E Suite` | Waves 1–3 (audits final DOM) | `npx tsc --noEmit` + `npx vitest run` + `npx playwright test tests/accessibility/a11y.spec.ts` |

> **Gate Policy**: Never run `npm run build` / `pnpm build` unless explicitly authorized by the user. Validate every wave using `npx tsc --noEmit`, focused `npx vitest run`, and focused `npx playwright test`.

---

## Wave 1: Map 2D/3D & Elevation Profile UX/Cleanup

- [x] **T1.1 Remove `TimeCompareBar.tsx`, `timeLayers.ts`, and unit tests (Alternativa A)**
  - Delete `consorcio-web/src/components/map2d/TimeCompareBar.tsx`, `consorcio-web/src/lib/api/timeLayers.ts`, and `consorcio-web/tests/unit/timeLayers.test.ts`.
  - Remove `<TimeCompareBar>` mount and imports from `consorcio-web/src/components/map2d/MapaMapLibreView.tsx` and update `consorcio-web/tests/unit/MapaMapLibre.test.tsx`.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run tests/unit/MapaMapLibre.test.tsx`.

- [x] **T1.2 Delete dead map files, props, and branches (`Audit §2.3`, `ADM-08`)**
  - Delete `consorcio-web/src/components/map2d/PropuestasEtapasFilter.tsx` and `consorcio-web/src/components/map2d/pointAlongLine.ts` (and any orphaned unit test).
  - Remove the 11 unused `InfoPanel` props and dead `showEmbeddedMapControls` / `showEmbeddedRasterLegend` branches in `consorcio-web/src/components/map2d/MapUiPanels.tsx:142-155, 525-605, 619-627` and `MapaMapLibreView.tsx:815-825`.
  - Remove the dead non-embedded `MapPanelShell` branch in `consorcio-web/src/components/map2d/InfoPanel.tsx:642-667`.
  - Remove the dead `showVectorSections` branch in `consorcio-web/src/components/terrain/TerrainLayerTogglesPanel.tsx:231-396`.
  - Remove duplicate below-the-fold KPI cards in `consorcio-web/src/components/MapaPage.tsx:267-288` and replace the duplicate embedded `<TerrainViewer3D>` in `consorcio-web/src/components/admin/DemPipelinePanel.tsx:161-174` with a direct link to `/mapa` in 3D mode.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run tests/unit/MapUiPanels.test.tsx tests/unit/InfoPanel.test.tsx`.

- [x] **T1.3 Fix `MeasurementToolbar.tsx`, polygon `undo()`, and personal measurements lifecycle (`MAP-01`, `MAP-02`, `MAP-03`)**
  - Add Tabler icons (`IconArrowBackUp`, `IconDeviceFloppy`, `IconEye`/`IconEyeOff`, `IconTrash`) and Mantine `<Tooltip>` wrappers to `"Deshacer"`, `"Guardar"`, and saved measurement buttons in `consorcio-web/src/components/map2d/MeasurementToolbar.tsx:224-238`.
  - Update `undo()` in `consorcio-web/src/components/map2d/useMeasurement.ts:467-481` to remove the last vertex when `mode === 'measuring-area'` (`Polygon`) in addition to `LineString`.
  - Add polygon fill layer (`type: 'fill'`) and visibility/clear controls to `consorcio-web/src/components/map2d/usePersonalMeasurementsLayer.ts:10-34`, `personalMeasurements.ts:27-44`, and `MeasurementToolbar.tsx`.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run src/components/map2d/__tests__/MeasurementToolbar.test.tsx src/components/map2d/__tests__/useMeasurement.test.ts`.

- [x] **T1.4 Unify 3D sidebar controls, wire `layerFineControl`, and isolate `map3d` presets (`MAP-04`, `MAP-05`)**
  - In `consorcio-web/src/components/terrain/TerrainViewer3DChrome.tsx:465-505`, pass a real `layerFineControl` adapter to `<LayerControlsPanel variant="3d">` and remove duplicate DEM layer/opacity selectors between `TerrainLayerTogglesPanel` and `LayerControlsPanel`.
  - In `consorcio-web/src/components/map2d/LayerControlsPanel.tsx:456`, pass `variant === '3d' ? 'map3d' : 'map2d'` to `applyPreset(...)` in `MapPresetChips`.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run src/components/terrain/__tests__/TerrainViewer3DChrome.test.tsx src/components/map2d/__tests__/LayerControlsPanel.test.tsx`.

- [x] **T1.5 Fix `ElevationProfileChart` unbacked switches, single-instance mounting, and 3D dock (`MAP-06`, `MAP-07`, `MAP-08`)**
  - In `consorcio-web/src/components/map2d/ElevationProfileChart.tsx:180, 379-389, 454-456`, hide `"Comparar relevamiento"` when `pairedSurvey == null` and hide `"Terreno vs solera"` when `!solera.ok`.
  - In `consorcio-web/src/components/map2d/InfoPanel.tsx:546-568`, unmount/collapse the inline `<ElevationProfileChart>` when the bottom `ElevationProfileDock` is open.
  - In `consorcio-web/src/components/terrain/TerrainViewer3DChrome.tsx:303-312` and `TerrainViewer3D.tsx:938-1043`, pass `onOpenCanalProfile` to `InfoPanel` and mount `ElevationProfileDock` inside the relative 3D viewport container.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run src/components/map2d/__tests__/ElevationProfileChart.test.tsx`.

- [x] **T1.6 Resolve Top-Left and Bottom viewport layout collisions (`Audit §2.2`)**
  - Refactor Top-Left positioning in `consorcio-web/src/styles/components/map.module.css`, `MapaMapLibreView.tsx`, and `MapActionsPanel.tsx:96-109` so `.workspaceBurger`, `MapSearchBox` + `MapShareLink`, `2D/3D` toggle, and `HazardControls` never overlap, and remove the duplicate permalink action in `MapActionsPanel`.
  - Apply `--map-bottom-dock-offset` in `MapaMapLibreView.tsx`, `TerrainViewer3D.tsx`, and `map.module.css` so `FichaTerritorialPanel`, `RoadFlowPanel`, and `MapCursorReadout` shift above `ElevationProfileDock` when open.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run tests/unit/MapaMapLibre.test.tsx`.

---

## Wave 2: Citizen Participation & Field Geometry UX

- [x] **T2.1 Fix `SuggestionGeometryControl.tsx` click race condition, `LineString` vertices, and touch controls (`CIT-01`, `CIT-02`)**
  - In `consorcio-web/src/components/map/SuggestionGeometryControl.tsx:96-206`, guard `handleClick` when `queryRenderedFeatures` hits `suggestion-point-layer` so clicking a vertex deletes it without re-adding a point at the same coordinates.
  - Render all vertices as circular handles for both `Point` and `LineString` geometries.
  - Add touch-friendly `"Mi ubicación (GPS)"`, `"Deshacer último punto"`, and `"Limpiar dibujo"` buttons in `SuggestionGeometryControl.tsx` / `SuggestionGeometrySection.tsx:134-135`.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run tests/unit/SuggestionGeometryControl.test.tsx`.

- [x] **T2.2 Hide canal map by default on administrative categories and guard OAuth photo drafts (`CIT-03`, `CIT-04`)**
  - In `consorcio-web/src/components/FormularioSugerencia.tsx:217` and `src/components/suggestion-form/SuggestionGeometrySection.tsx:126`, collapse the geometry map behind an optional toggle when a non-spatial/administrative category is selected.
  - In `consorcio-web/src/components/FormularioReporte.tsx:200-204` and `src/components/report-form/useReportFormSubmission.ts:52-65`, persist small photo drafts (`≤ 2 MB`) in `sessionStorage` across Google OAuth redirects (or warn/gate before redirect).
  - **Verify**: `npx tsc --noEmit` and `npx vitest run tests/unit/FormularioSugerencia.test.tsx tests/unit/FormularioReporte.test.tsx`.

- [x] **T2.3 Unify citizen step headers, admin basemap parity, and `StatusBadge` (`CIT-05`, `ADM-05`, `ADM-09`)**
  - Unify `consorcio-web/src/components/report-form/StepHeader.tsx:14-46` and `src/components/suggestion-form/SuggestionStepIndicator.tsx:13-57`.
  - Switch `consorcio-web/src/components/admin/sugerencias/components/SugerenciaGeometryMap.tsx:105-113` to Esri World Imagery satellite tiles and add a `"Ver en el mapa"` deep link / preview in `src/components/admin/reports/components/ReportDetailModal.tsx:144-161`.
  - Consolidate duplicate status badge helpers across admin panels into `consorcio-web/src/components/ui/StatusBadge.tsx:11-18`.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run tests/unit/SugerenciaGeometryMap.test.tsx tests/unit/ReportDetailModal.test.tsx`.

---

## Wave 3: Admin Workflow Cohesion & State Fixes

- [x] **T3.1 Fix `ProfilePanel.tsx` render-phase state mutation (`ADM-02`)**
  - In `consorcio-web/src/components/ProfilePanel.tsx:70-75`, move `profileForm.setFieldValue('nombre', profile.nombre)` out of the render body into a `useEffect` triggered only on initial profile load or cancel.
  - Add a unit test verifying that clearing the `"Nombre"` input to `""` stays empty while editing.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run tests/unit/ProfilePanel.test.tsx`.

- [x] **T3.2 Move `ReportsPanel` and `SugerenciasPanel` filtering and KPI counters to server-backed queries (`ADM-01`)**
  - Update `consorcio-web/src/components/admin/reports/ReportsPanel.tsx:55-173`, `reportsPanelUtils.tsx:18-41`, and `src/components/admin/sugerencias/SugerenciasPanel.tsx:117-124` to pass `status`, `category`, and `search` to the backend query hooks, reset `page` to `1` on filter change, and compute KPI badges from global totals rather than the 10 items on the current page.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run tests/unit/ReportsPanel.test.tsx tests/unit/SugerenciasPanel.test.tsx`.

- [x] **T3.3 Remove dead suggestion history UI and connect scheduled suggestions to `Reuniones` (`ADM-03`, `ADM-04`)**
  - Remove the dead `"Historial de Gestión — Mostrar (0)"` section and misleading history toast in `consorcio-web/src/components/admin/sugerencias/SugerenciasPanel.tsx:153-216` and `components/SuggestionDetailModal.tsx:179-243`.
  - Extend `fetchReferrables` in `consorcio-web/src/components/admin/management/reuniones/useReunionesController.ts:85-110` and `components/AgendaModal.tsx:72-188` to include scheduled/pending suggestions.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run tests/unit/SugerenciasPanel.test.tsx tests/unit/ReunionesPanel.test.tsx`.

- [x] **T3.4 Align role navigation, complete `PadronPanel` / `FinanzasPanel` CRUDs, and use `<Link>` (`ADM-06`, `ADM-07`, `ADM-09`)**
  - In `consorcio-web/src/components/admin/AdminLayout.tsx:59, 170-183`, restrict `/admin/conocimiento` link to `admin` role and render the user's actual role label.
  - Add `email`, `telefono`, and edit/delete actions in `consorcio-web/src/components/admin/management/PadronPanel.tsx:193-225`; expose full fields in `finanzas/components/EditGastoModal.tsx:25-44` and `FinanzasSummaryTab.tsx:24-34`.
  - Replace internal `<a href>` navigation with TanStack Router `<Link>` in `consorcio-web/src/components/UserMenu.tsx:71-232` and `HomePage.tsx:219-456`.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run tests/unit/AdminLayout.test.tsx tests/unit/PadronPanel.test.tsx`.

---

## Wave 4: WCAG 2.1 AA Hardening & Authenticated a11y E2E Suite

- [x] **T4.1 Hoist `<LiveRegionProvider>` to `RootLayout.tsx` (`A11Y-01`)**
  - Mount `<LiveRegionProvider>` once in `consorcio-web/src/components/RootLayout.tsx` and remove the broken child `<LiveRegionProvider>` wrappers in `ReportsPanel.tsx:46` and `SugerenciasPanel.tsx:86`.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run tests/unit/liveRegion.test.tsx`.

- [x] **T4.2 Add keyboard navigation and ARIA combobox/chart semantics to `ElevationProfileChart` and `MapSearchBox` (`A11Y-03`, `A11Y-04`)**
  - Add `tabIndex={0}`, summary `aria-label`, and `ArrowLeft`/`ArrowRight`/`PageUp`/`PageDown`/`Home`/`End` handlers to `<svg>` in `consorcio-web/src/components/map2d/ElevationProfileChart.tsx:579-592`.
  - Implement WAI-ARIA `combobox` + `listbox` + `option` semantics and `ArrowDown`/`ArrowUp`/`Enter`/`Escape` keyboard navigation in `consorcio-web/src/components/map2d/MapSearchBox.tsx:96-182`.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run src/components/map2d/__tests__/ElevationProfileChart.test.tsx src/components/map2d/__tests__/MapSearchBox.test.tsx`.

- [x] **T4.3 Fix missing ARIA labels, dangling IDs, button roles, dark-mode contrast, and colorblind-safe slope ramp (`A11Y-05`, `A11Y-06`, `A11Y-07`)**
  - Add accessible labels in `consorcio-web/src/components/admin/sugerencias/components/SugerenciasFilters.tsx:24-49`, remove dangling `aria-labelledby="modal-title-detail"` in `ReportDetailModal.tsx:104`, and fix `id="lng-format-help"` in `src/components/ui/accessibility/coordinates.tsx:110`.
  - Add `role="button"`, `tabIndex={0}`, and keyboard activation to `MapPanelShell.tsx:242-250` and `ProximaReunionSection.tsx:36-45`; scope `radioGroup.tsx:76, 124` focus queries to a local `useRef` and fix dark-mode selection contrast.
  - Update `consorcio-web/src/components/map2d/slopeColor.ts:17-21` and `MapaMapLibreView.tsx:427-445` to use a colorblind-safe Okabe-Ito/Viridis ramp with legend/text labels.
  - **Verify**: `npx tsc --noEmit` and `npx vitest run tests/unit/radioGroup.test.tsx tests/unit/coordinates.test.tsx`.

- [x] **T4.4 Authenticate `tests/accessibility/a11y.spec.ts` and expand route coverage (`A11Y-02`)**
  - Update `consorcio-web/tests/accessibility/a11y.spec.ts:4-11` to inject authenticated session state and API mocks before scanning `/perfil`, `/admin`, `/admin/reports`, and `/admin/sugerencias`.
  - Assert `await expect(page).not.toHaveURL(/\/login/)` on every protected route scan, and add scans for `/participacion?tab=sugerencias` and `/mapa` with panels open.
  - **Verify**: `npx playwright test tests/accessibility/a11y.spec.ts`.
