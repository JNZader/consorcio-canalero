## Exploration: conocimiento-normas-editor (Perspective: architecture)

Basis: `origin/main` @ `f86965f0` (2026-10-21), inspected with `git show` / `git grep`. The checked-out branch `feat/deps-audit-locks` was not used. Corpus repo inspected read-only (`git -C`, `rg`): HEAD `f55b96fa`, `origin/master` `2e75370e`, 1 commit ahead, untracked `fuentes-crudas/barrido-bo-2025-2026-10-15/`. Nothing was modified, pushed, enabled or ingested. Not written into `consorcio-conocimiento-semantico`.

"Usable" (owner) = page returns legal units with vigencia, norma-vs-secundaria and the served corpus SHA; unattended prose stays off. Prose-only is NOT the definition, so no "proposal not ready" stop is triggered. Assessed against that definition below.

### Verification ledger (claim -> result)

| Claim | Result | Evidence |
|---|---|---|
| `conocimiento_qa_enabled` defaults false | VERIFIED | `gee-backend/app/config.py:182` |
| Router 503s when flag is off | VERIFIED | `router.py::enforce_conocimiento_flag` (503 `funcionalidad_no_disponible`); every route depends on it: POST via `enforce_conocimiento_qa_enabled` (flag first), reads via `_SOLO_LECTURA`, `/estado` directly. Mounted unconditionally at `app/api/v2/router.py:45` |
| There is a search/norms route to "keep on" | **FALSE** | Router has exactly 4 routes: `POST /preguntas`, `GET /preguntas`, `GET /preguntas/{id}`, `GET /estado`. None returns retrieval results synchronously. Step 1 is not "split a flag", it is "add a route plus its own gate" |
| Corpus pin `12043582bf80...` | VERIFIED, and it is baked in 8+ places | `corpus_expectations.yaml:33`, `eval/gold_set.yaml:74`, `answer_set.yaml:31`, `expected_clasificacion.yaml:21`, `slm_bench.yaml:69/78/88`, `Makefile:353`, `docs/rag/runbook-encendido.md`, `rag_*.py` docstrings |
| bm25_ce hit@5 31/34 = 0.9118, hit@10 33/34, MRR 0.719, cit-prec 0.5294 | VERIFIED as recorded (not re-run) | `design.md:1240-1241`, `tasks.md` F2. Run: 2026-10-22, main `575cc16a`, pin `12043582`, "same lab database", real reranker, `transformers` 5.20.2, "Not deployed" |
| 31/34 was local CUDA, not the box | VERIFIED by code + docs | `BGEReranker(device="cuda")` raises `RerankerNoDisponible` without CUDA; no CPU option exists (`reranker.py`). CPU = 98.9 s/query. Runbook s0.2: box is CX33, 2 shared vCPU, **no GPU**. GPU host = owner workstation (RTX 5060 Ti, `design.md:209`). Box hardware itself is from docs, not probed live |
| Abstention precision at recall 1.00 ~0.44 | **NOT FOUND** | Committed figure is **0.489** (LOOCV, recall 1.000): `design.md:1229`, `umbral_abstencion.yaml:12`, `umbral_abstencion.py:23`. 0.44 appears nowhere on `origin/main`. Use 0.489 unless the owner has a newer run. Threshold artifact is `estado: no_derivado` |
| Corpus repo state | VERIFIED | HEAD `f55b96fa`, `rev-list origin/master..HEAD` = 1, untracked barrido dir present, MANIFEST: 49 docs / 1806 units / integracion 14 |
| Nine drafts in `pedidos-8803` | VERIFIED | `01..09-*.md` + README; 8 on Ley 8803, #8 (DNV) on Ley 27.275 |
| Only CLI is `rag_ingest.py`; no corpus MCP | VERIFIED | `git grep mcp` finds nothing in `gee-backend`/`consorcio-web/src` besides the unrelated provider bridge URL |
| The production box has the August pin ingested and active | **UNVERIFIABLE from repo** | `tasks.md` F1/F2: "Not deployed; the production index was not re-ingested." Runbook is a procedure, no evidence it ran. Step 1's "stale cache" premise needs an operator read of `rag_corpus` on the box |

