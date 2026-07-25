# Tasks: Readecuar zonas del consorcio desde basins

## Overview

**Total Tasks**: 12  
**Phases**: 4 (Modelo → Sugerencia → Edición → Publicación)  
**Goal**: Reemplazar progresivamente la zonificación manual por zonas agrupadas desde basins con sugerencia automática editable.

---

## Phase 1: Modelo y contratos

- [ ] **1.1 Definir modelo draft/approved para zonificación derivada**
  - **AC**:
    - existe modelo conceptual o persistente para drafts y aprobadas
    - queda trazabilidad basin -> zona
  - **Dependencies**: None

- [ ] **1.2 Definir contrato backend/frontend para propuestas de zonas**
  - **AC**:
    - existe payload para draft zoning proposal
    - incluye zonas sugeridas y membresías de basins
  - **Dependencies**: 1.1

- [ ] **1.3 Documentar coexistencia de zonas manuales y zonas derivadas**
  - **AC**:
    - queda claro qué capa es vigente, cuál es draft y cuál histórica
  - **Dependencies**: 1.1

---

## Phase 2: Generación de propuesta automática

- [ ] **2.1 Implementar heurística inicial de agrupación de basins**
  - **AC**:
    - el sistema puede producir una propuesta inicial reproducible
    - cada basin queda asignada a una sola zona sugerida
  - **Dependencies**: 1.1, 1.2

- [ ] **2.2 Exponer endpoint/acción para generar propuesta**
  - **AC**:
    - puede invocarse desde UI o admin flow
    - devuelve draft utilizable
  - **Dependencies**: 2.1

- [ ] **2.3 Mostrar propuesta inicial en el mapa**
  - **AC**:
    - la propuesta se visualiza distinta de la manual
    - se entiende qué basin pertenece a qué zona sugerida
  - **Dependencies**: 2.2

---

## Phase 3: Edición manual asistida

- [ ] **3.1 Permitir renombrar zonas sugeridas**
  - **AC**:
    - nombres editables y persistidos en draft
  - **Dependencies**: 2.3

- [ ] **3.2 Permitir mover una basin entre zonas**
  - **AC**:
    - una basin puede reasignarse manualmente
    - el draft sigue consistente
  - **Dependencies**: 2.3

- [ ] **3.3 Permitir unir/dividir zonas sugeridas**
  - **AC**:
    - el usuario puede ajustar granularidad operativa
  - **Dependencies**: 3.2

- [ ] **3.4 Guardar draft sin publicar**
  - **AC**:
    - se conserva el trabajo intermedio
    - no cambia la zonificación vigente
  - **Dependencies**: 3.1, 3.2, 3.3

---

## Phase 4: Aprobación y adopción gradual

- [ ] **4.1 Aprobar draft como nueva zonificación vigente**
  - **AC**:
    - existe acción explícita de aprobación
    - la capa aprobada queda disponible para mapas
  - **Dependencies**: 3.4

- [ ] **4.2 Mostrar nueva zonificación aprobada en 2D/3D**
  - **AC**:
    - la capa aprobada puede verse en ambas vistas
    - convive temporalmente con la manual
  - **Dependencies**: 4.1

- [ ] **4.3 Verificar flujo completo y documentar reemplazo gradual**
  - **AC**:
    - generar propuesta, editar, guardar, aprobar funciona
    - queda documentado cómo retirar o archivar la capa manual
  - **Dependencies**: 4.2
