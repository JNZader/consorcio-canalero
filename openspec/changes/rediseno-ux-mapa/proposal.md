# Proposal: Rediseño UX/UX del mapa (sidebar colapsable, responsive real)

## Intent

El mapa 2D (MapaMapLibre) es hoy incómodo en desktop **y** en mobile por igual. Tres dolores concretos, verificados en código:

1. **Activación de capas confusa** — `LayerControlsPanel.tsx` es una lista PLANA de ~15 checkboxes + sección Canales aparte, sin categorías, sin buscador, sin iconos. Con ~20 capas reales (`map2dDerived.ts:216-266`) el usuario no encuentra lo que busca.
2. **Comportamiento de capas activas pobre** — no hay opacidad por capa, ni reorden, ni un indicador "N capas activas". El único control fino vive disperso (`RasterLegend`, filtro de etapas en `LeyendaPanel`).
3. **Layout/scroll rotos (la RAÍZ)** — la página apila verticalmente (`MapaPage.tsx`), el control de capas vive DEBAJO del mapa (`.mapBottomBar`, `map.module.css:24-38`), y el mapa se crea SIN `cooperativeGestures` (`useMapInitialization.ts`) → la rueda/touch siempre zoomea y captura el scroll de la página.

Objetivo: rediseñar la UI/UX completa del mapa con un **único sistema responsive** (sidebar colapsable en desktop, Drawer full-screen en mobile), resolviendo los 3 dolores en fases.

## Scope

### In Scope

**Fase 1 — Layout responsive + quick win (la raíz):**
- Activar `cooperativeGestures: true` en la creación del mapa (`useMapInitialization.ts`) + hint de zoom.
- Reemplazar el apilado vertical por **sidebar colapsable** de controles a la IZQUIERDA del mapa (desktop) y **Drawer full-screen ☰** (mobile), reutilizando el patrón de `Header.tsx:158-198` (`Drawer` + `useMediaQuery`).
- Al colapsar el sidebar, el mapa recupera ancho. Migrar el contenido de `.mapBottomBar` (LayerControls + Leyenda) al sidebar/Drawer.

**Fase 2 — Agrupación + búsqueda de capas (Dolor 1):**
- Re-agrupar las capas por familia natural (Base / Hidrografía / Territorio / Pilar Verde / Canales / Análisis-rasters) con `Accordion` de Mantine + buscador + iconos, tocando solo `buildVectorLayerItems` (`map2dDerived.ts`) + `LayerControlsPanel.tsx`.
- Mantener paridad con el panel de toggles 3D (`TerrainLayerTogglesPanel`).

**Fase 3 — Control fino por capa activa (Dolor 2, estructural):**
- Opacidad por capa + indicador "N capas activas" + (si el riesgo lo permite) reorden. Toca `useMapLayerEffects.ts`, nuevos slots en `mapLayerSyncStore.ts` (con bump de versión de persist) y los z-orders hoy hardcodeados.

### Out of Scope
- Rediseño del terreno 3D más allá de mantener paridad de agrupación de toggles.
- Cambios en el pipeline de datos geo / lazy-load de geojson (NO regresionar).
- Nuevas capas o analítica nueva.
- Cambios de auth/roles.

## Approach

