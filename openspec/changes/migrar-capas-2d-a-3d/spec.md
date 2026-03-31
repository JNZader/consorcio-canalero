# Delta Specification: Migrar capas 2D a la vista 3D

## Purpose

La vista 3D MUST evolucionar desde un visor de terreno único hacia una vista cartográfica 3D utilizable, con overlays raster y vectoriales equivalentes a un subconjunto explícito de la vista 2D.

## Layer Parity Matrix

### Raster overlays prioritarios

La vista 3D SHOULD soportar estos tipos de layer raster servidos por `/api/v2/geo/layers/{id}/tiles/{z}/{x}/{y}.png`:

- `dem_raw`
- `slope`
- `aspect`
- `flow_dir`
- `flow_acc`
- `twi`
- `hand`
- `profile_curvature`
- `tpi`
- `terrain_class`
- `flood_risk`
- `drainage_need`

### Vector overlays prioritarios

La vista 3D SHOULD soportar estas familias de capas vectoriales:

- zona consorcio
- cuencas GEE (`candil`, `ml`, `noroeste`, `norte`)
- basins
- red vial por consorcio
- hidrografía
- capas públicas vectoriales
- activos de infraestructura

## Requirements & Scenarios

### Requirement: Terrain source stability

La vista 3D MUST mantener el `raster-dem` actual como única fuente de relieve y NO debe reemplazarlo cuando el usuario cambia overlays temáticos.

#### Scenario: Cambiar overlay raster sin resetear el terreno
- GIVEN la vista 3D cargó el DEM correctamente
- WHEN el usuario cambia de overlay `dem_raw` a `flood_risk`
- THEN el source `terrain-rgb` sigue siendo el mismo
- AND solo cambia la textura/overlay visible sobre el relieve
- AND no reaparece `dem dimension mismatch`

### Requirement: Raster overlay selection

La vista 3D MUST permitir seleccionar un raster overlay activo entre las capas DEM/composite disponibles.

#### Scenario: Mostrar flood_risk sobre el terreno
- GIVEN existe una capa `flood_risk` en `useGeoLayers`
- WHEN el usuario la selecciona como overlay activo en 3D
- THEN la vista 3D usa su tile URL como raster drapeado
- AND mantiene la base satelital debajo con la opacidad configurada

#### Scenario: Mantener compatibilidad con clases/rangos ocultos
- GIVEN el usuario ocultó clases o rangos de un raster compatible
- WHEN ese raster se visualiza en 3D
- THEN el tile URL incluye `hide_classes` y/o `hide_ranges`
- AND la leyenda refleja el estado actual

### Requirement: Vector overlay rendering

La vista 3D MUST renderizar un primer subconjunto de capas vectoriales usando sources/layers nativos de MapLibre.

#### Scenario: Mostrar cuencas en 3D
- GIVEN `useGEELayers` devolvió `candil`, `ml`, `noroeste` y `norte`
- WHEN el usuario activa "Cuencas" en la vista 3D
- THEN se agregan sources GeoJSON y layers `fill`/`line` equivalentes
- AND el estilo visual conserva color, borde y opacidad razonables respecto a 2D

#### Scenario: Mostrar caminos coloreados
- GIVEN `useCaminosColoreados` devolvió la red vial
- WHEN el usuario activa "Red Vial" en 3D
- THEN se crea un source GeoJSON
- AND las features se dibujan como `line` con el color por consorcio ya presente en sus propiedades

#### Scenario: Mostrar infraestructura registrada
- GIVEN `useInfrastructure` devolvió activos
- WHEN el usuario activa "Activos de Infraestructura" en 3D
- THEN los activos se muestran como layer `circle` o `symbol`
- AND el usuario puede distinguir tipo/color al menos visualmente

### Requirement: 3D layer controls

La vista 3D MUST exponer controles mínimos de capas para ser utilizable sin volver a 2D.

#### Scenario: Activar y desactivar overlays en 3D
- GIVEN el usuario está en la vista 3D
- WHEN interactúa con el panel de capas
- THEN puede activar/desactivar familias de overlays soportadas
- AND el estado visible se refleja inmediatamente en el mapa

#### Scenario: Ajustar opacidad del raster overlay
- GIVEN hay un raster overlay activo
- WHEN el usuario modifica la opacidad
- THEN cambia solo la opacidad del overlay raster
- AND ni el DEM ni la base satelital pierden estabilidad

### Requirement: Progressive parity documentation

El cambio MUST dejar una matriz clara de paridad entre capas 2D y 3D.

#### Scenario: Auditar cobertura de capas
- GIVEN el proyecto mantiene 2 vistas distintas (2D y 3D)
- WHEN un desarrollador revisa la documentación del cambio
- THEN puede ver qué capas están migradas a 3D
- AND cuáles quedan pendientes y por qué

## API / Contract Notes

- Se seguirá reutilizando `buildTileUrl(layer.id, { hideClasses, hideRanges })` para rasters.
- Los vectores seguirán consumiéndose desde hooks ya existentes; este cambio NO requiere nuevos contratos backend en su primera fase.
- Si una capa no es compatible con 3D, la UI SHOULD mostrarla como pendiente o no disponible, en lugar de fallar silenciosamente.
