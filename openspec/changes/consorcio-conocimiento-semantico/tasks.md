# Tasks: Conocimiento Semántico V1 — Cited Legal Q&A for the Comisión Directiva

Artifact language: English, consistent with `proposal.md`, `design.md` and the three spec files.
Retrieval tasks follow the **ratified amendment** (`design.md:1118-1155`): candidate generation is real
BM25 (config `B50`), the vector leg is out of candidate generation, ranking is `bge-reranker-v2-m3`
depth-50 fp16 on GPU, `es_secundaria` exclusion is load-bearing, no lexical signal ever enters the
cross-encoder score, per-document cap REJECTED, bars re-ratified.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~3,000–3,400 (authored, additions + deletions) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | U1 → U2 → U3 → U4 → U5 → U6 → U7 → U8 → U9 → U10 |
| Delivery strategy | ask-on-risk (not overridden by the orchestrator) |
| Chain strategy | pending (owner picks stacked-to-main vs feature-branch-chain before apply) |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Forecast | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|---------:|----------------------|-----------------|-------------------|
| U1 | Three-class `clasificacion` rule + migration `conocimiento_005` + `expected_clasificacion.yaml` | PR 1 | ~330 | `pytest tests/new/conocimiento/test_rag_ingest_frontmatter.py tests/new/conocimiento/test_rag_privacy.py` | `alembic upgrade head && alembic downgrade -1` on a scratch DB | migration + `repository.py` rule; revert restores the `privado` hardcode |
| U2 | B50 retrieval: in-process BM25 index + reranker port + `modo="bm25_ce"` | PR 2 | ~400 | `pytest tests/new/conocimiento/test_recuperacion_bm25.py` | `make rag-eval` (GPU box) reproducing hit@5 ≈ 0.759 | new `recuperacion/` module + one `MODOS` entry; existing modes untouched |
| U3 | `conocimiento-embed` sidecar + `Embedder` adapter + `(modelo, revision_hf)` guard | PR 3 | ~300 | `pytest tests/new/conocimiento/test_embed_sidecar.py` | `docker compose up -d conocimiento-embed && curl /ready` | `docker/embed/` + adapter; guard change is additive |
| U4 | Router: rules → centroid, LOOCV margin, `mixto` signature, decision record | PR 4 | ~360 | `pytest tests/new/conocimiento/test_routing.py` | `make rag-eval` router block (confusion matrix) | `routing.py` + one table; no serving path depends on it until U7 |
| U5 | Generation core: payload exclusion, citation enforcement, 5 states | PR 5 | ~400 | `pytest tests/new/conocimiento/test_generacion.py` | `GeneradorDeterministico` fixture run | `generacion.py`; provider not wired yet |
| U6 | Provider adapter + quota/spend + worker timeouts + config | PR 6 | ~260 | `pytest tests/new/conocimiento/test_costos.py` | quota-exhaustion request against a local stub | `proveedores.py` + `config.py` knobs |
| U7 | HTTP surface (submit→id + status), queue, schemas, no-router retirement (same unit) | PR 7 | ~300 | `pytest tests/new/conocimiento/test_qa_surface.py` | `curl -H 'Authorization: …' POST /api/v2/conocimiento/preguntas` | router mount + flag; flag-off makes it inert |
| U8 | `consorcio-web` CD page (bandeja) | PR 8 | ~280 | `npm run test -- ConocimientoPanel` | manual admin login → ask one legal question | route + panel; hidden page is not the boundary |
| U9 | Eval extension: answer metrics, router accuracy, post-exclusion abstention | PR 9 | ~350 | `pytest tests/new/conocimiento/test_eval_answers.py` | `make rag-eval` full report | `eval/` additions; V0 retrieval blocks unchanged |
| U10 | G9 runbook, compose block, box measurements, docs | PR 10 | ~200 | `pytest tests/new/conocimiento -q` (regression only) | the runbook itself, dry-run on the box | docs + external compose edit; no code |

*(amended 2026-08-23 — async queue model, owner decision 0.5: U6/U7/U8 are re-scoped by amendment A3 in
`design.md`. U6 loses the in-flight semaphore and its timeouts move worker-side; U7 becomes submit→id plus a
status/listing surface backed by a queue; U8 becomes a mailbox page. Line forecasts are unrevised and should be
re-estimated before the chain strategy is picked.)*

## Phase 0: Owner decisions (BLOCKING — do not choose on the owner's behalf)

- [ ] 0.1 **BLOCKING for U9 + enablement — abstention policy.** The amendment leaves this open
      (`design.md:1145-1148`): reranker confidence is a worse signal than cosine (LOOCV precision `0.489`
      at recall `1.000`; `docs/rag/reranker-experiment-2026-08-23.md:133-179`). Options on the table, owner
      picks one: (a) relax recall to ≥ `0.90` keeping precision ≈ `0.48`; (b) keep recall `1.00` and build a
      new signal (none-of-the-above candidate / entailment check / OOD classifier). Until answered, U9's
      abstention row is `not-evaluable` and the surface is not enabled. No task below picks a side.
- [x] 0.2 **BLOCKING for U1 merge** — ratify `FUENTES_PUBLICAS` and `TIPOS_INSTITUCIONALES` against the
      generated `expected_clasificacion.yaml`, not in the abstract (`design.md:1096-1102`).
      **RATIFIED 2026-08-23** — `FUENTES_PUBLICAS` gains `boletinoficial.gob.ar` (national gazette) and
      `justiciacordoba.gob.ar` (Córdoba judiciary); NEW RULE: an INDEX/landing URL never establishes
      publication, only concrete-document URLs match. Corpus lands 26 `publico` / 1 `institucional` /
      8 `privado` (`artifacts/rag/expected_clasificacion-draft-r2-2026-08-23.yaml`). See amendment A1.
- [x] 0.3 **BLOCKING for U4 scoring** — ratify the router numeric bar (`operational → legal` ≤ 0.05, overall
      ≥ 0.85, n ≥ 40 with a 10-per-class floor) and the labeled set (`design.md:175-186, 1106-1107`).
      **PARTIALLY RESOLVED 2026-08-23** — process ratified: the orchestrator drafts ~40–50 labeled questions,
      the owner ratifies the set, and the numeric bar is fixed **only after measuring on the ratified set**.
      The bar itself stays UNSET and must not be written into code or `eval/` before that. See amendment A4.

      **CLOSED — BAR RATIFIED BY THE OWNER 2026-08-24.** Fixed with the measured numbers in hand, which is
      what the 2026-08-23 process decision protected. The ratified bar, verbatim:

      > **accuracy held-out ≥ 0.70 · operational→legal = 0 (dura) · mixto→legal ≤ 2 (con follow-up nombrado
      > para bajarla)**

      Codified in `routing.BarraRouter` (`exactitud_minima=0.70`, `operational_a_legal_max=0`,
      `mixto_a_legal_max=2`, `ratificada=True`) and `evaluar_barra` now issues a REAL verdict. Against the
      held-out figures of the ratified n=49 set (accuracy 0.755 · operational→legal 0/12 · mixto→legal 2/13)
      the bar **PASSES on all three components**. Two notes on how it is written:

      - `operational → legal` is a **COUNT and not a fraction**. The proposed `≤ 0.05` was a rate; the owner
        ratified a hard zero, and there is no sample size at which one fabricated figure about a real
        person's debt becomes a rounding error.
      - `ratificada=False` is **kept reachable and still tested**. It is the state a future set or a future
        bar re-enters when nobody has fixed it, and a flag that only ever holds one value is a flag nobody
        can use. `test_una_barra_sin_ratificar_reporta_y_no_dictamina` holds that path.

      **FOLLOW-UP (named, not deferred into silence):** *reducir `mixto→legal` (hoy 2/13) vía tuning de
      banda/piso — re-medición en U9 con más gold.* The bar was ratified AT the measurement rather than
      comfortably above it, so 2 is a ceiling nobody should read as a target. The lever is the calibration
      grid (`banda` / `piso` in `seleccionar_parametros`), and the honest way to move it is more labeled
      items, not a tighter fit on 49 — which is why the re-measurement is scheduled in U9 next to F2.
- [x] 0.4 **BLOCKING for U6** — provider/model pin, re-derived per-query cost, published no-training +
      retention terms, `conocimiento_quota_diaria_usuario`, `conocimiento_spend_ceiling_usd`, and the three
      timeout values (`design.md:619-625, 1103-1110`).
      **PIN RATIFIED 2026-08-23** — `deepseek-v4-flash` via the opencode-go pool, routed by mcp-llm-bridge;
      pinned in **config, not code**. Cost/quota/ceiling values remain unset pending re-derivation against
      this pin (the Claude-class figures in the body are stale). Terms verification is new task 6.7 and is a
      hard pre-enablement gate. See amendment A2.
- [x] 0.5 **BLOCKING for enablement — serving host for the reranker.** GPU or hosted reranking endpoint is a
      hard requirement (`design.md:1132-1134`); the box has no GPU and a weaker CPU than the measured
      i7-12700K, whose depth-50 figure is 98.9 s and is a *lower bound* for the box
      (`docs/rag/reranker-experiment-2026-08-23.md:357-371`).
      **DECIDED 2026-08-23 — ASYNCHRONOUS MAILBOX.** Questions are queued; a GPU worker (the owner's
      workstation, when available) processes them in batches; the answer appears when processed, with an
      honest `pendiente` state meanwhile. This SUPERSEDES the synchronous serving model: the 60 s/87 s
      deadline analysis stops being a serving gate and becomes the worker's budget, the
      `503 reranker_no_disponible` is replaced by the queue state, and U7's HTTP surface becomes
      submit→id + status. See amendment A3 for the full supersession table.
- [x] 0.6 Answer-set size (n ≥ 30 answers proposed) and routing-record retention (90 days proposed)
      (`design.md:1113-1114`). **RATIFIED AS PROPOSED 2026-08-23** — n ≥ 30 answers, 90-day retention.

## Phase 1: Classification rule + migration (U1)

- [x] 1.1 **Migration `conocimiento_005`** in `gee-backend/app/db/migrations/versions/`: widen
      `CHECK (clasificacion IN ('publico','privado'))` — `models.py:156-157`, created at
      `conocimiento_001_rag_corpus_schema.py:85-86` — to `('publico','institucional','privado')`, and add the
      nullable `clasificacion_evidencia` column (`design.md:414-420`, `design.md:962`). **This runs BEFORE any
      re-ingest**: ingest is one transaction (`scripts/rag_ingest.py:170, :219-232`) and an `institucional`
      row against the narrow CHECK rolls the whole re-ingest back.
- [x] 1.2 Migration downgrade demotes every `institucional` row to `privado` before re-creating the narrow
      CHECK; mirror the CHECK in `models.py`.
- [x] 1.3 RED: `test_conocimiento_005_roundtrip` — an `institucional` row inserts after upgrade, and the
      downgrade demotes rather than failing the CHECK (real PG, `tests/new/conocimiento/`).
- [x] 1.4 RED: three-class derivation tests replacing `test_clasificacion_defaults_to_privado`
      (`test_rag_ingest_frontmatter.py:113-116`) — the 11 checked-in fixtures against their expected class
      **and evidence string** (`design.md:352-364, 970`).
