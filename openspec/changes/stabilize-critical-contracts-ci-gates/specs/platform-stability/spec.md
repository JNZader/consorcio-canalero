# Platform Stability Specification

## Purpose

Definir el comportamiento obligatorio para estabilizar contratos API criticos, alinear datos de tramites y sugerencias, y convertir CI en un gate bloqueante con TDD + mutation testing.

## Requirements

### Requirement: Contrato canonico para resolver reportes

El sistema MUST exponer y consumir un contrato unico para `reports/resolve` entre frontend y backend. La operacion SHALL estar documentada en OpenAPI real y validada por pruebas de contrato.

#### Scenario: Resolucion de reporte con payload valido

- GIVEN un reporte pendiente existente
- WHEN el cliente frontend invoca `reports/resolve` con payload canonico
- THEN el backend responde `2xx` con estructura de respuesta canonica
- AND el estado del reporte queda actualizado de forma consistente

#### Scenario: Payload incompatible con contrato

- GIVEN un cliente que envia campos fuera del contrato
- WHEN se ejecuta `reports/resolve`
- THEN el backend responde `4xx` con error de validacion estructurado
- AND CI detecta el desvio por test de contrato

### Requirement: Tramites alineados de punta a punta

El sistema MUST mantener un catalogo canonico de estados de tramites consistente en UI, schemas backend y migraciones SQL.

#### Scenario: Alta de tramite con estado permitido

- GIVEN un estado incluido en el catalogo canonico
- WHEN se crea o actualiza un tramite
- THEN frontend, backend y DB aceptan el mismo valor sin transformaciones ambiguas

#### Scenario: Estado no canonico

- GIVEN un estado fuera del catalogo canonico
- WHEN se intenta persistir un tramite
- THEN la validacion lo rechaza con mensaje explicito
- AND no se escribe estado invalido en base de datos

### Requirement: Sugerencias sin drift de schema

El sistema MUST alinear endpoints, schemas y migraciones del modulo sugerencias bajo un modelo de datos unico.

#### Scenario: Flujo sugerencia en setup limpio

- GIVEN una base inicializada con migraciones vigentes
- WHEN se crea, consulta y actualiza una sugerencia
- THEN todas las operaciones completan sin errores de columnas/campos faltantes

#### Scenario: Ejecucion sobre esquema viejo

- GIVEN una instancia en version previa compatible
- WHEN se aplican migraciones de upgrade
- THEN la transicion conserva datos validos o aplica defaults explicitados
- AND el backend opera con el nuevo contrato sin fallback silencioso

### Requirement: CI bloqueante para calidad minima

El sistema SHALL bloquear merge/deploy cuando fallen lint, typecheck, tests, contract checks o mutation thresholds definidos.

#### Scenario: Fallo de calidad en PR

- GIVEN una PR con errores de tests o mutation score por debajo del umbral
- WHEN se ejecuta CI
- THEN el workflow falla sin `continue-on-error`
- AND la rama no queda habilitada para merge

#### Scenario: Deploy condicionado

- GIVEN un pipeline de deploy
- WHEN algun check previo falla
- THEN el despliegue no se ejecuta

### Requirement: Estrategia TDD obligatoria por historia

El equipo MUST ejecutar cada historia en ciclo RED/GREEN/REFACTOR con evidencia trazable en commits o tareas.

#### Scenario: Implementacion de historia critica

- GIVEN una tarea activa de reportes, tramites, sugerencias o CI
- WHEN se implementa el cambio
- THEN primero se agrega test fallando (RED)
- AND luego se implementa lo minimo para pasar (GREEN)
- AND finalmente se refactoriza manteniendo tests en verde (REFACTOR)

### Requirement: Mutation testing incremental backend y frontend

El sistema SHOULD ejecutar mutation testing en modulos criticos con politica incremental de umbrales y enforcement en CI.

#### Scenario: Mutation score debajo del umbral

- GIVEN una PR que modifica modulos en scope de mutation
- WHEN backend o frontend obtienen score menor al umbral
- THEN CI falla y exige reforzar tests

#### Scenario: Adopcion inicial por alcance acotado

- GIVEN etapa inicial de adopcion
- WHEN se ejecuta mutation testing
- THEN solo cubre dominios criticos (`reports`, `tramites`, `sugerencias`, `api clients`)
- AND el resto del codigo queda fuera temporalmente con backlog explicito
