# ROADMAP — consorcio-canalero

> Fuente de verdad del estado de los arcos de trabajo. Actualizar en cada PR que
> cierre o abra un frente. Complementa (no reemplaza) los artefactos SDD de
> `openspec/changes/` — que hoy son **untracked por convención** y viven solo en
> los checkouts locales — y la memoria persistente de sesión (engram, proyecto
> `consorcio-canalero`).
>
> Última actualización: **2026-09-25** · Mantiene: @javier
>
> Estrategia de producto (canalero · caminero · ficha nacional · MBAgro crop-ops):
> `docs/strategy/exploracion-productos-2026-09.md`. Incluye GeoCuenca INTA (visor GEE Salado). No fusionar MBAgro. No pelear el visor gratis de Salado.

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
| **Multi-hazard viewer** (lifecycle + visible integration + legend + session restore + `/mapa` URL + E2E) | #250-#255 | Ocho slices en main 2026-08-26→31. B3 `#250` · B3b `#251` · B3c `#252` · C6 `#253` · C5 `#254` (B3B-NEW-003: `?basin=` sobrevive el load del catálogo) · E2E `#255`. Código cerrado. Archive local en `openspec/changes/archive/2026-08-31-multi-hazard-viewer/`. El canary de prod corre el journey citizen; operator queda credential-gated. |
| **Celery Beat healthcheck** | #300 | Beat deja de heredar el HTTP healthcheck del backend; módulo `app.beat_healthcheck`. Deployado en box. |
| **Image-policy Debian 13.7 + sunset** | #301 | Hotfixes perl/gzip/sqlite/pcre2; sunset prorrogado a **2026-10-31**; baseline honesto 56 filas. Imágenes production en box. |
| **Frontend alpine libexpat** | #302 | Digest `nginx:1.30.4-alpine` + `apk upgrade` → `libexpat 2.8.5-r0`; desbloquea Final Frontend Image Gate (CVE-2026-93990). |
| **Wave C1 — Mantine 9** | #324 | `@mantine/*` 8 → 9.6.2; props `Collapse`/`Grid`; patch `@mantine+core+9.6.2`. |
| **Wave C2 — MapLibre 5** | #326 | `maplibre-gl` 4 → 5.24.0; `canvasContextAttributes` para export PNG/PDF. |
| **Wave C3 — Vite 8** | #327 | `vite` 7 → 8, `@vitejs/plugin-react` 6; `rolldownOptions` code-splitting. |
| **Wave C4 — toolchain FE** | #328 | Vitest 5, Stryker 10, Biome 2; pre-commit Biome alineado. |
| **Wave C5 — SQLAlchemy 2.1 + psycopg3** | #329 | SQLAlchemy 2.1.1, `psycopg[binary]` 3.x; URLs `postgresql+psycopg://`; `.sqlstate` en timeouts ficha. |

## ✅ RAG — cadena COMPLETA (2026-08-25)

Las 10 unidades de `consorcio-conocimiento-semantico` mergeadas: U1 #217 · U2 #219 · U3 #220 · U4 #222 · U5 #224 · U6 #225 · U7 #226 · U8 #227 · U9 #228 · U10 #229. Cada una con ciclo apply → verify adversarial → fix-forward. El runbook de encendido vive en `docs/rag/runbook-encendido.md`.

## 📋 La cola actual (orden acordado)

1. **Actos del owner para el encendido** (gate §4.3 del runbook — nada defaultea):
   - Firma de términos del proveedor (6.7 — procedimiento en `docs/rag/proveedor-terminos.md`). Re-pinedo 2026-09-02 a `claude-fable-5-1` / `claude-cli` (Max consumer, no-entrenamiento con el toggle OFF, retención 30 días / Covered Model). El flag sigue off.
   - Decisión de abstención (0.1 — la única de Fase 0 abierta; se corta con los datos de la eval)
   - Corridas GPU en la workstation: `answer_set` n≥30 por el path real + grading + re-grade ciego ≥1 día · `slm_bench` (deepseek vs Qwen3-8B — la escalera 9.6b) · margen real de `bm25_ce` · knobs de costo (A2)