### Current State

**Gate.** `settings.conocimiento_qa_enabled` is the kill switch and the first dependency of the mailbox. `enforce_conocimiento_qa_enabled` = flag AND terms record AND provider credential AND embedder sidecar `/ready`. All of those four are prose-generation facts (GLM provider via bridge, BGE-M3 sidecar). None is needed to list norm units. Reads of the mailbox take only flag+admin; `/estado` takes flag+admin.

**Retrieval.** `service.recuperar(db, corpus_sha, pregunta, modo=..., reranker=...)`:
- `modo="bm25_ce"`: `_recuperar_bm25_ce` = `expandir_consulta_recuperacion` -> `obtener_indice(db, sha)` (in-process BM25 over `es_secundaria=false` units, built from the stored `tsv` column, 0.14 s / ~2 MB) -> `lexemas_de_consulta` (stems **in Postgres** via `to_tsvector('spanish')`) -> top-50 -> `ordenar_por_ce(reranker, ...)[:k]` -> `hydrate_citations`. No vector column, no embedder, no `qvec` (passing one raises). **Reranker is a hard requirement**: `reranker is None` -> `RerankerRequerido`. A test pins this (`test_recuperacion_bm25.py:781`, "BM25 alone is candidate generation; it was never measured as ranking").
- `fts`: Postgres FTS, no embedder, no GPU. Published ablation baseline.
- `vector`/`hybrid`: need the sidecar and the dev-only `embedding` column.

So `recuperar` does **not** need the vector stack for `bm25_ce`; it needs Postgres + a reranker. The reranker is the only GPU dependency.

**Reranker runtime.** Worker-only today: `scripts/rag_worker.py` under `venv-rag` (torch/CUDA), items stay `pendiente` when no GPU. HTTP never reranks. The eval (`rag_eval.py`) also needs it, so the 57-item gold can only run on the workstation.

**What the worker adds around retrieval** (`trabajador._recuperar`): synthetic-embedding refusal, `verificar_umbral_abstencion` (decision 0.1), `assert_unidades_publicas` classification filter before generation. A norms route sits **beside** the worker, not on top of it, so it does not inherit or touch the abstention path.

**Citation payload.** `schemas.CitaRecuperada` already carries `citation_key`, `texto` (byte-exact), `tipo`, `es_secundaria`, `jurisdiccion`, `estado_vigencia`, `relevancia_consorcio`, `fuente_url`, `source_file`, `source_offset`, plus `score_ce`/`rango_bm25`. `ResultadoRecuperacion` carries `corpus_sha`, `modo`, `reranker_modelo`, `reranker_sintetico`. Vigencia is **document-level** frontmatter text (`estado_vigencia`, NOT NULL for derecho aplicable via `conocimiento_003`); `generacion.esta_vigente` / `es_derogada` already interpret it. Everything the "usable" definition lists exists except a sync route.

**Pin and ingest.** `rag_ingest.py`: `verify_corpus_pin` requires `HEAD == --corpus-sha` and a **clean** tree; `load_corpus` then requires `corpus_expectations.yaml` to pin the same SHA and declare every document; `gate_corpus` runs article-count / inventory / heading / file-inventory / verbatim / key-uniqueness gates; `load_corpus` also needs the pinned reranker **tokenizer snapshot** (`rechunk.contar_tokens_reranker`, `tokenizers` package; no torch). Then one transaction: `upsert_corpus(activo=True)`, documents, units, `prune_unidades`.

### Findings that change the plan

