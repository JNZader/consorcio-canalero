# Tasks: Análisis automático de cuenca para corredores prioritarios

## Overview

**Total Tasks**: 10  
**Phases**: 4 (SDD → Backend batch → Frontend workflow → Validación)  
**Goal**: convertir el corredor manual en un sistema de análisis automático por cuenca/zona/consorcio.

---

## Phase 1: SDD

- [x] **1.1 Crear proposal/spec/design/tasks del cambio**
  - **AC**:
    - existe `openspec/changes/auto-corridor-basin-analysis/`
  - **Dependencies**: None

## Phase 2: Backend automatic analysis

- [x] **2.1 Diseñar contrato de `auto-analysis`**
  - **AC**:
    - request soporta ámbito + modo + perfil
    - response incluye batch summary + candidates
  - **Dependencies**: 1.1

- [x] **2.2 Implementar generación automática de candidatos**
  - **AC**:
    - el sistema genera candidatos sin puntos manuales
    - respeta el ámbito seleccionado
  - **Dependencies**: 2.1

- [x] **2.3 Evaluar candidatos con el motor de corridor routing**
  - **AC**:
    - cada candidato produce resultado válido o `unroutable`
  - **Dependencies**: 2.2

- [x] **2.4 Implementar ranking explicable**
  - **AC**:
    - los candidatos vienen ordenados por score
    - el breakdown es entendible en UI
  - **Dependencies**: 2.3

- [x] **2.5 Exponer endpoint backend**
  - **AC**:
    - existe endpoint `POST /geo/routing/auto-analysis`
  - **Dependencies**: 2.4

## Phase 3: Frontend workflow

- [x] **3.1 Crear flujo principal de análisis automático en admin**
  - **AC**:
    - el usuario puede lanzar análisis por ámbito
    - el flujo manual queda secundario
  - **Dependencies**: 2.5

- [x] **3.2 Mostrar ranking + detalle en mapa**
  - **AC**:
    - cada candidato puede abrirse sobre el mapa
    - la UI distingue candidatos inválidos
  - **Dependencies**: 3.1

- [x] **3.3 Permitir guardar/reusar candidatos recomendados**
  - **AC**:
    - candidatos seleccionados pueden persistirse como escenarios
  - **Dependencies**: 3.2

## Phase 4: Validation

- [x] **4.1 Escribir TDD de backend auto-analysis**
  - **AC**:
    - tests unitarios/contract en verde
  - **Dependencies**: 2.5

- [x] **4.2 Escribir tests frontend del flujo automático**
  - **AC**:
    - tests de controller/UI en verde
  - **Dependencies**: 3.3

- [ ] **4.3 Verificar UX operativa**
  - **AC**:
    - no se obliga a elegir origen/destino manual para el caso principal
    - el sistema explica resultados vacíos o inválidos
  - **Dependencies**: 4.1, 4.2
