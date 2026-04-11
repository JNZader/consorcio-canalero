# Delta Specification: Análisis automático de cuenca para corredores prioritarios

## Purpose

El sistema MUST poder analizar automáticamente una zona operativa, cuenca o todo el consorcio para proponer corredores/intervenciones prioritarias sin requerir origen y destino manuales.

## Core Concepts

### Analysis Scope
Ámbito geográfico sobre el que corre el análisis automático:
- `zona`
- `cuenca`
- `consorcio`

### Candidate Corridor
Corredor candidato generado automáticamente por el sistema y evaluado con el motor de routing existente.

### Ranked Recommendation
Resultado candidato con score total, breakdown y motivo de priorización.

## Requirements & Scenarios

### Requirement: Automatic basin analysis
El sistema MUST poder ejecutar un análisis automático por ámbito.

#### Scenario: Analizar una zona operativa
- GIVEN una zona operativa válida
- WHEN el operador solicita análisis automático
- THEN el sistema explora candidatos dentro de esa zona
- AND devuelve un ranking de corredores sugeridos

#### Scenario: Analizar una cuenca
- GIVEN una cuenca válida
- WHEN el operador solicita análisis automático
- THEN el sistema genera candidatos sobre la cuenca completa
- AND devuelve un ranking consolidado

### Requirement: No manual origin/destination required
El sistema MUST generar candidatos sin requerir puntos manuales.

#### Scenario: Ejecutar análisis automático
- GIVEN un ámbito válido
- WHEN se lanza el análisis
- THEN el request no requiere `from_lon/from_lat/to_lon/to_lat`
- AND el sistema deriva internamente pares/corredores candidatos

### Requirement: Reuse routing engine
El sistema SHOULD reutilizar el corridor routing ya existente.

#### Scenario: Evaluar un candidato
- GIVEN un candidato detectado automáticamente
- WHEN se evalúa
- THEN el sistema puede correr el motor `network` o `raster`
- AND devuelve centerline/corridor/summary bajo el contrato existente o derivado

### Requirement: Ranking and explainability
El sistema MUST rankear y explicar los candidatos.

#### Scenario: Revisar ranking
- GIVEN un análisis automático exitoso
- WHEN el operador revisa los resultados
- THEN cada candidato incluye score total
- AND breakdown por criterios
- AND justificación entendible

### Requirement: Clear no-route signaling
El sistema MUST distinguir candidatos inválidos de candidatos válidos.

#### Scenario: Candidato sin ruta útil
- GIVEN un candidato que no produce route usable
- WHEN el backend lo evalúa
- THEN el resultado se marca explícitamente como `unroutable` o equivalente
- AND la UI no lo muestra como una ruta de 0 m válida

### Requirement: Automatic-analysis UI workflow
La UI MUST ofrecer el análisis automático como flujo principal.

#### Scenario: Usar la pantalla de sugerencias de red
- GIVEN el panel admin de sugerencias de red
- WHEN el operador entra al módulo
- THEN puede lanzar “Analizar cuenca automáticamente”
- AND ve ranking, mapa y detalle de candidatos
- AND el flujo manual queda disponible como opción secundaria

### Requirement: Persisted analysis batches
El sistema SHOULD poder guardar el lote de análisis.

#### Scenario: Guardar un análisis automático
- GIVEN un ranking ya generado
- WHEN el operador decide conservarlo
- THEN el sistema persiste el batch y sus candidatos
- AND luego se puede reabrir desde la UI

## API Notes

### Proposed endpoints
- `POST /api/v2/geo/routing/auto-analysis`
- `GET /api/v2/geo/routing/auto-analysis/{id}`
- `GET /api/v2/geo/routing/auto-analysis/{id}/candidates`

### Proposed request fields
- `scope_type` (`zona|cuenca|consorcio`)
- `scope_id` (nullable for consorcio)
- `mode` (`network|raster`)
- `profile`
- `max_candidates`
- `weights` (optional)

### Proposed response fields
- `analysis_id`
- `scope`
- `summary`
- `candidates`
- `ranking`
- `stats`

