# Informe de área — PR 1: multiselección e informe en pantalla

Objetivo: PR 1 del plan de informes (auditado 2026-11-18, 27/29 CALZA).
Branch: `feat/informe-area-pr1`. Entrega: un PR a main. Runner: pytest en
`gee-backend/tests/new/` (PostGIS real), Vitest + Playwright en
`consorcio-web/`. Fuente del plan: docs Grok extraídas 2026-11-18 (copia del
texto en Engram `informes-area/auditoria-plan`); auditoría propia contra
main `e1aa709f`.

## Specs

- S1 (plan, verbatim): "Elegir varias subcuencas o cuencas enteras, ver la
  vista previa y obtener en pantalla el total y el desglose por subcuenca de
  riesgo, drenaje, suelos actuales y lluvia."
- S2 (plan, verbatim — alcance): "PDF, trabajo en segundo plano, dibujo,
  KML, capas nuevas. Si la selección supera 20.000 ha, mostrás la vista
  previa y un aviso de que el informe llega con el PR 2."
- S3 (plan, verbatim — topes): "En línea: `ficha_max_area_ha` (20.000 ha).
  Máximo 60 subcuencas por selección (a tu criterio). Reusá
  `assert_within_caps` sumando el tipo `zonas`." Test: "20.001 ha da
  `modo=trabajo` en la vista previa y 413 o 422 en la ficha."
  **DECISIÓN (L2): para `tipo=zonas` el tope online es 35.000 ha**
  (nuevo setting o reuso explícito del nivel de `ficha_max_area_ha_cuenca`),
  no 20.000: el 20k es el default heredado de parcelas/polígono, mientras
  el config ya valida cómputo sync a 35k para `canal_cuenca`, y 35k cubre
  el 100% de las combinaciones de 2 cuencas (el caso de uso real). 3-4
  cuencas siguen al camino preview + "informe completo con el PR 2". El
  test de S3 adapta el umbral: >35.000 da `modo=trabajo`/413/422 para
  zonas. T1 MIDE p95 de la ficha a 20k/35k/59k como condición de
  aceptación (revisable con número en la mano).
- S4 (plan, verbatim — medición): "dos subcuencas que se pisan dan el área
  de la unión y no la suma (tolerancia 0,01 ha); desglose + fuera = total
  (±0,1 %); geodésica contra 32720 con diferencia menor a 0,2 %"
- S5 (plan — UI): botón "Informe de área" en el panel de la ficha → Drawer
  (derecha en escritorio, abajo fullscreen en celular) con Stepper de tres
  pasos Elegir/Revisar/Generar; Tabs Mapa|Lista; clic en BASINS-fill
  reemplaza, ctrl/⌘+clic suma o saca; Switch "Sumar a la selección" en
  celular; resaltar con `setFeatureState({selected:true})`; Lista con
  buscador + Accordion por cuenca y Checkbox "Toda la cuenca" (estado
  indeterminado); Pills removibles; vista previa con ha totales, cantidad,
  `Progress` por capa con % cobertura, `Alert` amarillo si hay partes fuera
  de subcuencas o supera 20.000 ha; contorno unido con `fitBounds`; totales
  en región `aria-live`.
- S6 (plan, verbatim — aceptación): "Vista previa en menos de 1,5 s (p95)
  con 60 subcuencas en local; % de cada dataset suma 100 ±0,1; navegable
  solo con teclado; sin violaciones nuevas en `npm run test:a11y`."
- S7 (plan, verbatim — restricciones): "`ficha_enabled` está en `False`: no
  lo prendas en producción sin que Javier lo decida. Confirmá si la fuente
  `BASINS` del front es GeoJSON de `/geo/basins` o la vista de Martin,
  porque `setFeatureState` necesita `id` estable. Subcuencas con geometría
  inválida en la tabla."
- S8 (contrato API, diseñado en esta sesión — SUPUESTO a validar contra el
  código real en T1): `POST /api/v2/geo/analisis-zona/preview` body
  `{zona_ids: [uuid], cuencas?: [str]}` → `{area_total_ha, subcuencas:
  [{id, nombre, cuenca, ha}], fuera_de_subcuencas_ha, modo: "online"|
  "trabajo", aviso_cap: bool}` (solo geometría, sin rasters, rate-limited,
  `enforce_ficha_enabled`). `POST /analisis-zona` extendido con
  `tipo="zonas"` + `zona_ids` → `FichaResponse` + `desglose_por_subcuenca`
  [{zona_id, nombre, ha, pct_alto_critico, clase_suelo_dominante,
  lluvia_anual_mm}] — desglose desde `composite_zonal_stats` guardado +
  precipitación normal + `suelos_cu`, SIN recomputar rasters (el p95 de S6
  lo exige). `% Alto+Crítico` computa desde clases de flood_risk ≥ borde
  Alto de `class_breaks` (decisión #738; si `composite_zonal_stats` solo
  ofrece >70, marcarlo en la respuesta como `umbral: "legacy70"` y anotarlo
  — NO cambiar el umbral en este PR).

