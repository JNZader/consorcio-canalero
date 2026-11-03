# Proposal: Frontend UX, Functional Consolidation & WCAG 2.1 AA Hardening (`consorcio-web`)

## Intent

Consolidate and remediate `consorcio-web` UI/UX layout collisions, functional duplication, broken field/desktop controls, admin state/workflow inconsistencies, and WCAG 2.1 AA accessibility gaps identified in the 2026-11-03 audit (`HEAD` at `a8979b82`).

Recent feature waves (`#618` through `#632`) introduced rich analytical capabilities to the 2D/3D map viewer and longitudinal elevation profile, but left 14 control surfaces competing for the same viewport, invisible desktop buttons in measurement tools, mobile-hostile field geometry controls in citizen suggestions, disconnected or client-only paginated admin workflows, a degraded temporal bar (`TimeCompareBar`) that duplicates `/admin/images` while breaking anonymous map views, and a silent no-op `useLiveRegion()` / unauthenticated accessibility E2E suite.

## Scope

### In Scope (4 Waves)

| Wave | Slug | Deliverable Summary |
|---|---|---|
| **Wave 1** | `Wave 1: Map 2D/3D & Elevation Profile UX/Cleanup` | Remove `TimeCompareBar.tsx` and `timeLayers.ts` (Alternativa A); delete dead map code (`PropuestasEtapasFilter.tsx`, `pointAlongLine.ts`, dead `MapUiPanels.tsx` / `InfoPanel.tsx` / `TerrainLayerTogglesPanel.tsx` branches, duplicate KPIs below `MapaPage.tsx`); resolve Top-Left and Bottom viewport collisions; unify 3D raster controls and wire `layerFineControl` + `map3d` presets; fix `MeasurementToolbar.tsx` icons/tooltips, polygon `undo()`, and saved personal measurements clear/visibility/fill; hide unbacked `ElevationProfileChart` switches and prevent dual sidebar+dock chart mounting; wire `onOpenCanalProfile` and dock containment in 3D (`MAP-01`..`MAP-08`). |
| **Wave 2** | `Wave 2: Citizen Participation & Field Geometry UX` | Fix `SuggestionGeometryControl.tsx` point-click race condition, render `LineString` vertices, and add touch-friendly undo/clear buttons; hide canal drawing map on administrative/non-spatial suggestion categories; switch `SugerenciaGeometryMap.tsx` to Esri World Imagery and add map preview / `"Ver en el mapa"` to `ReportDetailModal.tsx`; warn/preserve photo attachment expectations across Google OAuth redirects; unify step headers and `StatusBadge` (`CIT-01`..`CIT-05`, `ADM-05`, `ADM-09`). |
| **Wave 3** | `Wave 3: Admin Workflow Cohesion & State Fixes` | Fix `ProfilePanel.tsx` render-phase state mutation; move `ReportsPanel` and `SugerenciasPanel` filters and KPI counters to server-backed queries / real totals; remove dead `"Historial de Gestión"` UI and misleading toast in `SugerenciasPanel` / `SuggestionDetailModal`; connect scheduled suggestions to `/admin/reuniones` and reconcile agenda models; align `/admin/conocimiento` role visibility and dynamic role badge in `AdminLayout.tsx`; complete `PadronPanel` and `FinanzasPanel` CRUD/summary views; replace internal `<a href>` navigation with TanStack Router `<Link>` (`ADM-01`..`ADM-09`). |
| **Wave 4** | `Wave 4: WCAG 2.1 AA Hardening & Authenticated a11y E2E Suite` | Hoist `<LiveRegionProvider>` to `RootLayout.tsx`; add keyboard/screen-reader support to `ElevationProfileChart.tsx` (`<svg>`) and `MapSearchBox.tsx` (`combobox`/`listbox`); fix missing labels and broken ARIA references in `SugerenciasFilters.tsx`, `ReportDetailModal.tsx`, and `coordinates.tsx`; fix button semantics and dark-mode contrast in `MapPanelShell.tsx`, `ProximaReunionSection.tsx`, and `radioGroup.tsx`; replace red-yellow-green `slopeColor.ts` ramp with a colorblind-safe Okabe-Ito/Viridis-aligned ramp + legend; authenticate `tests/accessibility/a11y.spec.ts` to audit `/perfil`, `/admin/*`, `/participacion?tab=sugerencias`, and open map panels (`A11Y-01`..`A11Y-07`). |

