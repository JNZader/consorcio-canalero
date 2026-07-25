# Tasks: Mejoras UX, historial y reportes

## Overview

**Total Tasks**: 12  
**Phases**: 4 (UX → Metadata → Export → Verification)  
**Goal**: Cerrar el flujo operativo de zonificación aprobada con mejor UX, historial enriquecido y capacidad de compartir/exportar resultados.

---

## Phase 1: Pulido UX 2D/3D

- [ ] **1.1 Revisar y normalizar posiciones de paneles 2D**
  - **AC**:
    - paneles principales no se superponen
    - la jerarquía visual de controles es clara
    - el estado inicial reduce ruido visual
  - **Dependencies**: None
  - **Files Modified**: `consorcio-web/src/components/MapaLeaflet.tsx`, styles related files

- [ ] **1.2 Revisar y normalizar posiciones/defaults en 3D**
  - **AC**:
    - panel de capas 3D mantiene comportamiento coherente con 2D
    - zonificación aprobada y overlays históricos tienen defaults claros
    - paneles flotantes no tapan información crítica
  - **Dependencies**: 1.1
  - **Files Modified**: `consorcio-web/src/components/terrain/TerrainViewer3D.tsx`, related styles

- [ ] **1.3 Unificar naming y acciones visibles entre 2D y 3D**
  - **AC**:
    - botones/paneles equivalentes usan naming consistente
    - el usuario puede identificar la capa principal aprobada en ambas vistas
  - **Dependencies**: 1.1, 1.2
  - **Files Modified**: 2D/3D components as needed

---

## Phase 2: Historial enriquecido

- [ ] **2.1 Extender modelo persistido de approved zoning con metadatos opcionales**
  - **AC**:
    - schema/db admite `display_name`, `comment`, `approved_by`
    - migraciones no rompen datos existentes
  - **Dependencies**: None
  - **Files Modified**: backend model/migration files

- [ ] **2.2 Ajustar repository/router para guardar y leer metadatos**
  - **AC**:
    - `current`, `history` y `restore` siguen funcionando
    - nuevas aprobaciones aceptan metadatos opcionales
  - **Dependencies**: 2.1
  - **Files Modified**: `gee-backend/app/domains/geo/repository.py`, `router.py`, schemas if applicable

- [ ] **2.3 Exponer campos en frontend de aprobación e historial**
  - **AC**:
    - el usuario puede cargar nombre/comentario/aprobador al aprobar
    - el historial muestra los nuevos campos cuando existan
    - versiones viejas siguen viéndose bien
  - **Dependencies**: 2.2
  - **Files Modified**: `consorcio-web/src/hooks/useApprovedZones.ts`, `MapaLeaflet.tsx`, types/contracts

---

## Phase 3: Exportación y reportes

- [ ] **3.1 Implementar descarga GeoJSON de la versión aprobada actual**
  - **AC**:
    - existe acción visible para descargar GeoJSON
    - el archivo corresponde a la versión activa persistida
    - maneja correctamente el caso sin versión activa
  - **Dependencies**: 2.2
  - **Files Modified**: backend router/repository and frontend UI hooks/components

- [ ] **3.2 Implementar layout imprimible/reporte mínimo**
  - **AC**:
    - existe una vista o layout apto para impresión
    - incluye mapa y metadatos básicos de la versión
  - **Dependencies**: 3.1
  - **Files Modified**: frontend components/routes/styles as needed

- [ ] **3.3 Agregar acción Imprimir / Exportar PDF desde frontend**
  - **AC**:
    - la acción está visible en el panel de zonificación/historial
    - dispara flujo de impresión utilizable desde navegador
  - **Dependencies**: 3.2
  - **Files Modified**: frontend UI files

---

## Phase 4: Verificación

- [ ] **4.1 Agregar/actualizar tests backend del historial enriquecido**
  - **AC**:
    - cubren metadatos opcionales
    - cubren restauración append-only
  - **Dependencies**: 2.x
  - **Files Modified**: backend tests

- [ ] **4.2 Validar manualmente UX 2D/3D y flujos de exportación**
  - **AC**:
    - paneles no se pisan
    - defaults son coherentes
    - GeoJSON descarga correctamente
    - impresión produce salida usable
  - **Dependencies**: 1.x, 3.x
  - **Files Modified**: none required

- [ ] **4.3 Documentar alcance final y pendientes posteriores**
  - **AC**:
    - el cambio documenta qué se resolvió en UX/historial/reportes
    - deja explícito que la analítica con canales va en un cambio separado
  - **Dependencies**: 4.2
  - **Files Modified**: `openspec/changes/mejoras-ux-historial-reportes/*`, optional docs