1. **Ingest is publish.** `upsert_corpus(..., activo=True)` sets the new row active and does not deactivate the old one; `corpus_activo` returns `ORDER BY ingested_at DESC`. The new SHA is therefore served the moment ingest commits. The eval reads the DB, so it can only run **after** ingest. "Do not publish if hit@5 < 0.72" cannot be honored by ingesting into the serving DB first. It needs ingest+eval on the lab DB, then a prod ingest, or an explicit `activo=false` rollback runbook. No such guard exists today.
2. **The corpus checkout cannot ingest as-is.** Clean-tree gate fails on the untracked barrido dir (and on any uncommitted state). Declared SHA must be the commit being ingested; `f55b96fa` is unpushed, so any other machine cannot `git checkout` it.
3. **Re-ingest touches far more than the DB.** Pin migration = `corpus_expectations.yaml` (35 documents declared, `articulos_declarados: 1383`; live corpus has 49 documents / 1806 units, so 14 documents need policies, `key_prefix`, `key_style`, exclusions), `expected_clasificacion.yaml` (has a generator, `rag_expected_clasificacion.py`), `gold_set.yaml` (+ owner-side private YAML pinned to the same SHA; `harness.verificar_corpus_sha` and `_textos_privados` refuse a mismatch), `answer_set.yaml`, `slm_bench.yaml`, `Makefile`, runbook, and `umbral_abstencion.yaml` identity (currently `no_derivado`, so passes vacuously). No generator for `corpus_expectations.yaml` was found.
4. **Gold items can silently lose their targets.** Between pin and HEAD, 22 files changed (6098+/171-). Of the documents that existed at the pin, modified ones include `decreto-318-2007` (+162 lines changed), `resolucion-srh-157-2013`, `resolucion-dnv-908-2026`, `resolucion-general-aprhi-004-2026`, `consorcio-10-de-mayo-registro-aprhi`, `ley-8803` (`tipo: ley` -> `ley-provincial`, benign: already in `TIPOS_DERECHO_APLICABLE`; the D-22 synonym becomes dead). New `ley-8614-...` and `ley-8614-...-consolidada` coexist, which adds near-duplicate norma units to the BM25 pool. Every `citas_esperadas` key must be re-validated against the new snapshot **before** the 0.72 comparison means anything. A hit@5 drop can be a data-migration artifact, not a retrieval regression, and the reverse.
5. **BM25-only is an unmeasured ranking.** The design deliberately refuses it (`RerankerRequerido`, D: "never measured as ranking"). The 0.655/0.759 figures compare candidate generators *with the same reranker*; no committed number exists for BM25 order alone. Whatever the HTTP page serves without a GPU needs its own arm name, its own measured hit@5 on the 57-item gold (needs no GPU, only a new harness arm), and must never be labeled `bm25_ce`. The 31/34 may be shown only next to the arm that produced it.
6. **Markdown-only CLI means a second ranker.** `lexemas_de_consulta` stems in Postgres `to_tsvector('spanish')`, and the index is built from the stored `tsv`. Reproducing that over markdown needs a different stemmer -> different lexemes -> different ranking. That violates "no second ranker" and invalidates the measured number. A CLI that reuses `service.recuperar` needs a Postgres.
7. **"Search/norms stay on" needs a classification rule, not only a flag.** Corpus documents default to `privado` unless promoted (`clasificar_documento`). `assert_unidades_publicas` admits `{publico, institucional}` for egress. Admin-only display of a private unit is not egress, but **export of a request that cites a private unit is** (the drafts go to third-party agencies). `chequear`/export must reuse `CLASIFICACIONES_ENVIABLES` and fail closed.
8. **Empty norms result must not read as an abstention.** `abstencion` means "no applicable norm" and is decision 0.1 (open). The norms route returns ranked units or "no ranked result for this arm"; it must never say "no norm applies".

### Affected Areas

