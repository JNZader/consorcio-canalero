# ROADMAP — consorcio-canalero

> Fuente de verdad del estado de los arcos de trabajo. Actualizar en cada PR que
> cierre o abra un frente. Complementa (no reemplaza) los artefactos SDD de
> `openspec/changes/` — que hoy son **untracked por convención** y viven solo en
> los checkouts locales — y la memoria persistente de sesión (engram, proyecto
> `consorcio-canalero`).
>
> Última actualización: **2026-08-24** · Mantiene: @javier

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

## 🔄 En vuelo

| Ítem | Estado |
|---|---|
| **RAG U4** — router | PR #222 abierto. Barra ratificada CON datos (accuracy held-out ≥0.70 · `operational→legal`=0 como conteo · `mixto→legal`≤2 con follow-up). Gold set de 49 preguntas ratificado. |
| **RAG U5** — generación | Fix-forward del verify en curso (CRITICAL: regla sin-cita evadible por título markdown pegado — clasificación por línea). La compuerta de privacidad sobrevivió el bypass-hunt completo. |

## 📋 La cola de la semana (orden acordado)

1. **RAG U6-U10**: proveedores (`deepseek-v4-flash` vía bridge + verificación de términos no-training ANTES de encender) → buzón asincrónico HTTP → página CD en consorcio-web → eval (answer-set n≥30 graded + brazo bm25_ce desde la GPU + **escalera SLM 9.6b**: 8B→2B→≤1B, cada peldaño por medición) → runbook G9.
   - Decisión del owner pendiente en el camino: **abstención (0.1)** — se corta en U9 con más gold. Única decisión de Fase 0 abierta.
2. **🎉 Ceremonia de encendido conjunto** (decisión 2026-08-24: caminos + RAG en UN viaje al box):
   deploy backend → `alembic upgrade head` (el box está en `conocimiento_004`; camina 0021→0022→0023→005→006 de una) → ETL red_vial (dry-run vs GEE PRIMERO) → task de cruces → verificación no-regresión → re-ingest corpus RAG con tres clases → runbook RAG → flags.
   Después: **archives** de flujo-caminos y consorcio-conocimiento-semantico.
3. **Multi-hazard viewer re-cut** — retomar en 2/7: faltan b3 (lifecycle, el grande), b3b, c6, c5, e2e+CI estricto.
4. **Lluvia v2** — exploración lista (`openspec/changes/lluvia-intensidad-subdiaria/explore.md`): recomendación = `lluvia-antecedente-referencia` (normal+percentil por ventana, CERO GEE nuevo) + higiene del bug mm/hr de IMERG como fix-entre-SDDs. Espera el "dale" del owner.
5. **Pared de "Discrepancias" en la ficha territorial** — fix UI propuesto (comprimir 153 `expected_interval` a un rango); espera el "dale".

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
