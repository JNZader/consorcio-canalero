# Archive Report — consorcio-rag

**Change**: `consorcio-rag` — Consorcio RAG V0, Cited Legal Retrieval Foundation
**Repo**: `/home/javier/programacion/consorcio-canalero`
**Archived**: `2026-08-11` → `openspec/changes/archive/2026-08-11-consorcio-rag/`
**Artifact store**: hybrid (openspec files + Engram topics)
**Merged**: PR **#178**, squash → `main` @ `ac1f177e`
**Deployed**: prod Hetzner @ `a2435144` (2026-08-11), dormant by design
**Verification verdict**: PASS-with-notes — 0 CRITICAL · 2 WARNING · 5 SUGGESTION

---

## 1. What shipped

A measured retrieval layer over the consorcio's curated legal corpus, with **no user-facing
surface**. The premise the whole change exists to serve is `proposal.md:5` — *derecho + LLM
sin cita = peligro* — so V0 builds the layer and *measures* it, and ships nothing anybody can
query.

Delivered as a 4-slice feature-branch chain (infra → ingestion → retrieval → eval), each slice
reviewed on its own diff, only the tracker branch reaching `main`.

| Slice | Delivered |
|---|---|
| 1 | `docker/postgres/Dockerfile` derivative + `docker-compose.pgvector.yml` (dev-only, opt-in), `conocimiento_001`/`conocimiento_002` migrations with the conditional pgvector no-op, `ddl.py` capability probe, `make rag-db`/`test-rag` guards |
| 2 | MANIFEST regex-v3 parser (D-9 composite keys, D-10 scoped to `norma-tecnica`, D-22 `ley`≡`ley-provincial`), the three inventories (article counts, non-article `tipo_chunk`, `excluidos`), heading-coverage + corpus-file + verbatim-substring + token-ceiling gates, repository/service, `scripts/rag_ingest.py`, migration `conocimiento_003` |
| 3 | BGE-M3 + multilingual-e5-large embedders (lazy, ingestion-extra only), `scripts/rag_embed_batch.py` + `rag_load_vectors.py` (staging-table load, identity-checked exemptions), FTS + vector legs with `citation_key` tie-breaks and a pinned `hnsw.ef_search`, RRF(k=60) fusion, migration `conocimiento_004` embedding provenance, `scripts/rag_query_latency.py` |
| 4 | Three-mode ablation harness (`fts` / `vector` / `hybrid`), LOOCV abstention-threshold selection, the metric set with published denominators, the 52-question gold set (26 public + 26 private-by-reference), markdown + JSON report with methodology/provenance/exemption/latency blocks, `scripts/rag_eval.py` |

**Ingestion, executed against the pinned corpus** (`corpus_sha 12043582bf8016288a7e8084e85a4b713a97af2f`):
35 documents → **1448 rows, all citation keys unique** = 1383 article units (the MANIFEST's own
declared total, re-derived independently as `1358 + 6 + 19 + 0` rather than inherited) + 65
non-article units. Gate zero re-run first: `GATE FINAL: 39/39 OK`. Re-ingest is byte-identical;
determinism is asserted over the whole row, not a projection.

**Retrieval** returns every hit with verbatim `texto`, citation key, `tipo`, `es_secundaria`,
`jurisdiccion`, `estado_vigencia` and `relevancia_consorcio` — the last one carried verbatim
precisely so a hit on Res. 4/2026 ("NO debe citarse como fundamento…") cannot read as
equivalent grounds to a Ley 9750 article that `tipo` alone would rank the same. Provenance is
schema-backed in both directions: a model change at load needs `--replace-model`, and
`service.recuperar` refuses when the query embedder disagrees with the recorded model or when
the snapshot was never loaded.

**Gates at verify** (executed, not inherited): `pytest tests/` — the real CI scope — **exit 0 ·
2927 passed / 66 skipped / 0 failed**; `pytest tests/new/conocimiento/` **389 / 61 / 0**;
`make test-rag` **29 passed / 0 skipped**; `make test-rag-corpus` **32 passed / 0 skipped**.
Both `make` targets treat a skip as a failure, so "passed" cannot mean "did not run". All 66
skips are mechanically gated and disclosed (61 corpus/pgvector + 5 pre-existing live-backend).

