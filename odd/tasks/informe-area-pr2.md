# Informe de área — PR 2: trabajo en segundo plano y PDF

Objetivo: PR 2 del plan de informes. Branch: `feat/informe-area-pr2`. Runner:
pytest `tests/new/` (PostGIS real), Vitest, Playwright. Base: PR 1 mergeado
(`2fa3beba`). Fuente: plan auditado 2026-11-18; PR 0 (`#739`) ya entregó
`format_es` + `NumberedCanvas` ("Página n de N") — OBLIGATORIO reusarlos.

## Specs

- S1 (plan, verbatim): "Que cualquier selección hasta 150.000 ha genere un
  informe en PDF en segundo plano, con estado visible, caché y link de
  descarga."
- S2 (alcance, verbatim): "Tabla `informes_area`, tarea Celery, rutas para
  crear y consultar, builder del PDF con las secciones disponibles hoy,
  `Mis informes` en el front." Fuera: "Capas nuevas (PR 4), riesgo
  calibrado (PR 5), KMZ y mapa de campo (PR 6)."
- S3 (estructura, verbatim): "Crear `app/domains/geo/informe_area/` con
  `models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`,
  `tasks.py`, `mapas.py` (render estático) y
  `app/shared/pdf/builders_informe_area.py`. Tocar `models.py`
  (`TipoGeoJob.INFORME_AREA`), `celery_outbox.py`
  (`CeleryTaskKey.INFORME_AREA`), `config.py` (topes), registro del router
  en `app/api/v2`."
- S4 (caché, verbatim): "Normalizá la geometría (unión, `ST_SnapToGrid` a
  1e-7, WKB ordenado) y los ids ordenados; `hash_seleccion` = sha256. La
  clave suma versiones de cada capa (fecha de `geo_layers` o del ETL) y
  `version_plantilla`. Si existe un `completed` con la misma clave,
  devolvés ese. Para subcuencas enteras sin recorte podés leer
  `composite_zonal_stats` como atajo."
- S5 (topes, verbatim): "`informe_area_max_ha = 150000` (el doble de las 4
  cuencas), `informe_area_max_zonas = 120`,
  `informe_area_max_vertices = 20000` después de simplificar, máximo 3
  trabajos en curso por usuario y rate limit en la creación. Valores a tu
  criterio, documentados en el PR."
- S6 (PDF, 7 secciones): 1 Resumen (nombre, fecha, ha, subcuencas/cuencas,
  mapa ubicación, 4 KPIs: % Alto+Crítico riesgo, % Alto+Crítico drenaje, %
  clases I-III suelo, lluvia anual media, ranking subcuencas) · 2 Riesgo
  hídrico (qué mide en una frase, mapa con leyenda/escala/norte, tabla
  clase·ha·%, nota de método, desglose — frases por clase SOLO post-PR 5) ·
  3 Drenaje · 4 Suelos (`suelos_cu` actual; PR 4 lo cambia) · 5 Lluvia
  (normales mensuales CHIRPS en barras, anual, `fuente`+`periodo`, aviso
  píxel ~5 km) · 6 Consideraciones (cobertura por capa, límites, descargo
  en lenguaje claro) · 7 Fuentes (cada capa fecha/resolución/link).
  "Tabla completa por subcuenca si son más de 8; el resto va al final de
  cada sección."
- S7 (sin deps nuevas, verbatim): "rasterio recorta y clasifica, Pillow
  pinta la paleta de `class_breaks.py`, y ReportLab dibuja contorno,
  subcuencas, escala gráfica y norte. Fondo: nada o una miniatura
  Sentinel-2 de GEE; **nunca Esri**" → map stack policy (`AGENTS.md`,
  mergeado en #737: Esri PROHIBIDO en productos derivados).
- S8 (tests, verbatim): "la tarea con una selección de prueba termina en
  `completed` con PDF; la segunda llamada igual devuelve `desde_cache:
  true` sin encolar; cambiar la versión de una capa invalida la caché;
  150.001 ha da 422; falla de GEE deja `failed` con `error` legible. El PDF
  tiene 'Página 1 de N', las secciones en orden y los totales de la tabla
  coinciden con `resultado` (±0,1 ha)." + Vitest del polling y de "Mis
  informes".
