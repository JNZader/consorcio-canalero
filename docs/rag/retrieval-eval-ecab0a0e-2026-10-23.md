# Evaluación de recuperación — consorcio-rag V0

Generado: 2026-10-23T01:50:24.281137+00:00

## Procedencia (leída de `rag_corpus`, no de un sidecar)

- corpus_sha: `ecab0a0ed9cfbfb7bca0f7673f0283bc75bb406e`
- estado: ingerido pero **nunca embebido** (`embedding_modelo IS NULL`)
- modelo de embeddings: —
- revisión HF: —
- sha256 del artefacto: —
- embeddings cargados en: —
- sintético: no

| leg | torch | transformers | device |
|---|---|---|---|
| corpus (batch GPU) | no registrado en la base | no registrado en la base | no registrado en la base |
| consulta (este proceso) | — | — | cpu |

> La fila del corpus dice `no registrado en la base` a propósito: la migración `conocimiento_004` graba modelo, revisión, `sintetico`, sha256 del artefacto y timestamp — **no** la versión de torch ni el device del batch. Esos viven sólo en el sidecar, que un segundo batch sobre la misma revisión del corpus sobrescribe. Imprimir acá los valores de ESTE proceso sería atribuirle a los vectores del corpus un entorno que nunca los produjo (ledger RAG4-002); el sha256 de arriba es el puntero al sidecar que sí los tiene.

- RRF k = 60 · LEG_LIMIT = 50

## Gold set

- ítems: 57 (respondibles 34 · abstención 23)
- ratificado: 2026-08-10
- corpus_sha del gold set: `ecab0a0ed9cfbfb7bca0f7673f0283bc75bb406e`
- evaluable: sí

## Latencia de embebido de consulta

- **no medida en esta corrida.** El criterio de latencia (design.md D3) no está evaluado en este documento.
- Para medirlo: `venv-rag/bin/python scripts/rag_query_latency.py --gold-set app/domains/conocimiento/eval/gold_set.yaml --device cpu --threads 2 --json artifacts/rag/latencia.json`, y volvé a correr `rag_eval.py --latencia artifacts/rag/latencia.json`.

## Modo `bm25_sin_ce`

**Veredicto: NO EVALUABLE**

- modo 'bm25_sin_ce': el par de abstención es `not-evaluable` — no hay señal ratificada para este arm y la decisión 0.1 del owner sigue ABIERTA. Las métricas de recuperación de arriba SÍ están medidas; lo que no puede emitirse es el veredicto de habilitación (task 9.5).

| métrica | valor | barra | fuente | n | ¿pasa? |
|---|---:|---:|---|---:|---|
| hit-rate@5 | 0.647 | ≥ 0.72 | answerable subset | 34 | NO |
| hit-rate@10 | 0.765 | ≥ 0.80 | answerable subset | 34 | NO |
| MRR | 0.563 | ≥ 0.55 | answerable subset | 34 | sí |
| citation-precision | 0.407 | ≥ 0.33 | answerable subset | 34 | sí |
| norma-vs-secundaria | 1.000 | = 1.00 | answerable subset | 34 | sí |
| vigencia-correctness | 0.667 | = 1.00 | answerable subset | 3 | NO |
| abstention recall | n/d | = 1.00 | sin señal ratificada (decisión 0.1 del owner, ABIERTA) | — | not-evaluable |
| abstention precision | n/d | ≥ 0.80 | sin señal ratificada (decisión 0.1 del owner, ABIERTA) | — | not-evaluable |

**Metodología (divulgación obligatoria — design.md D6)**

- Señal de abstención: sin señal ratificada (decisión 0.1 del owner, ABIERTA)
- Regla de selección: highest precision among thresholds reaching abstention recall 1.00; ties broken by the lower threshold. Grid = the observed values of the signal named above, with nothing appended.
- Validación: leave-one-out cross-validation, one fold per gold item (leave-one-out)
- n = 0
- Umbral shipped (ajustado sobre el conjunto completo): 0.000000 — por FALLBACK
- Par que decide el go/no-go (**LOOCV held-out**): recall n/d · precision 0.000
- Par de la misma muestra: recall n/d · precision 0.000 — **upper bound (fit on the scoring sample)**, no decide nada
- folds con fallback: 0 de 0 (0.0%) — un fallback frecuente es en sí mismo una señal de no-go

**Cobertura de las piernas**

- operador de la pierna léxica: OR — disyunción de los lexemas que parsea websearch_to_tsquery
- piernas que corrieron en este modo: bm25
- preguntas corridas: 57
- sin candidatos FTS: 57 (100.0%)  — esta pierna no corre en este modo
- sin candidatos vector: 57 (100.0%)  — esta pierna no corre en este modo
- sin candidatos BM25: 1 (1.8%)

