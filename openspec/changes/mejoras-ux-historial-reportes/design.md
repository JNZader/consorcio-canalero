# Design: Mejoras UX, historial y reportes

## Technical Approach

El cambio se divide en tres ejes coordinados:

1. **UX 2D/3D**
   - refinar layout, defaults y jerarquía visual
   - converger naming y acciones frecuentes

2. **Metadatos de versiones**
   - extender el modelo persistido de approved zoning con campos opcionales
   - mantener compatibilidad hacia atrás

3. **Exportación/reporte**
   - reutilizar la versión activa persistida como fuente única
   - generar descargas y vistas imprimibles sin depender de estado del navegador

## Architecture Decisions

### Decision: Use approved zoning as single source of truth for exports
**Choice**: Toda exportación o impresión se genera desde la zonificación aprobada activa persistida en backend.

**Rationale**: Evita inconsistencias entre draft, browser state y backend; simplifica auditoría y soporte.

### Decision: Keep metadata optional
**Choice**: `display_name`, `comment` y `approved_by` serán opcionales.

**Rationale**: Preserva compatibilidad con versiones existentes y no bloquea aprobaciones rápidas.

### Decision: Start report output with browser-printable layout
**Choice**: Implementar primero un layout amigable para impresión/PDF desde el navegador, antes de introducir generación server-side de PDF.

**Rationale**: Menor complejidad, menos dependencias y suficiente para la necesidad inicial.

## Proposed Backend Model Extension

Current approved zoning record should evolve with optional fields:

```py
GeoApprovedZoning
- id
- version
- is_active
- feature_collection_json
- created_at
- restored_from_id?
- display_name?
- comment?
- approved_by?
```

## Proposed Frontend UX Structure

### 2D / 3D controls
- Mantener paneles flotantes, pero con:
  - posiciones más estables
  - estados iniciales minimizados donde corresponda
  - naming consistente
- Acciones clave de zonificación agrupadas:
  - ver estado actual
  - abrir historial
  - exportar
  - imprimir

### Historial
Cada item debería mostrar:
- versión
- fecha
- nombre amigable
- aprobador
- comentario
- badge de activa
- acción restaurar

### Export actions
En el panel de zonificación/historial:
- `Descargar GeoJSON`
- `Imprimir / Exportar PDF`

## Implementation Phases

### Phase A: UX polish
- revisar posiciones de paneles y toggles
- normalizar estados iniciales
- alinear naming 2D/3D

### Phase B: Metadata persistence
- migración de base de datos
- extender schemas/repository/router
- extender hooks/frontend forms

### Phase C: Export/report MVP
- endpoint o acción de descarga GeoJSON
- vista/layout imprimible
- botón de impresión/exportación desde frontend

## Testability Strategy

- Tests backend para:
  - guardar versión con metadatos
  - listar historial enriquecido
  - restaurar sin perder metadatos estructurales
- Tests frontend para:
  - render de historial con campos opcionales
  - export actions visibles según exista o no approved zoning
- Smoke manual para:
  - 2D/3D defaults
  - descarga GeoJSON
  - impresión browser-friendly

## CI / Validation Strategy

- `npm run typecheck`
- tests backend del dominio geo
- validación manual de impresión/export y coherencia visual 2D/3D
