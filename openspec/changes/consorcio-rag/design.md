# Design: Consorcio RAG V0 — Cited Legal Retrieval Foundation

## Technical Approach

A new offline domain `gee-backend/app/domains/conocimiento/` turns the external, SHA-pinned corpus
into a queryable, measurable retrieval layer. Three boundaries carry the whole design:

1. **Verbatim vs indexable text.** `texto` is a byte-exact substring of the source file and is the
   only thing ever shown as a citation. `texto_indexado` (title + structural path + `texto`) is what
   FTS and the embedder see. Enrichment can never leak into a citation.
2. **Two independent legs, fused by rank.** FTS (`tsvector('spanish')` + GIN) and vector
   (`vector(1024)` + HNSW cosine) are queried separately and fused by RRF (k=60) in pure Python.
   No blended score exists anywhere in the codebase.
3. **pgvector is dev-only, and the schema says so.** The vector column lives in a *conditional*
   migration and is **not mapped in SQLAlchemy**. CI, prod and `Base.metadata.create_all` never see
   it; the vector leg fails loudly rather than degrading to FTS.

V0 ships no HTTP surface. Every entry point is a script; the deliverable is a markdown report.

## Architecture Decisions

### D1 — Schema and keys

| Aspect | Choice | Rejected | Rationale |
|---|---|---|---|
| PK of `rag_unidad` | Natural composite `(corpus_sha, citation_key)` | `UUIDMixin` (house default); bare `citation_key` | Immutable externally-keyed snapshot, referenced by nothing. The natural key makes idempotent upsert and the uniqueness gate free, and lets two snapshots coexist for A/B. Deliberate, documented deviation from `app/db/base.py:33`. |
| Snapshot isolation | `rag_corpus(corpus_sha PK, repo_url, manifest_version, unidades_declaradas, ingested_at, activo)`; every repository method takes `corpus_sha` as a **required positional argument** | Implicit "latest" / a global | A forgotten snapshot filter is a `TypeError`, not silent double results. |
| FTS | `tsv GENERATED ALWAYS AS (setweight(to_tsvector('spanish', coalesce(epigrafe,'')),'A') \|\| setweight(to_tsvector('spanish', texto_indexado),'B')) STORED` + GIN | Trigger-maintained column; runtime `to_tsvector` | Generated columns require IMMUTABLE: the **2-arg** `to_tsvector(regconfig, text)` is immutable (the 1-arg form is only STABLE and would be rejected) — the literal `'spanish'` is load-bearing, not style. |
| Vector | `vector(1024)` (BGE-M3 dense), HNSW `vector_cosine_ops`, **default** `m=16, ef_construction=64` | Tuned HNSW; IVFFlat; no index | At n≈1,400 an exact scan is sub-10 ms and 100 % recall. The index exists so V1 inherits the identical query plan shape, not for speed. Tuning here would be measuring noise. |
| Legal metadata | `rag_documento`: `tipo` (12 values, `ley`≡`ley-provincial` per D-22), `es_secundaria` (derived, NOT NULL), `jurisdiccion` (Text, NOT NULL), `estado_vigencia`, `relevancia_consorcio` (Text, NULL), `verificacion`, `clasificacion` (`publico`/`privado`, **default `privado`**), `fuente_url`, `fecha_sancion/bo` | Loose JSONB | `tipo` + `estado_vigencia` travel with **every** hit (proposal Success Criteria), and so do `jurisdiccion` + `relevancia_consorcio` — see the carriage rule below; `clasificacion` default-deny is the mechanical form of the privacy boundary (D3). |
| Provenance | `corpus_sha CHAR(40)` on both tables; `rag_unidad.source_file`, `source_offset` | Trusting the file tree | The verbatim gate needs the exact source bytes it claims to be a substring of. |

**Why `relevancia_consorcio` and `jurisdiccion` are typed columns and not dropped metadata.**

- `relevancia_consorcio` is the **only** place the corpus records its do-not-cite warning, and no other
  column can derive it. `resolucion-4-2026-bioagroindustria-reglamento-11059.md:3` declares
  `tipo: resolucion-ministerial` — derecho aplicable, so `es_secundaria = False` — while the same file's
  `relevancia_consorcio` (`:46-51`) reads *"RÉGIMEN HERMANO — CONTEXTO COMPARATIVO, NO DERECHO APLICABLE
  AL CONSORCIO CANALERO … NO debe citarse como fundamento de ninguna obligación ni facultad de un
  consorcio canalero."* Two further documents open their `relevancia_consorcio` with the same
  "RÉGIMEN HERMANO — … NO DERECHO APLICABLE AL CONSORCIO CANALERO" header
  (`ley-11059-consorcios-camineros.md:75`, `decreto-280-2025-facultades-bioagroindustria.md:33`), and the
  field is equally load-bearing in the opposite direction — Ley 6604 uses it to record that its art. 36
  inc. f) is character-identical to art. 39 inc. g) of Ley 9750
  (`ley-6604-consorcios-riego.md:32-38`). Without the column a hit on `res4-2026#anexo#art9` is
  architecturally indistinguishable from a hit on `9750#3` — the precise *derecho + LLM sin cita =
  peligro* failure this initiative exists to prevent.
