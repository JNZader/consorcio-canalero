# Delta Specification: Rediseño UX/UX del mapa

## Purpose

El mapa 2D MUST ofrecer un modelo de interacción **responsive único** (sidebar colapsable en desktop, Drawer full-screen en mobile), MUST dejar de capturar el scroll de la página, y SHOULD permitir descubrir, agrupar y controlar finamente las capas sin scrollear más allá del mapa.

## Requirements & Scenarios

### Requirement: Responsive controls shell (sidebar ↔ drawer)
El mapa MUST presentar sus controles en un contenedor responsive único: un **sidebar colapsable** a la izquierda del canvas en viewports desktop, y un **Drawer full-screen** disparado por un botón ☰ en viewports mobile. El breakpoint MUST derivarse con `useMediaQuery` (Mantine), NO con estilos desktop parcheados.

#### Scenario: Desktop — colapsar el sidebar devuelve ancho al mapa
- GIVEN el usuario está en un viewport ≥ `sm` (desktop)
- WHEN colapsa el sidebar de controles con el botón de colapso
- THEN el sidebar se reduce a un icono/barra estrecha
- AND el canvas del mapa se re-dimensiona ocupando el ancho liberado

#### Scenario: Mobile — el botón ☰ abre un Drawer full-screen
- GIVEN el usuario está en un viewport < `sm` (mobile)
- WHEN toca el botón ☰
- THEN se abre un `Drawer` a `size="100%"` con todos los controles de capas y leyenda
- AND al cerrarlo el mapa queda a pantalla completa sin controles superpuestos

#### Scenario: Un solo árbol de controles alimenta ambos modos
- GIVEN los mismos datos de capas/leyenda
- WHEN se renderiza en desktop (sidebar) o mobile (Drawer)
- THEN ambos modos muestran el MISMO conjunto de controles y estado
- AND no existe duplicación divergente de la lista de capas

### Requirement: Cooperative gestures y hint de zoom
El mapa MUST crearse con `cooperativeGestures: true` para que la rueda/gesto de un dedo NO capture el scroll de la página. La UI SHOULD mostrar un hint de cómo hacer zoom.

#### Scenario: Rueda del mouse sobre el mapa no roba el scroll de la página
- GIVEN el mapa está embebido en una página con scroll
- WHEN el usuario hace scroll con la rueda sobre el canvas SIN modificador
- THEN la página scrollea normalmente y el mapa NO zoomea
- AND con Ctrl+rueda (o dos dedos en touch) el mapa SÍ zoomea

#### Scenario: Hint visible de cómo hacer zoom
- GIVEN cooperativeGestures activo
- WHEN el usuario intenta zoomear con la rueda sin modificador
- THEN aparece el hint nativo/propio indicando el gesto correcto

### Requirement: Layer grouping and search
El panel de capas MUST agrupar las capas por familia (Base, Hidrografía, Territorio, Pilar Verde, Canales/Pilar Azul, Análisis-rasters) usando `Accordion`, y MUST ofrecer un buscador que filtre por nombre de capa. Cada grupo SHOULD tener icono.

#### Scenario: Capas agrupadas por familia
- GIVEN existen ~20 capas vectoriales y rasters
- WHEN el usuario abre el panel de capas
- THEN cada capa aparece bajo su familia en un item de Accordion
- AND ninguna capa queda sin familia asignada

#### Scenario: Buscar una capa por nombre
- GIVEN el panel de capas está abierto
- WHEN el usuario escribe texto en el buscador
- THEN solo se muestran las capas cuyo nombre coincide (case-insensitive)
- AND los grupos sin coincidencias se ocultan o colapsan

### Requirement: Active-layer count and fine control
El panel MUST mostrar un indicador de "N capas activas". Cada capa activa MUST permitir ajustar su opacidad. El reorden por capa MAY ofrecerse si no rompe el z-order default.

#### Scenario: Contador de capas activas
- GIVEN el usuario activa/desactiva capas
- WHEN cambia la cantidad de capas visibles
- THEN el indicador "N activas" se actualiza en tiempo real

#### Scenario: Ajustar opacidad de una capa activa
- GIVEN una capa vectorial/raster está activa
- WHEN el usuario mueve el control de opacidad de esa capa
- THEN la capa se re-renderiza con la opacidad elegida
- AND las demás capas no cambian su opacidad

#### Scenario: El z-order/opacidad default no cambia
- GIVEN el usuario NO toca opacidad ni orden
- WHEN se cargan las capas
- THEN el z-order y la opacidad iniciales son idénticos a los previos a este cambio

### Requirement: 2D/3D toggle parity
La agrupación y naming de toggles de capas MUST mantenerse coherente entre la vista 2D (`LayerControlsPanel`) y la 3D (`TerrainLayerTogglesPanel`).

#### Scenario: Toggles equivalentes en 2D y 3D
- GIVEN el usuario alterna entre 2D y 3D
- WHEN abre el panel de capas en cada vista
- THEN encuentra las mismas familias y nombres para las capas compartidas

### Requirement: Persist store backward compatibility
Al agregar slots de opacidad/orden por capa, `mapLayerSyncStore` MUST bumpear la version del persist y MUST migrar el estado guardado sin perder la visibilidad previa del usuario.

#### Scenario: Estado persistido previo sigue válido
- GIVEN un usuario con visibilidad de capas guardada bajo la version anterior del persist
- WHEN carga la app tras el bump de version
- THEN su visibilidad de capas se conserva
- AND los nuevos campos (opacidad/orden) toman defaults seguros sin romper el render

## API / Contract Notes

- `LayerItem` (en `map2dDerived.ts`) SHOULD extenderse con un campo `category` (const-object typado, no union suelto) para agrupar.
- Los slots nuevos del store (opacidad/orden por `layerId`) MUST ser opcionales/aditivos para preservar compat.
- No se agregan endpoints backend: este cambio es 100% frontend.

## Test-Guard Inventory

| Method / Unit | Test file | Test name | Type |
|---------------|-----------|-----------|------|
| `MapWorkspace` (sidebar↔drawer por breakpoint) | `MapWorkspace.test.tsx` | renders sidebar on desktop / drawer on mobile | contract |
| `useMapInitialization` (cooperativeGestures) | `useMapInitialization.test.ts` | map created with cooperativeGestures=true | regression |
| `buildVectorLayerItems` (category asignada) | `map2dDerived.test.ts` | every layer item has a category | contract |
| `LayerControlsPanel` (búsqueda + grupos) | `LayerControlsPanel.test.tsx` | filters by name / groups by family / active count | contract |
| opacidad por capa aplicada al render | `useMapLayerEffects.test.ts` | opacity slot applied; default unchanged | regression |
| persist migration (version bump) | `mapLayerSyncStore.test.ts` | old persisted visibility preserved after bump | regression |
| responsive E2E (sidebar/drawer + no scroll-trap) | `mapa-rediseno.spec.ts` (Playwright) | desktop collapse widens map / mobile drawer / wheel scrolls page | e2e |
