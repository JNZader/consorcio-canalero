# GEM-15 Fase 2 — Hidrología comparada vs GLO-30 (issue #723)

Objetivo: generar los números hidrológicos que el paper de GEM-15 no tiene, para
decidir la Fase 3 (#724). Branch: `feat/gem15-fase2-hidrologia`. Estrategia de
entrega: un PR a main cuando los números estén documentados. Runner: pytest —
contratos con fakes en `gee-backend/tests/unit/`, integración real PG en
`gee-backend/tests/new/`; los pasos de análisis
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
| T1 | S1 | ETL: descarga GEM-15 dtm del AOI como GeoTIFF aparte (asset `projects/climate-and-sustainability/assets/gem-15_v1`, banda `dtm`) + GLO-30 del mismo AOI, sin tocar `download_dem_impl` | hecho | 094238ac |
| T2 | S2 | Grilla geoid EGM96→EGM2008: obtenerla y aplicarla al GEM-15 antes de cualquier comparación | hecho | edcb2eb3 |
| T3 | S2 | Debias regional GEM-15 vs GLO-30 sobre terreno estable (máscara de pendiente; offset medido, no asumido) | hecho | 14ee33ca |
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
- L4 (2026-11-16): T1 hecho en 094238ac (RED→GREEN, 6/6 unit). Review RDD
  (lente review-reliability, lineage review-7bc233fdce5d4f2c): APPROVED,
  authority quemada. Tres hallazgos informativos NO bloqueantes, anotados como
  deuda: (a) R3-failure-path-tmp-leak WARNING — el .tmp.tif persiste si el
  download falla a mitad; mitigado por el sweeper de .tmp.tif que ya vive en
  `processing_wbt_support` (mismo comportamiento que `download_dem_impl`, el
  gemelo es intencional); (b) R3-parity-wiring-untested SUGGESTION — el
  same-grid de ambas llamadas solo está probado en main() no-cover; (c)
  R3-runner-dir-mismatch SUGGESTION — corregido: esta cabecera ahora declara
  tests/unit además de tests/new.
- L5 (2026-11-16): T2 hecho en edcb2eb3 — grillas us_nga_egm96_15.tif +
  us_nga_egm08_25.tif del CDN de PROJ (SHA256 pineado, fail-closed, se bajan
  una vez al volumen /data/geo/{area}/fase2/grids/). Sonda con grillas REALES
  sobre el AOI: corrección N96−N08 = −0.59 a −0.68 m — decímetros con
  variación espacial, consistente con el disclaimer de fase 1; es la
  ondulación que puede redirigir flujo en llanura. La sonda cazó un bug real
  (muestrear EGM08 con la geometría de EGM96 → offsets ~20 m silenciosos);
  corregido y fijado con test de regresión de geometrías distintas. 7/7 tests.
  Review del commit: primero correction_required (hallazgos severos nunca
  mostrados — el selector de untracked bloqueaba), luego de T3 el provider
  autorizó recover scope_changed → sucesor review-b6221222bae4b1fc en curso.
  ADEMÁS: review 4R del branch completo (T1+T2+doc) APPROVED y quemado
  (lineage review-f2de63b5a79f862d).
- L6 (2026-11-16): T3 hecho en 14ee33ca — stable_mask = rango focal 3x3 <
  STABLE_WINDOW_RANGE_M (2 m) en AMBOS DEMs; offset = mediana de la diferencia
  en celdas estables, MAD y fracción estable reportadas en
  debias_report.json; fail-loud si < MIN_STABLE_CELLS (1000). 5/5 tests, 18/18
  del feature. Queda correr el ETL real en el contenedor cuando se corran
  T1→T3 sobre el AOI.