### Prod deploy evidence

Deployed in the 4-PR train at `a2435144`. **RAG went to prod dormant, and the dormancy is the
designed behaviour, not an omission**: migrations `conocimiento_001`, `003` and `004` applied;
`conocimiento_002` took its conditional branch on the default pgrouting image and logged its
WARNING verbatim:

```
conocimiento_002: 'vector' extension not available on this Postgres image — skipping the
embedding column and HNSW index. This is expected on the default pgrouting image; the
vector column only exists on consorcio-postgres:16-vector (docker-compose.pgvector.yml),
which is dev-only and opt-in.
```

That is `conocimiento_002_pgvector_embeddings.py::upgrade` doing exactly what the Scope
Decision bought: production Postgres is untouched, PostGIS / pgRouting / Martin are unrisked,
and the image swap stays a V1 decision the ablation is supposed to *earn*. Evidence: Engram
#14001 (`consorcio/deploy-2026-08-11`).

## 2. The Judgment Day saga

The design phase and the apply phase each went through Judgment Day. Both terminated
**APPROVED**, and the apply phase used **exactly 2 rounds — the convergence budget was never
extended**.

**Design JD (2026-08-10)** — two blind judges over `design.md`. Both verified the two
structural claims sound and the parser faithful to the MANIFEST traps. Six confirmed findings
fixed in design artifacts (no code existed yet): the COPY-into-existing-PK-rows impossibility
(→ staging table + `UPDATE … FROM`), non-deterministic leg ordering, `relevancia_consorcio`
being architecturally unrepresentable, the abstention threshold swept and scored on the same
sample (→ LOOCV), the exit-code-5 guard blind to `skipif` skips, and the no-op-once stranded
volume. Scoped re-judge: **both CLEAN, unanimous, terminal APPROVED**, round 1 closed within
budget.

**Apply JD Round 1** — 1 **BLOCKER** + 5 CRITICAL + 4 WARNING, all fixed. The blocker:

> **RJDA-001 ≡ RJDB-001 — 12 real full-name + D.N.I. pairs of the consorcio's sitting Comisión
> Directiva, committed in slice 2.** Both judges reached it independently and both returned
> NO-GO on it alone.

The names are public in APRHI resolutions; the pairing with a national ID is the leak, and the
sibling fixture had already established `[DNI-OMITIDO]` as the standard. Nothing had been
pushed (`git ls-remote` re-verified empty at fix time), so the fix was a **history rewrite, not
a tip commit**: the fixture was redacted in the original slice-2 commit itself and the three
stacked branches replayed onto it, with the old→new SHA remapping table recorded in the ledger
rather than the prose being falsified. **The purge was verified three independent times, never
asserted**: each of the 12 numbers returns 0 commits from `git log -S` over the new tips; a
`git grep -E '\b[0-9]{1,2}\.[0-9]{3}\.[0-9]{3}\b'` over the fixtures tree of all 12 reachable
commits is clean; and Judge B re-ran the searches from scratch in Round 2 rather than reading
the Round-1 record. The working tree at verify holds 12 `[DNI-OMITIDO]` and zero dotted-ID
patterns. Redaction broke nothing — the tests assert citation keys and counts, never DNI text.

**Round-1 re-judge — the judges disagreed, and that is the round's lesson.** RJDB returned
CLEAN; RJDA returned FAILING with `RJDA-101` (BLOCKER) and `RJDA-102` (CRITICAL). **The
contradiction was resolved by execution, not by argument**: the orchestrator ran the failing
test at the tip and read its exit code. RJDA-101 was real — the branch could not pass CI,
because a guard grepped file *content* for `import torch` while slice 3's two imports are
lazy — and B missed it because B verified the fixes and not the suite. *A scoped re-judge that
reads a diff can confirm every intent in it and still not notice the branch is red.*

RJDA-102 then paid a second dividend. Correcting a documentation defect (the artifact called
`pytest tests/new/` "the CI shape"; CI runs `pytest tests/`) meant running the real scope, which
surfaced 14 failures in files no chain commit touched. The hypothesis that they were
pre-existing is exactly what execution refuted — `pytest tests/ --ignore=tests/new/conocimiento`
was green at 2538 — and the bisection landed on `env.py`'s `logging.config.fileConfig`, whose
default `disable_existing_loggers=True` permanently disables every already-created logger
process-wide. Fixed at the cause (`env.py:55`), with a regression test whose witness logger is
created at import time.