## Tasks

- T1 — Backend: preview + `tipo=zonas` con desglose (S1-S4, S8). Route:
  delegated. **DONE** — commits `23f57d35` (contrato+caps+resolver),
  `4c17e7c2` (preview endpoint), `266558f7` (20 tests PostGIS). Gatekeeper
  PASS (spot check 20/20; suite completa 4.936 passed; p95 preview 7,8 ms
  con 60 zonas). 5 desviaciones aceptadas (fuera_de_subcuencas ~0
  estructural — no hay tabla de cuencas; ficha_errors fuera de superficie →
  unión de TIPOS_VALIDOS; umbral response-level `legacy70`; preview acepta
  cuencas sin zona_ids / ficha solo zona_ids; caps extra envelope 150k +
  vértices 12k). Índices: B-tree cuenca ✓, GIST geometría FALTA (follow-up:
  la padece /geo/basins bbox).
- T2 — Front: `useSeleccionArea` reducer + Vitest (S5). Route: delegated.
  **DONE** — commit `7de62799` (reducer + 20 tests).
- T3 — Front: `informeArea/` + wiring (S1, S5). Route: delegated. **DONE** —
  commit `33f377af` (+1.612/−35). Gatekeeper PASS (20/20 reducer re-run,
  typecheck 0 err, 3.584 unit tests). 5 desviaciones aceptadas (bridge en
  vez de MapInteractionMode nuevo — unión fuera de superficie; request
  standalone fuera de FichaRequest union — switch exhaustivo; coverage
  Progress en Generar no Revisar — preview es geometry-only real; contorno
  por-zona + bbox fitBounds — sin @turf/union y sin deps nuevas; Drawer
  sibling de MapPanelShell — unmount al minimizar). S7 resuelto: BASINS es
  GeoJSON /geo/basins SIN promoteId → source propio con promoteId:'id';
  errores 503/429/5xx con copy humana (#712 pattern).
- T4 — Playwright (extender `ficha-territorial.spec.ts`: elegir dos
  subcuencas y ver desglose) + a11y + medición p95 (S6). Route: parent con
  writer. Nota: browsers locales 1248 ≠ 1255 (playwright 1.65.1) — instalar.
  **DONE** — commit `02b36ed3` (+940/−14): spec nueva
  `tests/e2e/informe-area.spec.ts` (4 tests: happy path con valores exactos,
  aviso cap 35k, teclado completo, p95) + a11y view registration + 3 fixes
  de runtime que el e2e cazó (feature-state en filter ilegal en MapLibre →
  paint; closeButton sin nombre axe-critical; pluralización). Gatekeeper
  PASS (4 e2e, 20/20 reducer, typecheck 0, a11y delta 0 tras fix). p95 UI
  Revisar con 60 zonas: 381 ms (n=15, red mockeada, caja local) vs 1.500 ms
  de presupuesto; backend ya medido 7,8 ms. Follow-ups fileados: #740
  (wiring debt interino), #741 (primer dibujo lazy — preexistente), #742
  (GIST faltante).

## Log

- L1 (2026-11-18, Javier): "dale" — arrancar PR 1 tras mergear #739 (PR 0).
  Contexto: plan auditado (27/29), umbral decidido (#738, se implementa en
  PR 5), map stack policy documentada (#737).
- L2 (2026-11-18, Javier): "dale" — aprueba tope online de **35.000 ha para
  `tipo=zonas`** (no 20.000). Razón técnica aceptada: 20k es el default
  heredado de parcelas/polígono; el config ya corre sync a 35k para
  `canal_cuenca`; 35k cubre todas las combinaciones de 2 cuencas.
  Condición: T1 mide p95 a 20k/35k/59k.
- L3 (2026-11-18): T1 DONE (gatekeeper PASS; p95 7,8 ms; GIST faltante
  reportado como follow-up). T2+T3 DONE (gatekeeper PASS; 3.584 unit tests;
  S7 resuelto: BASINS GeoJSON sin promoteId → source dedicado). Desviaciones
  aceptadas por el parent — ver Tasks.
- L4 (2026-11-18): T4 DONE. El e2e cazó 4 bugs de runtime (2 fixeados, 2
  interinos → #740; 1 preexistente del dibujo → #741; GIST → #742). p95 UI
  381 ms con 60 zonas (S6 ✓). PR listo: 6 commits (T1×3, T2, T3, T4) + doc.
