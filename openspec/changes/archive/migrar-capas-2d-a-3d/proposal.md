# Proposal: Migrar capas 2D a la vista 3D

## Intent

Extender la nueva vista 3D basada en MapLibre para que pueda mostrar progresivamente las capas hoy disponibles en `MapaLeaflet`, empezando por las capas raster ya servidas como tiles y luego incorporando capas vectoriales, controles y paridad funcional básica con la vista 2D.

## Scope

### In Scope

#### Fase 1: Paridad inicial de overlays raster
- Incorporar en `TerrainViewer3D` las capas raster del pipeline DEM/composite que hoy se muestran en 2D:
  - `dem_raw`, `slope`, `aspect`, `flow_dir`, `flow_acc`, `twi`, `hand`, `profile_curvature`, `tpi`, `terrain_class`
  - `flood_risk`, `drainage_need`
- Permitir seleccionar cuál raster se "drapea" sobre el terreno 3D.
- Mantener compatibilidad con `hide_classes` y `hide_ranges` donde aplique.
- Mantener la textura satelital/base debajo del overlay raster configurable.

#### Fase 2: Capas vectoriales prioritarias
- Incorporar overlays GeoJSON/lineales básicos en 3D para:
  - zona consorcio
  - cuencas GEE (`candil`, `ml`, `noroeste`, `norte`)
  - basins
  - red vial coloreada por consorcio
  - hidrografía publicada
  - capas públicas vectoriales
- Mostrar activos de infraestructura como markers/puntos en MapLibre.

#### Fase 3: Controles y UX mínima compartida
- Panel de toggles de capas visible en 3D.
- Control de opacidad para overlay raster activo.
- Leyenda del raster activo y de clases/rangos visibles.
- Estructura para futuras popups/tooltips sobre capas vectoriales.

### Out of Scope
- Paridad total inmediata con todas las interacciones avanzadas de Leaflet.
- Edición/manual marking de activos sobre la vista 3D.
- Comparador de imágenes satelitales tipo slider en 3D.
- Extrusión avanzada de features vectoriales (edificios, líneas 3D reales).
- Unificación completa del código 2D/3D en esta primera migración.

## Current State

La vista 2D (`MapaLeaflet`) ya soporta:
- base layers: OpenStreetMap + satélite Esri
- imagen satelital seleccionada y comparación
- overlays GEE vectoriales (zona + cuencas)
- basins PostGIS
- overlays raster DEM/composite vía XYZ
- red vial coloreada
- intersecciones
- capas públicas vectoriales
- hidrografía
- activos de infraestructura
- leyendas y toggles de clases/rangos para rasters

La vista 3D (`TerrainViewer3D`) hoy solo soporta:
- terreno DEM (`raster-dem`)
- textura única drapeada sobre el terreno
- satélite base
- slider de exageración
- manejo básico de errores

## Approach

### Paso 1: Crear un modelo de capas 3D explícito
Definir una configuración de capas soportadas por la vista 3D, separando:
- `terrain source` (DEM para relieve)
- `raster overlays` drapeados
- `vector overlays` MapLibre (`fill`, `line`, `circle`, `symbol`)

### Paso 2: Empezar por rasters ya servidos
Reusar `useGeoLayers`, `buildTileUrl`, `GEO_LAYER_LABELS`, toggles de clases/rangos y leyendas existentes para que el usuario pueda elegir el raster activo sobre el relieve.

### Paso 3: Incorporar vectores prioritarios
Crear sources/layers GeoJSON en MapLibre para cuencas, zona, caminos, basins, hidrografía y capas públicas. Empezar sin edición ni popups complejos.

### Paso 4: Converger UX 2D/3D
Agregar un panel de capas 3D con naming y agrupaciones compatibles con 2D para reducir la diferencia mental entre vistas.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `consorcio-web/src/components/terrain/TerrainViewer3D.tsx` | Modified | Pasará de viewer simple a viewer con gestión de overlays raster y vectoriales |
| `consorcio-web/src/components/MapaPage.tsx` | Modified | Deberá pasar estado/configuración de capas relevantes a la vista 3D |
| `consorcio-web/src/components/MapaLeaflet.tsx` | Reference only | Fuente de verdad actual para identificar paridad funcional deseada |
| `consorcio-web/src/hooks/useGeoLayers.ts` | Reused/possible modified | Reuso de tiles, labels, toggles de clases/rangos |
| `consorcio-web/src/hooks/useGEELayers.ts` | Reused | Reuso de capas vectoriales GEE |
| `consorcio-web/src/hooks/useBasins.ts` | Reused | Reuso de basins |
| `consorcio-web/src/hooks/useWaterways.ts` | Reused | Reuso de hidrografía |
| `consorcio-web/src/hooks/usePublicLayers.ts` | Reused | Reuso de capas publicadas |
| `consorcio-web/src/hooks/useInfrastructure.ts` | Reused | Reuso de activos/markers |
| `consorcio-web/src/components/RasterLegend.tsx` | Reused/possible adapted | Leyenda para raster activo en 3D |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Exceso de complejidad en `TerrainViewer3D` | High | Separar lógica en hooks/helpers de sources y paneles UI |
| Pérdida de performance en 3D al sumar muchas capas | Medium | Migrar por fases, limitar cantidad de overlays activos simultáneamente |
| Divergencia funcional entre 2D y 3D | Medium | Definir matriz explícita de paridad por capa y feature |
| Estilos vectoriales inconsistentes con Leaflet | Medium | Centralizar estilos compartidos o mapearlos explícitamente |
| Nuevos errores MapLibre por sources dinámicos | Medium | Cambios incrementales y pruebas manuales capa por capa |

## Rollback Plan

1. Mantener `TerrainViewer3D` funcional con solo DEM + textura única si la migración parcial introduce regresiones.
2. Implementar cada grupo de capas detrás de estado/feature flags simples en el componente 3D.
3. Si una familia de overlays falla (por ejemplo caminos o basins), revertir solo ese grupo sin perder el viewer 3D base.

## Dependencies

- Vista 3D actual estable con DEM (`terrain-rgb`) ya funcionando.
- Hooks de datos 2D existentes (`useGeoLayers`, `useGEELayers`, `useBasins`, `useWaterways`, `usePublicLayers`, `useInfrastructure`).
- Endpoints backend actuales de tiles y GeoJSON.

## Success Criteria

- [ ] La vista 3D permite elegir al menos un raster DEM/composite distinto del DEM base como overlay activo.
- [ ] La vista 3D soporta toggles para un primer set de capas vectoriales prioritarias.
- [ ] Existe una matriz documentada de qué capas 2D ya están disponibles en 3D y cuáles faltan.
- [ ] La UX básica de la vista 3D permite activar/desactivar capas y entender qué está visible.
- [ ] No se reintroduce el fallo `dem dimension mismatch` durante la migración.

---

**Change**: migrar-capas-2d-a-3d  
**Location**: openspec/changes/migrar-capas-2d-a-3d/proposal.md  
**Status**: Ready for Review  
**Next Step**: Specification (`/sdd:continue migrar-capas-2d-a-3d`)
