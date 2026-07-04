# Tasks: Rediseño UX/UX del mapa

## Overview

**Total Tasks**: 18
**Phases**: 4 (Layout responsive + quick win → Agrupación/búsqueda → Control fino → Verificación)
**Enfoque**: TDD-first. React Compiler activo → NO `useMemo`/`useCallback` manual. Cada fase es un PR independiente y shippeable.

---

## Phase 1: Layout responsive + quick win (la raíz)

- [x] **1.1 Activar cooperativeGestures (RED→GREEN)**
  - RED: `useMapInitialization.test.ts` — assert que las opciones del `Map` incluyen `cooperativeGestures: true`.
  - GREEN: agregar `cooperativeGestures: true` en `new maplibregl.Map({...})` de `map2d/useMapInitialization.ts`.
  - **AC**: test verde; rueda sin modificador no zoomea.
  - **Files**: `consorcio-web/src/components/map2d/useMapInitialization.ts`, `useMapInitialization.test.ts`

- [x] **1.2 Crear MapWorkspace (RED→GREEN)**
  - RED: `MapWorkspace.test.tsx` — con `matchMedia` desktop renderiza sidebar+canvas; con mobile renderiza canvas + Drawer cerrado y botón ☰.
  - GREEN: crear `map2d/MapWorkspace.tsx` con `useMediaQuery('(min-width: 48em)')`, `Drawer size="100%"` (patrón `Header.tsx:158-198`), sidebar colapsable con botón.
  - **AC**: ambos modos renderizan el mismo `controls` prop.
  - **Files**: `consorcio-web/src/components/map2d/MapWorkspace.tsx`, `MapWorkspace.test.tsx`

- [x] **1.3 Grid CSS sidebar↔canvas**
  - Reescribir `.mapWorkspace` a grid `sidebar | canvas`; agregar estado colapsado (columna estrecha); retirar `.mapBottomBar` 2-col.
  - **AC**: al colapsar, el canvas gana ancho; mobile 1-col.
  - **Files**: `consorcio-web/src/styles/components/map.module.css`
  - **Dependencies**: 1.2

- [x] **1.4 Cablear MapWorkspace en MapaMapLibre**
  - Reemplazar el bloque `.mapBottomBar` (`MapaMapLibre.tsx:781-804`) por `<MapWorkspace canvas={...} controls={<LayerControlsPanel/> + <LeyendaPanel/>} activeLayerCount={...}/>`. Añadir botón ☰/colapso.
  - **AC**: controles ya no viven debajo del mapa; mapa + controles en una sola pantalla sin scroll extra.
  - **Files**: `consorcio-web/src/components/MapaMapLibre.tsx`
  - **Dependencies**: 1.2, 1.3

- [x] **1.5 Ajustar MapaPage al nuevo layout**
  - Revisar altura/contención (`clamp(...)`) para que el workspace no fuerce scroll de página.
  - **AC**: sin doble scroll; mapa+controles caben en viewport típico.
  - **Files**: `consorcio-web/src/components/MapaPage.tsx` (verificado — sin cambio de código necesario: al mover los controles al sidebar el footprint vertical del workspace se redujo de 3 filas apiladas (topBar/canvas/bottomBar) a topBar + [sidebar|canvas]; el clamp `calc(100dvh - 250px)` sigue vigente y ahora sobra-holgado, elimina el doble scroll. El wrapper `Paper overflow:hidden` de MapaPage contiene correctamente el grid.)
  - **Dependencies**: 1.4

- [x] **1.6 Hint de zoom**
  - Verificar/estilar el hint de cooperativeGestures (o uno propio) al intentar wheel sin modificador.
  - **AC**: hint visible y legible en light/dark.
  - **Files**: `consorcio-web/src/components/MapaMapLibre.tsx` / styles
  - **Dependencies**: 1.1

---

## Phase 2: Agrupación + búsqueda de capas (Dolor 1)

- [x] **2.1 Agregar category a LayerItem (RED→GREEN)**
  - RED: `map2dDerived.test.ts` — assert que TODO item de `buildVectorLayerItems` tiene `category` válida.
  - GREEN: const-object `LAYER_CATEGORY` + campo `category` por capa en `buildVectorLayerItems` (`map2dDerived.ts:216-266`).
  - **AC**: ninguna capa sin familia; tipo derivado del const-object (skill typescript).
  - **Files**: `consorcio-web/src/components/map2d/map2dDerived.ts`, `map2dDerived.test.ts`

- [x] **2.2 Accordion por familia en LayerControlsPanel (RED→GREEN)**
  - RED: `LayerControlsPanel.test.tsx` — capas renderizan agrupadas por category en `Accordion`.
  - GREEN: reemplazar lista plana por `Accordion` de Mantine, un item por familia, con icono por grupo.
  - **AC**: 6 familias; Canales conserva su sub-sección master + per-canal.
  - **Files**: `consorcio-web/src/components/map2d/LayerControlsPanel.tsx`, test
  - **Dependencies**: 2.1

