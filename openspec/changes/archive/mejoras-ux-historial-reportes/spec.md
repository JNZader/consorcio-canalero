# Delta Specification: Mejoras UX, historial y reportes

## Purpose

La app MUST ofrecer una experiencia más consistente entre las vistas 2D y 3D, y la zonificación aprobada MUST poder auditarse y compartirse con metadatos y exportaciones mínimas de uso operativo.

## Requirements & Scenarios

### Requirement: Coherent 2D/3D defaults
La app MUST definir defaults claros y consistentes para capas, leyendas y paneles en 2D y 3D.

#### Scenario: Abrir una vista con zonificación aprobada existente
- GIVEN existe una zonificación aprobada activa
- WHEN el usuario entra a la vista 2D o 3D
- THEN la app prioriza visualmente la zonificación aprobada
- AND no muestra por defecto overlays históricos que generen ruido
- AND los paneles flotantes arrancan minimizados o en posiciones coherentes

#### Scenario: Cambiar entre 2D y 3D sin re-aprender controles
- GIVEN el usuario alterna entre Leaflet y MapLibre
- WHEN abre paneles de capas o historial
- THEN encuentra nombres, acciones y jerarquía visual equivalentes
- AND entiende cuál es la capa principal activa en cada vista

### Requirement: Enriched approved-zone history
Cada versión aprobada SHOULD admitir metadatos operativos adicionales.

#### Scenario: Aprobar una nueva versión con contexto
- GIVEN el usuario aprueba una nueva zonificación
- WHEN completa datos opcionales de nombre, comentario y aprobador
- THEN esos metadatos se guardan junto con la nueva versión
- AND quedan visibles en el historial

#### Scenario: Ver historial enriquecido
- GIVEN existen varias versiones aprobadas
- WHEN el usuario abre el historial
- THEN ve al menos número de versión, fecha, nombre amigable, aprobador y comentario si existe
- AND puede distinguir claramente cuál es la activa

### Requirement: Backward compatibility for existing versions
Las versiones ya guardadas MUST seguir funcionando aunque no tengan los nuevos metadatos.

#### Scenario: Mostrar baseline existente
- GIVEN existe una versión anterior creada antes del enriquecimiento
- WHEN el frontend la lista en historial
- THEN la versión sigue visible y restaurable
- AND los metadatos faltantes se muestran como vacíos/opcionales sin romper la UI

### Requirement: Export approved zoning
La app MUST permitir exportar la zonificación aprobada actual desde la fuente persistida en backend.

#### Scenario: Descargar GeoJSON de la zonificación aprobada
- GIVEN existe una zonificación aprobada activa
- WHEN el usuario elige exportar GeoJSON
- THEN se descarga un archivo con el FeatureCollection aprobado actual
- AND el archivo incluye metadatos básicos de versión

#### Scenario: Intentar exportar sin zonificación aprobada
- GIVEN no existe una zonificación aprobada activa
- WHEN el usuario intenta exportar
- THEN la UI informa claramente que no hay una versión aprobada disponible
- AND no falla silenciosamente

### Requirement: Printable/report-friendly output
La app SHOULD ofrecer una salida apta para impresión o PDF.

#### Scenario: Preparar un reporte imprimible
- GIVEN existe una zonificación aprobada activa
- WHEN el usuario elige imprimir/exportar reporte
- THEN la app muestra un layout limpio con mapa y metadatos de versión
- AND el resultado puede imprimirse desde el navegador o exportarse a PDF con fidelidad razonable

### Requirement: Restore remains append-only
La restauración de versiones MUST seguir siendo append-only incluso con metadatos nuevos.

#### Scenario: Restaurar una versión antigua
- GIVEN el usuario restaura una versión histórica
- WHEN el backend crea la nueva versión activa derivada
- THEN la versión restaurada original no se modifica
- AND la nueva versión puede tener metadatos visibles y auditables

## API / Contract Notes

- El contrato de approved zoning SHOULD extenderse con campos opcionales como:
  - `display_name`
  - `comment`
  - `approved_by`
- Los endpoints actuales de `current`, `history` y `restore` MUST seguir funcionando para datos existentes.
- La exportación GeoJSON MAY servirse desde un endpoint dedicado o desde el `current` con cabeceras/formatos de descarga.
