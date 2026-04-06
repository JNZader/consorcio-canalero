# Pendientes — Consorcio Canalero

> Última actualización: 2026-04-06

---

## 1. Datos abiertos via Martin (MVT público)

**Estado:** Aprobado, sin implementar.

**Qué es:**
Página o sección pública que exponga las capas PostGIS del sistema como tiles MVT consumibles desde QGIS, otras apps o el propio frontend. Martin ya está corriendo y publica automáticamente las tablas — falta:

- Endpoint o página en el frontend que liste las capas disponibles con sus URLs de tiles
- Documentar las URLs de cada fuente:
  - `parcelas_catastro` → `http://<servidor>:3000/parcelas_catastro/{z}/{x}/{y}`
  - `zonas_operativas` → `http://<servidor>:3000/zonas_operativas/{z}/{x}/{y}`
  - `canal_suggestions` → `http://<servidor>:3000/canal_suggestions/{z}/{x}/{y}`
  - `puntos_conflicto` → `http://<servidor>:3000/puntos_conflicto/{z}/{x}/{y}`
  - `assets` → `http://<servidor>:3000/assets/{z}/{x}/{y}`
- Posible ruta: `/api/v2/public/layers/catalog` que devuelva el listado con metadatos
- Considerar si Martin debe estar expuesto directamente al exterior o proxeado por el backend FastAPI

**Archivos relevantes:**
- `consorcio-web/src/hooks/useMartinLayers.ts` — `MARTIN_URL`, `getMartinTileUrl()`
- `gee-backend/app/domains/capas/` — dominio de capas existente
- `docker-compose.yml` — configuración del servicio Martin

**Decisión pendiente:**
- ¿Martin expuesto directamente (puerto 3000 público) o proxeado por FastAPI?
- ¿La página de datos abiertos requiere autenticación o es completamente pública?

---

## 2. Exportación a QGIS (.qgz)

**Estado:** Aprobado, sin implementar. Hay una **pregunta bloqueante sin responder**.

**Pregunta bloqueante:**
> ¿Los técnicos tienen acceso de red al servidor cuando usan QGIS, o trabajan offline en campo?

La respuesta cambia completamente el approach:

### Opción A — Técnicos con acceso de red al servidor
Generar un `.qgz` que apunte a las URLs de Martin en el servidor. Las capas se cargan dinámicamente desde la red cuando el técnico abre el archivo.

```
Capas en el .qgz:
  - Parcelas catastro  → Martin MVT URL del servidor
  - Zonas operativas   → Martin MVT URL del servidor
  - Canales            → Martin MVT URL del servidor
  Ventaja: siempre datos actualizados, .qgz liviano
  Desventaja: sin red → sin datos
```

### Opción B — Técnicos offline (trabajo en campo)
Generar un `.qgz` con los datos embebidos como GeoPackage (.gpkg) o GeoJSON adjunto. El archivo es autocontenido.

```
Capas en el .qgz:
  - GeoPackage con snapshot de los datos al momento de la exportación
  Ventaja: funciona sin red
  Desventaja: datos pueden quedar desactualizados, archivo más pesado
```

**Implementación técnica (cualquier opción):**
- Backend: endpoint `GET /api/v2/geo/export/qgis` que genere el `.qgz`
- El `.qgz` es un ZIP con un archivo `.qgs` (XML) adentro
- Librería sugerida: `qgis` Python API o generación manual del XML (más simple, sin dependencia de QGIS instalado)
- Requiere definir qué capas incluir y con qué estilos

**Archivos relevantes:**
- `gee-backend/app/domains/geo/router.py` — donde agregar el endpoint
- `gee-backend/app/shared/` — donde poner el generador de .qgz
- `consorcio-web/src/` — botón de descarga en la UI (panel de capas o settings)

---

## Contexto de la sesión anterior (mapa 2D — completado)

Para referencia, esto se implementó en las últimas sesiones y ya está funcionando:

- ✅ Mapa 2D migrado a MapLibre GL (reemplaza Leaflet)
- ✅ Imagen satelital GEE como overlay raster (`type: 'raster'`, no `type: 'image'`)
- ✅ Comparación de imágenes con slider (two-map approach — CSS clip-path)
- ✅ Suelos IDECOR con colores exactos del viewer 3D (GeoJSON + `getSoilColor`)
- ✅ Catastro via Martin MVT (`parcelas_catastro` table, 1322 parcelas importadas)
- ✅ Ordenamiento de capas: rasters debajo de vectores (sentinel layer `vector-layers-start`)
- ✅ Toggles de capas ocultan entrada cuando no hay datos
- ✅ Leyenda dinámica refleja capas visibles (suelos por clase CAP, hidrografía, cuencas, etc.)
- ✅ Tests de integración para dominio territorial (30 tests, pytest + PostGIS real)
- ✅ 43 errores de linter backend corregidos