- [x] **2.3 Buscador de capas (RED→GREEN)**
  - RED: test — escribir texto filtra por nombre (case-insensitive) y oculta grupos sin match.
  - GREEN: `TextInput` de búsqueda que filtra `layerItems` por `label`.
  - **AC**: filtro reactivo sin memoization manual.
  - **Files**: `consorcio-web/src/components/map2d/LayerControlsPanel.tsx`, test
  - **Dependencies**: 2.2

- [x] **2.4 Indicador "N capas activas" (RED→GREEN)**
  - RED: test — Badge muestra el conteo de `vectorVisibility` en true.
  - GREEN: derivar conteo y pasarlo a `MapWorkspace`/panel como `Badge`.
  - **AC**: se actualiza al togglear.
  - **Files**: `LayerControlsPanel.tsx`, `MapWorkspace.tsx`
  - **Dependencies**: 2.2

- [x] **2.5 Verificar paridad 2D/3D**
  - Confirmar que `TerrainLayerTogglesPanel` (3D) muestra las mismas familias/nombres para capas compartidas; ajustar naming si divergió.
  - **AC**: test/afirmación de paridad de familias.
  - **Files**: `consorcio-web/src/components/terrain/*TogglesPanel*`, test
  - **Dependencies**: 2.1

---

## Phase 3: Control fino por capa activa (Dolor 2, estructural)

- [x] **3.1 Slots opacidad/orden en el store + migración (RED→GREEN)**
  - RED: `mapLayerSyncStore.test.ts` — estado persistido de la version previa conserva visibilidad tras el bump; nuevos campos con defaults.
  - GREEN: agregar `opacityByLayer?`/`orderByLayer?` (opcionales) a los slices 2d/3d; bump `version` + `migrate`.
  - **AC**: sin pérdida de visibilidad; slots aditivos.
  - **Files**: `consorcio-web/src/stores/mapLayerSyncStore.ts`, test

- [x] **3.2 Aplicar opacidad en useMapLayerEffects (RED→GREEN)**
  - RED: `useMapLayerEffects.test.ts` — con `opacityByLayer` set, la capa usa esa opacidad; sin set, opacidad default idéntica a hoy.
  - GREEN: leer el slot y aplicar en `setPaintProperty` sin tocar los z-orders/opacidades hardcodeadas cuando no hay override.
  - **AC**: default NO cambia (regression guard).
  - **Files**: `consorcio-web/src/components/map2d/useMapLayerEffects.ts`, test
  - **Dependencies**: 3.1

- [x] **3.3 Control de opacidad por capa en la UI (RED→GREEN)**
  - RED: test — `Slider` por capa activa dispara `onOpacityChange(layerId, value)`.
  - GREEN: `Slider` de opacidad en cada capa activa dentro del Accordion.
  - **AC**: mover slider re-renderiza solo esa capa.
  - **Files**: `LayerControlsPanel.tsx`, test
  - **Dependencies**: 3.2

- [x] **3.4 Agrupar props de control fino en MapUiPanels**
  - Introducir un prop objeto (`layerFineControl: { opacityByLayer, onOpacityChange, activeCount }`) en vez de props sueltos; no expandir la superficie de ~60 props.
  - **AC**: no se agregan props planos nuevos; tipos vía interface dedicada.
  - **Files**: `consorcio-web/src/components/MapUiPanels.tsx`
  - **Dependencies**: 3.3

- [x] **3.5 Reorden por capa** (APROBADA por el usuario 2026-07-04)
  - Drag-reorder que escribe `orderByLayer` y `useMapLayerEffects` respeta el orden. Snapshot visual antes/después.
  - **AC**: z-order default sin cambios cuando no hay override.
  - **Files**: `LayerControlsPanel.tsx`, `useMapLayerEffects.ts`, store
  - **Dependencies**: 3.2

---

## Phase 4: Verificación

- [ ] **4.1 E2E responsive + scroll-trap (Playwright)**
  - `mapa-rediseno.spec.ts`: (a) desktop, colapsar ensancha el canvas; (b) mobile, ☰ abre Drawer full-screen; (c) wheel sobre el mapa scrollea la página.
  - **AC**: los 3 escenarios verdes.
  - **Files**: `consorcio-web/tests/e2e/mapa-rediseno.spec.ts`
  - **Dependencies**: 1.x, 2.x

- [ ] **4.2 Regression: lazy-load geojson + dep-arrays**
  - Verificar que `useSoilMap`/`useCatastroMap` (`enabled`) y los effects de carga no se regresionaron; no hay `useMemo`/`useCallback` manual nuevo.
  - **AC**: sin cargas eager nuevas; grep de memoization manual limpio.
  - **Files**: revisión de `map2d/*` hooks
  - **Dependencies**: 3.x

- [ ] **4.3 Validación manual + typecheck**
  - `npm run typecheck` + smoke manual: sidebar/Drawer en desktop y mobile reales, opacidad, buscador, paridad 2D/3D.
  - **AC**: typecheck verde; UX validada en ambos viewports.
  - **Dependencies**: 4.1, 4.2
