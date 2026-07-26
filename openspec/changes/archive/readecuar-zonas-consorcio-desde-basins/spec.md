# Delta Specification: Readecuar zonas del consorcio desde basins

## Purpose

El sistema MUST poder generar una propuesta inicial de nuevas zonas del consorcio agrupando `basins`, pero esa propuesta MUST ser editable por el usuario antes de quedar aprobada como nueva zonificación operativa.

## Core Model

### Basin
Unidad mínima operativa/hidrológica existente.

### Proposed Zone
Agrupación sugerida de una o más basins, editable.

### Approved Zone
Agrupación ya validada por el usuario y publicada como zonificación vigente.

## Requirements & Scenarios

### Requirement: Suggested grouping from basins
El sistema MUST poder producir una sugerencia inicial de agrupación de basins.

#### Scenario: Generar propuesta inicial
- GIVEN existen basins operativas disponibles
- WHEN el usuario solicita readecuar zonas del consorcio
- THEN el sistema genera una propuesta de agrupación
- AND cada basin pertenece a exactamente una zona sugerida
- AND la propuesta queda identificada como editable/no aprobada

### Requirement: Transparent grouping criteria
La sugerencia SHOULD basarse en criterios explícitos y revisables.

#### Scenario: Auditar por qué una basin quedó en una zona sugerida
- GIVEN una propuesta de nuevas zonas ya generada
- WHEN un desarrollador o usuario avanzado revisa la documentación o metadatos
- THEN puede entender el criterio principal de agrupación
- AND puede revisar o cuestionar la propuesta

### Requirement: Manual reassignment of basins
El usuario MUST poder corregir la propuesta automática.

#### Scenario: Mover una basin a otra zona
- GIVEN una propuesta de zonas sugeridas
- WHEN el usuario detecta que una basin debería pertenecer a otra zona
- THEN puede reasignarla manualmente
- AND la composición de ambas zonas se actualiza
- AND el resultado sigue siendo válido

### Requirement: Merge and split suggested zones
El usuario MUST poder ajustar el tamaño operativo de las zonas.

#### Scenario: Unir dos zonas sugeridas
- GIVEN dos zonas sugeridas contiguas o relacionadas operativamente
- WHEN el usuario decide unificarlas
- THEN el sistema crea una sola zona resultante
- AND conserva trazabilidad de qué basins la componen

#### Scenario: Dividir una zona sugerida
- GIVEN una zona sugerida demasiado grande o incómoda operativamente
- WHEN el usuario decide dividirla
- THEN el sistema permite separar sus basins en dos o más zonas nuevas

### Requirement: Editable metadata
El usuario MUST poder adaptar la nomenclatura operativa.

#### Scenario: Renombrar zona sugerida
- GIVEN una zona sugerida recién creada
- WHEN el usuario modifica su nombre
- THEN el nuevo nombre se guarda en el draft
- AND no afecta todavía las zonas aprobadas vigentes

### Requirement: Draft vs approved separation
El sistema MUST separar propuesta editable de zonificación aprobada.

#### Scenario: Guardar draft sin publicar
- GIVEN el usuario ajustó parcialmente la propuesta
- WHEN guarda cambios sin aprobar
- THEN la propuesta queda persistida como draft
- AND la zonificación vigente no cambia

#### Scenario: Aprobar nueva zonificación
- GIVEN el usuario terminó de revisar la propuesta
- WHEN confirma la aprobación
- THEN la nueva agrupación pasa a ser zonificación vigente
- AND queda disponible para 2D/3D como capa aprobada

### Requirement: Transitional coexistence
El sistema SHOULD permitir comparar durante la transición.

#### Scenario: Ver manual vs nueva zonificación
- GIVEN existe una propuesta o una nueva zonificación aprobada
- WHEN el usuario visualiza capas en el mapa
- THEN puede distinguir la capa manual anterior de la nueva zonificación derivada de basins
- AND no se pierde referencia histórica durante la transición

## UX Notes

- La agrupación automática debe presentarse como “sugerida”, no como definitiva.
- La edición debe minimizar fricción: mover basin, unir zonas, dividir zonas, renombrar.
- La aprobación debe ser una acción explícita.

## API / Contract Notes

- La persistencia SHOULD modelar al menos dos estados: `draft` y `approved`.
- La capa aprobada SHOULD ser consumible por 2D y 3D igual que otras capas vectoriales.
- El modelo SHOULD conservar trazabilidad de qué basins componen cada zona.
