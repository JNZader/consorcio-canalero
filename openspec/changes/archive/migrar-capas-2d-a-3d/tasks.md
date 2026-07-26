# Tasks: Migrar capas 2D a la vista 3D

## Overview

**Total Tasks**: 12  
**Phases**: 4 (Inventario → Raster 3D → Vector 3D → UX/Verificación)  
**Goal**: Llevar un subconjunto útil y explícito de las capas 2D a la vista 3D sin romper la estabilidad del terreno.

---

## Phase 1: Inventario y estructura base

- [ ] **1.1 Documentar matriz de paridad 2D -> 3D en `terrainLayerConfig.ts`**
  - **AC**:
    - existe listado explícito de capas raster soportadas en 3D
    - existe listado explícito de capas vectoriales prioritarias
    - cada entrada indica estado: `supported`, `planned`, `not_supported_yet`
  - **Dependencies**: None
  - **Files Modified**: `consorcio-web/src/components/terrain/terrainLayerConfig.ts` (new)

- [ ] **1.2 Extraer panel/control de capas 3D**
  - **AC**:
    - `TerrainLayerPanel.tsx` existe
    - soporta selección de raster overlay activo
    - soporta toggles de visibilidad para overlays vectoriales
    - soporta slider de opacidad del overlay raster
  - **Dependencies**: 1.1
  - **Files Modified**: `consorcio-web/src/components/terrain/TerrainLayerPanel.tsx` (new)

---

## Phase 2: Raster overlays en 3D

- [ ] **2.1 Reusar `useGeoLayers` en la vista 3D**
  - **AC**:
    - `TerrainViewer3D` recibe/consume layers raster disponibles
    - identifica overlays DEM/composite compatibles
    - deja el DEM de relieve separado del overlay visual
  - **Dependencies**: 1.1
  - **Files Modified**: `consorcio-web/src/components/terrain/TerrainViewer3D.tsx`

- [ ] **2.2 Implementar selección de raster overlay activo**
  - **AC**:
    - el usuario puede elegir un raster overlay distinto del DEM base
    - el source/layer raster visible cambia sin recrear el terrain source
    - no reaparece `dem dimension mismatch`
  - **Dependencies**: 2.1
  - **Files Modified**: `consorcio-web/src/components/terrain/TerrainViewer3D.tsx`

- [ ] **2.3 Reusar `buildTileUrl()` con `hide_classes` / `hide_ranges`**
  - **AC**:
    - overlays categóricos/continuos compatibles respetan los filtros activos
    - los query params se construyen igual que en 2D
  - **Dependencies**: 2.2
  - **Files Modified**: `consorcio-web/src/components/terrain/TerrainViewer3D.tsx`, possible helper file

- [ ] **2.4 Mostrar leyenda/opacidad del raster activo en 3D**
  - **AC**:
    - el raster activo tiene control de opacidad
    - la leyenda refleja el tipo de layer activo
  - **Dependencies**: 2.2, 2.3
  - **Files Modified**: `consorcio-web/src/components/terrain/TerrainLayerPanel.tsx`, `consorcio-web/src/components/RasterLegend.tsx` (if needed)

---

## Phase 3: Vector overlays prioritarios en 3D

- [ ] **3.1 Incorporar zona + cuencas GEE como sources/layers MapLibre**
  - **AC**:
    - zona consorcio visible en 3D
    - cuencas GEE visibles en 3D
    - estilos equivalentes razonables a 2D
  - **Dependencies**: 1.1, 1.2
  - **Files Modified**: `consorcio-web/src/components/terrain/TerrainViewer3D.tsx`, helper files

- [ ] **3.2 Incorporar basins y capas públicas vectoriales**
  - **AC**:
    - basins visibles con fill/line
    - capas públicas visibles con estilo básico
  - **Dependencies**: 3.1
  - **Files Modified**: `consorcio-web/src/components/terrain/TerrainViewer3D.tsx`

- [ ] **3.3 Incorporar red vial e hidrografía**
  - **AC**:
    - caminos visibles en 3D con color por consorcio
    - hidrografía visible en 3D como line overlay
  - **Dependencies**: 3.1
  - **Files Modified**: `consorcio-web/src/components/terrain/TerrainViewer3D.tsx`

- [ ] **3.4 Incorporar activos de infraestructura como puntos 3D/2.5D**
  - **AC**:
    - activos visibles como `circle` o `symbol` layer
    - color/tipo distinguibles
  - **Dependencies**: 3.1
  - **Files Modified**: `consorcio-web/src/components/terrain/TerrainViewer3D.tsx`

---

## Phase 4: Verificación y convergencia UX

- [ ] **4.1 Agregar tests para config/helpers de capas 3D**
  - **AC**:
    - existen tests para mapping de layers raster soportados
    - existen tests para estado de visibilidad/selección del panel 3D
  - **Dependencies**: 1.1, 1.2, 2.x
  - **Files Modified**: test files under `consorcio-web/src/components/terrain/` or `consorcio-web/src/components/terrain/__tests__/`

- [ ] **4.2 Verificar smoke manual de capas 3D**
  - **AC**:
    - cambiar overlay raster funciona
    - activar/desactivar vectores no rompe el mapa
    - no reaparece `dem dimension mismatch`
    - vista 3D sigue cargando estable después de tilt/zoom/pan
  - **Dependencies**: 2.x, 3.x
  - **Files Modified**: none required

- [ ] **4.3 Documentar cobertura 3D alcanzada**
  - **AC**:
    - se documenta qué capas 2D quedaron incorporadas en 3D
    - se documenta qué queda pendiente y por qué
  - **Dependencies**: 4.2
  - **Files Modified**: `openspec/changes/migrar-capas-2d-a-3d/*` and/or project docs if needed
