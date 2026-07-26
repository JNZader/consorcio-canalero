# Tasks: Corridor routing para trazado de canales

## Overview

**Total Tasks**: 8  
**Phases**: 3 (Spec/TDD → Backend MVP → Validación)  
**Goal**: agregar un endpoint backend de corridor routing sobre la red existente, con centerline, corredor y alternativas.

---

## Phase 1: SDD + TDD base

- [x] **1.1 Documentar proposal/spec/design/tasks**
  - **AC**:
    - existe change SDD completo en `openspec/changes/corredor-routing-canales`
  - **Dependencies**: None

- [x] **1.2 Escribir tests unitarios del contrato corridor**
  - **AC**:
    - hay tests para helpers puros
    - hay tests para endpoint con mocks
  - **Dependencies**: 1.1

---

## Phase 2: Backend MVP

- [x] **2.1 Implementar helpers puros de centerline/corridor**
  - **AC**:
    - se arma FeatureCollection de centerline
    - se arma polígono de corredor desde edges
  - **Dependencies**: 1.2

- [x] **2.2 Implementar shortest path con penalizaciones**
  - **AC**:
    - se pueden calcular alternativas con edge penalties
  - **Dependencies**: 1.2

- [x] **2.3 Implementar orquestador `corridor_routing`**
  - **AC**:
    - resuelve source/target
    - calcula centerline, corridor y alternativas
  - **Dependencies**: 2.1, 2.2

- [x] **2.4 Exponer endpoint `/routing/corridor`**
  - **AC**:
    - request/response válidos
    - contrato usable por frontend
  - **Dependencies**: 2.3

---

## Phase 3: Validación

- [x] **3.1 Ejecutar tests focalizados del nuevo módulo**
  - **AC**:
    - tests unitarios nuevos en verde
  - **Dependencies**: 2.4

- [x] **3.2 Verificar compatibilidad con shortest-path existente**
  - **AC**:
    - no se rompen tests del routing actual
  - **Dependencies**: 3.1

## Phase 4: Profiles operativos

- [x] **4.1 Agregar perfiles nombrados en backend**
  - **AC**:
    - existen perfiles `balanceado`, `hidraulico`, `evitar_propiedad`
    - resuelven defaults de ancho, alternativas y penalización
  - **Dependencies**: 2.4

- [x] **4.2 Exponer perfil en contrato frontend/backend**
  - **AC**:
    - request acepta `profile`
    - response summary devuelve perfil y penalización efectiva
  - **Dependencies**: 4.1

- [x] **4.3 Integrar selector de perfil en UI admin**
  - **AC**:
    - el usuario puede elegir perfil sin editar parámetros finos
    - el formulario aplica presets al cambiar perfil
  - **Dependencies**: 4.2

- [x] **4.4 Validar con tests focalizados**
  - **AC**:
    - tests backend y frontend del corridor routing siguen verdes
  - **Dependencies**: 4.3

## Phase 5: Persistencia y reutilización

- [x] **5.1 Persistir escenarios de corridor routing**
  - **AC**:
    - existe tabla dedicada para escenarios
    - se pueden guardar request + result + perfil
  - **Dependencies**: 4.4

- [x] **5.2 Exponer listado/detalle/export GeoJSON**
  - **AC**:
    - backend lista escenarios
    - backend devuelve detalle
    - backend exporta centerline/corridor/alternatives como FeatureCollection
  - **Dependencies**: 5.1

- [x] **5.3 Integrar historial guardado en frontend**
  - **AC**:
    - se puede guardar escenario desde la UI
    - se puede volver a cargar escenario guardado
    - la UI muestra alternativas y desglose explicable
  - **Dependencies**: 5.2

## Phase 6: Aprobación y exportes

- [x] **6.1 Marcar escenarios como aprobados**
  - **AC**:
    - el escenario persistido guarda estado de aprobación
    - se registra fecha y usuario aprobador
    - la UI distingue borrador vs aprobado
  - **Dependencies**: 5.3

- [x] **6.2 Exportar escenarios a PDF**
  - **AC**:
    - backend expone export PDF por escenario
    - frontend permite descargar el PDF desde historial
  - **Dependencies**: 6.1

## Phase 7: Raster corridor real y E2E

- [x] **7.1 Agregar modo raster multi-criterio**
  - **AC**:
    - request acepta `mode`
    - el backend soporta `mode=raster`
    - el costo raster combina pendiente, hidrología y propiedad
  - **Dependencies**: 6.2

- [x] **7.2 Cubrir el flujo completo con E2E**
  - **AC**:
    - existe un test E2E del flujo corridor
    - valida cálculo, guardado, aprobación y exportes
  - **Dependencies**: 7.1
