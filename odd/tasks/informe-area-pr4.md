# Informe de área — PR 4: más capas en el informe (IDECOR)

Objetivo: PR 4 del plan de informes. Branch: `feat/informe-area-pr4` (desde
main — depende del builder del PR 2, no del PR 3). Fuente: plan auditado.

## Specs

- S1 (plan, verbatim): "Que el informe tenga lo que le falta frente a
  GeoCuenca: suelos detallados, uso y cultivos, canales e imágenes de años
  húmedos."
- S2 (alcance, verbatim): "ETL de IDECOR a PostGIS o raster local, nuevas
  secciones del PDF y de la pantalla, desglose por subcuenca de cada una."
  Fuera: "Consultar IDECOR en vivo durante el informe (lento y frágil).
  Todo se baja antes por ETL."
- S3 (suelos, plan): WFS `idecor:carta_suelo_50mil_2025` en JSON por bbox
  de la zona; guardar con fecha de bajada. Tabla por unidad cartográfica:
  símbolo, series y %, clase, IP, agua útil a 1 y 2 m, ha y %; IP ponderado
  por área. Migración `idecor_suelos_50mil` (geometría + cu, clase, ip,
  au_1m, au_1_5m, au_2m, serie_1..8, porc_1..4, nombre, tipo_unida, links a
  PDF). La sección 4 del PDF pasa de suelos_cu a IDECOR 1:50.000.
- S4 (cobertura, plan): `cobertura_uso_2024_2025` (10 m, 21 clases —
  CONFIRMAR si es raster) y `coberturas_estivales_2223`, `_2324`, `_2425`.
  Tabla de clases en ha y %, recurrencia de cultivo de verano en 3 campañas
  y % "Cuerpo de agua estacional" (clase 9). Rasters registrados en
  `geo_layers`.
- S5 (canales, plan verbatim): "Km de canales relevados y propuestos dentro
  del área (`vt_canal_network` o su tabla base), cruces con caminos
  (`cruce_camino`), puntos de conflicto; km de canal por subcuenca y por
  cada 1.000 ha."
- S6 (imágenes, plan verbatim): "Falso color de los eventos ancla 2015,
  2017 y 2025 usando `rainfall_event_imagery_candidate`; miniatura por GEE
  recortada al área, guardada como PNG en el informe."
- S7 (tests, plan verbatim): "ETL idempotente (dos corridas, mismo conteo);
  sumas de ha por sección iguales al área cubierta ±0,1 %; PDF con las
  secciones nuevas en orden; si IDECOR no responde, el informe sale igual
  con la sección marcada 'sin datos' y la cobertura en 0."
- S8 (aceptación, plan verbatim): "Para una subcuenca de prueba, cobertura
  de suelos 1:50.000 mayor a 95 % y tabla con series; las 3 imágenes
  presentes cuando GEE responde."
- S9 (riesgos, plan): "Licencia y cita de IDECOR (poné la fuente en cada
  sección); cambios de nombre de capas en el GeoServer de IDECOR (es un
  servicio externo); cuota de GEE." WFS verificado vivo 2026-11-18
  (totalFeatures 1.555, EPSG:4326).
- S10: desglose por subcuenca de cada capa nueva (S2) donde el desglose ya
  existe (filas por zona). Fuente citada en cada sección (S9).

## Tasks

- T1 — ETLs + secciones backend: suelos (S3), cobertura (S4), canales (S5),
  imágenes (S6), secciones PDF nuevas + desglose + fuentes, tests S7/S8.
  Route: delegated (un writer, commits por capa).
- T2 — Integración final + medición (idempotencia, cobertura >95% en
  subcuenca de prueba, imágenes cuando GEE responde). Route: parent con el
  writer de T1.

## Log

- L1 (2026-11-19, Javier): "dale....y prosigue hasta terminar todo" —
  maratón; PR 4 arranca en paralelo al CI del PR 3.
