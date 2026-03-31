# Delta Specification: Sugerencias con líneas para canales

## Purpose

El sistema MUST permitir que una sugerencia creada desde `/sugerencias` incluya geometría lineal opcional para marcar canales, prolongaciones o correcciones sobre el mapa.

## Core Model

### Text Suggestion
Sugerencia común sin geometría.

### Geometric Suggestion
Sugerencia que incluye una o más líneas GeoJSON asociadas.

### Official Existing Channel
Canal validado que forma parte de la capa `Canales existentes`.

## Requirements & Scenarios

### Requirement: Optional line geometry in suggestions
Una sugerencia MUST poder incluir líneas, pero la geometría MUST ser opcional.

#### Scenario: Enviar sugerencia textual sin geometría
- GIVEN un usuario en `/sugerencias`
- WHEN completa solo los campos textuales
- THEN la sugerencia se crea correctamente
- AND el sistema se comporta como hoy

#### Scenario: Enviar sugerencia con línea
- GIVEN un usuario en `/sugerencias`
- WHEN dibuja una línea y completa los datos requeridos
- THEN la sugerencia se crea correctamente
- AND la geometría queda guardada junto a la sugerencia

### Requirement: Basic line editing before submit
El usuario MUST poder corregir la línea antes de enviarla.

#### Scenario: Ajustar un canal olvidado antes de guardar
- GIVEN el usuario dibujó una línea aproximada
- WHEN mueve vértices o rehace el trazado
- THEN la línea final reflejada en la sugerencia es la corregida

### Requirement: Geometry validation
El sistema MUST validar que la geometría lineal sea razonable.

#### Scenario: Línea inválida
- GIVEN una sugerencia con geometría vacía o con menos de dos vértices útiles
- WHEN el usuario intenta enviarla
- THEN el sistema rechaza el envío geométrico
- AND muestra un mensaje claro

### Requirement: Admin visibility of suggested geometry
Admin MUST poder revisar la línea adjunta en el flujo administrativo.

#### Scenario: Ver sugerencia con línea en admin
- GIVEN existe una sugerencia con geometría lineal
- WHEN un operador/admin la abre
- THEN puede ver la línea en contexto
- AND puede distinguirla de una sugerencia solo textual

### Requirement: Clear separation from official channels
Una sugerencia geométrica MUST NOT convertirse automáticamente en `Canales existentes`.

#### Scenario: Sugerencia revisada pero no oficial
- GIVEN una sugerencia con línea ya enviada
- WHEN se visualiza en el sistema
- THEN queda marcada como propuesta pendiente
- AND no modifica automáticamente la capa oficial de canales existentes

### Requirement: Initial operational use case
El sistema SHOULD facilitar agregar un canal faltante mediante sugerencia geométrica.

#### Scenario: Registrar un canal olvidado
- GIVEN el usuario olvidó incluir un canal en `Canales existentes`
- WHEN entra a `/sugerencias` y dibuja ese canal
- THEN puede enviarlo como sugerencia geométrica
- AND queda disponible para revisión y posterior incorporación manual

## UX Notes

- El editor debe priorizar una herramienta de línea clara y simple.
- Debe ser evidente cuándo se está en modo dibujo y cuándo se está editando texto.
- La UI debe comunicar que la línea es sugerida/pediente, no oficial.
- El primer caso de uso es operativo, no cartográfico avanzado.

## API / Contract Notes

- El payload de creación pública de sugerencias SHOULD aceptar un campo opcional `geometry` o `geojson`.
- La geometría SHOULD almacenarse como GeoJSON de tipo `FeatureCollection` o lista de `LineString`.
- La lectura en admin SHOULD devolver esa geometría sin romper compatibilidad con sugerencias viejas.