**Round 2** closed every finding at the cause: the AST-based import guard plus the
supply-chain closure check, the `env.py` fix, gold-set/`corpus_sha` reconciliation, leg-native
abstention signals, the E5 embedder that argparse advertised and `get_embedder` did not
implement, and `math.fsum` for a mean whose last digits were interpreter-dependent.

**Final scoped re-judge (2026-08-11): RE-JUDGE A CLEAN + RE-JUDGE B CLEAN → JUDGMENT: APPROVED.**
Judge A re-executed the headline claim itself (`pytest tests/` → exit 0 · 2927/66/0) and
reconstructed the bisection arithmetic independently. Both judges' residual gap — their
sandboxes run neither `make` targets nor env assignments — was closed by orchestrator execution
at the tip, digit-for-digit against the Round-2 record.

**Shape of the failure, both judges converging**: this apply's defects were overwhelmingly
*ratified-decision-never-carried-through*, not wrong-algorithm. Nine of ten Round-1 fixes touch
the seam where a document, a CLI and a durable record were supposed to agree and did not.

### Ledger tally — archive-time recount, disclosed

The `verify-report.md` ledger-closure line reads **"2 BLOCKER + 18 CRITICAL across the change,
all `fixed`"**. A mechanical recount of the ledger's severity cells at archive time returns
**3 unique BLOCKER ids and 19 unique CRITICAL ids**. The difference is bookkeeping, not a
hidden finding, and both discrepancies are explainable:

- The third BLOCKER is the design-round COPY-load finding, whose synthesized severity is the
  disputed `BLOCKER/SUGGESTION` (Judge A BLOCKER, Judge B SUGGESTION; identical one-paragraph
  fix). Counting it as neither is defensible; recording that it was counted as neither is the
  point.
- The nineteenth CRITICAL is one row's worth of counting convention (`RAG4-001` appears twice —
  once self-reported by the apply, once re-raised by the lens — and `RJDB-103` is a
  missing-executed-proof row rather than a code defect).

Every one of those rows is `fixed` with a downstream verdict either way. Recorded here so a
future reader who recounts does not think they have found something.

**Refuter protocol**: STANDS ×4 on RAG2-001..004, STANDS on RAG3-001, STANDS ×2 on
RAG4-001/RAG4-003 (the latter with the severity called borderline and both directions recorded).
Judgment Day spawned no refuter fan-out — its two-judge convergence *is* the adversarial
verification, the documented exception. Per-slice reviews ran 1 lens + 1 batched refuter + 1 fix
round each, inside budget everywhere.

## 3. The FTS NO-GO measurement — the finding the ablation existed to produce

`proposal.md:32` justified the dev-only scope trim with a falsifiable promise: *"if FTS-only
clears the bar, the prod image swap never has to happen."* Slice 4 made that premise measurable
for the first time, and **it is FALSE**.

RAG4-001 had to be fixed before the question could even be asked: `websearch_to_tsquery` builds
a **conjunction**, so gold question D-1 compiled to eleven ANDed lexemes and the leg returned
zero rows — an empty leg, not a bad ranking, with `ts_rank_cd` never running. Four of six probe
questions returned nothing; the gold key was in the candidate set for zero of six. The FTS-only
arm would have measured websearch's grammar instead of the index, and `hybrid` would have
degenerated into vector-only *while keeping the fused label* — the "publish a comparison it
never made" failure D4 exists to prevent, arriving through the front door.

The fix splits `websearch_to_tsquery(…)::text` on its top-level `' & '`, ORs the positive terms,
keeps `!`-terms ANDed and casts back with `CAST(… AS tsquery)`. **The trap found while fixing is
why the obvious construction was not used**: round-tripping through `to_tsquery('spanish', …)`
re-stems already-stemmed lexemes and Snowball is not idempotent — `intervenir` → `interven`
(13 units) → `interv` (**0 units**). That looks like the fix and silently destroys recall on the
question's own keywords. The operator is disclosed as `FTS_OPERADOR` in markdown, JSON and next
to the coverage counters; there is **no automatic AND→OR retry, ever**.

