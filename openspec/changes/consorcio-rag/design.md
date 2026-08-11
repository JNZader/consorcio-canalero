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
| Vector | `vector(1024)` (BGE-M3 dense), HNSW `vector_cosine_ops`, **default** `m=16, ef_construction=64`; `hnsw.ef_search` pinned to `2 × LEG_LIMIT` per transaction on the leg | Tuned HNSW; IVFFlat; no index | **Measured, not assumed** (see "The vector leg's plan, measured" under D4): at n≈1,400 the leg plans as `Seq Scan` + top-N heapsort — exact, 100 % recall, ~11 ms. The index is **not** what produces that plan and V0 never touches it, because D4's `citation_key ASC` tie-break is an ordering no HNSW index scan can supply. It is built for V1, not inherited by V0. The `ef_search` pin is there because the default (40) is BELOW `LEG_LIMIT` (50): the day the plan does become an index scan, the leg would silently return 40. |
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
| Pre-flight | Tokenise every `texto_indexado` with the BGE-M3 (XLM-R) tokenizer; **abort loudly** if any exceeds 8192. MANIFEST forbids splitting long articles, so silent truncation is the only failure mode that could survive review. The abort is scoped to the EMBEDDING leg — see the note below. |
| Batch (GPU) | `scripts/rag_embed_batch.py` on the RTX 5060 Ti. `normalize_embeddings=True` (mandatory for cosine). **No query/document prefix** — BGE-M3 is symmetric, unlike BGE-v1.5/E5 which need one; adding a prefix silently degrades it. |
| Artifact | `vectors-{sha8}.copy` — PostgreSQL COPY text format, columns `(corpus_sha, citation_key, embedding)` with the pgvector literal `[v1,v2,…]`, float32-cast, `%.9g` (FLT_DECIMAL_DIG — the shortest form that round-trips a float4 exactly; pgvector stores float4, so nothing is lost). Sidecar `vectors-{sha8}.json`: model id + **HF revision SHA**, dims, normalized, corpus_sha, n_vectors, sha256 of the dump, torch/transformers versions, device, and the **`over_ceiling` key list** — see the Load row. |
| Load | `scripts/rag_load_vectors.py`, **COPY into a staging table, never into `rag_unidad`**. Direct `COPY rag_unidad (corpus_sha, citation_key, embedding)` cannot execute: ingestion (D2) already created every row, the PK is `(corpus_sha, citation_key)`, and **`COPY` has no upsert** — there is no `ON CONFLICT` clause for `COPY`. It would attempt inserts and fail on the PK for all ~1,400 rows. So: (1) pre-checks — refuse unless the dump's sha256 matches the sidecar, `corpus_sha` is the active snapshot, dims == 1024, and the **exemption identity check** below holds; (2) `CREATE TEMP TABLE rag_embedding_staging (corpus_sha CHAR(40), citation_key TEXT, embedding vector(1024)) ON COMMIT DROP` and `COPY` the dump into it; (3) `UPDATE rag_unidad u SET embedding = s.embedding FROM rag_embedding_staging s WHERE u.corpus_sha = s.corpus_sha AND u.citation_key = s.citation_key`; (4) post-checks **in the same transaction** — the `UPDATE` rowcount MUST equal `n_vectors`, the orphan anti-join (`SELECT s.citation_key FROM rag_embedding_staging s WHERE NOT EXISTS (SELECT 1 FROM rag_unidad u WHERE u.corpus_sha = s.corpus_sha AND u.citation_key = s.citation_key)`) MUST return zero rows, and the set of units left with `embedding IS NULL` MUST equal the sidecar's `over_ceiling` set **exactly**; any unresolved staging key or any unexpected NULL **aborts**. Single transaction, all-or-nothing: nothing commits unless every key resolved. |
| Query-time (V0 only) | Local BGE-M3 on **CPU**, loaded once per harness process. `scripts/rag_query_latency.py` reports p50/p95 over the gold questions (3 warm-ups, 3 repeats) with CPU model, core count and thread settings. Candidate run: throwaway container on the CX33 (`docker run --rm`, nothing installed on the host — prod's *state* stays untouched, though its CPU and network do not; see the Open Question). Alternative: a CPU-only container locally with matching cpuset, **labelled ESTIMATE** in the report. Owner call, still open. No V1 serving decision is made here. |
| API baseline | One extra eval leg over the same corpus with a hosted embedder, **gated** by `assert_public_domain(corpus_sha)`: it raises unless *zero* documents in the snapshot have `clasificacion <> 'publico'`. Default-deny, so the actas layer cannot ever fall through. |

**Over-ceiling units in V0 — ingested whole, embedded never, disclosed always.** "Abort" above means
*abort the embedding of that unit*, not abort ingestion. The two legs have different constraints and
conflating them costs real capability: the ceiling belongs to BGE-M3, while FTS has no such limit, so
refusing to ingest an over-ceiling unit would delete it from the lexical leg too — and the FTS-only leg
is exactly what slices 1-2 are built to keep independently useful for the ablation. The ratified V0
behaviour is therefore: **ingest whole** (never truncated — truncation would cite a fragment of a law as
the law), **exclude from embedding** in slice 3, **report on every run**. Three real units exceed the
ceiling at the pinned SHA (`10593#1`, `8560#5`, and one more), so this is a live path, not a hypothetical
one. `--strict-token-ceiling` is the opt-in that promotes the report to a hard abort for operators who
want ingestion to stop instead. The flag being opt-in is not itself disclosure: `GateReport.over_ceiling`
was populated and documented as "always reported — never silently dropped" while nothing carried it to
any output at all, so the default run disclosed nothing (ledger RAG2-004).

**The load pre-check counts the exemption, and pins WHICH units are exempt.** The obvious pre-check —
`n_vectors == count(rag_unidad WHERE corpus_sha = …)` — contradicts the ratified over-ceiling decision
one paragraph above: three units are deliberately never embedded, so a correct artifact is always three
vectors short and the check would reject every real dump. Relaxing it to
`n_vectors == count(…) − |over_ceiling|` fixes the arithmetic and opens a worse hole: **any** three
missing vectors would then pass, so a batch that silently dropped three arbitrary units — an OOM on the
last shard, a mis-slice, a resumed run — would load clean and leave three unrelated articles
unretrievable by the vector leg, invisibly (ledger R3-104).

So the sidecar pins the exempt **keys**, not just their count, and the loader verifies identity in both
directions before it opens the transaction:

1. every key in `over_ceiling` exists as a unit of that snapshot (an exemption naming a non-existent key
   is a lie about the corpus, not a rounding difference);
2. no key in `over_ceiling` appears in the dump (an "exempt" unit that was embedded anyway means the
   ceiling was applied to a different set than the one disclosed);
3. `dump keys ∪ over_ceiling == every unit key of the snapshot` — which subsumes the count check and is
   what actually makes "three are missing, and these are the three" a verified statement instead of a
   coincidence.

The post-check closes the same loop from the database side: after the `UPDATE`, the set of units still
carrying `embedding IS NULL` must equal the `over_ceiling` set exactly.

**The sidecar is RECORDED, not just consulted — migration `conocimiento_004` (ledger RAG3-001).**
As first written, the load read the sidecar, gated on parts of it, and then discarded all of it: what
reached the database was `rag_unidad.embedding` and nothing else. Three consequences, and none of
them has a symptom at the query surface, which is what makes them the same failure class as R3-104:

1. **The surviving model check is `dims == 1024`, which is not a check on the model.**
   `intfloat/multilingual-e5-large` is also 1024 dimensions — and it is already in
   `requirements-rag.txt` as the O.5 baseline leg, so it is a dump this repository really can produce
   by accident. It is also prefix-asymmetric (`query:` / `passage:`), where BGE-M3 takes no prefix at
   all. An e5 dump loaded over a BGE-M3 corpus passes every gate and turns the vector leg into noise
   that still returns 50 confident, fully attributed hits.
2. **`sintetico` lived only in argv.** `--allow-synthetic` let hash noise into the column, and
   nothing on the machine then recorded that the vectors *in the database* were noise. The whole
   "closed by construction" claim for `DeterministicEmbedder` rested on one CLI flag.
3. **The artifact is not a recovery path.** The dump path is `vectors-{sha[:8]}.copy`, so a second
   batch over the same corpus revision overwrites both the dump and its sidecar. "Read the sidecar"
   answers nothing once the file that described the load no longer exists.

So five nullable columns land on `rag_corpus` — `embedding_modelo`, `embedding_revision_hf`,
`embedding_sintetico`, `embedding_artifact_sha256`, `embeddings_loaded_at` — written **in the same
transaction as the `UPDATE`**, so provenance and vectors commit together or not at all. A stamp that
outlived a rolled-back load would be worse than none: it would name a model for vectors that do not
exist. All five NULL is meaningful and is the normal post-slice-2 state: ingested, never embedded.

Three gates fall out of it, and the point is that they are symmetric:

| where | rule |
|---|---|
| `preflight` (load) | same model → allowed, and `--replace-model` is REFUSED (a flag accepted when it changes nothing decays into runbook boilerplate). Synthetic → real → always allowed, no flag: friction belongs on the damage, not on the fix. Real → a different real → `--replace-model`, and the refusal names both models. Real → synthetic → BOTH `--allow-synthetic` and `--replace-model`. Its own exit code (3), because it is the one abort an operator may legitimately override. |
| `recuperar` (query) | refuses when `embedder.model_id` ≠ the recorded model, in **both** directions. Refusing only "real embedder over synthetic rows" would leave the mirror image — the smoke embedder over real vectors — producing a ranked list of pure noise, which is the same fabricated measurement with the operands swapped. |
| `recuperar` (query) | refuses a snapshot with no vectors at all (`EmbeddingsNoCargadas`) instead of letting the leg return `[]`, which is indistinguishable from "nothing matched". |

`Embedder.model_id` is therefore part of the contract, not metadata: BGE-M3 reports its HF id,
`DeterministicEmbedder` reports `deterministic`. The loudness lives in `sintetico`, which sits beside
the id in both the sidecar and `rag_corpus` — not in the id string.

Rejected: `.npy`/parquet dumps (extra dependency + column-order coupling), pickle (unsafe), API for
corpus embeddings (privacy posture + the box is CPU-only anyway).

### D4 — Retrieval and RRF

```
question ──┬─► FTS leg    : tsv @@ OR-of-lexemes(websearch_to_tsquery('spanish', q))
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

**The lexical leg ORs its lexemes. It used to AND them, and that made the FTS arm of the ablation
near-vacuous (ledger RAG4-001).** This bullet is an amendment: the original text named
`websearch_to_tsquery` as the operator, full stop, and `websearch_to_tsquery` builds a CONJUNCTION.

*The evidence, measured against the pinned corpus rather than reasoned about.* Six gold questions, the
real 1 448-unit snapshot at `12043582…`, the leg's own query:

| gold | expected key | AND: rows | AND: gold in top-50 | OR: rows | OR: gold in top-50 | OR: gold rank / rows matched |
|---|---|---:|---|---:|---|---|
| D-1 | `9750#14` | **0** | no | 50 | **yes @34** | 34 / 310 |
| D-2 | `9750#15` | **0** | no | 50 | **yes @12** | 12 / 304 |
| D-3 | `9750#24` | 1 | no | 50 | **yes @40** | 40 / 181 |
| D-5 | `9750#42` | **0** | no | 50 | no | 127 / 349 |
| D-6 | `9867#24` | 3 | no | 50 | **yes @25** | 25 / 287 |
| D-7 | `8803#6`  | **0** | no | 50 | no | never matched / 319 |

Under the conjunction the gold key was in the candidate set for **zero of six**, and four of the six
questions returned no rows at all — the `&` sits in the `WHERE` clause, so `ts_rank_cd` never runs. D-1
compiles to eleven ANDed lexemes (`'convoc' & 'asamble' & 'hor' & 'arranc' & 'lleg' & 'mit' & 'soci' &
'pod' & 'empez' & 'igual' & 'suspend'`) and `9750#14` — three lines about quórum — carries two of them.
Under the disjunction every question gets a full 50-candidate leg and the gold key is inside the
candidate set for four of six. Landing it at **rank 1** is the fusion's job, not this leg's; getting it
into the candidate set at all is the precondition fusion has nothing to work with without.

The two remaining misses are honest and worth naming. D-5's key sits at rank 127 of 349 — matched, out-ranked,
a `LEG_LIMIT` question. D-7's key never matches at all: its article shares no lexeme with the question,
which is a vocabulary gap no lexical operator can close and exactly what the vector leg is in the
design for. **That is the ablation finally being able to say something.**

*Why this was not "just tune the query".* `proposal.md:32` justified slices 1-2 on "if FTS-only clears
the bar, the prod image swap never has to happen". Under the conjunction that premise was
unfalsifiable: the FTS-only arm measured `websearch`'s grammar, and `hybrid` degenerated into
vector-only while keeping the fused label — the same "publish a comparison it never made" failure this
section's no-silent-fallback rule exists to prevent, arriving through the front door.

*The construction, and the trap inside the obvious one.* `websearch_to_tsquery('spanish', :q)::text`
is split on its top-level `' & '`; positive terms are re-joined with `' | '`, `!`-terms stay ANDed, and
the result is `CAST(… AS tsquery)`. Three properties, each load-bearing:

- **No second stemming.** Feeding the text back through `to_tsquery('spanish', …)` re-applies the
  dictionary to already-stemmed lexemes and the Snowball stemmer is **not idempotent**: measured,
  `intervenir` indexes as `interven` (13 units) and stems again to `interv` (**zero**). That
  construction looks like the fix and silently loses recall on the very words the question is about.
  `tsquery_in` — the cast — applies no dictionary, so the round trip is exact.
- **Exclusions survive.** ORing `!'rieg'` in would match every document *without* the word: a recall
  explosion wearing the fix's name. `canal -riego` still means "canal, not riego".
- **Injection-free by construction.** User text reaches SQL only as the bound parameter of
  `websearch_to_tsquery`, which is total and whose output is a quoted, escaped lexeme list. Nothing
  that returns from it is user text. The `' & '` split is safe because the default parser cannot emit a
  lexeme containing a space.

*No retry, ever.* One operator runs, always, and the report prints its name (`repository.FTS_OPERADOR`,
surfaced in the markdown, in the JSON and beside the coverage counters). An automatic AND-then-OR retry
would be exactly the silent degradation this section forbids for the vector leg, moved to the lexical
side. A question that reduces to nothing — empty, stopwords only, only an exclusion — builds the empty
tsquery and matches no row, which is an answer and stays distinguishable from a refusal.

*Residual cost, disclosed.* A wider net brings secondary sources into pages that previously held none
(`informe-f3#sec-3` now enters a quórum query), which is what the `norma-vs-secundaria = 1.00` bar
grades — by RANK, not by membership. And `CoberturaLegs` keeps counting empty legs: the instrument that
measured this defect is not removed because the reading improved.

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
- **The refusals live at two different layers, and mixing them up is how a caller loses two of
  them.** `repository.vector_search()` raises `VectorSupportUnavailable` when the extension or the
  column is absent — it never falls back to FTS, because silent degradation would make the ablation
  meaningless. It raises **nothing else**, and cannot: it receives a query *vector*, not an embedder,
  so it has no way to know which model produced the column it is searching. The two refusals added by
  RAG3-001 belong to the service layer and are raised by `service.verificar_embedder`, which
  `service.recuperar` calls **before either leg runs**: `EmbeddingsNoCargadas` when the snapshot has
  no vectors at all (the state slices 1-2 ship, where the leg would contribute `[]` and the fused
  answer would be FTS under a hybrid label) and `EmbedderMismatch` when the query embedder is not the
  one that wrote the column (D3). An earlier revision of this bullet credited all three to
  `vector_search()`; that was false, and false in the direction that invites the mistake below
  (ledger RAG3-R01).
- **Design rule: every retrieval consumer goes through `service.recuperar`, never a repository leg.**
  A caller that reaches for `repository.vector_search` directly still gets the capability check and
  loses BOTH provenance gates — it would cheerfully rank a real BGE-M3 corpus with the deterministic
  smoke embedder and hand back 50 confident, fully attributed, entirely fabricated hits. The eval
  harness (D6) is the caller this rule exists for, because its output is a *published measurement*:
  `app/domains/conocimiento/eval/` imports the service layer and nothing below it, and
  `test_rag_eval_harness.py::TestServiceLayerBoundary` asserts that mechanically over the eval
  package's own import graph instead of trusting the convention.

**The vector leg's plan, measured.** The original text here claimed both "at n≈1,400 an exact scan is
sub-10 ms and 100 % recall" *and* "the index exists so V1 inherits the identical query plan shape".
Those cannot both be true — an exact scan and an HNSW index scan are different plans — and the second
one was wrong. `EXPLAIN (ANALYZE)` over 1,400 seeded vectors on `consorcio-postgres:16-vector`
(pgvector 0.8.6, PostgreSQL 16.14), running the leg's real query:

```
Limit (actual time=11.062..11.070 rows=50 loops=1)
  ->  Sort (actual time=11.061..11.063 rows=50 loops=1)
        Sort Key: ((rag_unidad.embedding <=> $0)), rag_unidad.citation_key
        Sort Method: top-N heapsort  Memory: 28kB
        ->  Seq Scan on rag_unidad (actual time=0.096..10.648 rows=1400 loops=1)
              Filter: ((embedding IS NOT NULL) AND ((corpus_sha)::text = '…'))
              Rows Removed by Filter: 3
```

So the first half holds: V0's vector leg is an exact scan, 100 % recall, ~11 ms — and 50 of 50
candidates. The second half does not, and the reason is this design's own determinism rule: an HNSW
index can order by distance and nothing else, so `citation_key ASC` as the secondary sort key puts
the plan permanently out of its reach. Forcing it (`enable_seqscan = off`) did not change the plan;
only dropping the tie-break *and* removing the sort node does. **V0 therefore never uses the index,
and V1 will not inherit V0's plan — it will trade the exact tie-break for it.**

**`hnsw.ef_search` is pinned anyway, and that is not superstition.** With the tie-break dropped and
the index scan forced, the same query returns **`rows=40`** at pgvector's default `ef_search = 40`
and `rows=50` once it is raised. `ef_search` is a candidate ceiling, not a filter, and `LEG_LIMIT`
is 50 — so the moment the plan becomes an index scan, the leg silently loses 20 % of its depth while
the eval report keeps printing 50. `repository.vector_search` sets it per transaction via
`set_config('hnsw.ef_search', …, true)` (bound parameter; `SET LOCAL` takes none), derived as
`2 × LEG_LIMIT` so raising the leg depth cannot outgrow the budget. Under today's sequential-scan
plan it is a no-op that costs one round trip.

**Determinism caveat for the ablation.** Because V0's plan is exact, the ranked list is a pure
function of the data — index rebuilds cannot move it. That property belongs to the plan, not to the
system: if a later run does take the index scan, results become approximate and an HNSW graph rebuilt
between runs can rank differently over identical data. The eval runbook already embeds and loads
**once** per corpus revision (D3), and must keep doing so: no re-indexing mid-ablation.

### D5 — Abstention (tunable by construction)

`AbstentionPolicy(min_score, min_margin, require_both_legs)`. The eval sweeps `min_score` over the
observed signal grid **per mode** and reports the full precision/recall curve.
**Signals are not comparable across modes**, so three thresholds are calibrated, not one — conflating
them is how an ablation silently lies.

**AMENDMENT (apply-phase JD round 1, RJDB-002) — the signal is per mode, and a single-leg mode does
not use RRF.** The original wording above said "the observed fused-score grid", and taken literally it
made the `fts` and `vector` arms unmeasurable. RRF gives the top hit `1/(k + rango + 1)`; with ONE leg
that is `1/61` for every question whose leg returned anything and `0.0` for every question whose leg
returned nothing. The "grid" therefore holds at most two values, the LOOCV sweep explores an outcome
fixed before any data is read, and what the single-leg abstention bars actually measure is whether the
leg matched at all — a property of the query operator, not of confidence. Both single-leg bars were
predetermined to fail. The parenthetical "hybrid top-1 can reach 2/61, a single leg only 1/61" was a
correct observation whose consequence was missed: `1/61` is not a low ceiling, it is a CONSTANT.

The data to fix it was already carried and then discarded — `CitaRecuperada` holds `valor_fts`
(`ts_rank_cd`) and `distancia_vector` (cosine distance) per hit, and `senales_desde` read neither. So:

| mode | signal | transform | why |
|---|---|---|---|
| `fts` | `valor_fts` of the top hit | none — `ts_rank_cd` is already increasing in relevance with floor 0 | the leg's own ranking metric is the only real confidence it has |
| `vector` | `distancia_vector` of the top hit | `1 − d/2` | `<=>` is `1 − cos`, so it runs `[0, 2]` and *decreases* with relevance — the wrong direction for "abstain below". `1 − d/2 = (1 + cos)/2` is order-preserving and bounded in `[0, 1]` |
| `hybrid` | RRF top-1 | none | the only signal a fused mode HAS: `ts_rank_cd` and cosine distance are not commensurable and are never blended (D4) |

**The `/2` is load-bearing rather than cosmetic.** The obvious `1 − d` yields `cos`, which is negative
for any hit more than 90° from the query — and an empty page scores a flat `0.0`. A negative-similarity
hit would then rank BELOW "we retrieved nothing at all", so the weakest real answer would look less
confident than no answer, and a threshold between them would abstain on the real hit while answering the
empty one. Every scale used for a signal is therefore bounded below by 0, which is what makes the
empty-page `0.0` a genuine floor.

The two scales are never mixed inside one run: a missing leg value (structurally impossible in a
single-leg mode, where every fused key came from that leg) falls the WHOLE run back to RRF rather than
putting two incommensurable numbers in one grid. The scale in force is recorded on every
`SenalAbstencion` (`fuente_senal`), disclosed in the report's methodology block and in the JSON, and the
report raises a **SEÑAL CONSTANTE** warning whenever a mode's signals are all equal — the pathology this
amendment removes, kept visible in case it returns by another route.

Per-mode thresholds were already selected per mode by LOOCV, so nothing about the selection rule
changes; what changes is that the `fts` and `vector` grids are now real.

**Threshold selection is leave-one-out cross-validated; scoring never reuses the fitting sample.**
Sweeping `min_score` on the gold set and then reporting precision/recall *on that same set* fits the
threshold to the very items it is about to be graded on. The resulting numbers are a training fit read as
a measurement — post-hoc overfit wearing the costume of rigour, and the smaller the set the louder the
lie. So, per mode: for each gold item *i*, select the threshold by sweeping over the **other n−1** items
(same rule: highest precision among thresholds achieving recall 1.00; ties broken by the lower
threshold, deterministically — and if **no** threshold on that fold reaches recall 1.00, the fold falls
back to the highest-recall threshold, ties by precision, and is counted: a fallback that fires often is
itself a no-go signal and the report states the count), then classify item *i* with that held-out
threshold. The reported
precision/recall are computed over the n **held-out** predictions. At the ratified n = 52 this is 52
sweeps over a grid of ≤52 candidate scores — milliseconds, fully deterministic, no sampling. The **shipped** threshold is
the one selected over the full set; LOOCV measures how that selection rule generalises, and the two are
reported side by side.

**The go/no-go pair (recall 1.00 AND precision ≥ 0.80) is evaluated on the LOOCV-held-out predictions**,
never on the same-sample fit. A same-sample figure may still be reported — it is useful as a ceiling —
but it is labelled **upper bound** wherever it appears, and it never decides go/no-go. Implementation:
`select_threshold_loocv()` is a pure function in `abstention.py`, unit-tested and already inside the
mutation-testing target set.

Definitions, fixed here so the report cannot be argued with later:
`abstention recall = correct abstentions / |{items with clase == 'unanswerable'}|`;
`abstention precision = correct abstentions / all abstentions`.
The denominator is **read from `gold_set.yaml`, never written down here** — it was the literal `18`
until curation landed and made it 23, which is exactly the staleness CRA-101/CRB-101 predicted. It is
`None` rather than `1.00` when a sample holds no unanswerable item, because "nothing to miss" is the
most flattering possible way to report having measured nothing; and `precision` is `0.0` rather than a
vacuous `1.00` when a policy never abstains, so a never-abstaining policy cannot print a success next
to a recall of zero.

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
- **Runner**: `--mode fts|vector|hybrid`, same questions, same k, one code path — and that code path
  is `service.recuperar`, never a repository leg directly (the D4 rule; the harness's own imports are
  asserted, not assumed).
- **Metrics** (`metrics.py`, pure functions): hit-rate@5, MRR, citation-precision, norma-vs-secundaria,
  vigencia-correctness, abstention precision/recall. All are set comparisons against gold citation
  keys — **no LLM-as-judge in V0**. That removes the "judge leaks text" risk by construction rather
  than mitigating it, and keeps the harness deterministic (retrieval has no sampling). The abstention
  pair is computed over the **LOOCV-held-out** predictions of D5; the retrieval metrics have no fitted
  parameter and so have no leakage surface.

  **Metric definitions, fixed here for the same reason D5 fixes the abstention ones.** The spec sets
  seven BARS and defines exactly one of them (abstention recall). Three of the seven are `= 1.00`,
  which is unreachable under the obvious reading — `|top_k ∩ gold| / k` maxes out at 0.3 for a
  three-key question on a ten-hit page — so a bar without a definition is not a gate:

  | metric | definition | why not the obvious alternative |
  |---|---|---|
  | hit-rate@5 | 1 if any expected key is among the first 5 fused hits, averaged over the answerable subset | — |
  | MRR | `1/(rank+1)` of the **first** expected key in the returned page, 0 if absent | averaging over all expected keys scores a complete composite answer *below* a partial one |
  | citation-precision | **R-precision**: `\|top_m ∩ gold\| / m` with `m = \|gold\|` | any fixed window ≥ m makes "= 1.00" unreachable for a one-key question, i.e. a decorative bar. At rank m precision and recall coincide, so one number carries both coverage and noise |
  | norma-vs-secundaria | 1 unless the top hit is `es_secundaria`, or any hit lacks an explicit flag; **`None` when the page is empty** | the gold set's own rule — citing the informe instead of the article is a failure even when the content is right. It returned `1.0` for a page with no hits at all until the slice-4 fix round: "the top hit was not a secondary source" is vacuously true of a page with no top hit, so a mode that retrieved NOTHING cleared a hard `= 1.00` bar unanimously — a gate passed by failing. Absence now leaves the denominator, exactly as `vigencia-correctness` already did, and the report prints `n_separacion` beside the value |
  | vigencia-correctness | over trap questions only: every caveat-bearing key retrieved **and** every norma hit carrying a vigencia state | scoring it over all questions inflates the mean with free points from questions that never claimed the property |

  Scope: the five are computed over `respondibles` (`clase != 'unanswerable'`, so the `trampa-vigencia`
  items count toward the ratified 29). An unanswerable question has `|gold| = 0`, so each of these
  would be a division by zero wearing a score's clothes; those items are measured by the abstention
  pair, which was designed for them. An aggregate over an empty denominator is `None`, never `0.0` —
  zero is a measurement and its absence is not.

  **Consequence, stated rather than engineered around: the bar set is NESTED.** A run at
  citation-precision 1.00 necessarily clears hit-rate@5 ≥ 0.85 and MRR ≥ 0.70, because R-precision 1.00
  on every question puts a gold key at rank 0 everywhere. Those two therefore behave as diagnostics —
  they say how far a failing run sits from the bar — rather than as independent gates. That is a
  property of the ratified bars, not of these definitions.
- **Methodology disclosure is part of the report contract, not a footnote.** The template states, per
  mode: the threshold-selection rule, that selection was leave-one-out cross-validated, `n`, the
  shipped full-set threshold, the LOOCV-held-out precision/recall (the go/no-go figures), and the
  same-sample figures **explicitly labelled `upper bound (fit on the scoring sample)`**. A report that
  cannot state which of its numbers were fitted is not evidence.
- **The lexical operator is disclosed** (`repository.FTS_OPERADOR`), in the markdown beside the leg
  coverage counters and in the JSON at both the top level and per mode. RAG4-001 was a change to that
  operator and nothing else, and it moved the FTS arm from "zero candidates on six of six gold
  questions" to "a full leg on all six" — a report that prints leg metrics without naming the operator
  that produced them describes a comparison the reader cannot identify.
- **A verdict over a degraded fused leg states its scope.** `hybrid` whose lexical or vector leg came
  back empty for a strict majority of questions still gets a real verdict — the ablation informs and
  refusing to score would discard its finding — but the verdict line reads `GO (con leg FTS degradada —
  el veredicto refleja principalmente la pata vectorial)`, and the JSON carries
  `veredicto_calificado: bool` plus `legs_degradadas` so a machine reader does not parse Spanish. A bare
  `GO` printed three lines above a `LEG DEGRADADA` warning is the line that gets quoted without the
  warning. `hibrido_degenerado` uses the same strict-majority threshold as `leg_fts_degradada`: it
  previously fired only at 100 % empty, so one surviving question out of fifty switched the loudest
  warning in the report off.
- **The gold set and the snapshot must pin the same corpus revision, and the run refuses when they do
  not** (exit code 4, both SHAs named). `citas_esperadas` are keys of ONE revision; scored against
  another, a key that does not exist there is indistinguishable from a retrieval miss, so every metric
  drops and the report blames the retriever. The error direction is fail-safe — a spurious NO-GO, never
  a spurious GO — which is exactly why it needed a check rather than a warning: an unexplainable NO-GO
  costs a re-run of the whole GPU batch and the cause is one string comparison away. The owner-side
  private file is held to the same rule: it declares `para:` and `corpus_sha:` and both are verified
  before its 26 questions are allowed to resolve, because it is fetched from an environment variable
  pointing outside this repository and a stale copy is an ordinary slip. `gold_corpus_sha` is written
  into the report JSON so the record shows the check had two values to compare. All of it runs before
  the database is opened, before the report directory exists and before an embedder is built.
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
only ever touches the `embedding` column, which by construction is empty in this scenario.

**`-1` no longer lands on 002.** `conocimiento_004` is head as of slice 3 (`conocimiento_003` was head
at slice 2), so `alembic downgrade -1` now walks back 004 — the recovery above needs `alembic downgrade
conocimiento_002 && alembic
upgrade head`, or the guarded statements from `app/domains/conocimiento/ddl.py` executed directly (they
are the same source of truth migration 002 and the test fixture import, and being `IF NOT EXISTS`-guarded
they need no version-table surgery). Walking back past 003 is *safe* but not free: 003's downgrade
restores constraints the ingested corpus violates, so it DELETES the rows only 003 made legal — the
three fuente-secundaria documents with a NULL `estado_vigencia` and every `anexo-normativo` unit. That
is deliberate and lossless (`rag_*` is a derived artifact of a SHA-pinned corpus; `upgrade head` +
`scripts/rag_ingest.py` rebuilds them byte-for-byte), but it means the recovery costs a re-ingestion.
Before that remediation existed the downgrade did not merely cost something — it raised
NotNullViolation and was unrunnable on any database that had been ingested even once, which took every
documented rollback path down with it (ledger RAG2-002).

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
| `gee-backend/app/db/migrations/versions/conocimiento_004_embedding_provenance.py` | Create | Five nullable embedding-provenance columns on `rag_corpus` (RAG3-001) |
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
| Gate (no DB) | per-document **and** total unit counts for `tipo_chunk = 'articulo'` (1,383); the **separate** per-document inventory for non-article `tipo_chunk`s (65); **heading coverage** — every `#`/`##` heading is captured, declared, or explicitly excluded under a declared class; **corpus file inventory** — every `.md` in the checkout is a declared document or a declared non-document; verbatim substring; citation-key uniqueness; max-token pre-flight; every `rag_documento` carries `jurisdiccion` and, where the frontmatter has it, `relevancia_consorcio` | pytest over the SHA-pinned corpus; **local gate, not CI** — see "What CI actually covers" below |
| Integration (`@pytest.mark.pgvector`) | migration 001+002 apply/rollback; **002 guard symmetry** — upgrade twice and downgrade twice are both no-ops (`IF [NOT] EXISTS`), asserted on the vector image *and* on the vector-less default image where both directions must no-op without raising; generated tsvector; FTS leg; vector leg; **deterministic leg order** (two units tied on rank return in `citation_key` order across repeated runs); **vector staging load** — happy path updates every row, and a dump containing one unknown citation key aborts the transaction leaving every `embedding` NULL; `VectorSupportUnavailable` on a vector-less DB; idempotent re-ingest | testcontainers on `consorcio-postgres:16-vector` via `make test-rag` |
| E2E (the deliverable) | full ingest → embed → load → 3-mode eval → report | `make rag-eval`; report artifact reviewed by the owner |

**What CI actually covers, and what it does not.** The "Gate" row above runs over the SHA-pinned
corpus, and **CI has no corpus**: `consorcio-corpus-legal` is private and V0 is all-local by owner rule,
so CI never sets `RAG_CORPUS_PATH`. Every content assertion — the 35-document check, the 1383/65 counts,
the vigencia canary, verbatim fidelity, determinism, pruning, idempotency, the heading-coverage and
file-inventory gates — is therefore **skipped in CI, and the run is green**. That is the right call (the
alternative is shipping a private legal corpus into a CI runner) but it was undisclosed, which made
"CI is green" read as a claim about the corpus contract that it never was (ledger RAG2-005).

Two things make it honest rather than merely true:

* `make test-rag-corpus` selects exactly the `corpus`-marked tests and **fails on a SKIP**, mirroring
  `make test-rag`'s image check. A green local run cannot mean "nothing ran".
* a sentinel test fails — rather than skipping — when `RAG_CORPUS_PATH` is **set but wrong**: not a
  directory, no `MANIFEST.md`, not a git checkout, or sitting on a revision other than the pinned SHA.
  Set-but-wrong is the dangerous case, because `real_corpus_path()` returns `None` for it and the whole
  content suite then skips exactly as it does when no corpus was configured at all.

So: CI covers the **structural** tests; the corpus contract is a **local gate**, run via
`make test-rag-corpus RAG_CORPUS_PATH=…` before any slice-2 merge.

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
run. With the vector image up: `alembic downgrade conocimiento_002 && alembic upgrade head` (**not
`-1`** — `conocimiento_003` is head as of slice 2, so `-1` walks back 003 and re-ingestion is then
required; see D7). Both migrations are
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
