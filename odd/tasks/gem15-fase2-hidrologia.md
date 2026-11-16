# GEM-15 Fase 2 — Hidrología comparada vs GLO-30 (issue #723)

Objetivo: generar los números hidrológicos que el paper de GEM-15 no tiene, para
decidir la Fase 3 (#724). Branch: `feat/gem15-fase2-hidrologia`. Estrategia de
entrega: un PR a main cuando los números estén documentados. Runner: pytest
(`gee-backend/tests/new/`) para lo que sea testeable; los pasos de análisis
corren como ETL dentro del contenedor backend (`python -m app.domains.geo.etl.*`,
patrón de `generate_canal_catchments.py`).

## Specs

- S1 (issue #723, verbatim): "Derivar flow/catchments del mismo AOI desde GEM-15
  dtm vs GLO-30 (pipeline WBT igual para ambos)". Restricciones: NO retargetear
  `download_dem_impl` (`processing_wbt_support.py:256`, clavado a
  `COPERNICUS/DEM/GLO30`); NO pisar el `flow_dir` natural registrado como
  `natural_flow_dir_{area_id}` que usa `generate_canal_catchments.py:311`. Los
  rasters de la fase 2 viven en sufijos/directorios propios.
- S2 (issue #723, verbatim): "Conversión de datum EGM96→EGM2008 ANTES de comparar
  (grilla geoid) + debias: offset regional ajustado contra GLO-30 sobre terreno
  estable". No existe grilla geoid en el repo (verificado); hay que proveerla.
  Prohibido comparar cotas crudas entre datums.
- S3 (issue #723, verbatim): "Verdad de terreno que sólo el consorcio tiene: red
  de canales real, cruces conocidos, eventos de crecida registrados → comparar
  redes derivadas vs red real (métrica: % cruces correctamente derivados, desvío
  de líneas de flujo en llanura)". Disponible hoy: tabla `canal_consorcio`
  (41 relevados + 19 propuestos, GeoJSONs en `app/domains/geo/etl/data/`), y
  `cruce_camino` (derivados del DEM, no inventario relevado). Alcance decidido
  (L3): canales + cruces solamente; análisis SAR de crecidas, si hay registrados,
  entran como anexo cualitativo, no como métrica.
- S4 (issue #723, verbatim): "Documentar el veredicto con números en docs/
  (decide la Fase 3)". Convención: `docs/ALTIMETRIA-FUENTES.md`. No existe doc
  de fase 1; los números previos (RMSE 3.37 vs 3.85) están solo en el commit
  c0c8ae6e.
- Riesgo del issue (verbatim): "llanura pampeana plana — sesgo regional
  (-4.8..+1.9m según zona, sin número para Córdoba) y alcantarillas no carveadas
  por el estéreo óptico pueden redirigir escorrentía entera".

## Tasks

| ID | S# | Ruta | Estado | Commit |
|----|----|------|--------|--------|
| T1 | S1 | ETL: descarga GEM-15 dtm del AOI como GeoTIFF aparte (asset `projects/climate-and-sustainability/assets/gem-15_v1`, banda `dtm`) + GLO-30 del mismo AOI, sin tocar `download_dem_impl` | pendiente | — |
| T2 | S2 | Grilla geoid EGM96→EGM2008: obtenerla y aplicarla al GEM-15 antes de cualquier comparación | pendiente | — |
| T3 | S2 | Debias regional GEM-15 vs GLO-30 sobre terreno estable (máscara de pendiente; offset medido, no asumido) | pendiente | — |
| T4 | S1 | Correr pipeline WBT idéntico sobre ambos DEMs corregidos → flow_dir/flow_acc/streams/catchments con sufijos propios `_gem15` / `_glo30` | pendiente | — |
| T5 | S3 | Métricas vs verdad de terreno: % cruces correctamente derivados y desvío de líneas de flujo contra `canal_consorcio` relevados | pendiente | — |
| T6 | S4 | Doc `docs/GEM15-FASE2-HIDROLOGIA.md` con los números y el veredicto para #724 | pendiente | — |

## Log

- L1 (2026-11-16, Javier): "vamos por la fase 2" (tras handoff que describía el
  issue #723 como "pedida y no empezada"); luego "las dos" (fase 2 + higiene
  post-merge).
- L2 (2026-11-16): Explorer completó el mapa del pipeline (WBT vía pip whitebox
  dentro del contenedor backend; GEM-15 sin caché y sin conversión de datum en
  fase 1; sin grilla geoid en el repo; sin tabla de eventos de crecida; GeoJSONs
  de canales en el repo). Handoff completo en Engram
  `consorcio/gem15-fase2-explorer`.
- L3 (2026-11-16, Javier): "diria que 1....porque la realidad es que no hay un
  registro" — alcance de eventos = opción 1: métricas solo con canal_consorcio +
  cruces; SAR on-demand como anexo cualitativo si existen registros.
