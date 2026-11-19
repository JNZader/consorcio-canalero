# Informe de área — PR 5: riesgo hídrico calibrado

Objetivo: PR 5 del plan de informes. Branch: `feat/informe-area-pr5`. Base:
PRs 0-4 mergeados (`f7cb64c4`). Fuente: plan auditado + decisión #738.

## Specs

- S1 (plan, verbatim): "Que el riesgo hídrico diga algo verificable: qué
  parte de cada clase estuvo con agua en 2015, 2017 y 2025 y con cuánta
  lluvia."
- S2 (alcance, plan): "Corregir el historial fijo y el umbral, máscaras de
  agua de los eventos ancla, CHIRPS de 30 días, tabla de validación,
  frases por clase en el PDF." Fuera: "Cambiar los pesos de `flood_risk` o
  inventar umbrales en mm tipo Vázquez con tres eventos. Eso, si los datos
  lo justifican, es otro PR."
- S3 (archivos, plan): "`intelligence/tasks.py` y `calculations.py`
  (historial real), `composites.py` L263 (umbral), `class_breaks.py`,
  crear `app/domains/geo/calibracion_riesgo.py` y tabla
  `riesgo_validacion_evento`, sección del PDF."
- S4 (tabla, plan verbatim): "`riesgo_validacion_evento`: `evento_key`,
  `fecha`, `clase`, `ha_clase`, `ha_con_agua`, `pct_con_agua`,
  `lluvia_30d_mm`, `sensor`, `escena_id`, `version_flood_risk`,
  `created_at`. Una fila por evento y clase para toda la zona; el informe
  recorta por área."
- S5 (agua, plan verbatim): "Agua con MNDWI ≥ 0,1 como `water_delta.py`
  sobre la escena elegida del evento (o Sentinel-1 si no hay óptica,
  marcado aparte); cruce con las clases de `flood_risk` a 30 m; CHIRPS
  diario sumado 30 días antes de la fecha del evento."
- S6 (tests, plan verbatim): "Con una máscara sintética: si todo el
  Crítico está con agua, `pct_con_agua` da 100 %; la suma de `ha_clase` es
  el área de la zona; el índice por zona cambia cuando cambia el historial
  real."
- S7 (aceptación, plan verbatim): "Tabla de validación cargada para los 3
  eventos; esperable que % con agua crezca de Bajo a Crítico (si no pasa,
  documentalo y avisá a Javier antes de publicar frases)."
- S8 (riesgos, plan): "Nubes en las fechas; el agua dura poco y la escena
  puede ser tardía; confundir agua con arroz o lagunas permanentes
  (separá clase 9 de IDECOR)."
- S9 (#738 — DECISIÓN Javier): unificar el umbral con la leyenda —
  **Opción A con desglose**: el estadístico se deriva de `RANGE_CONFIGS`
  (cuenta desde inicio de Alto = 55), métricas separadas `ha_alto` (55-75)
  + `ha_critico` (≥75), KPI "% Alto+Crítico" = suma. Reemplazar
  `_HIGH_RISK_THRESHOLD = 70.0` por derivación; migración/ajuste de
  `composite_zonal_stats.area_high_risk_ha` (columns ha_alto+ha_critico o
  equivalente); recálculo de la tabla; el informe/PDF ya expone
  `umbral_alto_critico` — pasar de "legacy70" a "leyenda-55" y el
  desglose.
- S10 (historial real, plan): reemplazar `historial_inundacion = 0.3` fijo
  (`tasks.py:55`) por el % de la zona con agua en los eventos ancla
  (desde la tabla del PR); si una zona no tiene dato, dejar 0,3 y marcarlo.
- S11 (frases por clase): SOLO si S7 se cumple (% crece Bajo→Crítico);
  si no, documentar y NO publicar frases (el borrador de frases vive en el
  plan; el PDF del PR 2 ya tiene la nota de método).
- S12: título del PR (plan): `feat(riesgo): validación de flood_risk con
  eventos 2015, 2017 y 2025 y lluvia CHIRPS`.

## Tasks

- T1 — Backend: calibración completa (tabla S4, ETL de validación S5,
  corrección S9 + S10, tests S6) + sección PDF. Route: delegated.
- T2 — Gatekeeper + medición S7 (monotonicidad) + decisión frases S11.
  Route: parent.

## Log

- L1 (2026-11-19, Javier): "prosigue hasta terminar todo" — maratón;
  PR 5 tras merges 745/746.
