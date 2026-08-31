# ROADMAP — consorcio-canalero

> Fuente de verdad del estado de los arcos de trabajo. Actualizar en cada PR que
> cierre o abra un frente. Complementa (no reemplaza) los artefactos SDD de
> `openspec/changes/` — que hoy son **untracked por convención** y viven solo en
> los checkouts locales — y la memoria persistente de sesión (engram, proyecto
> `consorcio-canalero`).
>
> Última actualización: **2026-08-31** · Mantiene: @javier

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
| **Lluvia — eventos extremos** (detector + catálogo persistido + picker catalog-backed + puente de imágenes) | #237-#242 | Cadena de 6 slices en main 2026-08-26. HISTORIC_FLOODS hardcodeado MUERTO: el picker sirve el catálogo (calibración REAL con datos del box: 36 extrema/144 alta; sep-2025 detectado, feb-2017 confirmado ±3d, mar-2015 curado honesto). Falta SOLO el paso de ceremonia en el box (alembic upgrade + una corrida de `detector_cli` → 183 eventos reales) y el archive. 7 tickets de backlog en el tasks.md (destacan BL-GHA-CACHE-CEILING y BL-RATE-LIMIT-SUITE-CASCADE). |
| **Multi-hazard viewer** (lifecycle + visible integration + legend + session restore + `/mapa` URL + E2E) | #250-#255 | Ocho slices en main 2026-08-26→31. B3 `#250` · B3b `#251` · B3c `#252` · C6 `#253` · C5 `#254` (B3B-NEW-003: `?basin=` sobrevive el load del catálogo) · E2E `#255`. Código cerrado. Falta archive SDD. El canary de prod corre el journey citizen; operator queda credential-gated. |

## ✅ RAG — cadena COMPLETA (2026-08-25)

Las 10 unidades de `consorcio-conocimiento-semantico` mergeadas: U1 #217 · U2 #219 · U3 #220 · U4 #222 · U5 #224 · U6 #225 · U7 #226 · U8 #227 · U9 #228 · U10 #229. Cada una con ciclo apply → verify adversarial → fix-forward. El runbook de encendido vive en `docs/rag/runbook-encendido.md`.

## 📋 La cola actual (orden acordado)

1. **Actos del owner para el encendido** (gate §4.3 del runbook — nada defaultea):
   - Firma de términos del proveedor (6.7 — procedimiento en `docs/rag/proveedor-terminos.md`)
   - Decisión de abstención (0.1 — la única de Fase 0 abierta; se corta con los datos de la eval)
   - Corridas GPU en la workstation: `answer_set` n≥30 por el path real + grading + re-grade ciego ≥1 día · `slm_bench` (deepseek vs Qwen3-8B — la escalera 9.6b) · margen real de `bm25_ce` · knobs de costo (A2)
2. **🎉 LA CEREMONIA DE ENCENDIDO CONJUNTO** — `docs/rag/runbook-encendido.md` paso a paso: el box camina 6 revisiones (004→0021→0022→0023→005→006→007), ETL red_vial con dry-run vs GEE, task de cruces, re-ingest con 3 clases, sidecar, worker por systemd en la workstation, flags al final. Incluye el O.1 de flujo-caminos.
3. **Archives**: `flujo-caminos` y `consorcio-conocimiento-semantico` (post-ceremonia; 10.4 se marca con la medición real del box). `multi-hazard-viewer` se puede archivar ya (código + verify en main).
4. ~~**Multi-hazard viewer re-cut**~~ ✅ CÓDIGO CERRADO 2026-08-31 (#250-#255).
5. ~~**Lluvia v2** — `lluvia-antecedente-referencia`~~ ✅ CERRADO 2026-08-26 (#231-#235, archivado). Queda la higiene mm/hr de IMERG (backlog).
6. ~~**Lluvia — eventos extremos**~~ ✅ CÓDIGO CERRADO 2026-08-26 (#237-#242, verify final + archive en curso). Al box en la ceremonia: `alembic upgrade head` + `docker compose exec backend python -m app.domains.geo.rainfall.detector_cli`.
7. ~~**Pared de "Discrepancias" en la ficha**~~ ✅ CERRADO 2026-08-31 — la UI comprime `expected_interval` consecutivos a un rango+conteo (`expected_interval=<first> → <last> (N)`).
8. **Código restante (no box)** — (a) archive SDD multi-hazard; (b) ~~issue #164 pre-push harness~~ ✅ CERRADO 2026-08-31 (#257); (c) ~~CVE-2026-66046 `libexpat1`~~ congelado 2026-08-31 (#258); (d) sunset image-policy **sigue** 2026-09-18 — no se prorrogó; (e) ~~reaper de `geo_jobs`~~ heartbeat + idle 45 min (DEM/cruces; GEE sigue 300); (f) ~~`auto-corridor` 4.3 UX operativa~~ ABANDONED. Feature landed WIP `8c862d11` and was deleted the same day in admin cleanup `7c1297c3`/`0610cde6`. OpenSpec 11/12 is stale. Not restored. (g) ~~stabilize leftover 4.4 admin sugerencias `POST /interna` + `DELETE /{id}` 404~~ ✅ CERRADO 2026-08-31 — dead client/UI dropped; no backend routes added. 3.5 tramites label catalog (`pendiente` vs backend `ingresado`) **sigue** follow-up. El resto de OpenSpec 16/30 es tracker rot (v1 paths gone, cosmic-ray 0.30 / Stryker 75 already in CI). `ficha-territorial` A7 **ya está en main** (#108/#110/#111, 2026-08-02) — los checkboxes OpenSpec están stale. `lluvia-intensidad-subdiaria` es solo explore, no hay proposal.

## 🗄️ Backlog (anotado, sin apuro)

- ~~**Reaper de `geo_jobs`**~~ ✅ 2026-08-31: `reconcile_stale_geo_jobs` ya existía (15 min / 300 min). Idle 45 min + heartbeat en DEM `run_step` y cómputo de cruces; GEE sin heartbeat queda en 300 min. RUNNING huérfano → `error=worker_lost`.
- **Sunset image-policy: revisar antes del 2026-09-18.** Baseline backend 18 filas (14 HIGH + 4 CRITICAL) al 2026-08-31, incluyendo CVE-2026-66046 `libexpat1@2.8.3-1~deb13u1` (Debian `no-dsa`, unfixed en sid). El sunset **no** se movió.
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
