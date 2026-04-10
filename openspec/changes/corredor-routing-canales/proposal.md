# Proposal: Corridor routing para trazado de canales

## Intent

Agregar una primera versión de **corridor routing** sobre la red de canales/routing existente para que el sistema no devuelva solo una ruta mínima puntual, sino también un **corredor utilizable**, alternativas y metadata explicable para evaluación operativa.

## Scope

### In Scope

#### Fase 1: MVP backend orientado a red
- Mantener el routing existente basado en `canal_network`.
- Exponer un nuevo endpoint para calcular un corredor entre dos puntos.
- Devolver:
  - ruta central (`centerline`)
  - polígono de corredor (`corridor`)
  - alternativas cercanas
  - resumen de costos/distancias
- Soportar ancho configurable del corredor.
- Soportar penalización simple para generar alternativas sin reusar exactamente el mismo trazado.

#### Fase 2: Contrato listo para frontend/admin
- Diseñar respuesta consumible por 2D/3D.
- Exponer perfiles operativos (`balanceado`, `hidraulico`, `evitar_propiedad`).
- Incluir metadata explicable por alternativa:
  - distancia total
  - número de edges
  - edge ids usados

#### Fase 3: Base para costo multi-criterio futuro
- Modelar el endpoint y helpers de forma que luego puedan incorporar:
  - slope/HAND/TWI
  - catastro
  - flood risk
  - pesos por criterio

#### Fase 4: Persistencia y reutilización
- Guardar escenarios de corridor routing.
- Poder relos desde UI admin.
- Exportar el resultado consolidado como GeoJSON.

### Out of Scope
- Raster least-cost corridor full-resolution en esta primera entrega.
- UI completa de edición/slider de pesos.
- Optimización multi-criterio avanzada.
- Persistencia de escenarios de corridor routing.

## Current State

Hoy el sistema tiene:
- import de red de canales a `canal_network`
- construcción de topología pgRouting
- endpoint de `shortest-path`
- métricas de red

Pero solo devuelve una línea óptima única, lo que es insuficiente para evaluación territorial y trazado asistido.

## Approach

### Paso 1: Introducir concepto de corridor sobre la red existente
Usar la ruta central actual como base y derivar un polígono de corredor a partir de un buffer configurable sobre la geometría unificada de la ruta.

### Paso 2: Generar alternativas explicables
Recalcular rutas alternativas penalizando los edges ya usados por soluciones previas, para obtener variantes cercanas pero distintas.

### Paso 3: Diseñar contrato extensible
La respuesta debe servir hoy para network-based corridor routing y mañana para incorporar costo multi-criterio sin romper el contrato principal.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `gee-backend/app/domains/geo/routing.py` | Modified | helpers de corridor, alternativas y armado de respuesta |
| `gee-backend/app/domains/geo/router_hydrology_routing.py` | Modified | endpoint `/routing/corridor` |
| `gee-backend/app/domains/geo/router.py` | Modified | re-export/compatibilidad |
| `gee-backend/tests/unit/*routing*` | Modified/New | TDD del nuevo contrato y lógica |
| `openspec/changes/...` | New | artefactos SDD |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Alternativas demasiado parecidas a la ruta central | Medium | penalización configurable por edge |
| El buffer de corredor no represente viabilidad real de obra | Medium | dejar claro que es MVP sobre red, no raster corridor final |
| Tests existentes parchean nombres en `app.domains.geo.router` | High | mantener wrappers/exportaciones compatibles |

## Rollback Plan

1. Mantener intacto `shortest-path`.
2. Introducir `corridor` como endpoint paralelo.
3. Si el contrato no convence, eliminar el endpoint nuevo sin afectar la red existente.

## Dependencies

- `canal_network` y topología pgRouting ya operativos.
- Shapely disponible en backend para construir geometrías de corredor.
- Suite de tests mock-based del router geo.

## Success Criteria

- [ ] Existe endpoint backend de corridor routing.
- [ ] Devuelve centerline, corridor polygon y alternativas.
- [ ] El ancho de corredor es configurable.
- [ ] Hay tests TDD para contrato y helpers puros.
- [ ] La implementación deja base clara para costo multi-criterio futuro.

---

**Change**: corredor-routing-canales  
**Location**: openspec/changes/corredor-routing-canales/proposal.md  
**Status**: Ready for Review  
**Next Step**: Specification (`/sdd:continue corredor-routing-canales`)