### Out of Scope / NON-goals

- Backend database schema migrations (Alembic) or PostGIS table alterations.
- New Google Earth Engine (GEE) processing algorithms or new raster generation pipelines.
- Unrequested feature additions outside the remediation of the 29 audit findings (`TimeCompareBar`, `MAP-01`..`MAP-08`, `CIT-01`..`CIT-05`, `ADM-01`..`ADM-09`, `A11Y-01`..`A11Y-07`).
- Synthesizing fake design bed elevation (`solera_m`) or fake paired surveys in production when backend data does not provide them (instead, UI controls gracefully hide when data is absent).

## Capabilities

### Modified & Consolidated Capabilities

- `map-viewport-layout-and-controls`: Single non-overlapping layout grid for Top-Left and Bottom map chrome; removal of `TimeCompareBar`; unified 3D raster/vector controls and presets; complete measurement toolbar lifecycle (`MAP-01`..`MAP-08`).
- `citizen-field-geometry-and-forms`: Touch-compatible geometry editing without click race conditions, conditional spatial inputs, OAuth draft photo guardrails, and unified step/status visual language (`CIT-01`..`CIT-05`).
- `admin-operational-workflows`: Server-accurate filtering and KPIs, render-safe profile editing, truth-aligned suggestion history/meeting scheduling, role-accurate navigation, and complete consorciosta/expense management (`ADM-01`..`ADM-09`).
- `wcag-aa-accessibility-and-e2e`: Application-wide `LiveRegionProvider`, keyboard-navigable SVG charts and comboboxes, valid ARIA relationships, colorblind-safe slope symbology, and authenticated Playwright + `@axe-core/playwright` coverage (`A11Y-01`..`A11Y-07`).

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `consorcio-web/src/components/map2d/` | Modified / Deleted | Delete `TimeCompareBar.tsx`, `PropuestasEtapasFilter.tsx`, `pointAlongLine.ts`; update `MapaMapLibreView.tsx`, `MapUiPanels.tsx`, `MeasurementToolbar.tsx`, `useMeasurement.ts`, `personalMeasurements.ts`, `usePersonalMeasurementsLayer.ts`, `LayerControlsPanel.tsx`, `InfoPanel.tsx`, `ElevationProfileChart.tsx`, `ElevationProfileDock.tsx`, `MapSearchBox.tsx`, `MapActionsPanel.tsx`, `MapPanelShell.tsx`, `slopeColor.ts` |
| `consorcio-web/src/lib/api/` | Deleted / Modified | Delete `timeLayers.ts` and `tests/unit/timeLayers.test.ts`; update admin query hooks/clients where needed |
| `consorcio-web/src/components/terrain/` | Modified | Unify `TerrainViewer3DChrome.tsx`, `TerrainLayerTogglesPanel.tsx`, `TerrainViewer3D.tsx`, `TerrainLegendsPanel.tsx` |
| `consorcio-web/src/components/map/` & `suggestion-form/` & `report-form/` | Modified | Fix `SuggestionGeometryControl.tsx`, `SuggestionGeometrySection.tsx`, `FormularioSugerencia.tsx`, `FormularioReporte.tsx`, `StepHeader.tsx`, `SuggestionStepIndicator.tsx` |
| `consorcio-web/src/components/admin/` & `ProfilePanel.tsx` | Modified | Fix `ProfilePanel.tsx`, `ReportsPanel.tsx`, `ReportDetailModal.tsx`, `SugerenciasPanel.tsx`, `SuggestionDetailModal.tsx`, `SugerenciaGeometryMap.tsx`, `SugerenciasFilters.tsx`, `ProximaReunionSection.tsx`, `AdminLayout.tsx`, `PadronPanel.tsx`, `EditGastoModal.tsx`, `FinanzasSummaryTab.tsx`, `DemPipelinePanel.tsx`, `ReunionesPanel` / `AgendaModal.tsx` |
| `consorcio-web/src/components/RootLayout.tsx` & `ui/accessibility/` | Modified | Hoist `LiveRegionProvider` in `RootLayout.tsx`; fix `liveRegion.tsx`, `coordinates.tsx`, `radioGroup.tsx`, `StatusBadge.tsx`, `UserMenu.tsx`, `HomePage.tsx`, `MapaPage.tsx` |
| `consorcio-web/tests/` | Modified | Update unit tests and authenticate `tests/accessibility/a11y.spec.ts` |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Z-index / viewport reflow regressions when repositioning Top-Left and Bottom panels | Medium | Consolidate floating anchors into deterministic CSS flex/grid docks in `map.module.css` and verify at both desktop (`1280×800`) and mobile (`390×844`) viewports |
| Removing dead props in `MapUiPanels.tsx` / `InfoPanel.tsx` breaks existing unit test mocks | Medium | Update test fixtures in lockstep with prop interface cleanup and run `npx tsc --noEmit` + focused Vitest suites per wave |
| Unifying 3D raster controls (`TerrainLayerTogglesPanel` + `LayerControlsPanel`) alters test IDs expected by 3D tests | Low | Preserve canonical `data-testid` attributes (`active-layer-toggle-*`, `active-layer-opacity-*`) while wiring real `layerFineControl` callbacks |
| Authenticated `a11y.spec.ts` uncovers latent contrast or ARIA violations in `/admin/*` views | High | Execute Wave 4 ARIA/contrast fixes (`A11Y-01`..`A11Y-07`) prior to enabling strict zero-violation assertions on authenticated routes |
| Server-side filtering/KPI counts in `ReportsPanel` and `SugerenciasPanel` require existing query params to be forwarded | Low | Inspect existing FastAPI query params (`status`, `category`, `search`, `page`, `limit`) and pass them directly from the frontend hooks without altering DB schemas |

