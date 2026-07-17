# Design: Rediseño UX/UX del mapa

## Technical Approach

Introducir un componente de layout responsive **`MapWorkspace`** que envuelve el canvas de MapLibre y aloja los controles en un contenedor único que decide su forma según el viewport: **sidebar colapsable** (desktop) o **Drawer full-screen** (mobile). El contenido de controles (LayerControls + Leyenda) que hoy vive en `.mapBottomBar` (`MapaMapLibre.tsx:781-804`, DEBAJO del mapa) se mueve dentro de este contenedor, eliminando el scroll-trapping estructural. En paralelo, activar `cooperativeGestures` (quick win de 1 línea) y, por fases, mejorar la agrupación de capas (F2) y el control fino por capa (F3, el más riesgoso).

React Compiler está activo → **NO** se agregan `useMemo`/`useCallback` manuales. Mantine 8 provee todo (`Drawer`, `Accordion`, `Slider`, `useMediaQuery`, `ScrollArea`).

## Architecture Decisions

### Decision: `MapWorkspace` como único shell responsive
**Choice**: Un componente nuevo `map2d/MapWorkspace.tsx` que recibe `canvas` (el mapa) y `controls` (el árbol de controles) como children/props, y con `useMediaQuery('(min-width: 48em)')` renderiza sidebar+canvas en grid (desktop) o canvas + Drawer (mobile).
**Alternatives considered**: (a) dos árboles de controles separados para desktop/mobile; (b) CSS-only con media queries.
**Rationale**: Un solo árbol de controles evita divergencia (Spec: "un solo árbol alimenta ambos modos"). `useMediaQuery` es el patrón ya usado en `Header.tsx:158-198`. CSS-only no puede montar/desmontar un `Drawer` de Mantine.

### Decision: cooperativeGestures como primera tarea aislada
**Choice**: `cooperativeGestures: true` en el objeto de opciones de `new maplibregl.Map({...})` dentro de `useMapInitialization.ts`.
**Alternatives considered**: handler manual de wheel con Ctrl.
**Rationale**: Es el mecanismo nativo de MapLibre con hint incluido; reversible en 1 línea; beneficia desktop y mobile por igual.

### Decision: agrupar tocando solo la derivación + el presentacional
**Choice**: Agregar `category` a cada `LayerItem` en `buildVectorLayerItems` (`map2dDerived.ts:216-266`) y consumirla en `LayerControlsPanel` con `Accordion`. El store (`mapLayerSyncStore`) NO se toca en F2.
**Alternatives considered**: mover la agrupación al store.
**Rationale**: La familia es presentación derivada del catálogo, no estado persistente. Mantiene F2 de bajo riesgo y preserva la paridad 2D/3D (la derivación 3D consume el mismo catálogo).

### Decision: control fino (opacidad/orden) al final, aislado
**Choice**: F3 agrega slots `opacityByLayer` / `orderByLayer` (opcionales) al store con **bump de version del persist** + migración, y `useMapLayerEffects.ts` los aplica al `setPaintProperty`/orden de MapLibre.
**Alternatives considered**: hacerlo junto con F1.
**Rationale**: `useMapLayerEffects` es imperativo y grande, los z-orders están hardcodeados (`pilarVerdeLayers.ts`, `mapRasterOverlayHelpers.ts`) y las opacidades también (`mapLayerEffectHelpers.ts:62-314`). Es el eje con mayor blast radius → última fase, snapshot antes/después.

### Decision: contener los ~60 props de `MapUiPanels` sin empeorarlos
**Choice**: NO agregar props sueltos nuevos. Para F3, agrupar el control fino bajo un único prop objeto (ej. `layerFineControl: { opacityByLayer, onOpacityChange, activeCount }`) y, donde toque, empezar a agrupar familias de props relacionadas (export*, approval*, suggested*) en objetos. `MapWorkspace` recibe el JSX ya compuesto, no re-expande la superficie.
**Alternatives considered**: seguir agregando props planos.
**Rationale**: `MapUiPanelsProps` ya tiene ~60 campos (`MapUiPanels.tsx:48-142`); cada prop suelto nuevo empeora la fricción. Objetos agrupados acotan el crecimiento sin un refactor grande arriesgado en este change.

## Data Flow

