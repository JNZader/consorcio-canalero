# Proposal: Consorcio RAG V0 — Cited Legal Retrieval Foundation

## Intent

The Comisión Directiva answers legal questions (canal N°5 boundary dispute, obras audit) by hand-reading 35 legal documents. A curated corpus already exists — 1,383 article-level units, 12-type taxonomy separating *derecho aplicable* from *fuente secundaria*, 810 anti-hallucination substring gates (`~/Escritorio/consorcio/corpus-legal/MANIFEST.md`) — but it is inert markdown on a desktop. The approved initiative (engram #12574, #11648 item 4) gates a CD-only Telegram bot behind a measured retrieval layer, because **derecho + LLM sin cita = peligro**. V0 builds and *measures* that layer. It ships no user surface.

## Scope

### In Scope

- **pgvector, dev only** — derivative `FROM pgrouting/pgrouting:16-3.4-3.6.1` + PGDG `postgresql-16-pgvector`. Empirically confirmed absent from the pinned image (`pg_available_extensions` has no `vector` row; PG 16.2 Debian pgdg; `spanish` FTS config present).
- **Domain `gee-backend/app/domains/conocimiento/`** — models/schemas/repository/service, house pattern, **no router in V0**.
- **Ingestion pipeline** implementing MANIFEST regex v3 + type-scoped rules *verbatim*, with a count gate.
- **Schema** — `rag_documento` + `rag_unidad`, PK = the corpus's own citation key (`9750#3`, `res4-2026#anexo#art9`), `tsvector('spanish')` GENERATED + GIN, `vector(1024)` + HNSW cosine.
- **Hybrid retrieval** — independent FTS + vector queries fused by RRF (k=60). Never a blended score.
- **Embeddings** — self-hosted BGE-M3 (8192 ctx keeps long articles unsplit; nothing leaves infra), with an API baseline compared in the eval on public-domain law text only.
- **Eval set** — canal N°5 (7 Q/A, answerable) + obras-audit §5 (18 questions, abstention gold) + MANIFEST D/F-notes (adversarial vigencia traps).
- **Deliverable: an offline retrieval-quality report** with a three-mode ablation (FTS-only / vector-only / hybrid RRF) and the metrics below.

### Out of Scope

- **Production Postgres image swap** — see Scope Decision. Becomes a V1 dependency.
- V1 (`consorcio-rag-bot`: Telegram, whitelist `telegram_id`→padrón, answer generation) and V2 (`consorcio-rag-voz`: Whisper).
- Actas ingestion — blocked on *libro digital de actas* (carril 2); that is where real PII lives.
- **PixelRAG** — assessed and rejected for the V0 core (engram `sdd/consorcio-rag/pixelrag-assessment`); tracked candidate for the future actas/BO scanned-document layer, criteria = citation precision vs OCR+text, privacy, VLM serving cost.
- Any generative answering. An LLM-as-judge inside the offline eval is evaluation tooling, not product surface.
- Meteorological calculation — stays deterministic in Lluvia v2. RAG serves cited documentary context only.

## Scope Decision

- **Mode**: **Selective**
- **Justification**: The incoming scope conflated *"V0 needs pgvector"* with *"production needs pgvector"*. V0 has no user surface, so it needs no production database change — and consorcio runs **one single environment** (Hetzner box, compose outside this repo), where swapping the Postgres image also puts PostGIS, pgRouting and Martin tiles at risk for a feature nobody can use yet. Trimming that one item removes V0's highest-severity operational risk at zero cost to the deliverable. In exchange the eval gains a **three-mode ablation** (~free: same harness, three queries), so V1's go/no-go can answer *"do we need vectors in production at all?"* with numbers instead of assumption — and if FTS-only clears the bar, the prod image swap never has to happen.

## Decisions (owner review — recommended, not assumed)

| Question | Recommendation |
|---|---|
| **V1 go/no-go thresholds** | `hit-rate@5 ≥ 0.85`, `MRR ≥ 0.70` on the answerable set; **`citation-precision = 1.00`**, **`norma-vs-secundaria = 1.00`**, **`vigencia-correctness = 1.00`** (all three are mechanical properties — anything below 1.0 is an ingestion bug, not a model limit); `abstention recall ≥ 0.90` (≤2 of 18 false-confident) and `abstention precision ≥ 0.80`. Recall is the tighter bar because a false-confident legal answer to the CD is the catastrophic failure; a wrongful abstention is merely annoying. **Precondition**: the answerable gold set MUST reach ≥20 questions — thresholds over n=7 are noise. |
| **Embedding compute** | **One-shot batch on the local RTX 5060 Ti**, ship vectors as a `COPY` dump. ~1,400 units is minutes on GPU, and the CX33 is CPU-only. *Query-time* embedding is the permanent cost and a **V1** blocker, not a V0 one — V0 must **measure** BGE-M3 single-query CPU latency on the box and report it. API-for-queries is NOT recommended: user-typed CD questions may carry context the corpus does not. |
| **Corpus source location** | **Its own git repo** (`consorcio-corpus-legal`), pinned by commit SHA in the ingestion config. Keeps reproducibility without making this app repo the de-facto corpus editor, and pre-draws the boundary for the private actas layer. Low-effort fallback: leave it at `~/Escritorio/` + commit a checksum manifest. Units land in the DB either way. |
| **Privacy boundary** | Drawn at the **actas layer**, not now — the current corpus is public-domain law (SAIJ/BO). Spec requirement: nothing from a private corpus reaches an external embedding/VLM/judge without explicit owner decision. |

## Capabilities

### New Capabilities
- `knowledge-corpus-ingestion`: parse the corpus per MANIFEST rules; verbatim integrity, citation-key uniqueness, type taxonomy, vigencia flags.
- `knowledge-hybrid-retrieval`: FTS + vector RRF fusion, abstention threshold, the eval harness and its report contract.

### Modified Capabilities
- None.

## Approach

1. **Gate zero** — re-run the corpus's own `_gate-consolidacion-final.py`; 1,383 is inherited, not independently verified.
2. `docker/postgres/Dockerfile` derivative; dev `docker-compose.yml` switches `image:` → `build:`.
3. Alembic migration: `CREATE EXTENSION vector` + both tables + GIN + HNSW (default params — 1,383 rows makes index tuning a non-problem).
4. Ingestion: regex v3 with D-10 scoped to `tipo: norma-tecnica`, D-9 composite keys, D-22 `ley`≡`ley-provincial`. Long articles stay whole.
5. Embed offline on GPU; load vectors.
6. Retrieval service: two independent queries → RRF(k=60); abstention calibrated as an RRF top-1 cutoff against the answerable/unanswerable split.
7. Eval harness → written report, three modes, metrics above.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `docker/postgres/Dockerfile` | New | Derivative image + `postgresql-16-pgvector` |
| `docker-compose.yml:6` | Modified | `image:` → `build:` (dev only) |
| `gee-backend/app/domains/conocimiento/` | New | models/schemas/repository/service; no router |
| `gee-backend/app/db/migrations/versions/` | New | extension + `rag_documento` + `rag_unidad` + indexes |
| `gee-backend/tests/new/` | New | ingestion gates + eval harness |
| `gee-backend/requirements*.txt` | Modified | `pgvector`; embedding libs as an ingestion extra, not app runtime |
| Hetzner prod compose (outside repo) | **Untouched** | V0 changes no production service |
| `app/api/v2/`, all other domains | Untouched | Nothing mounted, no contract touched |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Global D-10 rule injects 31 false units across 5 secondary docs (the ~19%-loss trap) | High if missed | Rule SCOPED to `tipo: norma-tecnica`; gate test asserts total **and** per-document counts against MANIFEST |
| D-9 duplicate article numbers collide on PK | Med | Composite citation key per MANIFEST + `UNIQUE` + regression test |
| Long unsplit articles truncated by the embedder | Med | Measure max token count vs 8192 ctx **before** ingesting; fail loudly, never silently truncate |
| Thresholds scored over n=7 | High | Answerable gold set expanded to ≥20 before any go/no-go call |
| Inherited 1,383 count is wrong | Med | Gate zero re-runs the corpus script |
| Vigencia traps returned as live law (ley-8548 derogada, ley-10679 art.20) | Med | `estado_vigencia` on `rag_documento`, surfaced with every hit; adversarial trap questions in the eval |
| Eval LLM-as-judge leaks text externally | Low | Public-domain law only; actas NEVER — written as a spec requirement |

## Rollback Plan

**Ordering matters**: `alembic downgrade` FIRST (drops `rag_unidad`, `rag_documento`, then `DROP EXTENSION vector`), THEN revert `docker-compose.yml` to the pinned upstream image. Reverting the image while `vector` objects still exist leaves an unloadable database on the shared dev volume.

Then: delete `app/domains/conocimiento/` — it is mounted nowhere, so this is a file deletion with zero route or contract impact. The corpus markdown is an external read-only input and is never mutated. **No production rollback exists because V0 makes no production change.**

Impacted contracts: none. No API change, no migration to any existing table.

## Dependencies

- Corpus + its `_gate-consolidacion-final.py` (ready).
- BGE-M3 weights + the local GPU workstation for the one-shot batch.
- Owner ratification of the thresholds and the three decisions above.
- V1 (not V0) additionally needs: the production image swap, Telegram infra, `telegram_id`→padrón whitelist (`app/domains/padron/`), a citation-enforcing generation layer.

## Success Criteria

- [ ] `SELECT 1 FROM pg_extension WHERE extname='vector'` returns a row in dev.
- [ ] Ingestion loads exactly the MANIFEST unit count, total and per document.
- [ ] Every `rag_unidad.texto` is a byte-exact substring of its source file (corpus substring-gate method, run as a test).
- [ ] Citation keys are unique, including the D-9 collision cases.
- [ ] Hybrid retrieval returns fused results with `tipo` and `estado_vigencia` attached to every hit.
- [ ] Report delivered with all metrics across the three ablation modes, plus measured CPU query-embedding latency.
- [ ] The answerable gold set reaches ≥20 questions before any threshold is scored.
- [ ] No production service changed; existing test suite green.

## Proposal question round

Written here because this executor cannot ask interactively. Assumptions above need owner review on:

1. **Is the dev-only trim acceptable?** It means V0 proves the layer works but nothing is queryable on the box. Confirm, or state that a production-ready V0 is required (then the image swap and its single-environment risk return to scope).
2. **Who writes the extra ~13 answerable gold questions, and from which real CD disputes?** Without them the go/no-go is statistically meaningless — this is the single biggest unowned task.
3. **Are the six threshold numbers right?** Specifically: is `abstention recall 0.90` (2 false-confident answers out of 18 tolerated) acceptable for legal context, or must it be 1.00?
4. **Corpus repo**: split into `consorcio-corpus-legal` with SHA pinning, or the cheap checksum-manifest fallback?
5. **Anything the CD asks *routinely* that is missing from the eval set?** The two gold sources are both one-off disputes; if the everyday questions look different, the report will measure the wrong thing.

## Owner decisions (2026-08-10) — proposal question round CLOSED

1. **Infra defaults RATIFIED (all three)**: dev-only pgvector for V0 (prod Postgres image untouched until the FTS/vector/hybrid ablation proves vectors are needed); embeddings as a one-shot batch on the owner's local RTX 5060 Ti GPU shipped as a COPY dump, with V0 measuring real CPU single-query embedding latency on the CX33; corpus in its own git repository pinned by SHA from the app.
2. **Gold questions**: an agent drafts ~20 candidate Q/A pairs (with expected citations per unit) from the corpus and its derived analyses; the owner validates/curates them in one pass. The n≥20 precondition stands.
3. **Abstention recall threshold TIGHTENED by owner: 1.00 (was 0.90)** — in legal context a single falsely-confident answer to the Comisión Directiva is unacceptable; if the eval misses 1.00, the correct response is raising the system's abstention threshold, not lowering the bar. Precision ≥ 0.80 stands.

## Owner decisions round 2 (2026-08-10) — all-local V0

4. **Gold set RATIFIED in full**: the owner approved eval-preguntas-oro-DRAFT-2026-08-10.md verbatim — final set 29 answerable + 23 unanswerable = 52 (2.6× the n≥20 floor). Slice-4 denominators: 29/23.
5. **All-local V0 (owner rule: "nothing reaches prod until 100% functional locally")**: corpus batch embeddings on the owner's RTX 5060 Ti → COPY dump → local dev DB only; the CX33 query-latency measurement is DEFERRED to the V1 gate (V0 reports local GPU + CPU-capped-estimate numbers, labeled); production remains untouched by V0 in every respect.
6. **Baseline is LOCAL, not API**: BGE-M3 compared against multilingual-e5-large, both self-hosted on the owner's GPU — zero external calls, no text egress of any kind. The API-baseline option is dropped; the privacy boundary becomes vacuously satisfied for V0.