Then the real run — `scripts/rag_eval.py` against a scratch database holding the real ingested
corpus, `RAG_GOLD_PRIVADO_PATH` set, `--modo fts`:

```
gold set: 52 ítems (respondibles 29 · abstención 23) · corpus_sha 12043582bf8016288a7e8084e85a4b713a97af2f
  fts     NO-GO  (fallan: hit-rate@5, MRR, citation-precision, norma-vs-secundaria,
                  vigencia-correctness, abstention recall, abstention precision)
exit 0
```

| what the JSON says | value |
|---|---|
| `sin_candidatos_fts` | **0 of 52** — every gold question got a non-empty lexical leg |
| `leg_fts_degradada` | `false` |
| `operador_fts` | `OR — disyunción de los lexemas que parsea websearch_to_tsquery` |
| `gold_corpus_sha` / `corpus_sha` | identical, and the identity check had two values to compare |
| hit-rate@5 · MRR · citation-precision | 0.138 · 0.091 · 0.040 |
| norma-vs-secundaria (`n_separacion`) | 0.724 (**29**) |
| vigencia-correctness (`n_vigencia`) | 0.667 (**3**) |
| answerable questions with a gold key anywhere in the page | 5 / 29 |

**This is a NO-GO with healthy diagnostics, which is the strongest form of the result.** The leg
was not empty, not degraded, not mis-configured, and the gold set resolved against the right
snapshot — so the failure is a property of lexical retrieval over this corpus and these
questions, not of the harness. "Measured and failed" is a different verdict from "could not
measure", and this is the first.

**Consequence for V1**: the prod pgvector image swap can no longer be argued away by the
FTS-only escape hatch. Whether it is *needed* still depends on the vector and hybrid arms, which
are blocked on O.3. The scratch database was disposable; neither the main working tree nor the
dev database was touched.

## 4. Spec merge into the source of truth

Both capabilities are **new** — no pre-existing base spec, nothing to reconcile — so each
delta's requirements become the base spec whole. Written into the `rainfall-analysis` house
voice (purpose header, `## Requirements`, blank line after every Requirement and Scenario
heading); the deltas carried no ADDED/MODIFIED framing to strip, and no requirement text was
edited, reordered or dropped.

**`openspec/specs/knowledge-corpus-ingestion/spec.md` — 9 requirements / 26 scenarios**

| # | Requirement |
|---|---|
| 1 | Corpus Source Pinning and Idempotency |
| 2 | Type-Scoped Regex v3 Chunking and Section Exclusion |
| 3 | Frontmatter Field Carriage — Jurisdiccion and Relevancia-Consorcio |
| 4 | Citation Key Identity Preservation |
| 5 | Derecho-Aplicable vs Fuente-Secundaria Separation |
| 6 | Vigencia State and Dual-Redaction Preservation |
| 7 | Per-Document and Total Unit Count Gate |
| 8 | Exhaustive Inventory — No Silently Absent Section or File |
| 9 | Integrity Gates — Verbatim Substring and Token Ceiling |

**`openspec/specs/knowledge-hybrid-retrieval/spec.md` — 7 requirements / 16 scenarios**

| # | Requirement |
|---|---|
| 1 | Independent FTS and Vector Fusion by RRF |
| 2 | Result Provenance and Norma/Secundaria Separation |
| 3 | Confidence-Threshold Abstention |
| 4 | No User-Facing Surface in V0 |
| 5 | Three-Mode Ablation Eval Harness |
| 6 | Go/No-Go Thresholds and Gold-Set Precondition |
| 7 | Privacy Boundary on External Services |

Requirements 3, 8 and 9 of ingestion and requirements 2 and 6 of retrieval carry the JD Round-1
amendments in their final ratified form (`relevancia_consorcio` + `jurisdiccion` carriage, the
exhaustive-inventory gate that closed RAG2-001's class, the over-ceiling-is-not-truncation rule,
the do-not-cite provenance scenario, and the LOOCV cross-validation MUST).