- S9 (aceptación, verbatim): "Las 4 cuencas con desglose en menos de 5 min
  en el box; PDF de una cuenca de menos de 5 MB; repetir la misma selección
  devuelve el PDF en menos de 1 s."
- S10 (riesgos): memoria del worker (procesá por ventanas); almacenamiento
  de PDFs; **migración NO corre sola en el box** (AGENTS.md: aplicación
  manual documentada en el PR).
- S11 (decisiones Javier, L2): informes **privados por usuario** (sólo
  quien los crea los descarga; admin ve todos) · **vence a 90 días** con
  tarea diaria de limpieza de vencidos.
- S12: reuso obligatorio de PR 0/PR 1: `format_es`
  (fmt_num/fmt_ha/fmt_pct), `BrandedPDF` + `NumberedCanvas` ("Página n de
  N"), resolver zonas del PR 1 (`tipo=zonas`), desglose desde
  `composite_zonal_stats`, `umbral_alto_critico: "legacy70"` hasta #738.

## Tasks

- T1 — Backend infra: migración + modelo `informes_area`, repository,
  service (hash/normalización/caché S4), router (crear/consultar/descargar,
  rate limit, máx 3 en curso, privacidad S11), task Celery vía outbox +
  registro en allowlist, config (S5 + vence 90d), limpieza diaria. Route:
  delegated.
- T2 — PDF: `mapas.py` (contorno, subcuencas, escala, norte, leyenda —
  Pillow/rasterio, S7) + `builders_informe_area.py` (7 secciones, S6,
  reusa S12) + integración en la task. Route: delegated (tras T1).
- T3 — Front: `informeArea/MisInformes.tsx` (Tabla: nombre, ha, Badge
  estado, Progress, descargas — caché = descarga instantánea),
  `useInformeArea.ts` (React Query polling con backoff), paso Generar
  re-wire (TextInput nombre, SegmentedControl "Solo total"|"Total y
  subcuencas", notifications "Te avisamos cuando esté"). Route: delegated.
- T4 — Tests integración S8 completos + medición S9 local (tiempos, tamaño
  PDF, cache hit < 1 s) + Vitest T3. Route: parent con writer.

## Log

- L1 (2026-11-18, Javier): "mergeado...prosigue" — PR 2 tras #743.
- L2 (2026-11-18, Javier): "dale" — aprueba informes privados por usuario
  (admin ve todos) y vencimiento 90 días con limpieza diaria.
- L3 (2026-11-19): T1 DONE (f9d227ea/e0697b7c/76da291f/127e879a + parche
  parent b7fe001c celery include+beat). Suite 4.946 (+10 exactos). Caché
  sha256 en PostgreSQL puro; suelos_catastro sin señal de versión → fuera
  de la clave, documentado. Deviation aceptada: enum drift fix en
  service.py+test_geo_bugfixes (precedente 0022/0023).
- L4 (2026-11-19): T2 DONE (5bbc2125/068871bc) — mapas Pillow + 7 secciones,
  PDF bytea deferred (99 KiB vs 5MB; sweep atómico), task 0,22-0,47 s,
  cache-hit 25 ms. KPIs compartidos task/PDF (calcular_kpis) para que no
  diverjan. 13/13 gatekeeper re-run.
- L5 (2026-11-19): T3 DONE (c01280e6) — informesArea.ts separado (rutas
  autenticadas), backoff 5/15/30 s, MisInformes preserva el flujo.
  129/129; cobertura sobre los 4 pisos (78,81/73,62/77,41/80,39).
- L6 (2026-11-19): T4 DONE (6541520b) — e2e 7 escenarios (descarga real con
  filename RFC 5987, desde_cache sin sondeo probado por conteo de GETs,
  failed+reintento, Mis informes) + a11y 3 estados. Parent re-run 7/7 con
  E2E_APP_URL + dev server (los skips previos eran el modo blind del
  strictGate). Specs enrolados en tsconfig.tests.json (LI3A-004) por el
  parent. Stack docker local no viable (imágenes 4 meses) → S9 de caja
  queda para el deploy; citados números T2. PR listo.
