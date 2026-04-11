# Design: Análisis automático de cuenca para corredores prioritarios

## Technical Approach

La nueva feature se apoya en el corridor routing ya implementado, pero agrega una capa previa de:
1. detección de candidatos automáticos
2. evaluación batch
3. ranking operativo

## Architecture Decisions

### Decision: Keep manual and automatic flows separate
**Choice**: mantener el corridor manual actual y agregar un flujo automático paralelo.

**Rationale**: el manual sigue siendo útil para pruebas y casos guiados, pero el automático será el flujo principal para operación territorial.

### Decision: Candidate generation before routing
**Choice**: primero detectar pares/corredores candidatos a partir del ámbito, luego correr el motor existente por candidato.

**Rationale**: desacopla la heurística territorial del motor de routing y permite iterar el ranking sin reescribir todo el pipeline.

### Decision: Explicit unroutable candidate state
**Choice**: introducir un estado explícito para candidatos sin ruta útil.

**Rationale**: evita mostrar resultados engañosos como `0 m / 0 edges`.

### Decision: Batch summary + candidate detail
**Choice**: devolver tanto un resumen del análisis completo como una lista de candidatos detallados.

**Rationale**: el usuario necesita ver panorama general y también abrir cada candidato en detalle.

## Proposed Backend Changes

### New support module
Agregar un módulo tipo `routing_auto_analysis.py` para:
- recortar por ámbito
- detectar gaps/zonas críticas
- proponer candidatos
- evaluar candidatos con `corridor_routing(...)`
- rankear resultados

### Candidate generation heuristics
Primera versión:
- usar zonas con criticidad/riesgo alto
- usar gaps entre tramos de red cercanos
- usar proximidad a puntos de conflicto / sugerencias existentes
- priorizar candidatos dentro del límite del ámbito

### Ranking model
Score compuesto por:
- viabilidad de ruteo
- longitud/costo
- beneficio hídrico estimado
- afectación parcelaria
- prioridad del área

### UI changes
En `CanalSuggestionsPanel`:
- bloque principal “Análisis automático de cuenca”
- selector de ámbito
- selector de modo/perfil
- botón de análisis batch
- tabla/lista de candidatos
- acción “abrir en mapa” para cargar un candidato sobre el visor existente
- el card de corridor manual queda como avanzado/secundario

## Data Flow

```text
scope -> candidate generation -> candidate list
      -> corridor_routing(candidate_1)
      -> corridor_routing(candidate_2)
      -> ...
      -> scoring/ranking -> UI batch summary + map detail
```

## TDD Strategy

### Unit tests first
- generación de candidatos por ámbito
- ranking y score ordering
- casos `unroutable`
- contratos del batch analysis endpoint

### Then implementation
- support module de auto-analysis
- endpoint backend
- integración en controller/frontend admin

## Rollout

### Phase A
- análisis automático sobre zonas/cuencas con top-N candidatos
- UI básica de ranking

### Phase B
- persistencia de batch
- reapertura/caching
- aprobaciones sobre candidatos recomendados

