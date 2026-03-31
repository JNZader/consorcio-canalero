# Proposal: Readecuar zonas del consorcio desde basins

## Intent

Reemplazar progresivamente las zonas del consorcio definidas manualmente por una nueva capa de zonas derivadas a partir de la agrupación de `basins`/zonas operativas, usando una propuesta automática inicial pero permitiendo edición manual antes de consolidar la nueva zonificación.

## Scope

### In Scope

#### Fase 1: Modelo de agrupación sugerida
- Tomar las `basins` actuales como unidad mínima de agrupación.
- Generar una propuesta inicial de grupos de basins que formen nuevas zonas del consorcio.
- Definir criterios de sugerencia explícitos y auditables (ej. contigüidad, cercanía, continuidad operativa, afinidad hídrica).
- Mantener separación entre:
  - `basins` originales
  - `proposed zones`
  - `approved zones`

#### Fase 2: Edición manual asistida
- Permitir mover una basin de una zona propuesta a otra.
- Permitir unir o dividir zonas sugeridas.
- Permitir renombrar zonas.
- Permitir descartar la propuesta automática y rehacerla.

#### Fase 3: Publicación de nueva zonificación
- Persistir una versión aprobada de zonas del consorcio derivadas desde basins.
- Hacer que la nueva capa pueda convivir temporalmente con la capa manual anterior.
- Definir estrategia de reemplazo gradual de la capa manual en 2D y 3D.

### Out of Scope
- Automatización “ciega” sin posibilidad de edición.
- Reemplazo inmediato e irreversible de las zonas manuales existentes.
- Rediseño completo del módulo de administración GIS.
- Optimización avanzada de agrupación tipo clustering matemático sin validación operativa.

## Current State

Hoy el sistema muestra:
- `basins`/zonas operativas como una capa operativa derivada.
- `zona consorcio` como área general.
- zonas del consorcio históricas/manuales definidas con lógica no necesariamente alineada con las basins actuales.

El usuario quiere dejar atrás la zonificación manual y apoyarse en las basins como unidad base, pero sin perder control operativo sobre el resultado final.

## Approach

### Paso 1: Separar sugerencia de aprobación
La propuesta automática NO debe convertirse directamente en verdad de negocio. Debe existir un estado intermedio editable.

### Paso 2: Agrupar basins con heurísticas transparentes
La primera sugerencia debe salir de reglas simples, entendibles y revisables, no de un modelo opaco:
- contigüidad espacial
- tamaño/superficie de zona resultante
- cercanía de accesos o ejes viales relevantes
- continuidad operativa/hidrológica

### Paso 3: Diseñar un flujo semimanual asistido
La UI debe permitir:
- ver qué basins componen cada zona sugerida
- reasignar basins
- renombrar y validar zonas
- confirmar la nueva zonificación antes de publicarla

### Paso 4: Hacer coexistir manual vs propuesta durante transición
Mientras la nueva zonificación no esté aprobada, la capa manual actual debe seguir disponible como referencia.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `gee-backend` zonification domain | Modified/New | lógica de sugerencia, persistencia y versionado de zonas derivadas |
| `consorcio-web` map/admin UI | Modified | visualización y edición de zonas sugeridas/aprobadas |
| `useBasins` / basin consumers | Reused | basins siguen siendo la unidad mínima base |
| 2D/3D map views | Modified | deben mostrar zonas propuestas/aprobadas como nuevas capas |
| data model / DB | Modified | almacenamiento de agrupaciones, nombres y estado de aprobación |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| La agrupación automática no coincide con la lógica operativa real | High | Hacerla editable desde el inicio |
| Mezclar basins con manual zones genere confusión | Medium | Mantener capas diferenciadas y estados claros |
| El flujo de edición sea demasiado complejo | Medium | Empezar con operaciones básicas: mover, unir, renombrar |
| Persistencia/versionado de zonas genere deuda | Medium | Modelar draft vs approved desde el diseño |

## Rollback Plan

1. Mantener las zonas manuales existentes sin borrarlas.
2. Publicar las nuevas zonas como una capa paralela hasta validar su uso.
3. Si la propuesta no sirve, volver a mostrar solo la capa manual sin perder las basins.

## Dependencies

- `basins` actuales disponibles y confiables como unidad base.
- Visualización 2D/3D ya soportando capas operativas derivadas.
- Decisión explícita del usuario: la agrupación debe ser sugerida pero editable.

## Success Criteria

- [ ] Existe una propuesta automática inicial de zonas agrupando basins.
- [ ] La propuesta puede editarse manualmente antes de aprobarse.
- [ ] La nueva zonificación puede convivir con la manual durante transición.
- [ ] Hay un camino claro para reemplazar gradualmente las zonas manuales actuales.
- [ ] El criterio de agrupación queda documentado y revisable.

---

**Change**: readecuar-zonas-consorcio-desde-basins  
**Location**: openspec/changes/readecuar-zonas-consorcio-desde-basins/proposal.md  
**Status**: Ready for Review  
**Next Step**: Specification (`/sdd:continue readecuar-zonas-consorcio-desde-basins`)