- `jurisdiccion` is the MANIFEST's declared provincial/nacional filter (`MANIFEST.md:693`) and is one of
  the 11 common frontmatter keys present in every document (`MANIFEST.md:230-233`). Ingesting it costs one
  column in the pass that is already reading the frontmatter; deferring it costs a full re-ingest in V1.
- Both are **carried, never interpreted**. They are free text copied verbatim from frontmatter and
  surfaced as-is (D4). V0 derives no boolean from `relevancia_consorcio`: a regex over legal prose is
  exactly the silent misclassification this design refuses. `jurisdiccion` is NOT NULL (always present);
  `relevancia_consorcio` is nullable because the schema must not lie about a document that lacks it.

Citation keys are taken **verbatim from MANIFEST**, never re-derived: `9750#3`, `5589#193bis`,
`3780-C-65#punto-4`, `res4-2026#anexo#art9`, `10demayo#res189-2014#art1`, `srh-2013#punto-3.1`,
`informe-f3#sec-3`. Resolutions are always keyed by full identity (`res-aprhi-004-2026#art1`), never
`4#art1` — five distinct resolutions own an "art. 1". Units the MANIFEST indexes without declaring a key
follow its own document + section convention, pinned in `corpus_expectations.yaml` (D2).

### D2 — Ingestion pipeline

`parser.py` is a **pure function of (markdown text, frontmatter) → list[Unidad]**, zero DB. It
implements MANIFEST regex v3 verbatim (em-dash prefix group `Anexo|Anexo I+|Decreto|Resolutivo`,
alternation `Art.|Artículo|Punto|Norma`, suffix `bis|ter|qu[aá]ter|quinques|sextus`) plus three
scoped rules: `^## (\d)\. ` **only** when `tipo == 'norma-tecnica'` (D-10), the composite-key rule for
D-9, and whole-chunk handling for the un-articled Anexos I/XI of Res. DNV 908/2026.

**Two opposite-signed traps, named separately because conflating them has already happened once:**

- **Under-capture — the 19 % loss.** Running only the v2 `ART` regex misses the compound headings that
  integración 4 introduced (`## Anexo — Art. N`, `## Decreto — Art. N`, `## Resolutivo — Artículo N°`,
  `## Anexo II — Norma N`) and loses **260 units, 19 % of the corpus, without a single visible error**
  (`MANIFEST.md:629-633`). The fix is the v3 **prefix group**, applied to every document.
- **Over-capture — D-10 applied globally.** The `^## (\d)\. ` rule that D-10 *requires* for the Normas
  SRH 2013 (`MANIFEST.md:664-669`), if run unscoped, swallows the numbered commentary sections of five
  secondary documents and indexes **31 false normative units** (`MANIFEST.md:782-800`). The fix is the
  `tipo == 'norma-tecnica'` **scope**.

The two pull in opposite directions: the first loses real law, the second invents it. A single "the
D-10 trap" label covers only the second.

**Non-article sections.** Excluded `##` sections are an explicit deny-list transcribed from
`MANIFEST.md:752-780` and `:812-821` (procedencia y verificación, VISTO/considerandos of the general
norms, encabezado/firmas, nota de extracción, «Relevancia para consorcios canaleros», …). Sections the
MANIFEST marks as *content but not articulado* are **ingested with a distinct `tipo_chunk`**, never as
articles:

| `tipo_chunk` | What | MANIFEST authority |
|---|---|---|
| `articulo` | the 1,383 normative units | `MANIFEST.md:33-43` |
| `considerando` | VISTO/considerandos of the two Leones – Villa Elisa resolutions | `MANIFEST.md:778-780` |
| `guia-de-uso` | Ley 8803's four closing operational-advice sections | `MANIFEST.md:823-827` |
| `nota-vigencia` | Ley 10679 `## Vigencia de los fondos` — carries the text that **substituted** arts. 17/20/24; the captured articulado is the 2019 text and is no longer in force | `MANIFEST.md:857-860` |
| `ficha-registral` | 10 de Mayo `## Ficha registral APRHI` — "es justamente lo que se le va a preguntar al RAG sobre el propio consorcio" | `MANIFEST.md:834-836` |
| `seccion-secundaria` | the 6 secondary documents, keyed by document + section (`informe-f3#sec-3`, `auditoria-10-de-mayo#§3.2`) | `MANIFEST.md:746-750` |

**Keys for non-article units follow the corpus's own document + section convention**
(`MANIFEST.md:746-750`): `{documento}#{slug-de-sección}` — `informe-f3#sec-3`,
`auditoria-10-de-mayo#§3.2`, `srh-2013#punto-3.1`, and `10679#vigencia-de-los-fondos`, which is exactly
the key the gold draft expects for the T-1/T-2 canaries. The slug is the section heading lowercased with
spaces hyphenated, so it is derivable rather than invented, and `corpus_expectations.yaml` pins the
expected key of every non-article unit so it cannot drift away from the gold set's `citas_esperadas`.
Size note for the D3 pre-flight: the largest non-article chunk is that vigencia section
(252 lines, ~19.4 kB, ≈6 k XLM-R tokens) — legitimately one chunk, inside the 8192 ceiling, and close
enough to it that the ceiling gate must cover non-article units too, not only articles.