## Rollback Plan

Each wave is structured as an independent, self-contained set of commits/PRs:
- **Wave 1**: Reverting restores removed dead files and prior CSS positioning without affecting citizen or admin forms.
- **Wave 2**: Reverting restores prior `SuggestionGeometryControl` and citizen form components independently.
- **Wave 3**: Reverting restores prior admin panel components without touching map or citizen flows.
- **Wave 4**: Reverting restores prior accessibility wrappers and `a11y.spec.ts` without breaking runtime logic.

## Acceptance Criteria

- [ ] `TimeCompareBar.tsx`, `timeLayers.ts`, `timeLayers.test.ts`, `PropuestasEtapasFilter.tsx`, and `pointAlongLine.ts` are deleted with zero remaining imports, and `npx tsc --noEmit` passes cleanly.
- [ ] All 8 map findings (`MAP-01`..`MAP-08`) are resolved: measurement undo/save/clear/visibility work on desktop and mobile (including polygons), 3D fine layer controls and presets target the 3D store, unbacked profile toggles are hidden until data exists, only one `ElevationProfileChart` mounts at a time, and Top-Left / Bottom panels never overlap.
- [ ] All 5 citizen findings (`CIT-01`..`CIT-05`) are resolved: `SuggestionGeometryControl` supports touch undo/clear, renders `LineString` vertices, has no point-click race condition, hides the map for administrative suggestions, warns/handles photo persistence across OAuth, and shares unified step headers.
- [ ] All 9 admin findings (`ADM-01`..`ADM-09`) are resolved: `ProfilePanel` allows clearing/editing `nombre`, `ReportsPanel`/`SugerenciasPanel` filters and KPI badges reflect real totals across pages, dead suggestion history is removed, scheduled suggestions link to `Reuniones`, `/admin/conocimiento` nav matches role permissions, `PadronPanel`/`FinanzasPanel` expose full fields, `SugerenciaGeometryMap` uses Esri satellite imagery, `ReportDetailModal` includes map context, internal links use `<Link>`, and `StatusBadge` is consolidated.
- [ ] All 7 accessibility findings (`A11Y-01`..`A11Y-07`) are resolved: `<LiveRegionProvider>` is mounted once in `RootLayout.tsx`, `ElevationProfileChart` and `MapSearchBox` are keyboard-operable, all inputs/modals have valid ARIA labels/targets, `slopeColor.ts` uses a colorblind-safe ramp with legend, and `tests/accessibility/a11y.spec.ts` authenticates and passes with 0 critical/serious Axe violations across `/perfil`, `/admin/*`, `/participacion?tab=sugerencias`, and open map panels.