**Exención por ceiling de embedding**

- no aplica en este modo: la pierna léxica alcanza las unidades sin vector, así que ningún ítem sale del denominador.

**Por pregunta**

| id | clase | esperadas | devueltas (top-5) | score top-1 | fts | vec |
|---|---|---|---|---:|---:|---:|
| D-1 | answerable | `9750#14` | `9750#14`, `11059#27`, `11059#25`, `6604#24`, `9750#31` | 0.000000 | 0 | 0 |
| D-2 | answerable | `9750#15` | `11059#24`, `6604#11`, `11059#27`, `9750#13`, `9750#14` | 0.000000 | 0 | 0 |
| D-3 | answerable | `9750#24` | `11059#28`, `6604#17`, `11059#31`, `res4-2026#anexo#art28`, `9750#28` | 0.000000 | 0 | 0 |
| D-4 | answerable | `1315-2012#4` | `8555#4`, `8548#5`, `8614#68`, `8614-consolidada#68`, `8614#63` | 0.000000 | 0 | 0 |
| D-5 | answerable | `9750#42` | `11059#44`, `5350#74`, `11059#43`, `11059#42`, `9750#42` | 0.000000 | 0 | 0 |
| D-6 | answerable | `9867#24` | `9867#23`, `res-aprhi-3-2026#art1`, `6394#20bis`, `6394#22`, `res-bioagro-147-2026#art4` | 0.000000 | 0 | 0 |
| D-7 | answerable | `8803#6` | `8803#6`, `8803#contra-quien-se-puede-usar-en-este-expediente`, `10417#10`, `5589#88`, `8803#el-pedido-que-cumple-la-ley` | 0.000000 | 0 | 0 |
| D-9 | answerable | `8803#7` | `8803#7`, `10208#61`, `8803#el-reloj`, `8803#el-pedido-que-cumple-la-ley`, `8803#1` | 0.000000 | 0 | 0 |
| D-10 | answerable | `8803#8` | `8803#8`, `8803#el-pedido-que-cumple-la-ley`, `198-2025#anexo-i#art17#parte-3`, `5350#68`, `8803#los-tres-frentes-de-pelea-previsibles` | 0.000000 | 0 | 0 |
| D-11 | answerable | `9750#17` | `9750#17`, `9750#8`, `res-aprhi-025-2022#art1`, `res-aprhi-004-2026#encabezado-visto`, `res-aprhi-004-2026#art3` | 0.000000 | 0 | 0 |
| D-12 | answerable | `9750#25` | `9750#25`, `25506#6`, `9750#8`, `9750#33`, `9750#20` | 0.000000 | 0 | 0 |
| D-13 | answerable | `5350#66` | `5350#66`, `5350#56`, `5350#19`, `5350#11`, `6394#15` | 0.000000 | 0 | 0 |
| D-8 | answerable | `8560#5#parte-5`, `8560#5#parte-9`, `8560#5#parte-10` | `res-dnv-908-2026#anexo-ii#norma10`, `res-bioagro-147-2026#art1`, `res-srh-157-2013#art1`, `5589#220`, `318-2007#anexo#art27` | 0.000000 | 0 | 0 |
| C-1 | answerable | `9750#20`, `9750#6`, `10demayo#res005-2026#art1` | `9750#11`, `res4-2026#anexo#art28`, `9750#43`, `6604#40`, `res4-2026#anexo#art50` | 0.000000 | 0 | 0 |
| C-2 | answerable | `9750#11`, `9750#22` | `6604#17`, `11059#28`, `9750#20`, `res4-2026#anexo#art28`, `11059#26` | 0.000000 | 0 | 0 |
| C-3 | answerable | `9750#16`, `9750#33` | `10417#13`, `8614#20`, `10417#14`, `8614-consolidada#20`, `6604#26` | 0.000000 | 0 | 0 |
| C-4 | answerable | `9750#21`, `9750#15`, `9750#12` | `9750#15`, `6604#11`, `6604#37`, `6604#18`, `res4-2026#anexo#art27` | 0.000000 | 0 | 0 |
| C-5 | answerable | `9750#3`, `9750#21`, `9750#39` | `5589#96`, `8614#61`, `8614-consolidada#61`, `5589#239`, `25506#32` | 0.000000 | 0 | 0 |
| C-6 | answerable | `5350#80`, `5350#84`, `9867#1` | `5350#84`, `5350#81`, `5350#80`, `8803#contra-quien-se-puede-usar-en-este-expediente`, `198-2025#anexo-i#art21` | 0.000000 | 0 | 0 |
| C-7 | answerable | `5589#207`, `8560#28`, `5589#221` | `5589#221`, `res-dnv-1898-2025#art5`, `res-dnv-1898-2025#art1`, `5589#116`, `5589#219` | 0.000000 | 0 | 0 |
| C-8 | answerable | `res-dipas-395-2004#art1`, `res-dipas-395-2004#art3`, `10demayo#res189-2014#art1` | `res-dipas-395-2004#art5`, `res-dph-11821-1985#art1`, `res-dipas-395-2004#art1`, `res-srh-157-2013#art1`, `res-dph-11821-1985#art4` | 0.000000 | 0 | 0 |
| C-9 | answerable | `9750#18`, `25506#3`, `25506#6` | `9750#18`, `6604#15`, `25506#anexo`, `9750#25`, `25506#52` | 0.000000 | 0 | 0 |
| T-1 | trampa-vigencia | `10679#17`, `10679#vigencia-de-los-fondos#parte-1`, `9750#39` | `10679#20`, `10679#vigencia-de-los-fondos#parte-1`, `10679#vigencia-de-los-fondos#parte-2`, `10679#17`, `10679#vigencia-de-los-fondos#parte-3` | 0.000000 | 0 | 0 |
| T-2 | trampa-vigencia | `10679#20`, `10679#vigencia-de-los-fondos#parte-2` | `10679#20`, `10679#vigencia-de-los-fondos#parte-3`, `10679#vigencia-de-los-fondos#parte-2`, `11059#61`, `10679#50` | 0.000000 | 0 | 0 |
| T-3 | answerable | `9750#19`, `9750#12`, `9750#47` | `11059#25`, `6604#16`, `9750#19`, `res-aprhi-025-2022#art2`, `9750#12` | 0.000000 | 0 | 0 |
| T-4 | answerable | `11059#1`, `11059#3`, `10936#12` | `res-aprhi-004-2026#considerandos-pasajes-verificables`, `8560#69`, `10demayo#res189-2014#art1`, `8560#61`, `8555#1` | 0.000000 | 0 | 0 |
| T-5 | trampa-vigencia | `5589#244`, `5589#275`, `5589#276` | `6604#11`, `11059#16`, `8560#41bis`, `5589#180`, `srh-2013#punto-3#parte-4` | 0.000000 | 0 | 0 |
| V-1 | answerable | `9750#3`, `5589#202` | `5589#193sextus`, `5589#53`, `5589#36`, `198-2025#anexo-i#art18`, `res-srh-157-2013#considerandos-pasajes-verificables` | 0.000000 | 0 | 0 |
| V-2 | answerable | `5589#260`, `5589#235`, `5589#239` | `5589#239`, `5589#236`, `5589#240`, `5589#256`, `5589#263` | 0.000000 | 0 | 0 |
| V-3 | answerable | `5589#241`, `5589#256`, `5589#261` | `5589#256`, `5589#254`, `5589#253`, `5589#251`, `5589#252` | 0.000000 | 0 | 0 |
| Q-1 | answerable | `5589#238`, `5589#239`, `5589#202` | `5589#202`, `5589#239`, `5589#238`, `9750#25`, `8555#4` | 0.000000 | 0 | 0 |
| Q-2 | answerable | `5589#207`, `5589#208`, `1315-2012#2` | `3780-C-65#punto-3`, `res-dnv-908-2026#anexo-xi-modelo-de-resolucion-aprobatoria-particular-de-permisos-precarios-de-uso-de-la-zona-de-camino#parte-1`, `res-dnv-908-2026#anexo-i-nuevo-procedimiento-para-la-tramitacion-de-permisos-precarios-de-uso-de-la-zona-de-camino#parte-6`, `1315-2012#2`, `res-dnv-908-2026#anexo-xi-modelo-de-resolucion-aprobatoria-particular-de-permisos-precarios-de-uso-de-la-zona-de-camino#parte-4` | 0.000000 | 0 | 0 |
| Q-3 | answerable | `5589#254`, `5589#260` | `5589#254`, `5589#260`, `5589#253`, `5589#256`, `5589#240` | 0.000000 | 0 | 0 |
| Q-4 | answerable | `5589#235` | `5589#235`, `10417#13`, `8614#20`, `8614-consolidada#20`, `10679#vigencia-de-los-fondos#parte-7` | 0.000000 | 0 | 0 |
| X-1 | unanswerable | — | `318-2007#anexo#art27`, `res-dnv-908-2026#anexo-ii#norma25`, `8560#5#parte-10`, `res-dnv-908-2026#anexo-ii#norma10`, `res-bioagro-147-2026#art4` | 0.000000 | 0 | 0 |
| X-2 | unanswerable | — | `5589#220`, `8560#44`, `8560#5#parte-3`, `8560#77`, `res-srh-157-2013#art1` | 0.000000 | 0 | 0 |
| X-3 | unanswerable | — | `10679#vigencia-de-los-fondos#parte-8`, `10679#20`, `10679#vigencia-de-los-fondos#parte-5`, `10679#17`, `11059#61` | 0.000000 | 0 | 0 |
| X-4 | unanswerable | — | `3780-C-65#punto-3`, `1315-2012#6`, `10demayo#ficha-registral-aprhi`, `1315-2012#2`, `10demayo#res189-2014#art2` | 0.000000 | 0 | 0 |
| X-5 | unanswerable | — | `5589#219`, `5589#226`, `8614#71`, `8614-consolidada#71`, `9867#23` | 0.000000 | 0 | 0 |
| A-1 | unanswerable | — | `10679#vigencia-de-los-fondos#parte-3`, `10demayo#res189-2014#art1`, `res-srh-157-2013#art1`, `10demayo#ficha-registral-aprhi`, `8560#32` | 0.000000 | 0 | 0 |
| A-2 | unanswerable | — | `10demayo#res189-2014#art1`, `10demayo#ficha-registral-aprhi`, `8614#9`, `res-dnv-908-2026#art5`, `8614#7` | 0.000000 | 0 | 0 |
| A-3 | unanswerable | — | `10demayo#ficha-registral-aprhi`, `res-dnv-908-2026#anexo-xi-modelo-de-resolucion-aprobatoria-particular-de-permisos-precarios-de-uso-de-la-zona-de-camino#parte-3`, `res-srh-157-2013#art1`, `10demayo#res189-2014#art1`, `8614#9` | 0.000000 | 0 | 0 |
| A-4 | unanswerable | — | `10demayo#res189-2014#art1`, `10demayo#ficha-registral-aprhi`, `10demayo#res005-2026#art3`, `10demayo#res005-2026#art2`, `10demayo#res189-2014#art2` | 0.000000 | 0 | 0 |
| A-5 | unanswerable | — | — | 0.000000 | 0 | 0 |
| A-6 | unanswerable | — | `11059#41`, `6604#36`, `9750#39`, `10593#23`, `10679#26` | 0.000000 | 0 | 0 |
| A-7 | unanswerable | — | `9750#39`, `11059#41`, `9750#41`, `10679#28`, `8614#41` | 0.000000 | 0 | 0 |
| A-8 | unanswerable | — | `10demayo#ficha-registral-aprhi`, `10demayo#res189-2014#art1`, `10demayo#res005-2026#art1`, `res-srh-157-2013#encabezado-visto`, `25506#37` | 0.000000 | 0 | 0 |
| A-9 | unanswerable | — | `srh-2013#punto-2`, `8555#23`, `srh-2013#punto-3#parte-1`, `10936#10`, `5589#215` | 0.000000 | 0 | 0 |
| A-10 | unanswerable | — | `10demayo#res189-2014#art1`, `10demayo#ficha-registral-aprhi`, `res-dnv-908-2026#anexo-i-nuevo-procedimiento-para-la-tramitacion-de-permisos-precarios-de-uso-de-la-zona-de-camino#parte-2`, `res-aprhi-004-2026#encabezado-visto`, `10679#vigencia-de-los-fondos#parte-3` | 0.000000 | 0 | 0 |
| A-11 | unanswerable | — | `8560#71`, `8560#70`, `3780-C-65#punto-3`, `1315-2012#3`, `8555#27` | 0.000000 | 0 | 0 |
| A-12 | unanswerable | — | `8803#contra-quien-se-puede-usar-en-este-expediente`, `5350#38`, `res-dnv-908-2026#anexo-xi-modelo-de-resolucion-aprobatoria-particular-de-permisos-precarios-de-uso-de-la-zona-de-camino#parte-3`, `10demayo#ficha-registral-aprhi`, `9750#33` | 0.000000 | 0 | 0 |
| A-13 | unanswerable | — | `9750#3`, `5589#116`, `9750#21`, `8614#28`, `8614-consolidada#28` | 0.000000 | 0 | 0 |
| A-14 | unanswerable | — | `8803#los-tres-frentes-de-pelea-previsibles`, `8560#73`, `res-aprhi-025-2022#art2`, `6604#14`, `5350#22` | 0.000000 | 0 | 0 |
| A-15 | unanswerable | — | `5589#248`, `5589#17`, `5589#131`, `5589#19`, `5589#227` | 0.000000 | 0 | 0 |
| A-16 | unanswerable | — | `8803#los-tres-frentes-de-pelea-previsibles`, `5350#57`, `5589#223`, `5350#32`, `5589#169` | 0.000000 | 0 | 0 |
| A-17 | unanswerable | — | `10demayo#res005-2026#art1`, `10demayo#res005-2026#art3`, `res4-2026#anexo#art48`, `10demayo#res189-2014#art3`, `10demayo#res189-2014#art2` | 0.000000 | 0 | 0 |
| A-18 | unanswerable | — | `res-srh-157-2013#encabezado-visto`, `res-srh-157-2013#art2`, `res-aprhi-004-2026#art3`, `res-aprhi-004-2026#art2`, `res-aprhi-004-2026#encabezado-visto` | 0.000000 | 0 | 0 |