2. **🎉 LA CEREMONIA DE ENCENDIDO CONJUNTO** — `docs/rag/runbook-encendido.md` paso a paso: el box camina 6 revisiones (004→0021→0022→0023→005→006→007), ETL red_vial con dry-run vs GEE, task de cruces, re-ingest con 3 clases, sidecar, worker por systemd en la workstation, flags al final. Incluye el O.1 de flujo-caminos.
3. **Archives**: `flujo-caminos` y `consorcio-conocimiento-semantico` (post-ceremonia; 10.4 se marca con la medición real del box). ~~`multi-hazard-viewer`~~ ✅ Engram #15466 (2026-08-31); leftover untracked folder moved to `openspec/changes/archive/2026-08-31-multi-hazard-viewer/` (not git-added; OpenSpec commit decision is higiene).
4. ~~**Multi-hazard viewer re-cut**~~ ✅ CÓDIGO CERRADO 2026-08-31 (#250-#255).
5. ~~**Lluvia v2** — `lluvia-antecedente-referencia`~~ ✅ CERRADO 2026-08-26 (#231-#235, archivado). Queda la higiene mm/hr de IMERG (backlog).
6. ~~**Lluvia — eventos extremos**~~ ✅ CÓDIGO CERRADO 2026-08-26 (#237-#242, verify final + archive en curso). Al box en la ceremonia: `alembic upgrade head` + `docker compose exec backend python -m app.domains.geo.rainfall.detector_cli`.
7. ~~**Pared de "Discrepancias" en la ficha**~~ ✅ CERRADO 2026-08-31 — la UI comprime `expected_interval` consecutivos a un rango+conteo (`expected_interval=<first> → <last> (N)`).
8. **Código restante (no box)** — (a) ~~archive SDD multi-hazard~~ ✅; (b) ~~issue #164 pre-push harness~~ ✅ (#257); (c) ~~CVE-2026-66046 `libexpat1`~~ congelado (#258) + frontend alpine fix (#302); (d) ~~sunset image-policy~~ ✅ remediado + prorrogado (#301); (e) ~~reaper `geo_jobs`~~ ✅; (f) ~~`auto-corridor`~~ ABANDONED — OpenSpec local movido 2026-09-24 a `archive/2026-09-24-auto-corridor-basin-analysis/`; (g) ~~admin sugerencias / tramites labels~~ ✅. Higiene OpenSpec 2026-09-24 (untracked): también `ficha-territorial`, `stabilize-critical-contracts-ci-gates`, `lluvia-intensidad-subdiaria` → `archive/2026-09-24-*`. Activos en `openspec/changes/`: solo `flujo-caminos` + `consorcio-conocimiento-semantico` (archive **post-ceremonia**).

## 🗄️ Backlog (anotado, sin apuro)

- ~~**Reaper de `geo_jobs`**~~ ✅ 2026-08-31: `reconcile_stale_geo_jobs` ya existía (15 min / 300 min). Idle 45 min + heartbeat en DEM `run_step` y cómputo de cruces; GEE sin heartbeat queda en 300 min. RUNNING huérfano → `error=worker_lost`.
- **Sunset image-policy: revisar antes del 2026-10-31.** Prorrogado el 2026-09-24 (2026-09-18 → 2026-10-31) junto con remediación real: Debian 13.7 habilitó `perl-base 5.40.1-6+deb13u1`, `gzip 1.13-1+deb13u1`, `libsqlite3-0 3.46.1-7+deb13u2` y trixie-security `libpcre2-8-0 10.46-1~deb13u2`; los cuatro van como hotfix `--only-upgrade` en el Dockerfile (salen 7 perl + 1 gzip + 2 sqlite del baseline). La DB del día reveló deuda nueva sin fix en trixie (util-linux ×36, libxml2 +7, libexpat1 +3, systemd ×2): baseline backend **56 filas (55 HIGH + 1 CRITICAL)**, 0 con `FixedVersion`. Palanca: Debian 13.8 o DSA puntual; un digest nuevo de `python:3.11-slim-trixie` no ayuda.
- **Frontend nginx digest hold:** no subir tag `nginx` a 1.31.x hasta remedio Alpine/apk para **CVE-2026-6732** (`libxml2`). Mantener pin `nginx:1.30.4-alpine@sha256:dc5069…` + `apk upgrade` quirúrgico (patrón #302). Dependabot #308/#330 cerrados; ignore en `.github/dependabot.yml`. Revisar cuando Trivy deje de marcar HIGH en la imagen candidata.
- **Decisión estructural**: ¿commitear `openspec/changes/`? Hoy untracked — permitió el drift que U2 pagó. La reconciliación manual con `diff -r` es el paliativo vigente.
- Follow-up router: bajar `mixto→legal` (hoy 2/13) vía tuning de banda/piso — re-medición en U9 con más gold.
- Follow-ups RAG fuera del gate: re-chunk de las 10 unidades gigantes (fix principled de D-8), más gold de retrieval, juicio abierto del decreto 3780-C/65 (matchea por PDF de OTRO documento).
- ~~Limpieza worktrees + containers de ablación~~ ✅ 2026-09-24: 52 worktrees mergeados removidos; `consorcio-rag-o3` / `consorcio-rag-eval-pg` borrados (estaban Exited). Queda eventual leftover `consorcio-expat-20260831` (cache trivy root-owned) si `sudo rm` no corre. Imágenes rmeh: sin apuro.

## 🔑 Dónde vive cada cosa

| Qué | Dónde |
|---|---|
| Artefactos SDD (proposal/design/specs/tasks) | `openspec/changes/<change>/` — **untracked**, copias en checkout principal + worktrees, reconciliadas con `diff -r` |
| Reportes empíricos RAG (eval, diagnóstico, reranker, campaña recall) | `docs/rag/*.md` (untracked) + `gee-backend/artifacts/rag/` (gitignored — incluye gold del router ratificado) |
| Gold privado de retrieval + corpus legal | `~/Escritorio/consorcio/` (fuera del repo, checkout pineado `12043582`) |
| Memoria de decisiones/lecciones | engram, proyecto `consorcio-canalero` (topic keys `sdd/*`, `rag/*`, `backlog/*`) |
| Box (único entorno, DEV) | Hetzner `157.180.29.238:2222` — compose custom FUERA del repo; frontend en Cloudflare Pages (auto-deploy con cada merge) |
| Backups | `~/backups/` en el box, cron 04:00 UTC desde `~/ops-tools/consorcio/backup_local.sh` |
