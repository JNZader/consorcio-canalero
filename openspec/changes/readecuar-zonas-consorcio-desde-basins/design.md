# Design: Readecuar zonas del consorcio desde basins

## Technical Approach

La solución debe separar claramente tres niveles:

1. **Basins base**
   - fuente existente y estable
   - unidad mínima no editable en este flujo

2. **Draft zoning proposal**
   - agrupación sugerida inicial
   - editable por el usuario
   - no reemplaza todavía la zonificación vigente

3. **Approved zoning**
   - agrupación confirmada
   - nueva capa operativa oficial

## Architecture Decisions

### Decision: Assisted semimanual workflow
**Choice**: generar una propuesta automática inicial, pero exigir edición/aprobación explícita.

**Rationale**: Es lo que el usuario pidió y además evita errores de una agrupación 100% automática sin contexto operativo.

### Decision: Basins as immutable base units
**Choice**: no editar geometrías de basins durante esta etapa; solo agruparlas.

**Rationale**: simplifica el modelo y permite trazabilidad clara.

### Decision: Draft/approved persistence
**Choice**: guardar propuestas como drafts versionables y solo promover una a approved al publicar.

**Rationale**: permite iterar sin romper la operación diaria.

## Proposed Backend Model

```text
Basin
ZoneGroupingDraft
ZoneGroupingDraftItem (draft_id, basin_id, proposed_zone_id)
ApprovedZoneSet
ApprovedZoneItem (approved_set_id, basin_id, zone_id)
```

### Suggested minimum fields

#### ZoneGroupingDraft
- `id`
- `name`
- `status` = `draft`
- `created_at`
- `updated_at`
- `suggestion_method`

#### ProposedZone
- `id`
- `draft_id`
- `name`
- `color`
- `order`

#### ProposedZoneMembership
- `proposed_zone_id`
- `basin_id`

#### ApprovedZoneSet
- `id`
- `name`
- `status` = `approved`
- `approved_at`

## Suggestion Strategy

Primera versión: heurística simple y explicable.

Posibles reglas:
- contigüidad espacial entre basins
- equilibrio básico de tamaño/superficie
- continuidad de operación en territorio
- posibilidad futura de ponderar por caminos/infraestructura

La heurística inicial debe priorizar simplicidad sobre “optimalidad”.

## Proposed UI Flow

### Step 1: Generate proposal
- botón “Generar propuesta desde basins”
- devuelve draft con zonas sugeridas

### Step 2: Review and edit
- mapa 2D como entorno principal de edición
- cada basin coloreada por zona sugerida
- panel lateral con:
  - listado de zonas sugeridas
  - cantidad de basins por zona
  - superficie agregada
  - acciones: renombrar, unir, dividir

### Step 3: Reassign basin
- seleccionar basin
- elegir nueva zona destino

### Step 4: Approve
- publicar draft como nueva zonificación aprobada
- mantener visible la manual como referencia mientras se decida retirarla

## 2D / 3D Rendering Strategy

### 2D
- editor principal
- mejor para selección fina y revisión

### 3D
- visualización de resultado aprobado o draft
- no necesariamente editor principal en primera etapa

## Validation Strategy

- tests de consistencia:
  - cada basin pertenece a una sola zona por draft
  - no quedan basins huérfanas
  - merge/split preservan cobertura total
- smoke manual:
  - generar propuesta
  - mover una basin
  - renombrar zona
  - aprobar zonificación

## Migration Strategy

1. Mantener zonas manuales actuales.
2. Incorporar draft/propuesta como capa nueva.
3. Aprobar una nueva zonificación.
4. Recién entonces decidir si la manual se oculta, archiva o sigue como referencia.
