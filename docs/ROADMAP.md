# ROADMAP — consorcio-canalero

> Fuente de verdad del estado de los arcos de trabajo. Actualizar en cada PR que
> cierre o abra un frente. Complementa (no reemplaza) los artefactos SDD de
> `openspec/changes/` — que hoy son **untracked por convención** y viven solo en
> los checkouts locales — y la memoria persistente de sesión (engram, proyecto
> `consorcio-canalero`).
>
> Última actualización: **2026-08-26** · Mantiene: @javier

---

## ✅ Cerrado (en `main`)

| Arco | PRs | Nota |
|---|---|---|
| **flujo-caminos** (red vial + cruces + relevamiento + frontend) | #212, #214, #216, #218 (+#221 paridades) | Código completo. Falta SOLO el rollout O.1 (ver "Ceremonia de encendido") y el archive. O.2 registrado 2026-08-24 para los 4 slices. |
| **Lluvia** (tarjeta answer-first + cache freshness) | #184-#186, #206, #207 | En producción vía Cloudflare Pages. ARCHIVADO (`openspec/changes/archive/2026-08-22-*`). |
| Fix scroll tarjetas desktop | #213 | `max-height:100%` contra padre `auto` resuelve a `none` — raíces flex + `min-height:0`. |
| Hotfix proof anidado flaky | #215 | pytest-en-subproceso contra DB compartida = lotería por orden. Regla: `subprocess`+`pytest` dentro de `tests/` es bandera roja. |
| **RAG U1** — clasificación tres clases | #217 | La regla de privacidad: publico/institucional/privado, allowlist ratificada, `regla_sha256`+`REGLA_MECANICA_VERSION`. |
| **RAG U2** — retrieval B50 | #219 | BM25 in-process + bge-reranker-v2-m3, fiel línea-a-línea a la campaña medida (hit@5 0.759). Barras ratificadas. |
| **RAG U3** — sidecar de embeddings | #220 | Container BGE-M3 CPU-only con lock `--require-hashes`; guard de identidad por tupla `(modelo, revision_hf)` canonicalizada. |
| **Lluvia v2 — antecedente-referencia** (normal + percentil estacional por ventana d7/d30/d90) | #231-#235 | Cadena de 5 slices, TODA en main 2026-08-25/26. Verify final: matriz 16/16 SATISFIED, 0 CRITICAL. ARCHIVADO (`openspec/changes/archive/2026-08-26-*`). Regla nueva D0: complete-or-nothing en ambos lados del rank. 5 tickets de backlog heredados (ver Follow-ups del tasks.md archivado). |

## ✅ RAG — cadena COMPLETA (2026-08-25)

Las 10 unidades de `consorcio-conocimiento-semantico` mergeadas: U1 #217 · U2 #219 · U3 #220 · U4 #222 · U5 #224 · U6 #225 · U7 #226 · U8 #227 · U9 #228 · U10 #229. Cada una con ciclo apply → verify adversarial → fix-forward. El runbook de encendido vive en `docs/rag/runbook-encendido.md`.

## 📋 La cola actual (orden acordado)

1. **Actos del owner para el encendido** (gate §4.3 del runbook — nada defaultea):
   - Firma de términos del proveedor (6.7 — procedimiento en `docs/rag/proveedor-terminos.md`)
   - Decisión de abstención (0.1 — la única de Fase 0 abierta; se corta con los datos de la eval)
   - Corridas GPU en la workstation: `answer_set` n≥30 por el path real + grading + re-grade ciego ≥1 día · `slm_bench` (deepseek vs Qwen3-8B — la escalera 9.6b) · margen real de `bm25_ce` · knobs de costo (A2)
2. **🎉 LA CEREMONIA DE ENCENDIDO CONJUNTO** — `docs/rag/runbook-encendido.md` paso a paso: el box camina 6 revisiones (004→0021→0022→0023→005→006→007), ETL red_vial con dry-run vs GEE, task de cruces, re-ingest con 3 clases, sidecar, worker por systemd en la workstation, flags al final. Incluye el O.1 de flujo-caminos.
3. **Archives**: `flujo-caminos` y `consorcio-conocimiento-semantico` (post-ceremonia; 10.4 se marca con la medición real del box).
4. **Multi-hazard viewer re-cut** — retomar en 2/7: b3 (lifecycle), b3b, c6, c5, e2e+CI estricto.
5. ~~**Lluvia v2** — `lluvia-antecedente-referencia`~~ ✅ CERRADO 2026-08-26 (#231-#235, archivado). Queda la higiene mm/hr de IMERG (backlog).
6. **Lluvia — eventos extremos** (`lluvia-eventos-extremos`, el pedido del histórico + imágenes de impacto): S0 backfill 2021-2025 ✅ HECHO en el box (baseline 1991-2025 continuo, key v1 única, cero duplicados); exploración ✅ (HISTORIC_FLOODS = 3 dicts hardcodeados con UI completa; puente a imágenes ya existe; ventana dorada satelital 2017-2021). Próximo: B1/B2 — el catálogo persistido que alimenta HISTORIC_FLOODS, cero UI nueva.
7. **Pared de "Discrepancias" en la ficha** — fix UI propuesto, espera el dale.

## 🗄️ Backlog (anotado, sin apuro)

- **Reaper de `geo_jobs`**: worker muerto post-claim → RUNNING huérfano (TODO el dominio, herencia de los pipelines DEM; un huérfano bloquea el pre-check de cruces del área). Diseño candidato en engram `backlog/geo-jobs-orphan-running-reaper`.
- **Sunset image-policy: revisar antes del 2026-09-18** (18 CVEs sin fix documentadas).
- **Decisión estructural**: ¿commitear `openspec/changes/`? Hoy untracked — permitió el drift que U2 pagó. La reconciliación manual con `diff -r` es el paliativo vigente.
- Follow-up router: bajar `mixto→legal` (hoy 2/13) vía tuning de banda/piso — re-medición en U9 con más gold.
- Follow-ups RAG fuera del gate: re-chunk de las 10 unidades gigantes (fix principled de D-8), más gold de retrieval, juicio abierto del decreto 3780-C/65 (matchea por PDF de OTRO documento).
- Limpieza: worktrees viejos (`~/programacion/worktrees/consorcio-*` ya mergeados), container de ablación `consorcio-rag-o3` (127.0.0.1:55433), imágenes rmeh.

## 🔑 Dónde vive cada cosa

| Qué | Dónde |
|---|---|
| Artefactos SDD (proposal/design/specs/tasks) | `openspec/changes/<change>/` — **untracked**, copias en checkout principal + worktrees, reconciliadas con `diff -r` |
| Reportes empíricos RAG (eval, diagnóstico, reranker, campaña recall) | `docs/rag/*.md` (untracked) + `gee-backend/artifacts/rag/` (gitignored — incluye gold del router ratificado) |
| Gold privado de retrieval + corpus legal | `~/Escritorio/consorcio/` (fuera del repo, checkout pineado `12043582`) |
| Memoria de decisiones/lecciones | engram, proyecto `consorcio-canalero` (topic keys `sdd/*`, `rag/*`, `backlog/*`) |
| Box (único entorno, DEV) | Hetzner `157.180.29.238:2222` — compose custom FUERA del repo; frontend en Cloudflare Pages (auto-deploy con cada merge) |
| Backups | `~/backups/` en el box, cron 04:00 UTC desde `~/ops-tools/consorcio/backup_local.sh` |