## Margen contra el baseline FTS-only

**`not-evaluable`** — el arm `bm25_ce` **no se corrió** en esta corrida, así que no hay margen que publicar.

Para correrlo: `make rag-eval RAG_EVAL_PYTHON=venv-rag/bin/python RAG_EVAL_MODOS='--modo bm25_ce'`, que arma el cross-encoder `BAAI/bge-reranker-v2-m3` sobre los candidatos BM25.

## Barra del brazo `bm25_sin_ce`

| métrica | valor | barra | n |
|---|---:|---:|---:|
| `bm25_sin_ce` hit@5 | 0.647 | ≥ 0.72 | 34 |
| `bm25_sin_ce` norma-vs-secundaria | 1.000 | = 1.00 | 34 |
| `bm25_sin_ce` vigencia-correctness | 0.667 | = 1.00 | 3 |

- pérdidas de migración (claves del gold ausentes del snapshot): 0
- fallas de recuperación (claves presentes, ninguna en el top-5): 12

**Estado derivado: `no_superada`**

Para registrarla, copiá este bloque a `barra_sin_gpu.yaml` (`derivar_desde` lo arma; no se escribe a mano):

```yaml
estado: no_superada
modo: bm25_sin_ce
corpus_sha: ecab0a0ed9cfbfb7bca0f7673f0283bc75bb406e
n_respondibles: 34
hit_rate_at_5: 0.6470588235294118
separacion_norma_secundaria: 1.0
vigencia_correcta: 0.6666666666666666
metodologia: 'bm25_sin_ce: candidatos BM25 en orden BM25, sin cross-encoder. Medido
  sobre 34 ítems respondibles del gold, claves del gold re-validadas contra el snapshot,
  snapshot no sintético. Derivado por derivar_desde desde scripts/rag_eval.py.'
motivo: ''
```