- [x] 1.5 RED (threat: silent widening of the shippable set): a rule change not reflected in
      `expected_clasificacion.yaml` fails the unit diff (`design.md:1077`).
- [x] 1.6 RED (ordering): `informe-f3` short-circuits on `es_secundaria` **before** any host is read, and
      `fuentes_externas_verificadas` is never consulted (`design.md:290-300`).
- [x] 1.7 RED (host semantics): `www.saij.gob.ar` matches `saij.gob.ar`; `saij.gob.ar.evil.example` and
      `notsaij.gob.ar` do not (label-boundary suffix rule, `design.md:327-333`).
- [x] 1.8 GREEN: replace the `"clasificacion": "privado"` hardcode at `repository.py:164-166` with the
      ordered three-class rule inside `documento_row_from_frontmatter`; add `FUENTES_PUBLICAS`,
      `TIPOS_INSTITUCIONALES = {"registro-administrativo"}`, `CLASIFICACIONES_ENVIABLES`, and write
      `clasificacion_evidencia` alongside `clasificacion` (`design.md:275-342, 399-402, 998-1001`).
      *(amended 2026-08-23: `FUENTES_PUBLICAS` is the ratified 9-entry list including `boletinoficial.gob.ar`
      and `justiciacordoba.gob.ar`; and an allowlisted host only matches on a CONCRETE-DOCUMENT URL — the
      index/landing exclusion mechanism (`INDICE_NO_PUBLICACION` list or a documented heuristic) is U1's
      implementation choice and must be a checked-in artifact with tests under the same change control as
      `FUENTES_PUBLICAS`. See amendment A1.)*
- [x] 1.8b RED (index rule, added 2026-08-23): `https://www.aprhi.gob.ar/normativas/` does NOT promote a
      document even though `aprhi.gob.ar` is allowlisted, while a concrete document URL on the same host does.
      Regression fixture must include `decreto-3780-c-65` (loses its APRHI match, stays `publico` on its
      `www.cba.gov.ar` PDF) and `resolucion-dph-11821-1985` (loses its APRHI match, stays `publico` on
      `justiciacordoba.gob.ar`).
- [x] 1.9 GREEN: `assert_unidades_publicas(db, corpus_sha, claves) -> frozenset[str]` in `service.py`,
      returning the shippable subset by the raw-SQL join shape of `eval/privacy.py:49-58`; it never raises on
      a non-shippable unit (`design.md:433-441, 1039-1044`).
- [x] 1.10 GREEN: `eval/privacy.py`'s `assert_public_domain` stays `publico`-only and keeps whole-snapshot
      refusal; rewrite the stale docstring of
      `test_rag_privacy.py:85-92` and add the sibling test that an `institucional` snapshot also refuses
      (`design.md:249-257, 971`).