- `gee-backend/app/config.py` — new env-backed flag (default false) for the norms surface, distinct from `conocimiento_qa_enabled`.
- `gee-backend/app/domains/conocimiento/router.py` — new dependency (e.g. `enforce_conocimiento_normas`: norms flag + `corpus_activo` not None + `require_admin`; no terms/credential/sidecar), new routes. `/estado` is behind the qa flag, so the SHA badge must ship in the norms response itself or `/estado` needs its own relaxed dependency.
- `gee-backend/app/domains/conocimiento/service.py` — new arm for GPU-less ranking (separate `MODOS` entry; `bm25_ce` contract and its test untouched).
- `gee-backend/app/domains/conocimiento/` (new module) — `buscar` / `leer` / `chequear` library over a `Session`; reuses `recuperar`, `hydrate_citations`, `generacion.esta_vigente`/`es_derogada`, `CLASIFICACIONES_ENVIABLES`.
- `gee-backend/scripts/` — new CLI entry (`rag_ingest.py` house style).
- `gee-backend/app/domains/conocimiento/eval/harness.py`, `report.py`, `scripts/rag_eval.py` — new GPU-less arm; publish gate on hit@5 >= 0.72.
- `corpus_expectations.yaml`, `eval/gold_set.yaml`, `answer_set.yaml`, `expected_clasificacion.yaml`, `slm_bench.yaml`, `Makefile`, `docs/rag/runbook-encendido.md` — pin migration (step 2).
- `consorcio-web/src/components/admin/ConocimientoPanel.tsx`, `lib/api/conocimiento.ts` — today maps 503 `conocimiento_qa_enabled` to "no habilitado"; tests pin it (`ConocimientoPanel.test.tsx:460`). Norms page needs its own client + states.
- `gee-backend/tests/new/conocimiento/test_qa_surface.py` — contracts to keep: flag-off => 503 for mailbox, flag evaluated before auth. Add: norms routes up with qa flag off and mailbox still 503.
- Out of repo: private gold YAML (`RAG_GOLD_PRIVADO_PATH`), `corpus-legal/pedidos-8803` (editor fixtures; do not copy private question text).

### What would have to split (real symbols)

| Today | Split |
|---|---|
| `settings.conocimiento_qa_enabled` (one kill switch for mailbox + prose) | keep for mailbox; add `conocimiento_normas_enabled` for norms |
| `enforce_conocimiento_flag()` | stays qa-only; `/estado` keeps it |
| `enforce_conocimiento_qa_enabled()` (terms AND credential AND sidecar) | untouched, still guards `POST /preguntas` |
| `_SOLO_LECTURA` | untouched |
| (none) | new `enforce_conocimiento_normas()` = norms flag AND `repository.corpus_activo(db)` not None; refuses with a cause, never calls `verificar_terminos` / `SondaSidecar` |
| `trabajador._recuperar` (abstention guard + sintetico guard) | not reused; the norms path must still refuse `procedencia.sintetico` snapshots? Open: sintetico is about embeddings and BM25 arm reads none; decide explicitly |

### Editor slots (from the nine drafts; slot level only)

