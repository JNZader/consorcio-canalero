# Auditoría exhaustiva — Consorcio Canalero

Fecha: 2026-07-09  
Rama analizada: `fix/auditoria-2026-07-04`  
Alcance: revisión estática + verificaciones selectivas del frontend y backend, sin modificar código.

## Resumen ejecutivo

La app está en un estado razonable de salud general:

- `npm run typecheck` en frontend: OK
- `npm run lint` en frontend: OK, pero con advertencias
- tests focalizados de hooks de imágenes: OK
- `ruff check` en backend: OK
- tests backend focalizados de settings y visualización: OK
- `npm audit --omit=dev` en frontend: **0 vulnerabilidades runtime**

Pero encontré varios problemas importantes en el flujo de imágenes satelitales:

1. la carga de escenas históricas se sobreescribe sola;
2. la persistencia de imagen seleccionada pierde parámetros reales de búsqueda;
3. la validación de `tile_url` es demasiado laxa y el visor 3D la bypassa;
4. no hay cancelación/guard de requests en el explorador, así que una respuesta vieja puede pisar una nueva.

Además, el frontend todavía arrastra deuda de tooling y lint.

## Hallazgos priorizados

### 1) Alto — Las “Escenas históricas” se pisan con el fetch genérico del día

**Archivo:** `consorcio-web/src/components/admin/images/useImageExplorerController.tsx`

**Evidencia:**

- `loadHistoricFlood()` llama al endpoint histórico y actualiza `result`.
- Luego hace `setSelectedDay(data.flood_info.date)`.
- El efecto `useEffect([fetchImageForDate, selectedDay])` vuelve a disparar el fetch normal del día y pisa el resultado histórico.

**Impacto:**

La UI puede mostrar una imagen distinta a la histórica que el usuario eligió. Es un bug funcional de prioridad alta porque rompe una feature visible y recién agregada.

**Recomendación:**

- separar el estado de “flood histórico” del estado de selección manual;
- o agregar una bandera que evite que el efecto genérico corra cuando la carga proviene de un evento histórico.

---

### 2) Media/Alta — La persistencia de imagen es lossy y no restaura exactamente lo que el usuario eligió

**Archivos:**

- `consorcio-web/src/hooks/useSelectedImage.ts`
- `consorcio-web/src/hooks/useImageComparison.ts`
- `consorcio-web/src/lib/api/mapImage.ts`
- `gee-backend/app/domains/settings/router.py`
- `gee-backend/app/domains/settings/schemas.py`

**Evidencia:**

- Se persiste solo `sensor`, `target_date` y `visualization`.
- `toBackendParams()` fuerza `days_buffer: 10` y `max_cloud: null`.
- El restore usa `regenerateTile()` con defaults.
- `mode` no se persiste, así que Landsat 7 compuesto vuelve como `scene` normal.

**Impacto:**

La app no puede reconstruir el mismo tile que vio el usuario. Esto afecta sobre todo:

- Landsat 7 con modo `composite`;
- escenas ópticas con ventana o nubosidad ajustadas;
- consistencia entre pestañas/navegadores.

**Recomendación:**

- persistir `mode`, `days_buffer` y `max_cloud`;
- usar el contrato completo en backend y frontend para regenerar tiles sin pérdida.

---

### 3) Media — Validación demasiado permisiva de `tile_url` y bypass en el visor 3D

**Archivos:**

- `consorcio-web/src/lib/typeGuards.ts`
- `consorcio-web/src/components/terrain/TerrainViewer3D.tsx`

**Evidencia:**

- `isValidSelectedImage()` permite cualquier `https://...` salvo una restricción parcial sobre `googleapis.com`.
- `TerrainViewer3D` lee `consorcio_selected_image` de `localStorage` con un parseo propio y usa `tile_url` directamente.

**Impacto:**

Una entrada manipulada en `localStorage` puede hacer que el mapa/visor 3D cargue tiles desde un origen arbitrario. No es un RCE, pero sí una superficie innecesaria de carga remota.

**Recomendación:**

- centralizar la lectura en el guard compartido;
- restringir explícitamente a los hosts esperados de GEE/proxy interno;
- evitar parseos ad-hoc del mismo storage key.

---

### 4) Media — No hay cancelación ni guard de respuesta más reciente en el explorador

**Archivo:** `consorcio-web/src/components/admin/images/useImageExplorerController.tsx`

**Evidencia:**

- los fetch a `available-dates`, `scenes`, `historic-floods` y `get image` se disparan sin abort controller;
- el backend documenta que las llamadas GEE pueden tardar entre 30 s y 2 min.

**Impacto:**

Si el usuario cambia sensor/día rápido, una respuesta lenta puede llegar tarde y sobrescribir el estado nuevo con datos viejos.

**Recomendación:**

- usar `AbortController` por request;
- o guardar un `requestId` incremental y descartar respuestas obsoletas.

---

## Observaciones adicionales

### Estado de dependencias

- `npm audit --omit=dev`: 0 vulnerabilidades
- `npm audit`: 9 vulnerabilidades, todas en cadena de tooling/dev

O sea: runtime limpio, pero el toolchain todavía necesita mantenimiento.

### Lint

`npm run lint` reportó 14 warnings, principalmente:

- dependencias exhaustivas faltantes en `MapaMapLibre.tsx`
- complejidad alta en `LayerControlsPanel.tsx`
- complejidad alta en `useMapLayerEffects.ts`
- un warning en `useReportFormSubmission.ts`

### Tests ejecutados

Pasaron:

- `consorcio-web/tests/hooks/useSelectedImage.test.ts`
- `consorcio-web/tests/hooks/useImageComparison.test.ts`
- `gee-backend/tests/new/test_geo_visualization_router.py`
- `gee-backend/tests/new/test_geo_visualization_service.py`
- `gee-backend/tests/new/test_settings.py`

## Prioridad sugerida de remediación

1. Corregir el overwrite de “Escenas históricas”.
2. Persistir el estado completo de la imagen seleccionada.
3. Endurecer y centralizar la validación de `tile_url`.
4. Agregar cancelación/guard de requests en el explorador.
5. Planificar limpieza de dev dependencies y warnings de lint.

## Key Learnings

1. El flujo histórico del explorador de imágenes está acoplado al mismo estado que el flujo normal y eso provoca overwrite.
2. La restauración de tiles GEE necesita persistir más que sensor/fecha/visualización si se quiere reproducir exactamente la imagen vista.
3. El visor 3D no debe confiar en un `tile_url` leído directamente de `localStorage` sin pasar por el guard compartido.
4. GEE es suficientemente lento como para que la ausencia de abort/version guard sea un riesgo real de carrera.
