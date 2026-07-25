# Design: Migrar capas 2D a la vista 3D

## Technical Approach

La migración se hará en capas, no como un "port" completo de `MapaLeaflet`.

La arquitectura objetivo de la vista 3D será:

1. **Relieve estable**
   - `terrain-rgb` como fuente DEM única
   - `setTerrain()` solo para exageración y relieve

2. **Overlay raster activo**
   - un source/layer raster principal drapeado sobre el relieve
   - URL derivada de `buildTileUrl()`
   - opacidad configurable

3. **Overlays vectoriales MapLibre**
   - sources GeoJSON separados por familia
   - layers `fill`, `line`, `circle`, `symbol` según tipo de geometría

4. **Panel 3D de capas**
   - estado local o hook dedicado para visibilidad
   - reuso de labels/leyendas existentes siempre que sea posible

## Architecture Decisions

### Decision: Migración por familias de capa
**Choice**: Migrar primero raster overlays, luego vectores.

**Rationale**: Los rasters ya están servidos como tiles y encajan naturalmente con MapLibre 3D; los vectores requieren más trabajo de estilo, sources y UX.

### Decision: Mantener un único raster overlay activo inicialmente
**Choice**: En la primera etapa, soportar un raster temático activo a la vez sobre el relieve.

**Alternatives Considered**:
- múltiples rasters simultáneos con blend/opacidad independiente
- stack libre de rasters como en 2D

**Rationale**: Reduce complejidad, evita combinaciones visuales poco legibles y simplifica la UX inicial.

### Decision: Reutilizar hooks 2D existentes como data providers
**Choice**: `TerrainViewer3D` consumirá los mismos hooks de datos que la vista 2D, en vez de introducir fetches paralelos nuevos.

**Rationale**: Mantiene contratos existentes y evita duplicar lógica de carga/transformación.

### Decision: Separar UI de capas 3D del mapa base
**Choice**: crear un panel de capas/leyenda 3D propio en lugar de intentar replicar `LayersControl` de Leaflet.

**Rationale**: MapLibre no tiene equivalente directo; un panel React controlado será más estable y extensible.

## Proposed Frontend Structure

```text
consorcio-web/src/components/terrain/
├── TerrainViewer3D.tsx            # contenedor principal MapLibre
├── TerrainLayerPanel.tsx          # toggles / selector overlay / opacidad
├── terrainLayerConfig.ts          # matriz de capas soportadas en 3D
├── useTerrain3DLayers.ts          # hook para materializar sources/layers MapLibre
└── useTerrainRasterOverlay.ts     # hook para raster activo + hide_classes/hide_ranges
```

## Data Model Proposal

### 3D raster overlay descriptor

```ts
interface TerrainRasterOverlay {
  id: string;
  layerId: string;
  tipo: string;
  nombre: string;
  tileUrl: string;
  supportsClassFiltering: boolean;
  supportsRangeFiltering: boolean;
}
```

### 3D vector overlay descriptor

```ts
interface TerrainVectorOverlay {
  id: string;
  sourceId: string;
  label: string;
  visible: boolean;
  kind: 'fill' | 'line' | 'circle' | 'symbol';
}
```

## Implementation Phases

### Phase A: Raster parity
- mover selección de `textureLayerId` a un selector real de overlay 3D
- reusar `useGeoLayers` + `buildTileUrl`
- soportar opacidad y leyenda

### Phase B: Vector parity básica
- agregar sources/layers GeoJSON para zona, cuencas, basins
- agregar roads/hidrografía/capas públicas
- agregar markers de infraestructura

### Phase C: UX y convergencia
- agrupar overlays por familia
- documentar qué queda fuera de 3D
- preparar popups/tooltips y futura interacción avanzada

## Testability Strategy

- Mantener funciones puras para materializar config de layers MapLibre.
- Validar con tests unitarios:
  - mapping de `GeoLayer -> raster overlay`
  - mapping de GeoJSON datasets -> MapLibre source/layer descriptors
  - estado del panel (selección overlay, visibilidad, opacidad)
- Validar manualmente que no reintroduzca `dem dimension mismatch`.

## CI / Validation Strategy

- `tsc --noEmit -p consorcio-web/tsconfig.json`
- tests Vitest para helpers/hooks nuevos
- smoke manual en navegador para:
  - cambiar raster overlay
  - activar/desactivar capas vectoriales
  - mover/rotar/tilt del mapa sin errores MapLibre