Common structure across `01..09`: header block (pendiente id, what it is, destinatario + address, prioridad, regimen); optional channel note; **cuerpo de la nota**; **asunto de correo** (1-2 variants); "Si no contestan" (escalation: art. 7 plazo, art. 8 silencio = denegatoria, amparo por mora; for #8 the two 27.275 paths); "Qué hace falta para que sirva".

- **Legal slots (machine-fillable, must be unit-pinned)**: regime citation (`8803 art. 6` x23, `art. 7` plazo, `art. 8` silencio, `art. 5` gratuidad/costo, `art. 4`, `art. 3`, `art. 9`; for #8 the 27.275 articles), plazo in business days, effect of silence, remedy. Each is a `(citation_key, span, vigencia)` at the served SHA. `8803#5..#9` exist as units (Articles 1-11).
- **Document-identification slots (data, human-confirmed)**: act type/number/organ/date (e.g. "Res. 0133/01, D.P.V., 2001-03-30"), expediente number, annex list. Come from MANIFEST pendientes (F-2, F-9, F-33, F-4, NL-3, F-17, F-22+F-27, F-25, F-30), not from retrieval.
- **Human-only block**: `[REQUERENTE]` (x36), `[DNI]` (x36), `[DOMICILIO / CORREO]` (x27), `[CORREO]` (x8), destinatario address, channel choice (e.g. #4 has no working institutional mailbox, in-person is primary), copia certificada cost consent (#6, #7). Operational facts (canal, meters, hectares, official, damage) were not present in these nine; they belong to later "obra notes" and stay a human block.
- **Regime switch**: #8 is the only non-8803 request (national organ -> Ley 27.275, AAIP). A template needs a `regimen` enum that swaps the cited unit set, deadlines and escalation paths. "27.275 case already drafted" = #8; it needs `ley-nacional` units in the corpus (27.275 is not in the 49 documents listed; verify before step 4).
- **Regression**: render each of the nine from slots and diff against the hand-written body modulo the human placeholders. Export fails closed when any cited key is not in the pinned snapshot, not `enviable`, or whose `chequear` span/vigencia does not match.

### Coupling with `consorcio-conocimiento-semantico` (must not be reopened)

| Item | Status there | Boundary for this change |
|---|---|---|
| Abstention threshold (decision 0.1) | OPEN; `umbral_abstencion.yaml` `no_derivado`; `tasks.md` 0.1, 9.5 BLOCKED | Norms route returns units or "no ranked result". No threshold, no "nothing applicable" claim, no confidence cutoff |
| Entailment / none-of-the-above signal | candidate options for 0.1 | `chequear` is a deterministic structural check (unit, span, vigencia, sha). It must not grow semantic support judgment |
| OOD classifier / router (`routing.py`, `classificacion` stage) | exists for mailbox | Not called by norms routes or editor |
| Unattended generation (`generacion.py`, `trabajador.py`, provider pin, quota/spend 0/0/0) | off; terms+credential+sidecar gates | Kernel has no `redactar`; MCP exposes three commands; export never calls a provider |
| `bm25_ce` contract (`RerankerRequerido`, test `test_sin_reranker_es_una_negativa`) | ratified B50 | New arm is additive; do not relax `bm25_ce` |
| Re-chunk F1 keys `#parte-n` | measured locally, "production index not re-ingested" | Re-ingest changes prod keys from whatever prod holds today; stale-cache labeling must not assume key stability |

### Approaches

**A. Norms-only response on the existing HTTP, stale SHA labeled, then re-ingest.**
- Pros: smallest first slice; ships value before the corpus migration; fits the owner's step order.
- Cons: needs a GPU-less arm that is unmeasured; the page cannot quote 31/34 (that is the reranked arm on a different host); stale-cache premise unverified for prod; no CLI/MCP reuse, so `buscar/leer/chequear` logic would live inside a route and be extracted later.
- Effort: Low-Medium.

**B. CLI over markdown first, HTTP later.**
- Pros: no flag, no server, no auth surface; fast for the owner.
- Cons: cannot reproduce the ranker without Postgres stemming (finding 6) => second ranker; cannot return `corpus_sha` as *served*; `estado_vigencia` and classification come from ingest-time logic (`clasificar_documento`, `normalize_tipo`), so re-implementing them over markdown forks the rules; nothing validates against the DB the page will read.
- Effort: Medium, with a hidden rewrite later.

**C. One Python library used by both the HTTP norms route and the CLI; ranker used only where its runtime exists, otherwise a named GPU-less arm.**
- Pros: single code path (same discipline as `recuperar`'s "one code path, all modes"); MCP can be a thin mirror of the same three functions; GPU arm available from the workstation CLI (`BGEReranker`) and BM25 arm from the box; the arm and SHA are part of every result so the badge is truthful; keeps `bm25_ce` untouched.
- Cons: more up-front surface (library API, arm enum, result schema); needs the GPU-less arm measured before shipping; two arms produce different orders for the same query, which users will notice.
- Effort: Medium.

### Red-Team Analysis

| Approach | Vulnerability | Severity | Mitigation |
|---|---|---|---|
| A | Serves BM25 order, a ranking the design explicitly never measured; users read it as the 31/34 system | **Critical** | Separate arm id (`bm25`), measure hit@5 on the 57 gold before enabling, show arm in every response, never reuse `bm25_ce` label or its number |
| A | "Stale cache until step 2" assumes the box holds 12043582; docs say production was not re-ingested | High | Operator reads `rag_corpus` on the box first; if empty, step 1 cannot ship and step 2 comes first |
| A | Flag split done by loosening `enforce_conocimiento_flag` instead of adding a dependency => mailbox POST reachable without terms/credential, or tests that pin flag-first order regress | High | New dependency and flag; keep `test_qa_surface.py` contracts; add "qa off, norms on" test matrix |
| A | `/estado` and the panel's 503 mapping stay behind the qa flag, so the SHA badge vanishes exactly when norms are on and prose is off | Medium | Put `corpus_sha`, arm, `ingested_at`, stale marker in the norms response itself |
| A | Logic embedded in route; MCP/CLI later duplicate it | Medium | Extract to library in the same change (this is C) |
| A | Empty result rendered as "no norm applies" (abstention claim, decision 0.1) | High | Wording and schema: `sin_resultados_en_este_arm`, never `abstencion` |
| B | Needs a different stemmer than Postgres Spanish => second ranker, unmeasured | **Critical** | Eliminated unless the CLI talks to Postgres (then it is C) |
| B | Returns "corpus SHA" of a checkout, not of the served index; can disagree with the page | High | Not fixable without the DB |
| B | Re-implements vigencia/classification/`tipo` rules over raw markdown, forking `repository` logic | High | Eliminated by reusing ingest outputs |
| B | Private corpus path on a dev laptop becomes the only way to use the tool; no audit trail | Medium | n/a |
| C | Library API drifts into a third ranker via convenience parameters (blend, per-doc cap) | High | Library takes only `modo`; blend and cap are documented REJECTED (`reranker.py`); keep the arm list closed and tested |
| C | CLI on workstation with GPU and HTTP on box answer the same query differently, user cannot reconcile | Medium | Arm in every result; CLI default = the box's arm unless `--ranker ce` is passed; identical output schema |
| C | CLI against prod Postgres from the workstation widens DB credential exposure | Medium | Read-only DB role for the kernel; CLI refuses write paths; `rag_ingest.py` stays the only writer |
| C | `chequear` degenerates to "substring anywhere" | **Critical** | Signature `(citation_key, span, expected_vigencia, corpus_sha)`; verify key exists at that SHA, span is an exact substring **of that unit's `texto`**, vigencia status matches the stored `estado_vigencia`, SHA equals the active one; a different SHA is a refusal, not a warning |
| C | Export cites a `privado` unit into an outgoing request | **Critical** | Reuse `CLASIFICACIONES_ENVIABLES`; export fails closed; test with a private fixture |
| C | MCP thin mirror becomes the place where redactar creeps in | Medium | MCP tool list pinned by test to exactly `buscar`, `leer`, `chequear` |
| All | Step 2 activates the new SHA on ingest (finding 1) before hit@5 is known | **Critical** | Ingest+eval on lab DB; prod ingest only after the bar; documented `activo=false` rollback; gate in the runbook |
| All | Gold items lose targets after pin migration (finding 4) and hit@5 is judged against broken keys | High | Key-existence pre-check of all `citas_esperadas` against the new snapshot before running hit@5; report migration-induced misses separately |
| All | `corpus_expectations.yaml` for 14 new docs is hand work with no generator; a wrong exclusion silently drops units | High | Inventory gates already catch counts; add a diff report old-vs-new per document; this is the largest effort item of step 2 |
| All | Untracked/unpushed corpus state blocks reproducible ingest | High | Owner must commit/push (or ignore) the barrido dir and push `f55b96fa` before step 2; this exploration did not and must not |

### Red-Team Verdict

- **Strongest approach after attack:** **C**.
- **Approaches eliminated:** **B** as framed (markdown-only). It is only viable as C's CLI, which requires the DB. **A** is not eliminated, but as a standalone it fails on the unmeasured-arm and extract-later problems; it survives only as C's first deliverable.
- **Required mitigations before proposal:** (1) GPU-less arm named, additive, measured on the 57 gold, with a stated bar; (2) norms gate is a new dependency and flag; (3) ingest-is-publish resolved in the step 2 design; (4) `chequear` signature and the enviable-only export rule fixed in the spec; (5) gold key re-validation step in step 2.

### Recommendation

Approach **C**, delivered in the owner's order, with these corrections to the premises:

1. **Step 1** is "add `conocimiento_normas_enabled` + `enforce_conocimiento_normas` + a sync norms route returning units with `estado_vigencia`, `es_secundaria`, `tipo`, `corpus_sha`, arm, `ingested_at`, stale marker", not a flag split. HTTP serves the GPU-less arm; it does not and cannot call `BGEReranker`. Operator-verify what the box holds before promising "stale cache".
2. **Step 2** must restructure around "ingest = publish": lab ingest and 57-item run on the workstation first (needs GPU), bar 0.72 checked, then prod ingest. Budget the pin migration across the eight files in finding 3 and the 14-document expectations. Required inputs from the owner: a clean pushed corpus commit.
3. **Step 3**: library in `app/domains/conocimiento/` (new module) over a `Session`; CLI beside `rag_ingest.py`; MCP = three tools mirroring it. `buscar(modo)` where `bm25_ce` requires a real `Reranker` and the GPU-less arm is its own mode. `chequear` per the red-team signature.
4. **Step 4** editor: slot model above; the nine drafts as the regression; export gated by `chequear` + enviable-only + SHA equality.

"Usable" holds on the GPU-less arm **structurally** (vigencia, norma-vs-secundaria — BM25 index is norma-only — and SHA all present) but its **ranking quality is unknown until measured**. That is the one owner-visible consequence: the 31/34 is the workstation arm; the box page will show a different (to be measured) number.

### Risks

- Unmeasured BM25 order shown as the page's ranking (Critical) — gate with a measured number.
- Ingest activates the new SHA immediately (Critical) — no rollback guard exists today.
- Prod box state unknown (index present? which keys? F1 re-chunk not deployed).
- Pin migration spans ~8 files plus owner-private YAML; 14 new documents lack expectations; gold targets may move (22 files changed since the pin).
- Corpus repo: unpushed commit and untracked dir block `verify_corpus_pin`.
- Abstention figure mismatch: owner said ~0.44, repo says 0.489.
- Private-unit leakage via export to third parties.
- Two arms with different orders for one query.
- `require_admin` is a V1 approximation of the Comisión Directiva role (F3 open); the editor inherits it.
- Ley 27.275 text for pedido #8 is not among the 49 indexed documents; confirm before step 4.
- Sdd-explore did not run the eval or touch a DB; every measurement above is quoted from committed docs.

### Ready for Proposal

**Yes**, on the definition the owner gave (not prose-only), and because the three required facts are verified against `origin/main`: the flag (default false, 503 on every route), the pin (`12043582...`, baked into 8+ files), and where the reranker runs (CUDA only, workstation worker/eval; the box has no GPU and `BGEReranker` refuses CPU).

The proposal must carry these as explicit gates, not assumptions: (a) measured GPU-less arm on the 57-item gold before step 1 ships; (b) operator check of `rag_corpus` on the box; (c) ingest-is-publish handling and the 0.72 bar in step 2; (d) a clean, pushed corpus commit as a precondition; (e) the 0.44 vs 0.489 figure confirmed with the owner, since this change deliberately does not touch it. Do not start `sdd-propose` from this phase.