- [x] 1.11 **Generate `eval/expected_clasificacion.yaml`** (surfaced-not-fixed #3): write
      `scripts/rag_expected_clasificacion.py`, run it against the **private corpus checkout at
      `12043582bf8016288a7e8084e85a4b713a97af2f`**, and commit all 35 rows with `documento_id`, `tipo`,
      `es_secundaria`, expected `clasificacion`, evidence string and the `corpus_sha` header. Only 7 of 35 are
      derivable in-repo (6 secundaria + 1 `registro-administrativo`, `design.md:366-374`); the other 28 need
      the checkout. Refuse on `corpus_sha` divergence like `harness.py:254-269`.
- [x] 1.12 **Verification task, no code (surfaced-not-fixed #2):** settle
      `resolucion-dipas-395-2004-linea-ribera-provisoria` against the private checkout — does it carry a
      `FUENTES_PUBLICAS` host? If not it stays `privado`, its `res-dipas-395-2004#art1/#art3` keys are excluded
      and gold item **C-8 is partially grounded, not fully** (`design.md:422-430`). Record the finding in the
      PR and feed it into decision 0.2.
      *(amended 2026-08-23: SETTLED, favourably. The document carries
      `https://www.justiciacordoba.gob.ar/justiciaCordoba/Inicio/fileAdjunto.aspx?id=1070`, a concrete
      document on a now-allowlisted host, so it derives `publico` and **C-8 is FULLY grounded**. What remains
      of this task is to assert that outcome in the generated artifact, not to discover it.)*

## Phase 2: B50 retrieval (U2)

- [x] 2.1 RED: `recuperacion/bm25.py` postings-list index built from the lexemes already stored in `tsv` —
      textbook BM25 `k1=1.2`, `b=0.75`, IDF present. Assert `ts_rank_cd` is NOT used (measured −0.104 hit@5,
      `docs/rag/candidate-recall-campaign-2026-08-23.md:374-390`).
- [x] 2.2 GREEN: build the index once per `corpus_sha` (measured 0.14 s / ~2 MB / 1398 units), query stemming
      stays in Postgres via `to_tsvector('spanish', …)` so the analyzer cannot drift; top-50 over
      **`es_secundaria = false` units only** (`design.md:1126-1128, 1135-1136`).
- [x] 2.3 RED: the `es_secundaria` filter is load-bearing — without it norma-vs-secundaria collapses to
      `0.483` (`design.md:1135-1136`). Test asserts no secundaria unit can enter the candidate pool.
- [x] 2.4 GREEN: `recuperacion/reranker.py` — `bge-reranker-v2-m3` port over the 50 candidates, fp16, batch
      configurable; ranking score is the cross-encoder score ALONE.
- [x] 2.5 RED: no lexical signal may blend into the CE score (RRF −0.035/−0.069, CE×lexical −0.104/−0.207;
      `design.md:1136-1138`), and **no per-document cap** exists (rejected: hit@5 0.793 but
      vigencia-correctness collapses to 0.333, `design.md:1138-1139`). Both asserted as code contracts.
- [x] 2.6 GREEN: add `modo="bm25_ce"` to `MODOS` and wire it in `service.recuperar`
      (`service.py:291-348`) — BM25 candidates → reranker → top-k; the RRF fusion path
      (`service.py:345-348`) stays for the legacy `fts`/`vector`/`hybrid` modes and is not deleted.
- [x] 2.7 RED: in `modo="bm25_ce"` the retrieval path performs **zero** reads of the stored vector column
      (spy/assert). **Vector-leg disposition, stated rather than assumed:** the persisted BGE-M3 unit
      embeddings, the pgvector column/index, `rag_load_vectors.py` and runbook step 9 are **kept**; the
      amendment removes the vector leg from candidate generation only (`design.md:1129-1131`). Post-amendment
      the design retains a query-side vector for the **router centroid** (G1, `design.md:145-149`) — which the
      sidecar computes and which does not read the stored column — so **no serving consumer of the stored
      corpus vectors remains**. They stay for eval re-runs, the D-7 dense-only case
      (`docs/rag/candidate-recall-campaign-2026-08-23.md:400, 416-419`) and future re-measurement. Do not
      delete and do not repurpose silently; record this in the runbook (task 10.3).
- [x] 2.8 GREEN: bars in the report are the re-ratified ones — hit@5 ≥ 0.72, hit@10 ≥ 0.80, MRR ≥ 0.55,
      citation-precision ≥ 0.33, norma-vs-secundaria = 1.00, vigencia-correctness = 1.00
      (`design.md:1141-1145`). Update the retrieval delta's V1 gate (`spec.md:82`) in the same unit.
- [x] 2.8b GREEN — **"A synthetic ranker cannot open the gate"** *(the scenario 2.8's amendment added; split
      out 2026-08-23 because it was asserted in the spec and implemented nowhere)*. `ResultadoModo` carries
      `ranker_modelo` / `ranker_sintetico` up from `ResultadoRecuperacion`, and `report._gate_sintetico`
      refuses on it with the same treatment it gives synthetic embeddings — no verdict, `SINTETICO-` in the
      filename. Necessary because `bm25_ce` reads no vector column, so `ProcedenciaEmbeddings` says nothing
      about what ranked it: a stand-in ranker fabricates the entire order over honest embedding provenance.
      Both directions covered (synthetic ⇒ closed; real and no-ranker ⇒ no interference).

## Phase 3: Embedding sidecar and identity guard (U3)

- [x] 3.1 GREEN: `docker/embed/{Dockerfile,requirements-embed.lock,app.py}` — `/embed`, `/health`, `/ready`;
      fully pinned `--require-hashes` lock, CPU torch wheel, **no** `sentence-transformers`, NOT built from
      `requirements-rag.txt:23-33` (`design.md:122-128`).
      *(applied 2026-08-23. Lock generated with `uv pip compile --generate-hashes` against the PyTorch CPU
      index: 36 pins, `torch==2.8.0+cpu`, zero `nvidia-*`, zero `sentence-transformers`. **Deviation, stated
      rather than hidden:** the image does NOT re-implement the encoder — it copies `embedding.py` + `ddl.py`
      and imports `BGEM3Embedder`, so the batch and the sidecar share ONE CLS-pooling + L2-normalize path.
      Two implementations of one model is the drift `verificar_embedder` structurally cannot see, since both
      sides would still report `BAAI/bge-m3` at the same commit while producing different vectors. That
      import costs `sqlalchemy` (pure Python, one `text()` call in `ddl.py`) in the lock; the container is
      given no `DATABASE_URL` and opens no connection. Also added: the repo `docker-compose.yml` service
      (U10 owns the BOX's external compose, not this one) and `Dockerfile.dockerignore`, because the context
      must be the repo root for that import and an unbounded context ships secrets into layers.
      *Amended 2026-08-23:* the compose service carries `profiles: ["conocimiento"]`. It was described as "not
      started by default" while having no profile at all, which made a bare `docker compose up -d` on the box
      pull 2.2 GB of weights nobody asked for; the comment is now enforced rather than merely written. Also,
      the lock was regenerated with `--emit-index-url` so it records `--extra-index-url
      https://download.pytorch.org/whl/cpu` in the artifact itself — `torch==2.8.0+cpu` exists on that index
      and nowhere else, and a lock that names its index only in the Dockerfile is reproducible only for
      whoever already knows. Verified: zero pins changed, the diff is the header and the two index lines.)*
- [x] 3.2 GREEN: `/ready` is true only after model load + one warm-up embed; until then the surface answers
      `no_disponible` cause `embedder_no_listo` (`design.md:117-120`).
      *(applied 2026-08-23. Load runs on a daemon thread started by the lifespan, so `/health` answers during
      the 30–60 s load and the compose healthcheck probes `/health`, never `/ready` — a readiness-based
      healthcheck would restart-loop the container through its own cold start forever. Load failure and
      still-loading are kept as DIFFERENT states; collapsing them would make a permanently broken sidecar
      read as a slow one. Backend half is `embed_sidecar.py`: `conectar_sidecar` probes `/ready` and refuses
      with a named `causa` — `embedder_no_listo`, `embedder_inalcanzable`, `embedder_respuesta_invalida` —
      and never waits, never falls back to stage-1 rules and never redirects (`design.md:198-202`). New
      settings `conocimiento_embed_url` / `conocimiento_embed_timeout_s`. `count_tokens` REFUSES on this seam:
      it is an ingestion-time pre-flight that needs the real tokenizer in the process that truncates.)*
- [x] 3.3 RED: revision canonicalization — a symbolic pin and its resolved 40-hex hash compare EQUAL, two
      different hashes compare unequal, a non-resolvable ref refuses, `NULL == NULL` only for
      `DeterministicEmbedder` (`design.md:61-105`).
      *(applied 2026-08-23 — `canonicalizar_revision` / `resolver_revision` / `RevisionNoResoluble` in
      `embedding.py`; 11 tests in `TestCanonicalizacionDeRevision`.)*
- [x] 3.4 GREEN: invert `embedding.py:372-373` so the config `_commit_hash` wins over the symbolic argument;
      the sidecar reports the resolved value in `revision_hf`.
      *(applied 2026-08-23. `BGEM3Embedder.__init__` now calls `resolver_revision(revision, _commit_hash)` and
      keeps the requested pin as `revision_solicitada` — evidence in a bug report, never the compared value.
      The sidecar reports `embedder.revision`, so `EMBED_REVISION_HF` is an input and never the report. The
      precedence itself is asserted on the source, because the constructor needs torch and 2.2 GB of weights.
      **Deviation, stated rather than hidden:** `BGEM3Embedder.__init__` can now RAISE where it previously
      could not. `resolver_revision` ends in `canonicalizar_revision`, so a revision that is neither `None`
      nor a 40-hex commit — a tag on `config._commit_hash`, or a symbolic `revision=` argument with nothing
      resolved — leaves the constructor as `RevisionNoResoluble`. That subclasses `ValueError`, and
      `scripts/rag_embed_batch.py:260` catches `RuntimeError`/`ImportError` only, so on the INGEST path it is
      an uncaught traceback: the batch dies before `embed_snapshot` writes any dump or manifest. This is
      fail-closed BY CHOICE and the alternative was rejected: embedding a whole corpus and stamping it with a
      provenance the guard structurally cannot compare produces an artifact that loads fine and can never be
      verified against any serving process again — a silent, permanent hole, paid for at query time. The cost
      of the choice is that the exception message is the operator's entire error report, so it names the value
      it refused and both places a resolved hash can be pinned (`EMBED_REVISION_HF`, or a re-run that stamps
      `revision_hf`), and `test_the_refusal_names_the_pin_and_what_to_do_about_it` holds it to that. Not
      wrapped into a `return 2` in the batch script: the crash is correct, and a caught-and-reformatted
      version would only make an already-loud refusal quieter.)*
- [x] 3.5 GREEN: `verificar_embedder` (`service.py:259-288`) compares the tuple
      `(procedencia.modelo, procedencia.revision_hf) != (embedder.model_id, embedder.revision)`; a NULL stored
      revision is unknown provenance and refuses (`design.md:89-105`).
      *(applied 2026-08-23. Both operands are canonicalized first and a non-resolvable value on either side
      raises `EmbedderMismatch` naming it verbatim. The NULL exemption is keyed on `embedder.sintetico`, not
      on the NULLs: a REAL embedder reporting no revision is unknown provenance even when the row is also
      NULL, because matching two unknowns is matching nothing to nothing and calling it identity. Written as
      one tuple check via a `_REVISION_SINTETICA` sentinel rather than an early return, so a field added later
      cannot skip the exemption path.)*
- [x] 3.6 GREEN: `recuperar` gains keyword-only `qvec` — `service.py:342` becomes "use the caller's vector if
      given"; `require_vector_support` and `verificar_embedder` still run (`design.md:150-160`).
      *(applied 2026-08-23. One added refusal beyond the design: `modo="bm25_ce"` with a `qvec` raises, because
      that path reads no vector column at all and accepting-then-discarding would let a caller believe a
      vector reached the ranking with no symptom.)*

## Phase 4: Router (U4)

- [x] 4.1 RED: stage-1 deterministic lexicon (deuda/cuota/saldo, trámite, expediente, denuncia, "¿dónde…?",
      canal N°, coordinates, padrón-shaped name) — spec scenarios `routing spec:22-27, 33-45`.
      *(applied 2026-08-24. The lexicon fires ONLY when no legal marker is present, and that condition
      is the whole doorway to `mixto`: "¿qué dice la norma sobre la cuota y cuánto debo yo?" carries a
      `/finanzas` marker AND a norm word, so a lexicon firing on markers alone would redirect the spec's own
      worked `mixto` example (`routing spec:59`) and the class would be unreachable from the question that
      defines it. Family precedence is DECLARED (finanzas → tramites → denuncias → mapa) rather than
      incidental, because `routing spec:47-51` requires the same subject to always name the same surface.
      One decision beyond the design: `SUPERFICIE_OPERACIONAL_POR_DEFECTO = "/tramites"` for an `operational`
      outcome with no family marker (a bare padrón-shaped name). `routing spec:31` REQUIRES a named surface,
      G1 does not say which one when the subject family is unresolved, and `None` would break the spec. It is
      safe rather than a guess because every branch reaching it is ALREADY a redirect: the failure mode is an
      operator landing on the wrong tab, never invented prose. Flagged for owner review.)*

      *(**S-1 RATIFIED by the owner 2026-08-24.** `SUPERFICIE_OPERACIONAL_POR_DEFECTO = "/tramites"` stands,
      and the stated reason is that `/tramites` is the most general of the four surfaces — the one an
      operator lands on carrying the fewest wrong assumptions about what their own question was about. It
      was raised as an implementation decision and it was answered as a decision, so it is now pinned by
      `test_la_superficie_operacional_por_defecto_es_la_ratificada`, which asserts the LITERAL `"/tramites"`
      rather than the `SUPERFICIE_TRAMITES` alias: the alias would follow the constant wherever a refactor
      moved it, and what the owner ratified is the destination, not the name of a variable.)*
- [x] 4.2 RED: an `operational` question makes **zero** retrieval calls (spy) — `routing spec:13, 22-27`.
      *(applied 2026-08-24. The spy replaces `service.recuperar` on the module rather than arriving as a
      parameter: a parameter the production caller never supplies proves nothing, while replacing the symbol
      catches any future `routing.py` that reaches for retrieval by any import path. A third case was added
      beyond the task — a confident `legal` question does not retrieve either, because routing DECIDES and
      U7 wires. `DecisionRuta` is also asserted to carry no answer/citation field at all.)*
- [x] 4.3 RED: `mixto` top-2 signature — `{legal, operational}` (or `{legal, geoespacial}`) within the margin
      band **and** both above the absolute cosine floor ⇒ `mixto`, one response with both blocks; other doubt
      shapes redirect (`design.md:161-170`, `routing spec:53-70`).
      *(applied 2026-08-24. The `mixto` branch is evaluated FIRST and that ordering IS the exemption. Two
      test premises were wrong and were corrected rather than coded around: (a) cosine ignores magnitude, so
      "two weak scores" cannot be produced by a SHORT vector — `(0.05, 0.05, 0)` normalizes to the same
      0.707/0.707 as the canonical `mixto`; weakness is a DIRECTION pointing away from every axis. (b) with
      one axis per pure class, `min(top-2) < piso` while top-2 = {legal, operational} requires a NEGATIVE
      third component. Both are now asserted explicitly, plus a scale-invariance test.)*
- [x] 4.4 RED: sidecar unavailable ⇒ `no_disponible`, **never** a stage-1 redirect and never an abstention
      (`design.md:198-202`).
      *(applied 2026-08-24. `SidecarNoDisponible` propagates untouched — there is no `except` at this seam
      and there must not be one. Also asserted from the other side: a question stage 1 already decided never
      asks the sidecar anything, which is NOT a fallback (nothing failed, nothing degraded).)*
- [x] 4.5 GREEN: `routing.py` — rules → BGE-M3 centroid over the single query vector, margin confidence,
      LOOCV-calibrated threshold + band + floor, shipped threshold from the full set, same-sample figures
      labeled `upper bound` (`design.md:172-174`).
      *(applied 2026-08-24. `mixto` deliberately gets NO centroid: averaging questions that each sit between
      a different pair of classes produces a blur near the middle of everything, which then wins questions
      belonging to neither leg. `Centroides.__init__` REFUSES a `mixto` key for that reason and refuses a
      missing pure class, because cosine against a zero vector is undefined — not 0.0. LOOCV rebuilds the
      CENTROIDS as well as the parameters per fold: refitting only the parameters leaks the held-out item
      through the very direction it is scored against. `seleccionar_parametros` sweeps the observed grid with
      a stated PREFERENCE ORDER (fewer `operational → legal`, then more accuracy) — that is calibration, not
      a bar, and it decides nothing about shipping.)*
- [x] 4.6 GREEN: routing decision record `(pregunta, clase, margen, umbral_vigente, ts)` in the box's own
      Postgres — **question stored verbatim**, admin-read only, bounded retention, never in any eval or
      generation payload (`design.md:188-196`, `routing spec:85, 94-98`).
      *(amended 2026-08-23: retention window RATIFIED at **90 days** (decision 0.6) — no longer a proposal.)*
      *(applied 2026-08-24. `rag_decision_ruta` + migration `conocimiento_006` (chained onto
      `conocimiento_005`, the verified single tip; `alembic heads` re-checked after writing). Three points
      worth naming: (a) this is the one table in the domain that uses `UUIDMixin` — the other three carry
      natural composite keys because a snapshot's citation keys ARE its identity, and there is no natural key
      for "a question somebody asked at 14:32"; (b) `superficie` is nullable and its CHECK admits NULL,
      because `legal` is the one class that redirects nowhere and a NOT NULL column would force a sentinel
      surface onto every answered question — a sentinel that looks like a surface is the fabricated-redirect
      shape the router exists to prevent; (c) `margen`/`umbral_vigente` stay NULL for every stage-1 decision,
      since a lexicon rule computed neither and 0.0 would be a confidence on a decision that has none. The
      90-day window is EXECUTED by `purgar_decisiones_ruta` with a real row count — bounded retention nothing
      ever runs is retention forever with a comment — and the exact edge (`<`, so a row at the window edge
      survives) is asserted. The record deliberately stores no `qvec`, no `puntajes` and no citation surface.)*
- [x] 4.7 GREEN: `eval/router_set.yaml` + confusion-matrix block naming the `operational → legal` cell;
      unratified set ⇒ `not-evaluable` (`routing spec:100-104`).
      *(amended 2026-08-23, decision 0.3: the orchestrator drafts ~40–50 labeled questions and the owner
      ratifies the set; the **numeric bar is fixed only AFTER measuring on the ratified set**. Do not write
      `operational → legal ≤ 0.05` or `overall ≥ 0.85` into code or `eval/` before that measurement — they are
      still proposals. See amendment A4.)*

      *(applied 2026-08-24. `eval/router_set.yaml` is the RATIFIED projection of
      `artifacts/rag/router_gold_draft-2026-08-24.yaml` (n=49, 13/12/11/13), committed because every question
      is synthetic — none was transcribed from a `privado` document, so none inherits a classification.
      `cargar_router_set` refuses anything whose `estado` does not start with `RATIFICADO` AND re-checks the
      n>=40 / floor-of-10-per-class shape, because ratification is not a bypass of the sample size: a file
      edited down to twelve items still parses and would still print a matrix.

      MEASURED against the ratified set with the REAL BGE-M3
      (`BAAI/bge-m3` @ `5617a9f61b028005a4858fdac845db406aefb181`, `sintetico=False`, venv-rag, offline),
      shipped params umbral 0.004 · banda 0.098 · piso 0.577:

      | figure | held-out (LOOCV) | upper bound (fit on the scoring sample) |
      |---|---|---|
      | `operational -> legal` | **0** (0.000 of 12) | 0 |
      | overall accuracy | **0.755** | 0.857 |

      Held-out confusion (esperada \ predicha): legal 8/1/2/2 · operational 0/9/2/1 · geoespacial 0/0/11/0 ·
      mixto 2/2/0/9. Full block at `gee-backend/artifacts/rag/router-eval-2026-08-24.md` (gitignored).

      **NO VERDICT IS ISSUED.** `evaluar_barra` returns `estado="barra_no_ratificada"` and `veredicto=None`;
      the proposed bar is printed NEXT TO the figures so the owner can fix it with the numbers in hand
      (decision 0.3 is still open). For the record and without dictating: the dangerous cell is empty, and
      held-out overall sits below the proposed 0.85 while the same-sample upper bound sits at it — which is
      exactly the gap D5's discipline exists to expose. The mechanism is not decorative: flipping
      `BarraRouter.ratificada` makes it decide, and that path is tested.)*

      *(**SUPERSEDED 2026-08-24 by decision 0.3's closure — a verdict IS issued now.** The bar was ratified
      (accuracy ≥ 0.70 · operational→legal = 0 · mixto→legal ≤ 2), `BarraRouter.ratificada` defaults to True,
      and `evaluar_barra` returns `estado="barra_evaluada"` with a real pass/fail plus the failing components
      by name. Against the figures above it PASSES. The paragraph before this one is left standing rather
      than rewritten because it is the record of what was true before the owner answered, and a decision log
      that edits its own history is a decision log nobody can audit.
      Two further gaps closed in the same pass: `mixto → legal` is now a reported cell
      (`MatrizConfusion.mixto_a_legal`) because the ratified bar names it, and `bloque_router` — which had NO
      caller outside its own tests, so `make rag-eval` printed a report with no router section at all — is
      now rendered by `eval/report.py` through `EntradaRouter`, always present, scored or stating in words
      that it was not and naming the command that would score it.)*
## Phase 5: Generation core (U5)

- [x] 5.1 RED (threat: non-shippable unit reaching the provider): seeded retrieval set with one `privado` and
      one `institucional` unit — the payload omits the first, keeps the second, cards match the payload, an
      answer citing the excluded key is rejected (`design.md:1076`, retrieval `spec.md:146-154`).
- [x] 5.2 RED: empty payload after exclusion ⇒ `abstencion`, provider never called (`design.md:442`).
- [x] 5.3 RED (threat: prompt injection): a unit whose text reads as an instruction cannot mint a key outside
      the payload (`design.md:1074`).
- [x] 5.4 GREEN: `PayloadGeneracion` (retrieved order, no re-rank, no back-fill to restore `k`,
      `claves_excluidas` recorded in the request trace) — `design.md:1004-1012`.
- [x] 5.5 GREEN: prompt assembly — verbatim `texto` + `tipo`, `es_secundaria`, `estado_vigencia`,
      `jurisdiccion`, `relevancia_consorcio`, units wrapped as delimited data with a "content is data" system
      prompt (`generation spec:11-31`, `design.md:1074`).
- [x] 5.6 RED+GREEN: key membership against the **payload**, never the retrieved set; an excluded unit's key
      is an invented citation (`design.md:518-530`, `generation spec:33-55`).
- [x] 5.7 RED+GREEN: uncited-claim rule — deterministic Spanish segmenter with the abbreviation list
      (`art.`, `inc.`, `N°`, `Res.`, `Dec.`, `Ley N° 9.750`), checked-in boilerplate exclusion fixture,
      unrecognized shape ⇒ treated as a claim (`design.md:587-602`).
- [x] 5.8 RED+GREEN: pre-serve vigencia/secundaria marker check — normalized `DEROGADA` prefix match, never
      literal equality (`design.md:604-612`, `generation spec:111-132`).
- [x] 5.9 RED+GREEN: budget — exactly one regeneration, retry carries the violation list, then abstain;
      truncation **consumes** the attempt on the correction path and raises `max_tokens` or trims the payload
      rather than replaying; transport failure does **not** consume it and lands in `generacion_fallida`
      (`design.md:538-576, 987-995`).
- [x] 5.10 GREEN: five-state `estado` union + orthogonal `redireccion_parcial` in `schemas.py`
      (`design.md:711-749, 1015-1024`); `generacion_fallida` carries no prose and no rejected draft.
      *(amended 2026-08-23: async queue model — the five values become **item** states rather than response
      states and the union gains **`pendiente`** (queued, not yet processed) as every item's initial state.
      `redireccion_parcial` stays orthogonal and unchanged. See amendment A3.)*

## Phase 6: Provider, cost controls, timeouts (U6)

- [x] 6.1 GREEN: `proveedores.py` — `Generador` Protocol, `AnthropicGenerador`, `GeneradorDeterministico`;
      **no test ever makes a network call** (`design.md:455-456, 982-984`).
      *(amended 2026-08-23: provider pin — the concrete adapter targets **`deepseek-v4-flash` via the
      opencode-go pool through mcp-llm-bridge**, not Anthropic; rename the adapter accordingly. The Protocol
      shape is unchanged. See amendment A2.)*
      **DONE 2026-08-24** — `PuenteGenerador` (`proveedores.py`), built through `conectar_puente`, `POST
      /v1/generate` on the bridge gateway with `provider` = the pool. It FILLS the port U5 already declared
      rather than redefining it: the `Generador` Protocol, `SalidaProveedor` and the three exceptions stay in
      `generacion.py` and are imported here, and `test_el_adaptador_satisface_el_puerto_generador_de_u5`
      asserts the `isinstance` against the U5 Protocol. `sintetico = False`, so `assert_generador_publicable`
      admits it — which is the whole difference from `GeneradorDeterministico`. Zero network in tests: every
      seam runs on `httpx.MockTransport`, which is why `conectar_puente` takes a `transporte` nothing in
      production passes. Failure translation is explicit and split by STATE: timeout/connection/5xx ⇒
      `GeneracionTransporte` (retriable), 401/403/429 ⇒ `GeneracionNoDisponible` (retrying a 429 is a retry
      storm against a provider that just said stop, and a 401 never fixes itself), `max_tokens`/`length` ⇒
      `SalidaProveedor(truncado=True)` (the call COMPLETED — an enforcement violation, not a failure). **One
      addition the design did not name:** an UNREADABLE stop reason refuses instead of defaulting to
      "complete". Reading it as complete would serve a cut-off legal answer as a whole one, which is the
      model-self-report shortcut G3 forbids everywhere else.
      *(bounded correction, 2026-08-24 — two changes to the failure table above.* **(a)** *Every refusal in
      `_leer` — non-JSON body, non-object body, no text under any alias, unreadable stop reason — is now
      `GeneracionNoDisponible` and no longer `GeneracionTransporte`. A 200 whose body this adapter cannot read
      is a CONTRACT MISMATCH, not an outage: as transport it was retried inside the transport budget, billed
      twice to receive the identical unreadable body, and then reported to the operator as a network fault
      pointing at a healthy socket. Only timeout / connection / 5xx remain transport, which is the honest
      boundary — those are the ones a second attempt can actually change.* **(b)** *`PuenteGenerador` gains
      `close()` and the context-manager protocol, and `conectar_puente` documents the lifetime: it OPENS an
      `httpx.Client`, the worker builds one adapter per queued ITEM (the item budget is per item), and an
      unclosed pool at that rate is a descriptor leak that surfaces as a worker which stops answering and
      blames the provider. Also pinned: every alias in `CAMPOS_TEXTO`/`CAMPOS_CORTE`/`CORTE_COMPLETO`/
      `CORTE_POR_LONGITUD` is exercised by name against hard-coded literals, so deleting or renaming one turns
      red — an interoperability claim nobody tests is a guess.)*
- [x] 6.2 GREEN: config knobs in `app/config.py` per `design.md:968`, all fail-CLOSED.
      *(amended 2026-08-23: the model pin is one of these knobs — changing the model must be a config edit,
      never a code edit. `conocimiento_semaforo_timeout_s` and `conocimiento_max_concurrency` are dropped from
      the serving path with the semaphore (async queue model); the remaining timeouts become worker-side.)*
      **DONE 2026-08-24** — `conocimiento_proveedor_url` / `conocimiento_modelo` (= `deepseek-v4-flash`) /
      `conocimiento_pool` (= `opencode-cli`) / `conocimiento_proveedor_api_key` (empty ⇒ the adapter refuses
      to be CONSTRUCTED, not to answer the first question), the two surviving timeouts, and the three cost
      numbers. `proveedores.py` writes no model name anywhere, so changing the pin is exactly an env change —
      `test_el_modelo_viaja_desde_config_y_no_desde_el_codigo` builds two adapters on two models over one code
      path. The dropped semaphore knobs are asserted ABSENT by
      `test_no_queda_semaforo_ni_su_timeout_en_el_dominio`: a knob that survives its own decision is a knob
      someone will set, expecting an effect that no longer exists.
- [x] 6.3 RED: per-user daily quota keyed on the **authenticated user id**, calendar day in
      `America/Argentina/Cordoba`, Redis key `quota:conocimiento:{user_id}:{YYYY-MM-DD}` with TTL to local
      midnight — not `request.client.host` (`design.md:472-488`).
      **DONE 2026-08-24** — `costos.CuotaDiaria` over the narrow `AlmacenDeContadores` port ("add to a keyed
      number that expires"), with `AlmacenEnMemoria` as the test double. Key shape, per-user isolation, the
      TTL landing on Cordoba midnight (not 24 h later) and the day rollover are each their own test.
      `segundos_a_medianoche` is tested against the three-hour window every day in which `utcnow().date()`
      names the wrong day here.
- [x] 6.4 RED: spend accounting increments **per attempt** (worst case 4 calls ≈ USD 0.12–0.20), ceiling
      exceeded ⇒ `no_disponible`, never a cheaper or uncited answer (`design.md:666-673`).
      *(amended 2026-08-23: the per-attempt accounting rule is unchanged, but the USD figures are stale —
      they were derived from Claude-class list pricing and must be re-derived against the `deepseek-v4-flash`
      pin before `conocimiento_spend_ceiling_usd` is set. Ceiling exceeded now fails the queued ITEM, not an
      HTTP request.)*
      **DONE 2026-08-24, MECHANISM ONLY — the numbers stay unset.** `costos.MedidorDeGasto` charges BEFORE the
      attempt is issued, so a call that times out is still billed, as the provider bills it
      (`test_un_intento_que_falla_en_transporte_igual_se_cobro`). Refusal is `TechoDeGasto`, a
      `GeneracionNoDisponible` subclass carrying `causa`, and with the ceiling reached **no request leaves at
      all**. **Correction against the design's wording:** the ceiling refuses when this attempt WOULD cross it,
      not when it has ALREADY been crossed. "Already over" always overshoots by one attempt and lets a ceiling
      below one attempt's cost authorise an unbounded first call — a USD 0.05 ceiling quietly permitting a USD
      0.10 spend, once per window. Per A6 the three USD/quota numbers remain **unset, and unset REFUSES**
      (`CuotaNoConfigurada` / `TechoNoConfigurado`), including a per-attempt cost of 0, which would otherwise
      be a ceiling deleted while still looking configured.
      *(bounded correction, 2026-08-24 — two more ways this ceiling was quietly not a ceiling.* **(a)**
      *`conocimiento_spend_window_h` was read as `max(1, ventana_h)`, which repaired a misconfigured window
      toward the PERMISSIVE side: 0 or a negative value became a one-hour window, so a ceiling meant to hold
      over a day started resetting every hour and the deployment could spend it 24 times a day with nothing
      anywhere saying so. It now refuses with its own cause, `VentanaNoConfigurada`, on BOTH the spend and the
      read path — a meter that refuses to charge but reports USD 0.00 when asked is a diagnostic that lies to
      the operator chasing the refusal.* **(b)** *`TechoNoConfigurado` named both knobs whether or not both
      were unset; it now names which one and its value, because "both are unset" sends an operator to check a
      knob that was fine.)*
- [x] 6.5 RED: the three timeouts — provider attempt, 60 s hard request deadline aborting mid-attempt to
      `generacion_fallida`, 5 s semaphore acquire ⇒ `no_disponible` (`design.md:619-664`).
      *(amended 2026-08-23: async queue model — the provider-attempt timeout and the (renamed) per-item
      deadline become **worker-side** budgets bounding the processing of one queued item; there is no HTTP
      request to abort. The semaphore timeout is DROPPED: saturation is queue depth, not a refusal at the
      door. See amendment A3.)*
      **DONE 2026-08-24 — two timeouts, not three.** `conocimiento_provider_timeout_s` (20 s) bounds one
      attempt; `PresupuestoDeItem` (`conocimiento_item_deadline_s`, 60 s) bounds one queued item on a
      MONOTONIC clock, since it measures elapsed processing and no socket is waiting. `timeout_efectivo()` is
      the smaller of the two, or the item budget would be decorative — an attempt would run past it and the
      overrun would only be noticed afterwards. Expiry raises `PresupuestoAgotado`, which is deliberately
      neither `GeneracionTransporte` (a deadline the transport budget may retry past is a suggestion) nor
      `GeneracionNoDisponible` (the box was available; the item just did not finish, and "not available" would
      send an operator to inspect a healthy dependency). The semaphore timeout is not implemented, per A3.
      *(bounded correction, 2026-08-24 — the terminal state that docstring promises was not delivered by
      anything. `PresupuestoAgotado` was raised inside `PuenteGenerador.generar`, caught by neither the
      transport budget nor `generar_respuesta`, and escaped the one function that owns every terminal state:
      a spent item budget crashed the worker instead of failing the item. It now lives in `generacion.py`
      next to the other two generation exceptions — the state machine has to catch it and cannot import
      `proveedores.py` without a cycle, which is exactly why it escaped — is re-exported from `proveedores.py`
      next to the budget that raises it, and `generar_respuesta` ends it in `generacion_fallida` with motive
      `presupuesto_item_agotado: …`, without retrying past it.)*
- [x] 6.6 GREEN: no server-side answer cache; document the reason inline (`design.md:499-514`).
      **DONE 2026-08-24** — recorded as a block comment in `proveedores.py`, at the one place a cache would
      plausibly be added, because a decision recorded only in a design document is a decision the next reader
      of that file will not find. `test_dos_preguntas_identicas_son_dos_llamadas_al_proveedor` holds it
      mechanically instead of leaving it to the comment.
- [ ] 6.7 **BLOCKING pre-enablement, no code (added 2026-08-23, decision 0.4):** verify (a) the **exact model
      id** `deepseek-v4-flash` as the opencode-go pool actually exposes it, and (b) the provider's **published
      no-training-on-input and retention terms**; record both next to the pin (`design.md:493-497`). **If the
      terms cannot be verified, the flag is NOT enabled** — fail-closed, not a warning.
      **MECHANISM LANDED 2026-08-24; THE VERIFICATION IS THE OWNER'S AND IS STILL PENDING — the task stays
      OPEN, which is the honest state.** What exists in code: the checked-in record
      `app/domains/conocimiento/proveedor_terminos.yaml`, next to the pin so a silent terms change is a diff
      rather than a discovery, and `verificar_terminos`, which refuses when the record is absent, marked
      unverified, about another model, about another POOL (the same model id behind a different operator is
      different terms and different retention), missing no-training, carrying an unbounded `retencion_dias`,
      or missing any of its four evidence fields — a record nobody can audit is a claim, not a verification.
      The record ships `verificado: false`, so **the gate refuses today** and
      `test_el_registro_que_esta_hoy_en_el_repo_no_habilita_el_flag` holds that. The owner's procedure is
      `docs/rag/proveedor-terminos.md`; performing it flips the record AND that test, in one commit, with the
      evidence in it. A machine cannot read published terms — it can only refuse to pretend they were read.
      *(bounded correction, 2026-08-24.* **(a)** *THE GATE HAD NO CONSUMER — `verificar_terminos` was called by
      tests and by nothing on the serving path, so the whole mechanism was inert and flipping
      `conocimiento_qa_enabled` would have served questions against a record marked `verificado: false`. The
      consumer is now specified as the first ANDed fact of task 7.2's flag dependency; until 7.2 lands, this
      gate still guards nothing, which is the honest state and the reason both tasks stay OPEN.* **(b)**
      *"bounded retention" was satisfied by any non-negative integer, so `retencion_dias: 36500` passed. It now
      has a configurable ceiling, `RETENCION_MAX_DIAS = 365 * 3`, documented in the YAML: a hundred-year window
      is indefinite retention written in days. `0` remains legitimate and is the best answer — the provider
      publishing that it retains nothing.* **(c)** *the evidence check is pinned against the shape the real
      YAML SHIPS: every key PRESENT with an explicit `null`. The prior tests only ever deleted keys, so a gate
      written as `campo in registro` would have passed all of them and admitted the checked-in record — the one
      input this gate exists to refuse.)*
      **THE CONSUMER LANDED 2026-08-24 (task 7.2).** `verificar_terminos` is now the FIRST ANDed fact of
      `enforce_conocimiento_qa_enabled`, so the gate guards the serving path rather than only the tests, and
      `test_el_registro_QUE_ESTA_HOY_EN_EL_REPO_no_habilita_la_superficie` proves end to end that flipping
      `conocimiento_qa_enabled=true` still refuses while the record ships `verificado: false`. **This task
      nonetheless stays OPEN**, and that is the honest state: what was missing in U6 was the caller, and what
      is still missing is the OWNER READING THE PUBLISHED TERMS. A machine cannot do that; it can only refuse
      to pretend it was done. The procedure is `docs/rag/proveedor-terminos.md`.

## Phase 7: HTTP surface (U7)

- [x] 7.1 GREEN: `domains/conocimiento/router.py` mounted at `/api/v2/conocimiento`, dependency order
      `enforce_qa_enabled → require_admin → enforce_body_limit → enforce_qa_rate_limit → enforce_qa_quota →
      in-flight slot`; own limiter on `ratelimit:conocimiento:` (`design.md:699-709`).
      *(amended 2026-08-23: async queue model — `POST /preguntas` **enqueues** and returns an item id plus the
      initial `pendiente` state; it never carries an answer. Add a status surface for one item and a listing
      surface for the requester's items. The dependency order is unchanged **minus the in-flight slot**, which
      the queue replaces. See amendment A3.)*
      **DONE 2026-08-24.** Three routes: `POST /preguntas` → 202 `{id, estado: "pendiente", creada_en}`,
      `GET /preguntas/{id}` and `GET /preguntas` (the requester's bandeja). The queue itself is
      `conocimiento_007_buzon_consultas` + `buzon.py`. Four decisions worth naming:
      **(a) THE CLAIM HAS NO `en_proceso` STATE.** `reclamar_pendiente` takes the oldest `pendiente` with
      `FOR UPDATE SKIP LOCKED` and returns it STILL `pendiente`; the row lock lives for the worker's
      transaction. The `geo_jobs` pattern (commit `PENDING → RUNNING`, then process) has a real orphan window
      — a worker killed after the claim commit leaves a `RUNNING` nothing finishes, which is why
      `geo/reconciliation.py` exists — and this design does not inherit it: an aborted transaction releases
      the lock and the item is in the state it never left. No reaper was invented because nothing is orphaned,
      and no seventh state was added to a union the design fixed at six. The cost is stated in the module
      docstring: the item's transaction stays open for its processing (bounded by
      `conocimiento_item_deadline_s`), holding one connection and one row lock.
      **(b) THE STATE IS A COLUMN AND A PAYLOAD, and both ends are closed.** Three DB CHECKs (`estado` in the
      six; `pendiente` iff no payload; `pendiente` iff no `procesada_en`) plus `persistir_resultado` refusing
      a payload whose `estado` disagrees with the column, refusing to write `pendiente` as a RESULT, and
      refusing to overwrite an already-terminal item.
      **(c) RETENTION FOLLOWED THE TEXT.** `rag_consulta` stores the verbatim question exactly like
      `rag_decision_ruta`, so `repository.purgar_consultas` executes the same ratified 90-day window. Without
      it U7 would have repealed `conocimiento_006`'s retention by copying the text into a second table nobody
      purges. Keyed on SUBMISSION age, so an item nobody ever processed is not exempt.
      **(d) 404 AND NOT 403** for another admin's item: a 403 confirms the id exists, and the row holds the
      verbatim question a specific person asked.
      *(deviation from the sealed body, recorded rather than slid in: `RespuestaConocimiento` had NO field
      for the pure redirect's surface. `design.md:775-777` says `estado='redireccion'` carries no answer, no
      citation and no `redireccion_parcial` because "the redirect IS the response" — and the round-1 schema
      gave it nowhere to say WHERE, so the state was constructible but empty. U7 adds `redireccion:
      Redireccion | None`, present iff `estado='redireccion'` and mutually exclusive with the orthogonal
      `redireccion_parcial`.)*
      *(bounded corrections, 2026-08-24, from the U7 verify:*
      *(e) **the two READ routes no longer take the enablement AND** — only the kill switch and
      `require_admin`. Reading an answer already in the database needs no embedder, no credential and no
      verified terms: nothing leaves the box and nothing is computed. Gating them on the AND made the bandeja
      and the `demorado` badge that explains the silence disappear at exactly the moment something was wrong.
      `POST /preguntas` keeps the full AND, because submitting is what spends a quota slot and sends the
      question out. `/estado` was already exempt for the same reason.*
      *(f) **`limite` is validated** — `Query(ge=1, le=200)`. It reaches `LIMIT` directly, and a negative one
      was a `ProgrammingError` rendered as a 500: a broken-deployment report for a caller's typo.*
      *(g) **the item deadline now bounds the TRANSACTION, not only the Python budget.** (a) above claimed the
      open transaction was "bounded by `conocimiento_item_deadline_s`" and nothing enforced it: a hung
      reranker or provider held the claimed row's lock for as long as the process lived. `reclamar_pendiente`
      now sets a transaction-local `statement_timeout` from that deadline in the same transaction it takes the
      lock in (the `ficha_statement_timeout_ms` precedent, `design.md:647`), so Postgres cancels, the
      transaction aborts and the item is `pendiente` again — coherent with a claim that never wrote an
      intermediate state. The docstring now states the honest limit too: `statement_timeout` bounds each
      STATEMENT, so a hang in pure Python between queries is `PresupuestoDeItem`'s to bound, not this.)*
- [x] 7.2 GREEN: `conocimiento_qa_enabled: bool = False` + `enforce_conocimiento_qa_enabled` as the FIRST
      dependency, ANDed with **(0) the provider TERMS GATE**, (1) credential presence and (2) sidecar `/ready`
      (cached probe) — `design.md:678-698`.
      *(amended 2026-08-24, closing the U6 habilitation gap. The terms gate is the FIRST of the ANDed facts and
      is written literally as:*

      ```python
      verificar_terminos(
          cargar_terminos(),
          modelo=settings.conocimiento_modelo,
          pool=settings.conocimiento_pool,
      )   # raises TerminosNoVerificados ⇒ 503 base_de_conocimiento_no_lista,
          # cause `terminos_no_verificados`
      ```

      *Why this line and not a checklist item: U6 landed the whole mechanism — the checked-in record, the
      six refusals, `test_el_registro_que_esta_hoy_en_el_repo_no_habilita_el_flag` — and gave it **no
      consumer**. `verificar_terminos` is called by tests and by nothing on the serving path, so with the flag
      flipped to `true` the surface would answer questions with the record still marked `verificado: false`.
      A6/A2 say "if those terms cannot be verified, the flag is NOT enabled"; without this dependency the
      only thing enforcing that is somebody remembering. The refusal is a 503 and NOT a 500: an unverified
      record is a deployment that is not ready, the same class as the sidecar being down. It is checked
      per-request against the loaded record rather than once at import, so flipping the record is a deploy and
      never a code change — the same reason the pin lives in config. This dependency is the ONLY thing between
      `conocimiento_qa_enabled=true` and the public law text plus the CD member's question leaving the box.)*
      **DONE 2026-08-24 — the terms gate now has its consumer, written exactly as the amendment specifies.**
      `enforce_conocimiento_qa_enabled` checks, in this order: the flag; `verificar_terminos(cargar_terminos(),
      modelo=…, pool=…)` ⇒ 503 cause `terminos_no_verificados`; the credential ⇒ cause `credencial_ausente`;
      the cached `/ready` probe ⇒ cause `embedder_no_listo`. All three are 503 and never 500, all three are
      evaluated per request against loaded state, and the order is asserted: with all three false the cause
      reported is the TERMS one, and the sidecar is not even probed. The end-to-end proof that the mechanism
      is no longer inert is `test_el_registro_QUE_ESTA_HOY_EN_EL_REPO_no_habilita_la_superficie`: with the
      flag flipped to `true` and a credential present, the surface still refuses, because the checked-in
      record ships `verificado: false`. Mutation-checked: removing any one of the three facts fails the suite.
      The `/ready` probe caches its REFUSAL as well as its success (short TTL), so a dead sidecar is not
      probed once per request.
      *(bounded correction found while wiring this: `conectar_sidecar` leaked its `httpx.Client` on every
      FAILURE path. Harmless when it was called once at startup; with a readiness gate calling it once per TTL
      it leaks a pool every few seconds for as long as the sidecar is down — the exact condition under which
      the box can least afford to run out of descriptors. It now closes on the way out, and `SidecarEmbedder`
      gained the `close()`/context-manager pair `PuenteGenerador` already had.)*
      *(bounded corrections, 2026-08-24, from the U7 verify:*
      *(h) **the WORKER verifies the terms too**, and it is the one that matters: the worker is who actually
      transmits. Verifying at ENQUEUE says nothing about the moment of transmission — a record flipped to
      `verificado: false` after a hundred items were queued would have been discovered by nobody and all
      hundred would have been sent. `procesar_uno` now checks it in its pre-claim guard and
      `scripts/rag_worker.py` checks it again at startup. A flipped record STOPS THE WORKER and leaves the
      items `pendiente`: a policy the owner revoked is not those questions' fault, and `generacion_fallida`
      would blame them for it. Uncached — one small YAML read per poll, against a B50 retrieval and a hosted
      generation.*
      *(i) **the pre-claim guard also refuses an unbuildable provider**, beside the synthetic ranker.
      `ProveedorMalConfigurado` is raised at construction; discovered where the adapter was previously built —
      after routing and after a full B50 retrieval — every item in the queue would burn that work before
      hitting the same wall.*
      *(j) **a malformed `conocimiento_embed_url` is a named cause, not a 500.** Most bad values already
      landed as `embedder_inalcanzable`; two families did not, because they are not `httpx.HTTPError` — an
      unclosed IPv6 bracket raises inside `httpx.Client(...)` itself and an invalid IDNA host raises
      `UnicodeError` at request time. Both were a 500 on a readiness gate, sending the operator to look for a
      dead container instead of at the env var they mistyped. Caught by NAME, so a real bug still surfaces as
      a bug.)*
- [x] 7.3 GREEN: extend that first dependency with **reranker availability** (GPU/hosted endpoint) ⇒ 503
      `base_de_conocimiento_no_lista` cause `reranker_no_disponible`. Fail-closed only: the design authorizes
      no CPU fallback and no smaller model (`design.md:1132-1134`, decision 0.5).
      *(amended 2026-08-23: async queue model — the per-question `503 reranker_no_disponible` is REPLACED by
      the queue state. A GPU worker that is not currently up is the normal case, not an outage: items stay
      `pendiente`. Fail-closed still holds — no CPU fallback, no smaller model — and a permanently
      misconfigured worker surfaces on the diagnostic endpoint (7.6), not per question. Add the staleness
      obligation: when the worker has not run for longer than a configured window, say so instead of showing
      an indefinite `pendiente`.)*
      **DONE 2026-08-24 — as the amendment rescoped it, NOT as the body wrote it.** There is no per-question
      `503 reranker_no_disponible` and there must not be one: an intermittently-available GPU is the normal
      case under A3 and items simply stay `pendiente`. Fail-closed still holds in two places —
      `trabajador.procesar_uno` takes the reranker as a REQUIRED argument (a caller that cannot build one
      processes no items, which is the queue absorbing the GPU's absence) and refuses a `sintetico` ranker
      outright, BEFORE claiming an item, so a wiring fault is never recorded as "your question could not be
      answered". The staleness obligation is `buzon.esta_demorado` (strictly older than
      `conocimiento_worker_stale_after_s`; a terminal item is never "delayed"; an unset window disables the
      message rather than marking everything stuck), surfaced as `demorado` on each item and `worker_demorado`
      on the diagnostic. No heartbeat table: a `pendiente` older than the window IS a worker that has not
      picked it up, and a heartbeat would report a healthy worker while a poison item sat unclaimed.
- [x] 7.4 **Same work unit**: delete `tests/new/conocimiento/test_rag_no_router.py` AND add
      `test_qa_surface.py` with 401 anonymous / 403 `operador` + `ciudadano` / 503 flag-off-for-admin. The unit
      is not mergeable with the delete alone (`design.md:1057-1060`, retrieval `spec.md:8`).
      **DONE 2026-08-24 — deleted and replaced in the same commit.** `test_qa_surface.py` carries the three
      the task names plus the enablement-AND block, the mailbox block and the diagnostic block. Two additions
      beyond the letter: the limiter is asserted to key on `user:{id}` and never on the client IP (behind a
      proxy the IP collapses every admin into one bucket), and the unset quota is asserted to REFUSE rather
      than admit — `conocimiento_quota_diaria_usuario` is still blocked on the A6 cost re-derivation, so the
      surface refuses today with cause `CuotaNoConfigurada` even when everything else is green.
      *(suite-level interaction found and closed here: `DistributedRateLimitMiddleware` is a PROCESS
      singleton with a 100-request window keyed on the client IP, every TestClient in `tests/new/` shares
      that IP, and its in-memory fallback window does not reset between modules. This file's ~50 requests
      spent enough of that shared budget to fail ten unrelated `test_geo_public_route_caps` /
      `test_gee_public_contract` tests that ran after it — a failure with no relationship to the code that
      caused it. The module now stands the deployment-wide limiter down for itself and asserts the
      conocimiento route's OWN limiter directly instead.)*
      *(bounded corrections, 2026-08-24, from the U7 verify:*
      *(m) **`mixto` is now covered end to end** — submit → queue → worker → read, for BOTH routing spec
      scenarios: the legal leg answered with the redirect still present (#6) and the legal leg abstaining with
      the redirect still present (#7). The `parcial` variable in `procesar_uno` was set on every branch and
      asserted on none, so `parcial = None` was a live mutant and the spec's "MUST NOT drop the redirect
      because a legal answer was produced" had no test. Dropping it has no symptom on the page: the answer
      looks complete and the operational half of the question vanishes. The `mixto` class is produced by
      GEOMETRY — centroids equidistant from the query vector, margin exactly 0, inside `banda` and above
      `piso` — not by patching the classifier.*
      *(n) `GET /preguntas/{id}` gained its own 401/403 tests. It was the only route in the family without
      them, and the only one whose response body is a specific person's verbatim question rather than a list
      of the caller's own.)*
- [x] 7.5 RED (threat: question text leaving the box): the routing record round-trips the verbatim question
      AND the question appears in exactly **one** outbound payload — the generation call; embed and routing
      paths asserted local (`design.md:1075`, retrieval `spec.md:156-161`).
      *(amended 2026-08-23: async queue model — the assertion now spans submit→queue→worker: the queued item's
      stored question must not reach any outbound payload except the worker's single generation call.)*
      **DONE 2026-08-24, spanning submit→queue→worker as amended.** Two assertions.
      (1) `rag_decision_ruta` round-trips the verbatim question, read back with raw SQL — a digest would
      satisfy none of the scenario the record exists for.
      (2) The queued item is processed with the provider adapter behind an `httpx.MockTransport` that records
      every outbound request body: EXACTLY ONE call leaves the box and EXACTLY ONE payload contains the
      question. Routing and the embedder are local by construction (the sidecar is a container on the
      deployment's own network, the cross-encoder is the owner's GPU), so the only boundary-crossing seam is
      the generation call, and it is instrumented at the transport rather than at a wrapper that could be
      bypassed.
- [x] 7.6 GREEN: diagnostic `GET /api/v2/conocimiento/estado` (admin); serving refuses outright when
      `sintetico` is true (`design.md:751-752`).
      *(amended 2026-08-23: async queue model — this endpoint also reports **queue depth, oldest pending item
      and last successful worker run**; it is where a permanently-down worker becomes visible, since it is no
      longer a per-question 503.)*
      **DONE 2026-08-24.** Reports snapshot provenance (including `embedding_sintetico`), the three ANDed
      enablement facts with the cause of the first false one, and the queue block: depth, oldest pending,
      last successful worker run (derived from `max(procesada_en)`, not from a heartbeat that can report a
      healthy worker while every item it touches fails) and `worker_demorado`.
      *(one deliberate departure from the dependency chain, and the reason: `/estado` takes the FLAG and
      `require_admin` but NOT the three availability facts — it REPORTS them. An endpoint that 503s whenever
      the sidecar is down would be unreachable during exactly the outage it exists to describe, and A3 moved
      the "worker is down" fault off the per-question path and onto this endpoint specifically. It is still
      inert on a deployment that never turned the surface on.)*
      Serving's own refusal is separate and is in the WORKER, where retrieval happens: `_recuperar` raises
      `service.CorpusNoServible` on a snapshot with synthetic embeddings and the item ends `no_disponible`,
      rather than answering a legal question from vectors nobody trained.
      *(bounded corrections, 2026-08-24, from the U7 verify:*
      *(k) **`causa_no_listo` now follows the GATE's order** — terms → credential → embedder. It reported them
      terms → embedder → credential, so with all three false the diagnostic named the SIDECAR while the 503
      the operator was actually receiving named the TERMS record: two answers to "what is wrong" that sent
      them to different places. All three booleans are still reported; only which one the single `causa` line
      quotes changed.*
      *(l) **the queue-wide `worker_demorado` reuses `buzon.esta_demorado`'s arithmetic** (extracted as
      `espera_excedida`) instead of recomputing it. They were two copies of one comparison, and drift between
      them is silent: the banner and the per-item badge would disagree about the same worker.)*

- [x] 7.7 GREEN — **the mailbox's postman** *(added 2026-08-24; closes the CRITICAL the U7 verify raised:
      `procesar_uno` shipped with NO caller — no loop, no CLI, no scheduled task — so `POST /preguntas` wrote
      `pendiente` rows nothing would ever pick up and `GET /estado` would have reported a permanently delayed
      worker forever)*: `gee-backend/scripts/rag_worker.py`, the runner process.
      **DONE 2026-08-24.** Thin entry point on the house precedent (`scripts/rag_ingest.py`): every processing
      rule stays in `trabajador.py`. It builds the real dependencies once — the sidecar embedder, the CUDA
      cross-encoder, the router's centroids and thresholds fitted at boot on the RATIFIED labeled set with the
      CURRENT embedder, and a per-item generator factory — then polls, opening ONE transaction per item and
      committing per item.
      *(Shutdown is trivial and that is a property of the claim, not of the loop: `reclamar_pendiente` never
      commits an intermediate state, so a SIGTERM mid-item abandons the transaction, Postgres releases the
      lock and the item is still `pendiente` — the state it never left. Aborting costs the work spent on that
      one item and loses nothing else, so the handler only sets a flag and there is no drain phase to get
      wrong. The flag is a `threading.Event` so the empty-queue sleep wakes on it instead of taking up to a
      full `conocimiento_worker_poll_s` to notice.)*
      *(Deployment refusals — unverified terms, an unbuildable provider, a missing or synthetic reranker — are
      logged with their cause and the loop keeps polling: the ITEMS stay `pendiente` and are not failed,
      because a revoked policy or a missing credential is not those questions' fault. An unnamed exception
      propagates instead, since a loop that swallows bugs is a worker that reports itself alive while
      processing nothing.)*
      New knob: `conocimiento_worker_poll_s` (5.0). Exit codes: 0 clean stop on a signal · 1 refused to start
      · 2 usage, including "this interpreter has no torch" (`venv-rag`, D8 — no CPU rerank fallback exists).
      Tests: `tests/new/conocimiento/test_rag_worker.py`, every seam faked and no wall-clock sleeping.
      **Deployment is 10.2's, not this task's**: the `conocimiento-embed` compose block lives in the box's
      EXTERNAL compose file, and this worker needs its own service beside it (the `venv-rag` image, the GPU
      device reservation, `restart: unless-stopped`, and the same `.env`). U10 records that block verbatim
      along with the sidecar's; until it does, the worker is started by hand and `GET /estado` is how anyone
      finds out it is not running.

## Phase 8: `consorcio-web` page (U8)

- [x] 8.1 GREEN: child route `/admin/conocimiento` under `adminLayoutRoute`
      (`src/routeTree.gen.tsx:590-595`) + `ProtectedRoute allowedRoles={['admin']}`.
- [x] 8.2 GREEN: `src/lib/api/conocimiento.ts` + `src/hooks/useConocimientoQA.ts` (TanStack Query, finite
      `staleTime` ≈ 5 min, **no** `localStorage`/`IndexedDB` persistence) — `design.md:506-510`.
      *(amended 2026-08-23: async queue model — the client submits and then polls the item-status/listing
      surfaces rather than awaiting an answer from the submit call. The no-persistence rule is unchanged.)*
- [x] 8.3 GREEN: `components/admin/ConocimientoPanel.tsx` — five states + `redireccion_parcial`; citation
      cards with vigencia badge, secundaria chip, verbatim `relevancia_consorcio` banner, verbatim `texto`,
      `fuente_url` link; no paraphrase (`design.md:754-775`).
      *(amended 2026-08-23: async queue model — the page is a **bandeja (mailbox)**: a list of the user's
      questions with question text, state and the answer when it exists. It renders `pendiente` honestly
      (including the staleness message from 7.3) alongside the five terminal states. Citation-card rules are
      unchanged.)*
- [x] 8.4 RED: the panel cannot render a card for an excluded unit — the serialized list is already filtered
      server-side to payload keys (`design.md:765-768`).
- [x] 8.5 Fix-forward on the U8 verify findings *(2026-08-24; six warnings + one suggestion, no new surface)*:
      **W1** the vigencia badge's colour polarity was inverted — `!VIGENTE ⇒ red` painted `EN REVISIÓN` and
      `SIN DATOS` with the same red as `DEROGADA`, which is the panel asserting a repeal the corpus never
      stated. Now `DEROGADA*` ⇒ red, `VIGENTE*` ⇒ teal, everything else NEUTRAL, via the exported pure
      `colorDeVigencia`; the badge TEXT stays verbatim and the file's "never re-derives" claim is now true of
      the colour too. **W2** an `estado` outside `PRESENTACION_ESTADO` threw a `TypeError` with no error
      boundary above the list, so one unrecognized item blanked the whole bandeja; `presentacionDeEstado`
      degrades to `Estado no reconocido: <valor>` verbatim. **W3** `lib/api/conocimiento.ts` justified
      bypassing `apiFetch`'s one-shot 401 refresh with a panel-side session-expired state that did not
      exist — `SesionExpirada` now renders it with a link to `/login`. **W4** the poll's stop list covers only
      401/403/429/503, so a 500, a proxy HTML page or a network `TypeError` re-fetched every 15 s forever;
      `intervaloDeSondeo` stays pure and folds `fetchFailureCount` into a capped 15 s → 30 s → 60 s ladder
      that TanStack resets on success. **W5** the composer cleared synchronously on submit, destroying up to
      2000 characters on a 429/422 — it now clears in `onSuccess` only. **W6** `retry_after` was parsed into
      `extra` and never shown; the 429 (whose envelope carries no `detalle`) now reads "Límite de consultas
      alcanzado. Probá de nuevo en ~N s.". **S1** `CAUSA_LEGIBLE` covered only the three enablement facts, so
      the kill switch — the likeliest 503 on a fresh deployment — surfaced as the raw `conocimiento_qa_enabled`
      setting name, and the ceiling refusals arrived as Python class names (`type(exc).__name__`); all are
      mapped, and an unmapped cause is framed as an identifier rather than dropped.

## Phase 9: Eval extension (U9)

- [x] 9.1 GREEN: `eval/answers.py` + `answer_set.yaml` — invented-citation and uncited-claim scored against
      the **post-exclusion payload**, via the same `assert_unidades_publicas` call the request path uses
      (`design.md:787-794`, `generation spec:134-138`).
- [x] 9.2 GREEN: owner-graded citation faithfulness on n ≥ 30 **answers** *(RATIFIED 2026-08-23, decision
      0.6 — no longer a proposal)*, publishing `n_respuestas`,
      `n_afirmaciones` and the per-answer claim distribution; intra-rater re-grade on max(10%, 15 claims),
      below 15 ⇒ `not-evaluable` (`design.md:819-837`).
- [x] 9.3 GREEN: graded artifacts pinned to `(prompt_version, provider_model_pin, corpus_sha)`; refuse on
      divergence naming both operands, per `harness.py:254-269` (`design.md:839-845`).
- [x] 9.4 GREEN: **end-to-end (post-exclusion) abstention** as its own row next to the retrieval-level LOOCV
      pair, pinned to `(corpus_sha, expected_clasificacion_sha256)`; a reclassification re-triggers the
      measurement even with `corpus_sha` unmoved (`design.md:796-812`).
- [x] 9.1b GREEN — **publish the `bm25_ce` arm beside the FTS-only baselines** *(added 2026-08-23; owns the
      requirement the amended V1 serving gate created and no task delivered)*. The amended gate in
      `specs/knowledge-hybrid-retrieval/spec.md` requires the report to publish the `bm25_ce` arm side by
      side with the recorded FTS-only baselines "so the margin is visible rather than asserted" — and the
      harness cannot produce that arm today: `correr_modo` takes no `reranker` and passes none to
      `service.recuperar`, so a `bm25_ce` run raises `RerankerRequerido`; `LEGS_POR_MODO` has no `bm25_ce`
      entry, so its coverage block would report the fused legs of a mode that runs neither. Deliver: thread a
      `reranker` through `correr_modo`/`evaluar` and the `rag_eval.py` CLI, add the `bm25_ce` entry to
      `LEGS_POR_MODO` (its one candidate leg is BM25, not `fts`), and score the arm in the same document as
      the baselines. U2 already carries what this depends on: `ResultadoModo.ranker_modelo` /
      `ranker_sintetico` and `report._gate_sintetico`'s synthetic-ranker refusal, so an arm ranked by a
      stand-in publishes as a SMOKE RUN and never as a margin. The abstention row stays `not-evaluable`
      under 9.5 until decision 0.1 closes — publishing the retrieval margin does not require it.
- [ ] 9.5 **BLOCKED by decision 0.1** — encode whichever abstention bar the owner ratifies into
      `eval/umbral_abstencion.yaml` and the go/no-go block. Until then the row prints `not-evaluable` and the
      flag stays off. Do not pick a bar in code.
      *(U9 apply, 2026-08-24: left OPEN deliberately, and the surrounding machinery was built so it
      stays honest while it is. `eval/umbral_abstencion.yaml` ships `estado: no_derivado` with `umbral:
      null` and the measured reason (`0.489` precision at recall `1.000` for the reranker-confidence
      candidate); `derivar_desde` REFUSES to produce a threshold for a mode with no ratified signal;
      `harness.MODOS_SIN_SENAL_RATIFICADA` makes the `bm25_ce` abstention pair print `not-evaluable`
      rather than `NO-GO`, so the arm's retrieval margin publishes without the open decision reading as
      a retrieval failure. No bar was picked in code.)*
- [x] 9.6 GREEN: `eval/umbral_abstencion.yaml` header `(corpus_sha, embedding_modelo, embedding_revision_hf,
      n, metodologia)`; serving reads it and refuses with `base_de_conocimiento_no_lista` on mismatch
      (`design.md:852-859`).
- [x] 9.6b GREEN — **SLM candidate bench** *(owner-requested 2026-08-23)*: the graded n ≥ 30 answer
      set of 9.2 is run against BOTH the pinned provider model (`deepseek-v4-flash`, reference) AND one
      embedded SLM candidate (`Qwen3-8B-Instruct` quantized Q5, served on the owner's RTX worker —
      the async-queue model already absorbs its latency). Same prompt, same payloads, same graders,
      one comparison table: citation-precision, invented-citation rate, uncited-claim rate,
      groundedness, abstention behaviour, tokens/s. Artifact `eval/slm_bench.yaml` pinned to
      `(prompt_version, both model pins, corpus_sha)`. **Decision rule (owner-stated)**: if the SLM
      clears the same bars as the reference, the provider pin MAY move to the embedded SLM (killing
      task 6.7's terms-verification dependency and the external-provider surface entirely); then and
      only then a SMALLER rung is benched (≤2B, e.g. `Qwen3-1.7B`) on the same artifact, and only if
      THAT holds does a fine-tuned ≤1B become a project (distillation from the corpus — separate
      change, not this one). The ladder never skips a rung, and every rung is decided by this same
      graded artifact, never by vibes. Note the safety floor that makes small models viable AT ALL
      here: citation enforcement (U5) validates every citation against the payload post-hoc, so a
      weaker generator degrades into more rejections/abstentions — visible failures — never into
      silently confident fabrication.
- [x] 9.7 GREEN: mutation targets per `openspec/config.yaml` — `routing.py`, `generacion.py`,
      `eval/answers.py`, plus `recuperacion/bm25.py`; keep the module thresholds the repo already enforces.
- [x] 9.8 Fix-forward on the U9 verify findings *(2026-08-24; two CRITICALs, two warnings, two
      suggestions, no new surface)*: **C1** the whole `NO EVALUABLE` machinery of the `bm25_ce` arm was
      unguarded — three separate mutations survived the suite, and each turned owner decision 0.1
      (OPEN) into a published verdict about the retriever: dropping `or barras_no_evaluables` makes the
      verdict read `NO-GO` (measured and fell short — it was not), dropping `and not no_evaluable`
      lists the two unmeasured bars under "fallan:", and `no_evaluable=False` does both plus prints a
      denominator for a measurement that never happened. `test_eval_no_evaluable_guard.py` pins the
      four properties the verify prescribed — the pair renders `valor=None` / `n = —` /
      `not-evaluable`, the verdict is `NO EVALUABLE` and never `NO-GO`, a retrieval bar that REALLY
      fell short still appears in `barras_fallidas` (the guard is not a place failures hide), and the
      six re-ratified bars are still scored in this mode (spec:131). All three mutants RED, revert
      green. **W2** `answers._veredicto` scored its table off `barra.pasa` alone, so a three-answer set
      — below the ratified minimum, `not-evaluable` on its own page — still printed `sí` next to
      `0.000` for the spec'd bars: the arithmetic is real and the VERDICT is not emittable, the same
      discipline `GoNoGo.veredicto` applies below n = 20. `pasa_publicable` now gates both the markdown
      and the JSON on `metricas.evaluable`, and the block says why. **W3** the SLM bench never
      re-derived the post-exclusion universe, which made it the way around task 9.4: same recorded
      payloads, same `corpus_sha`, no database read. `cargar_y_comparar(db, ruta)` now runs
      `verificar_payload` over BOTH arms (parity compares `claves_payload`, not `claves_recuperadas`,
      so one arm can be stale while parity is clean), `verificar_paridad` additionally requires a
      coherent `expected_clasificacion_sha256` between arms, `PIN_REFERENCIA` — a dead constant until
      now — is compared against the reference arm, and the CLI's `_bench_slm` moved INSIDE the session
      block. **S1** `generador_sintetico` is now mandatory: `null` is not `false`, and a set with
      answers and no declaration was being published on the assumption that a real generator wrote
      them. **S3** the bench's inline arms are parsed through the new `answers.cargar_desde_mapping`
      instead of a `NamedTemporaryFile` round trip that wrote every arm's verbatim question and answer
      text — the exact bytes threat 7.5 names — to a world-readable `/tmp` file to read them straight
      back.

## Phase 10: Runbook, deploy, docs (U10)

- [x] 10.1 GREEN: write the G9 runbook (`docs/`) with the 11 ordered steps, each naming failure state and
      recovery, plus the reboot re-derivation probe matrix (`design.md:914-944`).
      **DONE 2026-08-24** — `docs/rag/runbook-encendido.md`. Steps 1–11 in the design's sealed order, plus
      **7a** as its own numbered step: the owner's terms verification (task 6.7) had no place in the sequence
      and a blocking manual gate that appears only in a prose paragraph is a gate that gets skipped. The probe
      matrix carries all seven rows including the two NON-database probes (image tag, sidecar identity), and
      the sealed rollback order closes it. The joint ceremony with `flujo-caminos` is stated at the top with
      its interleaving rule: **one shared `alembic upgrade head`**, neither arc running its own, and both
      flags flipping last.
- [x] 10.2 GREEN: record the `conocimiento-embed` compose block verbatim (it lives in the **external**
      compose file) + `CONOCIMIENTO_EMBED_URL` on the backend (`design.md:888-912`).
      *(extended 2026-08-24 by task 7.7: the SAME block must also declare the **worker** service that runs
      `scripts/rag_worker.py` — the `venv-rag` image, the GPU device reservation, `restart: unless-stopped`
      and the same `.env` as the backend. The queue has a postman as of 7.7; until this task records how the
      box starts it, the postman is started by hand and a box that reboots stops answering with the only
      symptom being items ageing on `GET /estado`.)*
      **DONE 2026-08-24** — runbook §0.1 (sidecar) and §0.2 (worker), each with the knob table and defaults.
      *Three corrections against the design's draft block, recorded IN the runbook rather than applied
      silently, because U3 shipped the sidecar and the repository's `docker-compose.yml` is the authority on
      its shape: `expose: 8002` (not a published loopback port — so the reboot probe is a `docker compose
      exec`, not a host `curl`), the volume is `conocimiento-embed-cache:/cache/huggingface` (the image's real
      `HF_HOME`), and the healthcheck hits `/health` through the image's own Python (`/ready` restart-loops
      the container through its own cold start, and `curl` is not in the image). `profiles: ["conocimiento"]`
      is deliberately NOT carried to the box: it exists to stop a developer's bare `up -d` from pulling 2.2 GB
      of weights, and on the box it would mean a reboot brings everything back with the answerer absent.*
      *The WORKER block carries two facts the task did not anticipate and that would have burned a
      maintenance window: **(a) it does not belong on the box at all** — it reranks on CUDA and the CX33 has
      no GPU, so per A3 its compose block belongs to the GPU host's file, reaching the box's Postgres over the
      same `DATABASE_URL`; **(b) no image in this repository builds `requirements-rag.txt`** (D8 keeps the
      CUDA stack out of every built image, and `Dockerfile.worker` is the Celery/GDAL geo worker — a different
      process). So the runbook ships the RUNNABLE form today, a systemd unit over the host `venv-rag`, and
      records the compose block as the target shape with its missing Dockerfile marked in the block itself.
      A compose block that names an image nobody can build is a runbook lying in YAML.*
- [x] 10.3 GREEN: reconcile the runbook with the amendment — step 9 still loads vectors and step 10 still
      smokes the vector extension, but the serving smoke is a `modo="bm25_ce"` retrieval; state that the
      stored corpus vectors have no serving consumer post-B50 (see task 2.7).
      **DONE 2026-08-24** — runbook §2. Says in words that the vectors are eval and future-option
      infrastructure, that step 9 can be deferred without blocking enablement, and that steps 8, 7a and §4.3
      cannot — so nobody later reads step 9 as evidence that serving is vector-backed.
- [ ] 10.4 Measurement on the **box**, not the workstation: CPU query-embedding latency
      (`scripts/rag_query_latency.py`) and sidecar RAM + cold-start under `docker stats`
      (`design.md:107-115`). Both precede runbook step 2.
      **STAYS OPEN — this is the honest state.** The PROCEDURE landed 2026-08-24 (runbook §4.1, with the
      exact commands and the `--threads 2` / cold-cache discipline that makes two runs on the same machine
      agree); the MEASUREMENT is an act on the Hetzner box and no artifact of it exists. Nothing here may be
      marked done from a workstation. *One correction to the procedure: `scripts/rag_query_latency.py`'s
      docstring names `docs/rag/preguntas-latencia.txt`, which does not exist in this repository. The runbook
      uses `--gold-set app/domains/conocimiento/eval/gold_set.yaml`, which does — a runbook command that
      cannot run is worse than no runbook.*
- [x] 10.5 GREEN: step 8 diff — all 35 rows of `rag_documento` (class **and** evidence) against
      `expected_clasificacion.yaml`, never a `count(*)` (`design.md:924`).
      **DONE 2026-08-24** — `gee-backend/scripts/rag_verificar_clasificacion.py` + 14 tests in
      `tests/new/conocimiento/test_rag_verificar_clasificacion.py`, RED before GREEN. The tests are written
      against the failures a count cannot see: a class SWAP that preserves every per-class count, a right
      class reached through the WRONG evidence string, a document in the artifact and missing from the
      snapshot, and the reverse. Two preconditions REFUSE with exit 2 rather than scoring — an artifact
      pinned to another `corpus_sha`, and a `regla_clasificacion_sha256()` that moved since the artifact was
      generated — because "0 divergences" out of an invalid comparison is the most expensive output this
      script could produce. Exit 0 clean · 1 divergence (STOP, flag off) · 2 refused/usage.
- [x] 10.6 GREEN: `pytest tests/` green (the real CI scope, not `tests/new/`) before the flag is flipped.
      **DONE 2026-08-24** — run against the whole `tests/` scope; result recorded in the apply report with
      its exact exit code. `ruff check` and `ruff format --check` both exit 0; `alembic heads` is a single
      head, `conocimiento_007`.

## Follow-ups (explicitly OUT of the apply gate)

- [ ] F1 **Re-chunk the 10 oversized units** (max 58,619 chars; the reranker truncates at 1024 tokens). The
      amendment schedules this as follow-up work, **not** an apply gate (`design.md:1150-1155`).
- [ ] F2 Grow the gold set beyond 29 answerable questions — one question is worth 0.034 hit@5, and the B50
      family reads as ≈ 0.72–0.76 (`design.md:1150-1153`,
      `docs/rag/candidate-recall-campaign-2026-08-23.md:423-458`).
- [ ] F3 A real Comisión Directiva role instead of the `require_admin` approximation (`proposal.md:78`).
- [ ] F4 Operational/geospatial data joins (`tramites`, `finanzas`, `padron`, `reuniones`) — V1 only redirects.
- [ ] F5 Revisit LLM-as-judge only when the answer set outgrows manual grading (`design.md:814-817`).
