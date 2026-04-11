# Proposal: Análisis automático de cuenca para corredores prioritarios

## Intent

Agregar un flujo de **análisis automático de cuenca** para que el sistema no dependa de origen/destino manuales y pueda proponer automáticamente corredores, tramos e intervenciones prioritarias sobre una zona operativa, cuenca o todo el consorcio.

## Scope

### In Scope

#### Fase 1: Análisis batch automático sobre la red/cuenca
- Permitir ejecutar un análisis automático por:
  - zona operativa
  - cuenca
  - todo el consorcio
- Detectar candidatos automáticos de corredor sin requerir puntos manuales.
- Reusar la red existente, perfiles y modo raster/network ya implementados.
- Generar un conjunto de escenarios candidatos rankeados.

#### Fase 2: Ranking y explicabilidad territorial
- Calcular score por candidato combinando:
  - conectividad
  - distancia/costo
  - mejora hidráulica estimada
  - afectación parcelaria
  - criticidad del área
- Devolver razones/resumen explicable por candidato.
- Diferenciar “sin salida útil” vs “candidato válido”.

#### Fase 3: UI orientada a análisis, no a trazado manual
- Agregar un flujo principal tipo “Analizar cuenca automáticamente”.
- Mostrar lista/ranking de candidatos.
- Permitir cargar uno al mapa para inspección.
- Mantener el modo manual como herramienta secundaria/avanzada.

#### Fase 4: Persistencia y workflow operativo
- Guardar el lote del análisis automático.
- Persistir escenarios candidatos derivados del análisis.
- Aprobar/exportar desde el ranking automático.

### Out of Scope
- Optimización hidrológica físicamente calibrada de máxima fidelidad.
- Simulación hidráulica 2D/1D completa.
- Eliminación inmediata del flujo manual actual.
- Planificación multiobjetivo exhaustiva a escala regional.

## Current State

Hoy el sistema tiene corridor routing manual:
- modo `network`
- modo `raster`
- perfiles operativos
- guardado/aprobación/export

Pero requiere que el operador marque origen y destino, lo que vuelve el flujo poco natural para análisis global de cuenca.

## Problem

Para uso real, el operador no siempre sabe de antemano qué par de puntos probar. Necesita que el sistema explore la cuenca completa y responda preguntas como:
- ¿Dónde conviene intervenir primero?
- ¿Qué corredores faltantes serían más valiosos?
- ¿Qué tramos tienen mejor relación entre beneficio hídrico y costo/afectación?

## Approach

### Paso 1: Detectar candidatos automáticamente
Partir de la geometría de la zona/cuenca y detectar:
- gaps de conectividad
- tramos conflictivos
- zonas con criticidad alta
- pares origen/destino candidatos

### Paso 2: Evaluar cada candidato con el motor existente
Para cada candidato:
- correr corridor routing en `network` o `raster`
- resumir el resultado
- calcular score comparativo

### Paso 3: Presentar ranking operativo
Devolver un ranking de escenarios sugeridos, con posibilidad de abrir uno en el mapa, guardarlo, aprobarlo y exportarlo.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `gee-backend/app/domains/geo/routing*.py` | Modified | orquestación batch y scoring automático |
| `gee-backend/app/domains/geo/router_hydrology_routing.py` | Modified | endpoints de auto-analysis |
| `gee-backend/app/domains/geo/repository.py` | Modified | selección de ámbitos/capas para análisis |
| `consorcio-web/src/components/admin/canal-suggestions/*` | Modified | nuevo flujo principal de análisis automático |
| `openspec/changes/...` | New | artefactos SDD |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Generar demasiados candidatos poco útiles | High | limitar por ámbito, heurísticas y top-N ranking |
| Tiempos de cálculo altos en todo el consorcio | High | batch async, caching y recorte espacial |
| Scores opacos o difíciles de explicar | Medium | devolver breakdown explícito por criterio |
| UI demasiado compleja con manual + automático | Medium | definir automático como flujo principal y manual como avanzado |

## Success Criteria

- [ ] Existe un análisis automático por zona/cuenca/consorcio.
- [ ] El sistema genera candidatos sin pedir origen/destino manual.
- [ ] Los candidatos vienen rankeados y explicados.
- [ ] La UI permite inspeccionarlos en el mapa.
- [ ] El flujo manual queda como complemento, no como única opción.

---

**Change**: auto-corridor-basin-analysis  
**Location**: openspec/changes/auto-corridor-basin-analysis/proposal.md  
**Status**: Draft  
**Next Step**: Specification (`/sdd:continue auto-corridor-basin-analysis`)