```
MapaMapLibre (owner de estado: vectorVisibility, layerItems, opacity…)
      │  compone
      ▼
  MapWorkspace  ──useMediaQuery──►  desktop: [Sidebar colapsable | Canvas]
      │                             mobile:  [Canvas] + Drawer(☰)
      │  (controls JSX)                          │
      ▼                                          ▼
  LayerControlsPanel (Accordion + buscador + opacidad + conteo)
      │  onLayerVisibilityChange / onOpacityChange
      ▼
  mapLayerSyncStore (zustand+persist, slices 2d/3d)  ──►  useMapLayerEffects (imperativo → MapLibre)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `map2d/MapWorkspace.tsx` | Create | Shell responsive sidebar↔drawer con `useMediaQuery` |
| `map2d/useMapInitialization.ts` | Modify | `cooperativeGestures: true` |
| `MapaMapLibre.tsx` | Modify | Reemplaza bloque `.mapBottomBar` (781-804) por `<MapWorkspace canvas controls>`; botón ☰/colapso |
| `map2d/LayerControlsPanel.tsx` | Modify | Accordion por `category` + `TextInput` buscador + `Slider` opacidad + Badge conteo |
| `map2d/map2dDerived.ts` | Modify | `LayerItem.category` en `buildVectorLayerItems`; const-object `LAYER_CATEGORY` |
| `MapUiPanels.tsx` | Modify | Modo sidebar; agrupar props de control fino en objeto (F3) |
| `map2d/useMapLayerEffects.ts` | Modify (F3) | Aplicar opacidad por capa sin alterar defaults |
| `stores/mapLayerSyncStore.ts` | Modify (F3) | Slots `opacityByLayer`/`orderByLayer` + bump version + migrate |
| `styles/components/map.module.css` | Modify | Grid `sidebar | canvas`; retirar `.mapBottomBar` 2-col |
| `pages/MapaPage.tsx` | Modify | Altura/contención con el nuevo layout |

## Interfaces / Contracts

```ts
// map2dDerived.ts — const-object, no union suelto (skill typescript)
const LAYER_CATEGORY = {
  BASE: 'base', HIDROGRAFIA: 'hidrografia', TERRITORIO: 'territorio',
  PILAR_VERDE: 'pilar_verde', CANALES: 'canales', ANALISIS: 'analisis',
} as const;
type LayerCategory = (typeof LAYER_CATEGORY)[keyof typeof LAYER_CATEGORY];

interface LayerItem { id: string; label: string; show: boolean; category: LayerCategory; }

// mapLayerSyncStore.ts (F3) — aditivo/opcional
interface MapLayerSlice { /* …existing… */ opacityByLayer?: Record<string, number>; orderByLayer?: string[]; }

// MapWorkspace.tsx
interface MapWorkspaceProps { canvas: ReactNode; controls: ReactNode; activeLayerCount: number; }
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `buildVectorLayerItems` asigna category a TODAS las capas | Vitest, assert sobre el array |
| Unit | `useMapInitialization` pasa `cooperativeGestures:true` | Vitest, spy sobre opciones del Map |
| Component | `LayerControlsPanel`: buscador filtra, grupos, conteo activas | Vitest + Testing Library |
| Component | `MapWorkspace`: sidebar en desktop / Drawer en mobile | Vitest + `matchMedia` mock |
| Unit | persist migrate preserva visibilidad tras bump | Vitest sobre el store |
| Regression | opacidad default sin cambios | Vitest snapshot de paint props |
| E2E | colapso ensancha mapa / Drawer mobile / wheel scrollea página | Playwright (`mapa-rediseno.spec.ts`) |

## Migration / Rollout

- F1 y F2 no requieren migración de datos. F3 sí: bump de `version` del persist de `mapLayerSyncStore` con función `migrate` que conserva `visibility` y agrega defaults de opacidad/orden. Cada fase es un PR independiente y shippeable; se puede detener tras F1 o F2.

## Open Questions

- [x] **F3 reorden por capa**: **RESUELTO (user, 2026-07-04)** — SÍ se incluye. Task 3.5 desbloqueada (queda en Fase 3, no se implementa en Fase 1). Sigue siendo aditiva: `orderByLayer` opcional, z-order default sin cambios cuando no hay override + snapshot antes/después.
- [x] Breakpoint exacto: **RESUELTO (user, 2026-07-04)** — `sm` = **48em**. `useMediaQuery('(min-width: 48em)')` para consistencia con `hiddenFrom="sm"` de Header.
- [x] ¿El sidebar colapsado recuerda su estado (persist)? **RESUELTO (user, 2026-07-04)** — SÍ, se persiste la preferencia de colapso (zustand+persist, patrón `mapLayerSyncStore`).
