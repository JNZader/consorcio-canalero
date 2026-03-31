# Proposal: export-import-geo-bundle

## Context
Hoy producción y desarrollo quedan desalineados en la parte geoespacial. Ya resolvimos importar subcuencas y zonificación aprobada, pero siguen faltando capas raster y metadata de `geo_layers`, lo que rompe o degrada la vista 2D/3D.

Además, el pipeline DEM no siempre está estable en todos los entornos, así que no conviene depender solamente de “reprocesar” para reconstruir producción.

## Problem
No existe un flujo repetible para mover el estado geoespacial entre entornos.

Actualmente faltan mecanismos para transportar de forma consistente:
- subcuencas operativas
- zonificación aprobada
- canales existentes y sugerencias aprobadas relevantes
- rasters DEM y derivados
- registros `geo_layers` / metadata asociada

## Proposal
Crear un bundle de exportación/importación geo que permita:

1. Exportar desde desarrollo un paquete geoespacial completo.
2. Importar ese paquete en producción desde admin.
3. Restaurar tanto vectores como rasters y metadata asociada.

## Scope
Incluye:
- export de vectores clave a GeoJSON
- export de rasters y manifest de capas
- import admin para restaurar vectores
- import admin para restaurar rasters + `geo_layers`
- validaciones y feedback de resultados

No incluye en esta etapa:
- versionado incremental sofisticado
- sincronización automática entre entornos
- diff visual entre bundles

## Risks
- bundles pesados por tamaño de TIFFs
- divergencia entre paths locales y paths productivos
- necesidad de normalizar referencias de archivos al importar
- posibilidad de sobrescribir capas útiles si no se hace con confirmación clara

## Acceptance Criteria
- se puede exportar un bundle geo desde desarrollo
- se puede importar el bundle en otro entorno desde admin
- tras importar, las subcuencas y la zonificación quedan operativas
- las capas DEM/derivadas cargan en 2D
- `dem_raw` vuelve a estar disponible para 3D
