# Tasks: Sugerencias con líneas para canales

## Overview

**Total Tasks**: 10  
**Phases**: 4 (Modelo → Formulario → Admin → Validación)  
**Goal**: Permitir adjuntar líneas GeoJSON a sugerencias, empezando por el caso de un canal faltante.

---

## Phase 1: Modelo y contrato

- [ ] **1.1 Definir contrato de geometría opcional en sugerencias**
  - **AC**:
    - el payload de creación acepta geometría opcional
    - mantiene compatibilidad con sugerencias textuales existentes
  - **Dependencies**: None

- [ ] **1.2 Extender modelo/persistencia de sugerencias**
  - **AC**:
    - puede guardarse GeoJSON lineal asociado a una sugerencia
    - la lectura devuelve la geometría cuando existe
  - **Dependencies**: 1.1

- [ ] **1.3 Definir etiquetado de estado “propuesta no oficial”**
  - **AC**:
    - queda claro en contrato/UI que no modifica `Canales existentes`
  - **Dependencies**: 1.2

---

## Phase 2: Formulario `/sugerencias`

- [ ] **2.1 Agregar editor simple de líneas en `/sugerencias`**
  - **AC**:
    - permite dibujar una o más líneas
    - permite limpiar y rehacer
  - **Dependencies**: 1.1

- [ ] **2.2 Permitir edición básica antes de enviar**
  - **AC**:
    - se pueden mover/corregir vértices o rehacer el trazo
  - **Dependencies**: 2.1

- [ ] **2.3 Integrar envío de geometría con el formulario actual**
  - **AC**:
    - la sugerencia textual sigue funcionando
    - la sugerencia con línea también se envía correctamente
  - **Dependencies**: 2.1, 1.2

- [ ] **2.4 Validar geometría y mensajes de error**
  - **AC**:
    - no se aceptan líneas inválidas
    - la UI explica cómo corregir el problema
  - **Dependencies**: 2.3

---

## Phase 3: Revisión administrativa

- [ ] **3.1 Mostrar indicador de sugerencias con geometría en admin**
  - **AC**:
    - una sugerencia con línea se distingue visualmente
  - **Dependencies**: 1.2

- [ ] **3.2 Mostrar la línea en detalle/admin**
  - **AC**:
    - admin puede ver la geometría sobre mapa o visor adecuado
    - puede compararla con `Canales existentes`
  - **Dependencies**: 3.1, 2.3

---

## Phase 4: Verificación del caso inicial

- [ ] **4.1 Verificar el flujo de “canal olvidado” extremo a extremo**
  - **AC**:
    - un usuario puede dibujar un canal faltante en `/sugerencias`
    - admin puede revisarlo sin mezclarlo automáticamente con datos oficiales
  - **Dependencies**: 2.4, 3.2