**The count gate is scoped to `tipo_chunk = 'articulo'`.** The MANIFEST's 1,383 is an inventory of
article-shaped units only — 1,377 v3 captures plus the 6 SRH points/Anexo (`MANIFEST.md:624-627`) — and
the six secondary documents contribute **0** to it on purpose (`MANIFEST.md:42`). Non-article units
therefore carry their **own** per-document expected inventory in `corpus_expectations.yaml`, asserted
with the same per-document strictness. Both halves are load-bearing: counting non-article chunks toward
1,383 breaks the gate, and not counting them **at all** is how the Ley 10679 vigencia section quietly
never gets ingested and the system answers *"el FDA venció en 2023"* with a byte-exact citation.

**Gates (hard tests, not warnings):** `corpus_expectations.yaml` — checked in, derived from MANIFEST —
carries **two inventories**: the article one (per-document expected count plus the per-class subtotals
1358 + 6 + 19 + 0 = 1383) and the non-article one (per-document expected `tipo_chunk` + citation key).
The gate asserts **total AND per document** on both; a total-only gate is exactly how a compensating
pair of over- and under-capture passes unnoticed. A second gate asserts `texto` is a byte-exact
substring of its source file (the corpus's own substring-gate method). A third asserts citation-key
uniqueness including the D-9 collision pairs.

**Corpus location** is a required CLI argument (`--corpus-path`) plus `--corpus-sha`; the ingester
verifies `git rev-parse HEAD` at that path equals the declared SHA and refuses on a dirty tree. No
baked path — `~/Escritorio/...` never appears in the repository.

**Idempotency**: `INSERT ... ON CONFLICT (corpus_sha, citation_key) DO UPDATE`. Re-running is a no-op;
a different SHA is a new snapshot, not a mutation. One caveat the upsert hides, stated so it is a
decision and not an oversight: `DO UPDATE` also silently overwrites a row whose **content** changed
while the SHA did not. That is impossible from a clean checkout of a pinned commit — which is why the
ingester verifies `git rev-parse HEAD` and refuses a dirty tree — but it is reachable from a re-emitted
corpus that reused a SHA, and the overwrite leaves no trace. Optional `--verify-unchanged` mode: when
`corpus_sha` is already present, compare a sha256 of `texto` per citation key first and **report the
divergence instead of overwriting it**. Off by default, one extra SELECT, and it turns a silent rewrite
into a diff.

### D3 — Embedding lifecycle

| Stage | Design |
|---|---|
| Pre-flight | Tokenise every `texto_indexado` with the BGE-M3 (XLM-R) tokenizer; **abort loudly** if any exceeds 8192. MANIFEST forbids splitting long articles, so silent truncation is the only failure mode that could survive review. |
| Batch (GPU) | `scripts/rag_embed_batch.py` on the RTX 5060 Ti. `normalize_embeddings=True` (mandatory for cosine). **No query/document prefix** — BGE-M3 is symmetric, unlike BGE-v1.5/E5 which need one; adding a prefix silently degrades it. |
| Artifact | `vectors-{sha8}.copy` — PostgreSQL COPY text format, columns `(corpus_sha, citation_key, embedding)` with the pgvector literal `[v1,v2,…]`, float32-cast, shortest round-trip repr (pgvector stores float4, so nothing is lost). Sidecar `vectors-{sha8}.json`: model id + **HF revision SHA**, dims, normalized, corpus_sha, n_vectors, sha256 of the dump, torch/transformers versions, device. |
| Load | `scripts/rag_load_vectors.py`, **COPY into a staging table, never into `rag_unidad`**. Direct `COPY rag_unidad (corpus_sha, citation_key, embedding)` cannot execute: ingestion (D2) already created every row, the PK is `(corpus_sha, citation_key)`, and **`COPY` has no upsert** — there is no `ON CONFLICT` clause for `COPY`. It would attempt inserts and fail on the PK for all ~1,400 rows. So: (1) pre-checks — refuse unless the dump's sha256 matches the sidecar, `corpus_sha` is the active snapshot, `n_vectors == count(rag_unidad WHERE corpus_sha = …)` and dims == 1024; (2) `CREATE TEMP TABLE rag_embedding_staging (corpus_sha CHAR(40), citation_key TEXT, embedding vector(1024)) ON COMMIT DROP` and `COPY` the dump into it; (3) `UPDATE rag_unidad u SET embedding = s.embedding FROM rag_embedding_staging s WHERE u.corpus_sha = s.corpus_sha AND u.citation_key = s.citation_key`; (4) post-checks **in the same transaction** — the `UPDATE` rowcount MUST equal `n_vectors`, and the orphan anti-join (`SELECT s.citation_key FROM rag_embedding_staging s WHERE NOT EXISTS (SELECT 1 FROM rag_unidad u WHERE u.corpus_sha = s.corpus_sha AND u.citation_key = s.citation_key)`) MUST return zero rows; any unresolved staging key **aborts**. Single transaction, all-or-nothing: nothing commits unless every key resolved. |
| Query-time (V0 only) | Local BGE-M3 on **CPU**, loaded once per harness process. `scripts/rag_query_latency.py` reports p50/p95 over the gold questions (3 warm-ups, 3 repeats) with CPU model, core count and thread settings. Candidate run: throwaway container on the CX33 (`docker run --rm`, nothing installed on the host — prod's *state* stays untouched, though its CPU and network do not; see the Open Question). Alternative: a CPU-only container locally with matching cpuset, **labelled ESTIMATE** in the report. Owner call, still open. No V1 serving decision is made here. |
| API baseline | One extra eval leg over the same corpus with a hosted embedder, **gated** by `assert_public_domain(corpus_sha)`: it raises unless *zero* documents in the snapshot have `clasificacion <> 'publico'`. Default-deny, so the actas layer cannot ever fall through. |

Rejected: `.npy`/parquet dumps (extra dependency + column-order coupling), pickle (unsafe), API for
corpus embeddings (privacy posture + the box is CPU-only anyway).

### D4 — Retrieval and RRF

```
question ──┬─► FTS leg    : tsv @@ websearch_to_tsquery('spanish', q)
           │               ORDER BY ts_rank_cd(tsv, q, 32) DESC,
           │                        citation_key ASC              LIMIT 50 ──┐
           │                                                                 ├─► rrf(k=60) ─► top-10
           └─► vector leg : ORDER BY embedding <=> :qvec ASC,                │        │
                                     citation_key ASC              LIMIT 50 ─┘        │
                            (raw SQL, ::vector cast)                                  ▼
                                                              hits + citation_key + verbatim texto
                                                              + tipo + es_secundaria + jurisdiccion
                                                              + estado_vigencia + relevancia_consorcio
                                                                        │
                                                              AbstentionPolicy ─► answer | abstain
```

- `fusion.py` is a pure function `reciprocal_rank_fusion(lists, k=60) -> [(key, score)]`, `1/(k+rank+1)`,
  identical to the rag-advanced formula. Fusing in Python (not SQL) keeps it unit-testable with zero DB
  and makes the three ablation modes share one code path.
- **Deterministic legs.** Both leg queries carry `citation_key ASC` as the secondary `ORDER BY`
  (`ts_rank_cd(...) DESC, citation_key ASC`; `embedding <=> :qvec ASC, citation_key ASC`). This is not
  cosmetic: PostgreSQL leaves the order of tied rows unspecified, and the corpus contains **45 articles
  of the Anexo of Res. 4/2026 whose entire body is the words "Sin Reglamentar"** (`MANIFEST.md:658-660`),
  plus their counterparts in Decreto 318/2007. They are near-identical text, so they collide on
  `ts_rank_cd` and sit within floating-point noise of each other on cosine distance. At the `LIMIT 50`
  boundary an arbitrary tie order decides **which** of them enters fusion at all, which flips fused ranks
  and therefore gold outcomes between runs over identical data.
- **Tie-break in fusion**: `(-score, citation_key)` ascending. The two together — sorted legs and sorted
  fusion — are what the D6 determinism claim rests on; either alone leaves a reproducibility hole.
- A unit absent from a leg contributes 0 from that leg. No imputation, no normalisation, no blending.
- Citation assembly returns `citation_key + tipo + es_secundaria + jurisdiccion + estado_vigencia +
  relevancia_consorcio + verificacion + fuente_url + verbatim texto`. Secondary sources are returned
  (they answer real questions) but carry `es_secundaria=True` so the consumer must name them as evidence,
  never as norm. `relevancia_consorcio` travels for the same reason and covers what `es_secundaria`
  cannot: a document that **is** derecho aplicable by `tipo` and still must not be cited as grounds for a
  canalero obligation (D1).
- `vector_search()` raises `VectorSupportUnavailable` when the extension/column is absent — it never
  falls back to FTS. Silent degradation would make the ablation meaningless.

### D5 — Abstention (tunable by construction)

`AbstentionPolicy(min_score, min_margin, require_both_legs)`. The eval sweeps `min_score` over the
observed fused-score grid **per mode** and reports the full precision/recall curve.
**Scores are not comparable across modes** (hybrid top-1 can reach 2/61, a single leg only 1/61), so
three thresholds are calibrated, not one — conflating them is how an ablation silently lies.

**Threshold selection is leave-one-out cross-validated; scoring never reuses the fitting sample.**
Sweeping `min_score` on the gold set and then reporting precision/recall *on that same set* fits the
threshold to the 38 items it is about to be graded on. The resulting numbers are a training fit read as
a measurement — post-hoc overfit wearing the costume of rigour, and the smaller the set the louder the
lie. So, per mode: for each gold item *i*, select the threshold by sweeping over the **other n−1** items
(same rule: highest precision among thresholds achieving recall 1.00; ties broken by the lower
threshold, deterministically — and if **no** threshold on that fold reaches recall 1.00, the fold falls
back to the highest-recall threshold, ties by precision, and is counted: a fallback that fires often is
itself a no-go signal and the report states the count), then classify item *i* with that held-out
threshold. The reported
precision/recall are computed over the n **held-out** predictions. At n≈38 this is 38 sweeps over a grid
of ≤38 candidate scores — milliseconds, fully deterministic, no sampling. The **shipped** threshold is
the one selected over the full set; LOOCV measures how that selection rule generalises, and the two are
reported side by side.

**The go/no-go pair (recall 1.00 AND precision ≥ 0.80) is evaluated on the LOOCV-held-out predictions**,
never on the same-sample fit. A same-sample figure may still be reported — it is useful as a ceiling —
but it is labelled **upper bound** wherever it appears, and it never decides go/no-go. Implementation:
`select_threshold_loocv()` is a pure function in `abstention.py`, unit-tested and already inside the
mutation-testing target set.

Definitions, fixed here so the report cannot be argued with later:
`abstention recall = correct abstentions / unanswerable(18)`;
`abstention precision = correct abstentions / all abstentions`.

The owner set **recall = 1.00**. Recall alone is trivially gamed by always abstaining, so the pass
condition is the **pair**: recall 1.00 **with** precision ≥ 0.80, measured on the held-out predictions
above. **If no mode's LOOCV-evaluated pair satisfies both, that is the V0 no-go** — a same-sample fit
that clears the bar does not overturn it — and the report states it as such and names the follow-ups
(cross-encoder rerank stage, larger unanswerable set, query classifier). It does not lower the bar.

### D6 — Eval harness

- **Gold set**: `app/domains/conocimiento/eval/gold_set.yaml`, committed. Per item: `id`, `pregunta`,
  `clase` (`answerable|unanswerable|trampa-vigencia`), `citas_esperadas` (citation keys), `fuente`,
  `validado_por` (`draft|owner`). A scored run **refuses to emit go/no-go** unless every item is
  `owner` and `answerable` count ≥ 20 — the n≥20 precondition and owner-validation decision become
  mechanical, not procedural.
- **Runner**: `--mode fts|vector|hybrid`, same questions, same k, one code path.
- **Metrics** (`metrics.py`, pure functions): hit-rate@5, MRR, citation-precision, norma-vs-secundaria,
  vigencia-correctness, abstention precision/recall. All are set comparisons against gold citation
  keys — **no LLM-as-judge in V0**. That removes the "judge leaks text" risk by construction rather
  than mitigating it, and keeps the harness deterministic (retrieval has no sampling). The abstention
  pair is computed over the **LOOCV-held-out** predictions of D5; the retrieval metrics have no fitted
  parameter and so have no leakage surface.
- **Methodology disclosure is part of the report contract, not a footnote.** The template states, per
  mode: the threshold-selection rule, that selection was leave-one-out cross-validated, `n`, the
  shipped full-set threshold, the LOOCV-held-out precision/recall (the go/no-go figures), and the
  same-sample figures **explicitly labelled `upper bound (fit on the scoring sample)`**. A report that
  cannot state which of its numbers were fitted is not evidence.
- **Determinism**: report pins corpus SHA, model HF revision, torch version and device for both legs.
  Both retrieval legs sort by `citation_key` as secondary key (D4), so tied units cannot reorder between
  runs; without it the pinned SHAs would guarantee reproducible *inputs* to a non-reproducible ranking.
  Corpus vectors come from the GPU, query vectors from CPU — a known ~1e-6 numerical asymmetry that is
  disclosed, not hidden.
- **Report**: `docs/rag/retrieval-eval-{sha8}-{YYYY-MM-DD}.md` + machine-readable `results.json`
  alongside. Under `docs/`, not `openspec/changes/`, so it survives `/sdd-archive`.

### D7 — Dev and test infrastructure (prod untouched)

| Concern | Design |
|---|---|
| Image | `docker/postgres/Dockerfile`: `FROM pgrouting/pgrouting:16-3.4-3.6.1` + pinned `postgresql-16-pgvector` from PGDG, with a build-time assert on `/usr/share/postgresql/16/extension/vector.control`. Tagged `consorcio-postgres:16-vector`. |
| Compose | **New file `docker-compose.pgvector.yml`**, used opt-in via `-f`. Rejected: `docker-compose.override.yml` (auto-merges, forcing an image build on every dev's `compose up`) and editing `docker-compose.yml:6` in place. Opt-in makes the dev-only boundary explicit instead of ambient. |
| Migrations | `conocimiento_001_rag_corpus_schema.py` — 3 tables + generated tsvector + GIN. **Runs everywhere, CI-safe.** `conocimiento_002_pgvector_embeddings.py` — probes `pg_available_extensions`; absent → logs WARNING and no-ops; present → `CREATE EXTENSION vector` + `ADD COLUMN embedding` + HNSW. Conditional DDL is normally a smell; here it is the literal encoding of the owner's dev-only decision, and CI's existing `alembic upgrade head` (`.github/workflows/deploy.yml:103`, running on the vector-less pgrouting image) stays green with **zero CI edits**. **Both directions are guarded so either branch is a no-op** — see below. |
| SQLAlchemy | `embedding` is **not mapped**. `tests/new/conftest.py:135` calls `Base.metadata.create_all` — a mapped `Vector` column would try to create a vector column on the PostGIS test image and break the *entire existing suite*. Consequence: no `pgvector` Python package in app runtime, no `requirements.lock` hash churn, and the vector leg is raw SQL (which it already had to be). |
| DDL drift | `app/domains/conocimiento/ddl.py` holds the embedding DDL statements; migration 002 **and** the test fixture both import them. One source of truth. |
| Tests | `conftest.py` gains `TEST_POSTGRES_IMAGE` (default unchanged `postgis/postgis:16-3.4`), attempts `CREATE EXTENSION vector` and exposes `HAS_PGVECTOR`. New marker `pgvector` **must** be registered in `gee-backend/pytest.ini` (`--strict-markers` is on) and skips when unsupported. `make test-rag` builds the image, exports `TEST_POSTGRES_IMAGE=consorcio-postgres:16-vector`, runs `pytest -m pgvector --junitxml=…` and enforces **two** conditions: exit code ≠ 5 **and** `skipped == 0` in the JUnit report. |
| CI | Unchanged. Parser, gates, fusion, metrics and abstention are pure Python and run in the existing job with no database at all — that is the bulk of the logic. The vector-dependent slice runs locally and its output is the eval report, which cannot be produced without it. |
| Prod | No file the Hetzner box consumes is touched: the server runs a compose outside this repository, so an opt-in compose file here is unreachable by construction. |

**Why exit code 5 alone is not a guard.** pytest exits 5 when **zero tests were collected** — a
collection-time signal. `skipif`/`pytest.skip` fire at **execution** time: the tests are collected, they
run, they skip, and pytest exits **0**. So the failure mode this guard exists to catch — the image
builds, `CREATE EXTENSION vector` quietly fails, `HAS_PGVECTOR` is False, every pgvector test skips — is
precisely the one exit 5 cannot see: it reports success. Asserting `skipped == 0` from the JUnit report
closes it, because under `TEST_POSTGRES_IMAGE=consorcio-postgres:16-vector` a skip in the `pgvector`
suite is by definition a broken image, never a legitimate environment. (A session-scoped
`pytest_collection_modifyitems` hook that turns the skip into a hard failure when the image tag names
the vector build would be equivalent; the JUnit assertion is preferred because it lives in `make
test-rag` and cannot be bypassed by running pytest directly with a different marker expression.)

**Migration 002 guard symmetry, and the recovery it makes possible.** Both directions use existence
guards, so each is a no-op on the branch that did not run: upgrade issues `CREATE EXTENSION IF NOT
EXISTS vector`, `ALTER TABLE rag_unidad ADD COLUMN IF NOT EXISTS embedding vector(1024)` and
`CREATE INDEX IF NOT EXISTS … USING hnsw`; downgrade issues `DROP INDEX IF EXISTS`, `ALTER TABLE …
DROP COLUMN IF EXISTS embedding` and `DROP EXTENSION IF EXISTS vector`. Without the downgrade guards,
rolling back on a database where 002 no-opped raises on a column that never existed — the migration
would be recorded as applied and un-rollable.

The case this is for: consorcio runs **one shared dev volume**. A developer runs `alembic upgrade head`
on the vector-less image, 002 no-ops, and alembic records it as applied. Later that developer opts into
`docker-compose.pgvector.yml`; `alembic upgrade head` now has nothing to do, and the embedding column
never gets created — a stranded volume with no path forward. **Recovery (runbook, one line):** with the
vector image running, `alembic downgrade -1 && alembic upgrade head`. The downgrade is a guarded no-op
(nothing to drop), the upgrade re-runs the probe, this time finds the extension, and creates the
objects. It is safe to repeat, and it destroys nothing: `rag_unidad` rows survive both steps because 002
only ever touches the `embedding` column, which by construction is empty in this scenario. The `-1` form
is valid **while `conocimiento_002` is head**, which it is for all of V0; once later migrations exist,
do not walk the chain back past them — execute the guarded statements from
`app/domains/conocimiento/ddl.py` directly instead. They are the same source of truth migration 002 and
the test fixture import, and being `IF NOT EXISTS`-guarded they need no version-table surgery.

This transition is **never exercised by CI** — CI runs `alembic upgrade head` against a fresh database
on the vector-less image every time, so it only ever sees the no-op branch. That is why the recovery is
documented as a runbook step here rather than claimed as a tested path; what *is* tested is the guard
symmetry itself (Testing Strategy, integration row).

### D8 — Code location

`gee-backend/app/domains/conocimiento/` per the house pattern (`models.py`, `schemas.py`,
`repository.py`, `service.py`) **with no `router.py` at all** — not even an empty one. An unmounted
router is dead code a future contributor will wire up by accident; V1 adds it when there is an endpoint
contract to test. Entry points are thin scripts in `gee-backend/scripts/` (house precedent:
`scripts/mutation_test.py`, `scripts/train_water_unet.py`) delegating to the service.
Migration naming follows the newest house convention (`lluvia_v2_001_…`) → `conocimiento_001_…`.
Heavy embedding dependencies live in a new `gee-backend/requirements-rag.txt`, never in the app image.

### D9 — PixelRAG

Restated from engram `sdd/consorcio-rag/pixelrag-assessment`: out of the V0 core. The problem it solves
(parsing destroys visual structure) is already solved better here — 1,383 hand-gated article units with
byte-exact verbatim citation beat VLM transcription, which is a *new* hallucination surface against the
golden legal rule; its benchmarks are web-QA, not cited legal retrieval with abstention; a VLM needs a
GPU the prod box does not have; and FAISS/Qdrant contradicts the pgvector-in-existing-Postgres decision.
It stays a tracked candidate for the future scanned actas / Boletín Oficial layer, where the evaluation
criteria are citation precision vs OCR+text, privacy, and VLM serving cost.

## File Changes

| File | Action | Description |
|---|---|---|
| `docker/postgres/Dockerfile` | Create | Derivative image + pinned `postgresql-16-pgvector` |
| `docker-compose.pgvector.yml` | Create | Opt-in dev override (`-f`), never auto-merged |
| `Makefile` | Modify | `rag-db`, `rag-ingest`, `rag-embed-load`, `rag-eval`, `test-rag` |
| `gee-backend/app/db/migrations/versions/conocimiento_001_rag_corpus_schema.py` | Create | 3 tables + generated tsvector + GIN |
| `gee-backend/app/db/migrations/versions/conocimiento_002_pgvector_embeddings.py` | Create | Conditional extension + embedding column + HNSW |
| `gee-backend/app/domains/conocimiento/{models,schemas,ddl,parser,fusion,abstention,repository,service}.py` | Create | Domain; no router |
| `gee-backend/app/domains/conocimiento/corpus_expectations.yaml` | Create | Per-document + per-class MANIFEST counts |
| `gee-backend/app/domains/conocimiento/eval/{gold_set.yaml,harness.py,metrics.py,report.py}` | Create | Gold set + 3-mode runner + metrics + report writer |
| `gee-backend/scripts/rag_{ingest,embed_batch,load_vectors,query_latency,eval}.py` | Create | Thin entry points |
| `gee-backend/tests/new/conftest.py` | Modify | `TEST_POSTGRES_IMAGE`, `HAS_PGVECTOR`, `pgvector_db` fixture |
| `gee-backend/tests/new/test_rag_*.py` | Create | Gates, fusion, metrics, retrieval |
| `gee-backend/pytest.ini` | Modify | Register the `pgvector` marker (`--strict-markers`) |
| `gee-backend/requirements-rag.txt` | Create | torch / FlagEmbedding / transformers — ingestion extra only |
| `docs/rag/retrieval-eval-*.md` | Create | The V0 deliverable |
| Hetzner prod compose, `app/api/v2/`, other domains | Untouched | — |

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit (no DB, runs in existing CI) | regex v3 + scoped rules; D-9/D-10/D-22 cases; RRF incl. ties and missing-leg; metrics; abstention policy; **LOOCV threshold selection** (a fixture where same-sample and held-out thresholds differ, so the two cannot be silently swapped); COPY-literal round-trip | pytest, table-driven fixtures from real corpus snippets |
| Unit — named trap cases (no DB) | **Ley 5589 art. 276 dual redaction**: the block opens `DEROGADO.` and preserves the derogated text below (`MANIFEST.md:851-853`); the parser MUST emit **one** unit containing both halves — a split that returns only the lower half hands back dead law as live. Sibling cases in the same row: arts. 4/6/82/84 (`Texto vigente` + `Redacción anterior, sustituida`) and art. 193 ter (inciso 4 substituted, prior text in a footnote). **Ley 9750 art. 39**: body is the original 2010 wording, the footnote transcribes both substitutions (`MANIFEST.md:854-855`) — the footnote MUST stay inside the unit, it is the T-1 canary's third expected citation. **Ley 10679 `## Vigencia de los fondos`** ingested as `tipo_chunk = nota-vigencia`, keyed `10679#vigencia-de-los-fondos`, and **excluded** from the 1,383 article count | pytest over the real corpus snippets; each trap is its own named test, like every other MANIFEST trap |
| Gate (no DB) | per-document **and** total unit counts for `tipo_chunk = 'articulo'` (1,383); the **separate** per-document inventory for non-article `tipo_chunk`s; verbatim substring; citation-key uniqueness; max-token pre-flight; every `rag_documento` carries `jurisdiccion` and, where the frontmatter has it, `relevancia_consorcio` | pytest over the SHA-pinned corpus; fails the build |
| Integration (`@pytest.mark.pgvector`) | migration 001+002 apply/rollback; **002 guard symmetry** — upgrade twice and downgrade twice are both no-ops (`IF [NOT] EXISTS`), asserted on the vector image *and* on the vector-less default image where both directions must no-op without raising; generated tsvector; FTS leg; vector leg; **deterministic leg order** (two units tied on rank return in `citation_key` order across repeated runs); **vector staging load** — happy path updates every row, and a dump containing one unknown citation key aborts the transaction leaving every `embedding` NULL; `VectorSupportUnavailable` on a vector-less DB; idempotent re-ingest | testcontainers on `consorcio-postgres:16-vector` via `make test-rag` |
| E2E (the deliverable) | full ingest → embed → load → 3-mode eval → report | `make rag-eval`; report artifact reviewed by the owner |

Mutation targets (per `openspec/config.yaml`): `parser.py`, `fusion.py`, `abstention.py`, `metrics.py`
— the pure modules where a surviving mutant means the gate is decorative. Threshold: match the repo's
existing cosmic-ray gate.

## Migration / Rollout

Dev only. Rollback order is unchanged from the proposal and matters: `alembic downgrade` **first**
(drops all three tables, the embedding column, then `DROP EXTENSION vector`), then stop using
`docker-compose.pgvector.yml`. Reverting the image while vector objects exist leaves an unloadable
database on the shared dev volume. No production rollback exists because V0 makes no production change.

**Stranded-volume recovery (see D7).** If `alembic upgrade head` ran on the vector-less image, 002 is
recorded as applied although it no-opped; opting into the vector image afterwards leaves no upgrade to
run. With the vector image up: `alembic downgrade -1 && alembic upgrade head`. Both migrations are
guarded with `IF [NOT] EXISTS` in both directions, so the downgrade is a no-op and the upgrade re-probes
and creates the objects. Repeatable, and non-destructive to `rag_unidad` rows. CI never reaches this
path (fresh database, vector-less image, always the no-op branch), which is exactly why it is written
down here.

## PR Slicing (auto-chain — total far exceeds the 400-line budget)

| # | Slice | Budget | Standalone verification |
|---|---|---|---|
| 1 | Infra + schema: Dockerfile, compose file, migrations 001/002 (symmetric `IF [NOT] EXISTS` guards), `models.py` incl. `jurisdiccion`/`relevancia_consorcio`, `ddl.py`, conftest/pytest.ini plumbing, Makefile (`test-rag` with the JUnit skip-count assertion) | ~380 | `SELECT 1 FROM pg_extension WHERE extname='vector'`; upgrade/downgrade idempotent both branches; existing suite green on the vector-less image |
| 2 | Parser + ingestion CLI + expectations (article **and** non-article inventories) + all three gates | ~400 | Exact MANIFEST counts, total and per document; non-article inventory matches; verbatim gate passes |
| 3 | Embedding batch/load scripts (COPY → staging → `UPDATE … FROM`) + retrieval repository (deterministic legs) + fusion + abstention | ~430 | Hybrid query returns fused hits with `tipo` + `jurisdiccion` + `estado_vigencia` + `relevancia_consorcio`; orphan key aborts the load; vector leg raises when unsupported |
| 4 | Eval harness + gold set + metrics + LOOCV threshold selection + report writer | ~440 | Three-mode report emitted with measured CPU query latency and the disclosed methodology block |

Chain: each PR targets the previous branch. Slices 1–2 are independently useful even if the vector legs
were abandoned (FTS-only would still work), which is the point of the ablation.

Slices 3 and 4 now sit above the 400-line target (staging-table load and LOOCV selection are the added
weight). The budget is a target, not a gate: if either apply diff overruns, slice 3 splits at
embed/load vs retrieval and slice 4 at harness/metrics vs report writer — both are clean seams with
independent verification, so the split costs a branch and nothing else.

## Open Questions

- [ ] CX33 latency measurement: throwaway container on the prod box, or a cpuset-matched local container
      labelled ESTIMATE? **Owner call, with the risk stated properly this time.** "Prod stays untouched"
      is true of *state* — `docker run --rm`, nothing installed, no volume, no compose file changed — and
      **false of resources**: the ~2.2 GB pull saturates the box's network, and loading BGE-M3 plus a
      CPU inference run pins the CX33's shared vCPUs and takes ~2.5 GB RSS for the duration. On a 2-vCPU
      shared instance also serving the app, that is latency the users feel. Neither option is free: the
      on-box run is the only measurement that answers the V1 question (can this box embed a query in
      acceptable time?), while the local cpuset proxy answers a different question and must be labelled
      ESTIMATE in the report. If the on-box run is chosen: schedule it in a low-traffic window (early
      morning), pull the image first and run the measurement as a separate step, cap it with
      `--cpus`/`--memory` so a runaway cannot starve the app, and record the wall-clock window in the
      report so any user-visible slowdown is attributable rather than mysterious.
- [ ] Hosted-embedding baseline provider: Voyage-3 (skill default, needs `VOYAGE_API_KEY`) or
      OpenAI `text-embedding-3-large` truncated to 1024 dims for a same-dimension comparison.
- [ ] The `consorcio-corpus-legal` repository does not exist yet; the ingester requires a git SHA, so
      creating and pushing it is a prerequisite of slice 2, not an implementation detail.
