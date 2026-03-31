# Proposal: Mejoras UX, historial y reportes

## Intent

Consolidar la experiencia operativa del mapa del consorcio en sus vistas 2D y 3D, completar el versionado de la zonificación aprobada con metadatos útiles para gestión, y agregar capacidades de exportación/reporte para que la zonificación pueda compartirse fuera de la app.

## Scope

### In Scope

#### Fase 1: Pulido final 2D/3D
- Revisar y ajustar posiciones de paneles flotantes en 2D y 3D.
- Definir defaults coherentes de capas visibles por vista.
- Alinear naming, botones, leyendas y estados vacíos entre Leaflet (2D) y MapLibre (3D).
- Reducir ruido visual cuando existe una zonificación aprobada.

#### Fase 2: Historial enriquecido de zonificación
- Permitir guardar notas/comentarios por versión aprobada.
- Guardar autor o identificador de quién aprobó.
- Permitir nombre amigable por versión (ej. “Zonificación operativa marzo 2026”).
- Mostrar estos metadatos en el historial del frontend.

#### Fase 3: Exportación y reportes
- Permitir descargar la zonificación aprobada actual como GeoJSON.
- Preparar una vista/resumen imprimible de la zonificación aprobada.
- Soportar exportación básica a PDF o flujo de impresión del navegador.
- Incluir metadatos de versión aprobada dentro del reporte/export.

### Out of Scope
- Analítica operativa nueva (prioridad vial hídrica, inundaciones, humedad/cobertura).
- Incorporación de canales existentes y otras capas faltantes para la línea analítica.
- Rediseño completo de la navegación general de la app.
- Autenticación/roles avanzados más allá de registrar un autor/aprobador textual o disponible en sesión.

## Current State

Hoy la app ya cuenta con:
- Vistas 2D y 3D funcionales y bastante alineadas.
- Zonificación aprobada persistida en backend/db.
- Historial versionado y restauración append-only.
- Panel de historial visible en el frontend.
- Integración de Sentinel seleccionado como overlay 3D.

Pero todavía faltan:
- Metadatos útiles por versión aprobada.
- Flujo claro para compartir/exportar la zonificación fuera del mapa.
- Ajustes finales de UX visual y consistencia entre vistas.

## Approach

### Paso 1: estabilizar UX operativa visible
Antes de agregar más datos al historial o reportes, cerrar detalles de layout, defaults y naming para que 2D/3D presenten una experiencia más homogénea.

### Paso 2: enriquecer el modelo de versión aprobada
Extender la persistencia de zonificación aprobada con campos de metadatos opcionales: nombre, comentario, aprobador, timestamps visibles y cualquier dato mínimo necesario para trazabilidad operativa.

### Paso 3: construir exportación desde la versión aprobada actual
Usar la zonificación aprobada ya persistida como fuente única para descargas y reportes, evitando reconstrucciones paralelas desde draft o browser state.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `consorcio-web/src/components/MapaLeaflet.tsx` | Modified | Ajustes UX de paneles, historial y acciones de exportación |
| `consorcio-web/src/components/terrain/TerrainViewer3D.tsx` | Modified | Ajustes UX/consistencia visual 3D |
| `consorcio-web/src/hooks/useApprovedZones.ts` | Modified | Lectura/escritura de metadatos enriquecidos |
| `consorcio-web/src/lib/query.ts` | Modified | Contratos frontend para historial/exportación |
| `gee-backend/app/domains/geo/models.py` | Modified | Metadatos adicionales en zonificación aprobada |
| `gee-backend/app/domains/geo/repository.py` | Modified | Persistencia/lectura de historial enriquecido |
| `gee-backend/app/domains/geo/router.py` | Modified | Endpoints para guardar metadatos y exportar/descargar |
| `docs/` or `openspec/` | Modified | Documentación de UX y flujos de exportación |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Agregar demasiados controles al historial y volverlo pesado | Medium | Mantener MVP simple: nombre, nota, aprobador |
| Inconsistencias entre exportado e historial activo | Medium | Exportar siempre desde la versión activa del backend |
| UX flotante siga sintiéndose cargada | Medium | Definir jerarquía clara de paneles por vista y defaults mínimos |
| PDF/print resulte frágil cross-browser | Medium | Empezar por impresión browser-friendly y GeoJSON confiable |

## Rollback Plan

1. Mantener exportación mínima a GeoJSON aunque PDF/print requiera más iteración.
2. Si los metadatos enriquecidos causan fricción, dejarlos opcionales sin romper versiones existentes.
3. Revertir solo cambios de layout visual sin tocar el historial persistido si la UX empeora.

## Dependencies

- Versionado de zonificación aprobada ya implementado.
- Vistas 2D/3D funcionales y persistencia backend estable.
- Base actual de approved zones como single source of truth.

## Success Criteria

- [ ] Las vistas 2D y 3D tienen paneles/defaults más coherentes y menos ruido visual.
- [ ] Cada versión aprobada puede tener nombre, comentario y aprobador visibles en el historial.
- [ ] La zonificación aprobada actual se puede descargar como GeoJSON.
- [ ] Existe un flujo de impresión o reporte usable desde la app.
- [ ] El historial sigue siendo append-only y no se rompe la restauración.

---

**Change**: mejoras-ux-historial-reportes  
**Location**: openspec/changes/mejoras-ux-historial-reportes/proposal.md  
**Status**: Ready for Review  
**Next Step**: Specification (`/sdd:continue mejoras-ux-historial-reportes`)
