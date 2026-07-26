# Tasks: export-import-geo-bundle

## Phase 1 — Diseño del bundle
- [ ] Definir estructura del bundle geo (manifest, vectores, rasters, metadata)
- [ ] Definir qué capas raster entran en el MVP
- [ ] Definir política de reemplazo vs merge

## Phase 2 — Export
- [ ] Implementar export de `zonas_operativas`
- [ ] Implementar export de zonificación aprobada activa
- [ ] Implementar export de `geo_layers` relevantes a manifest
- [ ] Implementar copiado/empaquetado de rasters al bundle

## Phase 3 — Import
- [ ] Implementar import de bundle desde admin/backend
- [ ] Restaurar vectores desde el bundle
- [ ] Restaurar rasters en directorio destino
- [ ] Registrar/normalizar `geo_layers` con nuevos paths

## Phase 4 — Validación
- [ ] Validar que `/geo/basins` funciona tras importar
- [ ] Validar que las capas DEM cargan en 2D
- [ ] Validar que `dem_raw` funciona en 3D
- [ ] Documentar uso operativo entre desarrollo y producción