**Scenario-count reconciliation, disclosed**: `verify-report.md` traces "all 20 ingestion
scenarios + all 15 retrieval scenarios". The archived deltas hold **26 and 16**. The traceability
claim itself is not in doubt — the verifier's per-scenario table is at Engram `sdd/consorcio-rag/verify-report`
(id 13792) — but the headline counts in the prose understate the specs by 6 and 1. Recorded so
the base specs are read as authoritative over that sentence.

## 5. Task state at archive

**73 checked / 2 unchecked**, and the 2 unchecked are exactly the owner-gated operations —
**4.14** (the real eval) and **O.3** (the RTX batch). No stale unchecked implementation task.
18 test-less tasks were spot-checked against the tree at verify; A6's recounts were verified
independently (`anexo-normativo` → 5, `contenido-no-declarado` → 12); the gold set verified at
52 owner-validated / 29 answerable / 23 unanswerable / 26 `pregunta_ref`.

**No archive-time checkbox was flipped.** Unlike `lluvia-insights`, whose owner-gated ops were
executed post-merge and reconciled at archive, O.3 and 4.14 remain genuinely undone — the RTX
batch has not run. Marking them would be fiction. They are carried into §6 as the runway.

## 6. Owner runway

**1. O.3 — the RTX batch** (owner's machine), verbatim from `verify-report.md:37`:

> `venv-rag` setup → `rag_embed_batch.py --preflight-only` → real batch → `make rag-embed-load`
> → `make rag-eval RAG_EVAL_PYTHON=../venv-rag/bin/python` with `RAG_GOLD_PRIVADO_PATH` set.
> Latency label defaults LOCAL; ESTIMATE per O.4 for the CPU-capped figure.

The full command sequence with its rationale is in the archived `apply-progress.md` §
"The owner command sequence". Three details that are load-bearing rather than decorative:

- **`RAG_GOLD_PRIVADO_PATH` must be set** or the run refuses: 26 of the 52 gold items live by
  reference in an owner-side file outside this repository, and an unresolved private item is a
  hard blocker rather than a quiet shrink of the denominator. The file's own `para:` and
  `corpus_sha:` are verified before any private question resolves (RAG4-003), exiting **4** and
  naming both SHAs on a mismatch.
- **`RAG_EVAL_PYTHON` is not optional decoration.** `vector` and `hybrid` build a real BGE-M3
  embedder, which needs `requirements-rag.txt` — the CUDA stack deliberately kept out of the app
  venv. Under plain `venv/` the run exits **2** naming `requirements-rag.txt`, `venv-rag` and the
  `--modo fts` escape hatch (RJDA-002). Absolute, slash-relative and bare-name overrides all
  resolve (RJDA-107).
- **`--preflight-only` first, and read its token counts.** The over-ceiling set is a property of
  the *embedder*, not a constant: 8192 under BGE-M3, **512** under multilingual-e5-large. "How
  far over" is what decides whether a unit is re-chunked upstream or accepted as FTS-only, and
  the sidecar now carries the measured count rather than a fabricated `8193` (RJDA-007).

**2. 4.14 — the real eval.** The lexical arm is already measured and is a NO-GO (§3). The vector
and hybrid arms await O.3's real vectors. When they land, the report answers the V1 question the
Scope Decision deferred: *do we need vectors in production at all?* — with numbers.

**3. The 12 `contenido-no-declarado` headings.** Twelve headings in the pinned corpus are
declared under that exclusion class rather than indexed. **Owner default: V0.1** — deferred out
of V0, revisited when the corpus next moves. The gate is honest about them either way: an
exclusion class must be declared at corpus level with its reason, and a heading in no inventory
aborts ingestion rather than vanishing.

**4. V1 prerequisites, unchanged**: the production Postgres image swap (now un-escapable via
FTS-only), Telegram infra, the `telegram_id`→padrón whitelist, and a citation-enforcing
generation layer. The privacy boundary moves from vacuous to real the moment actas enter.

## 7. Info bequest — the backlog this change leaves behind

Nothing here blocked archive. All of it survives the change.

**P1 — guard hardening (the CI guards that RJDA-101 rewrote are now stronger than the ones they
replaced, and still have named holes)**

1. **RJDB-201** — the geo-requirements check asserts only `{"torch", "segmentation-models-pytorch"}`,
   2 of the 5 `ML_DISTRIBUTIONS` formalised 30 lines above it. `Dockerfile.geo`/`Dockerfile.worker`
   install `requirements-geo.txt`; `sentence-transformers` landing there would pull torch into a
   server image unflagged. **One-word fix: `not in ML_DISTRIBUTIONS`.**
2. **RJDB-202** — the amended guard permits a lazy ML import in *any* app module, while the
   companion docstring claims `embedding.py` is the only one that names the heavy stack and
   nothing asserts it. A lazy `import torch` on a request path stays green in both checks and
   fails at runtime. **One assertion closes it**: files-with-ML-imports ⊆ `{embedding.py}`.
3. **RJDB-203** — the AST predicate sees only `Import`/`ImportFrom`, so a module-level
   `__import__("torch")` / `importlib.import_module("torch")` is invisible. Mitigated (not
   closed) by the closure check. Direct-URL requirement lines also normalize outside
   `ML_DISTRIBUTIONS`.

**P2 — provenance and rendering**

4. **RAG4-002** — `conocimiento_004` records model, HF revision, `sintetico`, artifact sha256 and
   a timestamp, but **not the batch's torch version or device**, which D6 requires "for both
   legs". Those live only in the sidecar, which RAG3-001 established is not durable. The report
   prints `no registrado en la base` rather than the query process's own torch/device — printing
   those would attribute a CPU box's environment to vectors produced on a CUDA one, a fabricated
   provenance line in the one block whose whole job is provenance. **Fix is two more nullable
   columns on `rag_corpus`, written in the same load transaction**, and it belongs to whoever
   owns the migration.
5. **RJDB-204** — RJDB-101's rendering fix ships unpinned: the only rendering test uses a
   1-key/1-question exemption, so the 10-cap, the `(+N more)` suffix and the
   markdown-capped/JSON-complete asymmetry are never exercised, and nothing asserts the absence
   of a hardcoded `8192`.
6. **RJDA-201** — `fileConfig` also calls `logging.config._clearExistingHandlers()`, which flushes,
   closes and de-registers every handler in the process. Not governed by `disable_existing_loggers`
   and unchanged by the RJDA-102 fix. Empirically inert under pytest; the next in-process alembic
   caller should not have to rediscover it.
7. **RJDB-104 ≡ RJDA-108** — the reverse-direction rollback note still says bare
   `alembic downgrade` "first", which is not a runnable command, and picking the target wrong is
   exactly how the stranded-volume runbook failed twice: name `downgrade conocimiento_001`. And
   `e5-large` is an advertised choice on three CLIs whose **real** construction path has never
   executed — `TestE5Embedder` injects a fake `sentence_transformers`. O.3's batch run will
   exercise it; until then it must not be mistaken for covered.

**P3 — doc hygiene (verify-report V-items, SUGGESTION/info)**

8. **V-2 / V-3** — `apply-progress.md` File Changes omissions and Coverage Table staleness.
9. **V-4** — task 4.1's cited test names drifted from the tree.
10. **V-5** — cosmic-ray mutation counts recorded stale.
11. **V-7** — `consorcio-web/public/version.json` hygiene.
12. **RJDA-202** — `--strict-token-ceiling` help text still says "over-8192-token units", the
    model-dependent-constant generalisation RJDB-101 removed from the report, one layer up.
13. **RJDA-203** — `_ml_imports` docstring claims module-level `try:`/`if:` wrappers all run at
    import time; true for `try:`, false for `if TYPE_CHECKING:`. Unreachable today.
14. **RJDB-205** — a comment sits on the `[0,1]`-bounds assertion claiming to exclude RRF's
    `1/61`, which that assertion satisfies; the exclusion is actually carried by
    `len(no_vacios) >= 2` two lines above. Reads stronger than it asserts.
15. **RAG2-007** — latent duplicate-heading dedup in `parser.py::_parse_non_articles`: the `seen`
    set is keyed on `citation_key`, so a second occurrence of an allow-listed heading would be
    dropped rather than reported. Not reachable in the pinned corpus. Deliberately not fixed —
    it needs a real second occurrence to specify the right behaviour.

**P4 — adjacent, not owned by this change**

16. **`tests/new/test_run_blocking.py::test_run_blocking_runs_concurrent_calls_in_parallel`** —
    pre-existing and untouched, flakes in the **local corpus-enabled full-suite shape only**.
    Measured: CI shape 4/4 green; corpus shape 6 failures in 9 runs; the test alone 5/5 green;
    `make test-rag-corpus` green. Three hypotheses falsified (tmpfs/memory, background `git gc`,
    fixture I/O weight — a 150× fixture reduction left the rate unchanged). **Not root-caused,
    and deliberately not papered over by editing someone else's assertion.** Recommended fix for
    its owner: assert the parallelism *ratio* (`elapsed < sum(durations) * 0.75`) instead of an
    absolute 0.18 s wall-clock budget.
17. **The pgrouting full-chain replay gap** — `throwaway_db` stamps `lluvia_v2_005` instead of
    replaying from empty, because a pre-existing migration runs `CREATE EXTENSION pgrouting`
    unconditionally and the default test image has no such package. Verified not to hide a broken
    chain (`alembic heads` reports a single head; CI's `alembic upgrade head` still replays the
    full chain on a fresh database, which is the prod-shaped case). Scoped to one test fixture,
    not to the migration graph.

## 8. Review process record

- **1 BLOCKER (PII) + 1 BLOCKER (red CI) + 19 CRITICAL-class rows change-wide, every one
  `fixed`** with a recorded downstream verdict — refuter adjudication, scoped re-review CLEAN,
  or a 2× CLEAN Judgment Day re-judge. See §2 for the recount reconciliation.
- **Convergence budget respected everywhere.** Judgment Day used exactly 2 rounds and was never
  extended; each per-slice review ran 1 fix round against a budget of 2.
- **Refuter protocol compliant**: one batched general refuter per slice over the merged
  BLOCKER/CRITICAL list, never one task per candidate; Judgment Day's two-judge convergence is
  the documented exception and spawned no refuter fan-out.
- **No CRITICAL hiding as `info`.** Every `info` row was audited at verify, and V-6 was closed by
  writing the nine summarized info findings out in full in the ledger rather than leaving them as
  prose.
- **Two review lessons worth keeping**, both earned by execution rather than argument: a scoped
  re-judge that reads a diff can confirm every intent in it and still not notice the branch is
  red (RJDA-101); and measuring a subset and calling it the gate is how a guard test stays red in
  CI while every artifact reports green (RJDA-102, `tests/new/` ≠ `pytest tests/`).

## 9. Artifact traceability (Engram)

| Artifact | Observation | Project |
|---|---|---|
| corpus legal (upstream input) | #11657 | javier |
| RAG design ratified | #11648 (item 4) | javier |
| over-ceiling FTS-only decision (slice 3) | #13613 | javier |
| Judgment Day apply — Round 2 final fix round | #13708 | javier |
| lesson: `tests/new/` ≠ `pytest tests/` | #13720 | javier |
| verify-report (full traceability table) | #13792 `sdd/consorcio-rag/verify-report` | consorcio-canalero |
| prod deploy `a2435144` | #14001 `consorcio/deploy-2026-08-11` | javier |
| archive-report | this document + `sdd/consorcio-rag/archive-report` | consorcio-canalero |

**Traceability note, disclosed**: records for this change are split across the `consorcio-canalero`
and `javier` Engram projects because the MCP process resolves the project from a fixed cwd. The
split is bookkeeping, not a content gap — the same disclosure `lluvia-insights` made.

## 10. Closure

Proposed with an owner question round that was answered in two explicit rounds, designed under a
Judgment Day that closed in one, implemented in 4 reviewed slices, judged again over the apply in
exactly 2 rounds ending APPROVED, verified PASS-with-notes, merged as PR #178 and deployed to prod
dormant exactly as the Scope Decision intended.

**What V0 promised was a measurement, and the measurement exists**: FTS-only does not clear the
bar, with healthy diagnostics proving the leg was working when it failed. The vector and hybrid
arms are one owner-side GPU batch away. **SDD cycle complete.** §6 is the runway and §7 is the
bequest; neither is a blocker.
