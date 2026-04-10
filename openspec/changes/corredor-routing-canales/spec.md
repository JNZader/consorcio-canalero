# Delta Specification: Corridor routing para trazado de canales

## Purpose

El sistema MUST poder calcular un **corredor de routing** entre dos puntos apoyándose en la red de canales existente, devolviendo una ruta central, un polígono de corredor y alternativas usables para revisión operativa.

## Core Concepts

### Centerline
Ruta principal derivada de shortest path sobre la red.

### Corridor
Polígono derivado de la centerline con un ancho configurable.

### Alternative Route
Ruta adicional calculada penalizando edges ya usados por soluciones previas.

## Requirements & Scenarios

### Requirement: Corridor routing endpoint
El sistema MUST exponer un endpoint para calcular corridor routing.

#### Scenario: Solicitar corridor entre dos puntos
- GIVEN un origen y un destino válidos
- WHEN el operador solicita corridor routing
- THEN el sistema devuelve una centerline
- AND devuelve un polígono de corredor
- AND incluye metadatos de distancia total y número de edges

### Requirement: Configurable corridor width
El sistema MUST permitir definir el ancho del corredor.

#### Scenario: Cambiar ancho del corredor
- GIVEN una ruta calculada
- WHEN el usuario envía un ancho distinto
- THEN el polígono resultante se recalcula con ese ancho
- AND la centerline no cambia por ese motivo

### Requirement: Alternative routes
El sistema SHOULD devolver rutas alternativas.

#### Scenario: Pedir alternativas
- GIVEN que existe una ruta principal
- WHEN el usuario pide alternativas
- THEN el sistema devuelve hasta N alternativas
- AND cada alternativa incluye su propio resumen
- AND el sistema evita reutilizar exactamente el mismo conjunto de edges si es posible

### Requirement: Explainable response
La respuesta MUST ser interpretable por frontend y auditoría técnica.

#### Scenario: Inspeccionar respuesta del corridor
- GIVEN una respuesta exitosa
- WHEN se revisa el payload
- THEN contiene `source`, `target`, `centerline`, `corridor`, `alternatives`
- AND cada ruta incluye `edge_ids`, `edges`, `total_distance_m`

### Requirement: Backward compatibility
La nueva funcionalidad MUST NOT romper el shortest-path existente.

#### Scenario: Seguir usando shortest path
- GIVEN clientes existentes del endpoint actual
- WHEN continúan usando shortest path
- THEN el comportamiento previo se mantiene intacto

### Requirement: Named routing profiles
El sistema MUST soportar perfiles de routing predefinidos para facilitar configuraciones operativas comunes.

#### Scenario: Usar perfil balanceado
- GIVEN un operador que no quiere ajustar parámetros finos
- WHEN solicita corridor routing con perfil `balanceado`
- THEN el sistema aplica defaults generales para ancho, alternativas y penalización

#### Scenario: Usar perfil hidraulico
- GIVEN un operador que prioriza un corredor más amplio y conservador
- WHEN solicita corridor routing con perfil `hidraulico`
- THEN el sistema aplica defaults del perfil hidráulico
- AND los devuelve en el resumen de la respuesta

#### Scenario: Usar perfil evitar_propiedad
- GIVEN un operador que quiere explorar más desvíos
- WHEN solicita corridor routing con perfil `evitar_propiedad`
- THEN el sistema aplica defaults del perfil de evitación
- AND los devuelve en el resumen de la respuesta

### Requirement: Persisted corridor scenarios
El sistema MUST permitir guardar y recuperar escenarios de corridor routing.

#### Scenario: Guardar un escenario calculado
- GIVEN un corridor routing ya calculado
- WHEN el operador guarda el escenario
- THEN el sistema persiste nombre, perfil, request y resultado
- AND el escenario queda disponible para recarga posterior

#### Scenario: Exportar un escenario guardado
- GIVEN un escenario persistido
- WHEN el operador pide su export GeoJSON
- THEN el sistema devuelve una `FeatureCollection`
- AND incluye centerline, corridor y alternativas etiquetadas

### Requirement: Scenario approval workflow
El sistema MUST permitir marcar escenarios guardados como aprobados.

#### Scenario: Aprobar un escenario
- GIVEN un escenario persistido
- WHEN un operador lo marca como aprobado
- THEN el sistema guarda `is_approved = true`
- AND registra fecha y usuario aprobador
- AND el escenario aprobado se refleja en el historial de UI

### Requirement: PDF export
El sistema MUST permitir exportar escenarios guardados a PDF.

#### Scenario: Exportar escenario a PDF
- GIVEN un escenario persistido
- WHEN el operador solicita export PDF
- THEN el sistema devuelve un documento PDF descargable
- AND el documento incluye parámetros, resumen, desglose de costo y alternativas

### Requirement: Raster multi-criteria corridor mode
El sistema MUST soportar un modo raster real además del routing sobre red.

#### Scenario: Solicitar corridor en modo raster
- GIVEN un origen y destino válidos y un raster de pendiente disponible
- WHEN el operador solicita corridor routing con `mode = raster`
- THEN el sistema calcula un least-cost path raster
- AND combina pendiente, hidrología y propiedad en la superficie de costo
- AND devuelve centerline, corridor y resumen bajo el mismo contrato general

## UX / Contract Notes

- La respuesta debe ser directamente renderizable como GeoJSON.
- El `corridor` debe representarse como `Feature` o `FeatureCollection` poligonal.
- Las alternativas deben venir ordenadas por costo ascendente.

## API Notes

### Proposed endpoint
- `POST /api/v2/geo/routing/corridor`

### Proposed request fields
- `from_lon`
- `from_lat`
- `to_lon`
- `to_lat`
- `corridor_width_m`
- `alternative_count`
- `penalty_factor`
- `profile`

### Proposed response fields
- `source`
- `target`
- `centerline`
- `corridor`
- `alternatives`
- `summary`