## Router (question classification)

**`not-evaluable`** — router thresholds were NOT scored.

El bloque del router no se puntuó: esta corrida no construyó un embebedor (`--modo fts` no necesita uno). Para puntuarlo: `make rag-eval RAG_EVAL_PYTHON=venv-rag/bin/python`.

## Métricas por respuesta (answer-level)

**`not-evaluable`** — las métricas por respuesta NO se puntuaron.

El bloque de métricas por respuesta no se puntuó: esta corrida no recibió `--answer-set`. Las respuestas las produce el worker con GPU (runbook G9) contra el pin real, y el owner las gradúa; recién entonces hay artefacto que pasarle a este comando.

## Bench de SLM candidato (task 9.6b)

**`not-evaluable`** — el bench NO se puntuó.

El bench de SLM no se corrió en esta corrida: no se pasó `--slm-bench`. Los dos brazos son corridas REALES — el pin de referencia y el candidato embebido, mismo prompt, mismos payloads, mismos graders — y las produce el worker con GPU (runbook G9).

> **Regla de escalera (del owner, transcripta):** Si el SLM despeja las MISMAS barras que la referencia, el pin del proveedor PUEDE mudarse al SLM embebido — lo que mata la dependencia de verificación de términos (task 6.7) y la superficie de proveedor externo por completo. Recién entonces se banca un peldaño MÁS CHICO (≤2B) sobre este mismo artefacto, y sólo si ESE aguanta, un ≤1B afinado pasa a ser un proyecto (destilación desde el corpus — cambio aparte, no éste). La escalera nunca saltea un peldaño, y cada peldaño lo decide este mismo artefacto graduado, nunca una impresión.

