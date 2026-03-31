# Spec: export-import-geo-bundle

## Requirement 1 — Export bundle geoespacial
El sistema DEBE poder generar un paquete exportable con el estado geoespacial relevante de un entorno.

### Incluye
- `zonas_operativas`
- zonificación aprobada activa
- manifest de capas geo
- archivos raster asociados a capas geo seleccionadas
- metadata mínima para reconstrucción

### Scenario: export completo
- Given que existen vectores y rasters cargados
- When un admin ejecuta la exportación
- Then el sistema genera un bundle con manifest y archivos requeridos

## Requirement 2 — Import bundle geoespacial
El sistema DEBE poder importar un bundle previamente exportado y restaurar su contenido.

### Scenario: importar bundle válido
- Given un bundle geo válido
- When un admin lo importa
- Then el sistema restaura vectores, rasters y metadata compatible

### Scenario: bundle inválido
- Given un bundle incompleto o corrupto
- When un admin intenta importarlo
- Then el sistema rechaza la operación con mensaje claro

## Requirement 3 — Restauración de subcuencas y zonificación
El bundle DEBE restaurar correctamente subcuencas operativas y zonificación aprobada.

### Scenario: restaurar vectores
- Given un bundle con GeoJSON válidos
- When se importa
- Then `/geo/basins` responde con features válidas
- And la zonificación aprobada actual queda disponible

## Requirement 4 — Restauración de capas raster
El bundle DEBE restaurar capas raster necesarias para 2D y 3D.

### Scenario: restaurar DEM y derivados
- Given un bundle con rasters DEM y derivados
- When se importa
- Then las capas raster pueden servirse por tiles en 2D
- And `dem_raw` puede usarse en 3D

## Requirement 5 — Manifest y normalización
El sistema DEBE usar un manifest para desacoplar paths locales de paths importados.

### Scenario: paths diferentes entre entornos
- Given que el bundle fue creado en desarrollo
- And el entorno destino usa otra estructura de carpetas
- When se importa
- Then el sistema reescribe rutas y registra `geo_layers` con paths válidos del entorno destino