Fases incrementales, cada una entregable y shippeable sola. Fase 1 es un quick win de alto impacto (layout + un one-liner). Fase 2 es de bajo riesgo (presentacional + derivación). Fase 3 es la más riesgosa (imperativo + store + z-order) y va última. Un solo componente de layout responsive (`MapWorkspace`) decide sidebar vs Drawer por breakpoint.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `consorcio-web/src/components/MapaMapLibre.tsx` | Modified | Reemplaza `.mapBottomBar` por `MapWorkspace` (sidebar/Drawer); pasa controles al sidebar |
| `consorcio-web/src/components/map2d/MapWorkspace.tsx` | New | Layout responsive: sidebar colapsable (desktop) / Drawer (mobile) |
| `consorcio-web/src/components/map2d/useMapInitialization.ts` | Modified | `cooperativeGestures: true` |
| `consorcio-web/src/components/map2d/LayerControlsPanel.tsx` | Modified | Accordion por familia + buscador + iconos + conteo de activas |
| `consorcio-web/src/components/map2d/map2dDerived.ts` | Modified | `buildVectorLayerItems`: agregar `category` a cada `LayerItem` |
| `consorcio-web/src/components/MapUiPanels.tsx` | Modified | Modo embebido/sidebar; agrupar props relacionadas para no empeorar la superficie (~60 props) |
| `consorcio-web/src/components/map2d/useMapLayerEffects.ts` | Modified (F3) | Opacidad por capa aplicada al render |
| `consorcio-web/src/stores/mapLayerSyncStore.ts` | Modified (F3) | Slots de opacidad/orden por capa + bump de version del persist |
| `consorcio-web/src/styles/components/map.module.css` | Modified | Grid de workspace sidebar↔canvas; elimina `.mapBottomBar` 2-col |
| `consorcio-web/src/pages/MapaPage.tsx` | Modified | Ajuste de altura/contención con el nuevo layout |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `cooperativeGestures` moleste a usuarios acostumbrados a scroll-zoom directo | Low | Hint claro ("usá Ctrl+scroll / dos dedos"); es el default de MapLibre para embeds |
| Romper paridad 2D/3D del panel de toggles | Med | Fase 2 toca solo derivación 2D; test de paridad explícito |
| Fase 3 rompe z-order / opacidades hardcodeadas | High | Fase aislada, última; snapshot visual antes/después; test de que el orden default no cambia |
| Bump de version del persist store invalida estado guardado del usuario | Med | Migración de persist que preserva visibilidad; defaults seguros |
| Introducir `useMemo`/`useCallback` manual (React Compiler activo) | Low | Prohibido salvo imprescindible; review lo verifica |
| Regresionar lazy-load geojson / dep-arrays optimizados | Med | No tocar `enabled` de useSoilMap/useCatastroMap ni los effects de carga |

## Rollback Plan

1. Fase 1 detrás de layout nuevo aislado en `MapWorkspace`: revertir el import en `MapaMapLibre.tsx` restaura `.mapBottomBar`.
2. `cooperativeGestures` es un one-liner reversible.
3. Fase 3 (store) es la única con migración: rollback = revertir el bump de version y los slots nuevos; visibilidad de capas se preserva porque los slots son aditivos/opcionales.
4. Cada fase es un commit/PR independiente; se puede parar después de F1 o F2 sin dejar el mapa roto.

## Dependencies

- Mantine 8 (`Drawer`, `Accordion`, `Slider`, `useMediaQuery`) — ya en uso.
- Patrón Drawer mobile de `Header.tsx` como referencia.
- Infra de modo flotante ya presente (`showEmbeddedMapControls`, `MapUiPanels.tsx:249`), hoy apagada.

## Success Criteria

- [ ] En desktop, los controles viven a la izquierda del mapa y el sidebar colapsa a un icono; al colapsar, el mapa gana ancho.
- [ ] En mobile, un botón ☰ abre un Drawer full-screen con todos los controles.
- [ ] La rueda del mouse sobre el mapa YA NO captura el scroll de la página (cooperativeGestures) y hay un hint visible.
- [ ] Las capas están agrupadas por familia, con buscador que filtra por nombre y un conteo de "N activas".
- [ ] Cada capa activa permite ajustar opacidad; el default de z-order/opacidad no cambia respecto de hoy.
- [ ] La paridad de toggles 2D/3D se mantiene.
- [ ] No hay `useMemo`/`useCallback` manual nuevo; no se regresiona el lazy-load de geojson.

---

**Change**: rediseno-ux-mapa
**Location**: openspec/changes/rediseno-ux-mapa/proposal.md
**Status**: Ready for Review
**Next Step**: Specification (`/sdd-continue rediseno-ux-mapa`)
