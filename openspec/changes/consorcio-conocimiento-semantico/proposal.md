# Proposal: Conocimiento Semántico V1 — Cited Legal Q&A for the Comisión Directiva

## Intent

V0 (`consorcio-rag`, archived 2026-08-11) built and measured a retrieval layer and deliberately shipped **no surface**: `tests/new/conocimiento/test_rag_no_router.py` asserts the router's absence. The Comisión Directiva still hand-reads 35 legal documents. V1 puts the layer in front of the CD — a protected page that answers legal questions with **verifiable citations**, and that says *"eso se consulta en X"* instead of inventing an answer to anything the legal corpus cannot ground.

## Owner decisions (2026-08-23, sealed)

| # | Decision |
|---|---|
| 1 | **Users**: Comisión Directiva only. No CD role exists (`admin`/`operador`/`ciudadano`); V1 gates on `require_admin`. |
| 2 | **Surface**: a page inside `consorcio-web` under existing JWT auth. Telegram/bot deferred. |
| 3 | **Scope**: strictly the legal corpus, mandatory citations, **plus the honest router** (explore Approach 3). Operational/geospatial questions get a redirect, never an answer. |
| 4 | **Deploy**: the single existing environment (Hetzner box, **development status**, app not formally in production). The `consorcio-postgres:16-vector` image swap is **in scope** as a ceremonied deploy step — verified backup (relocated + verified 2026-08-22) + rollback plan. |

## Assumptions (explore's open questions 2/4/6, stated not deferred)

- **Q2 query mix**: mostly legal-interpretation and procedural questions ("¿qué dice la norma / qué procedimiento corresponde?").
- **Q4 geospatial**: the need is *"what does the norm say"*, not *"where does it apply"*. No spatial linkage in V1.
- **Q6 gold set**: grows with **router-classification** cases labeled `legal` / `operational` / `mixed`; the answer-quality set stays legal-answer-only. Owner must review before any threshold is scored.

## Scope

### In Scope

- **Prerequisite gate — O.3 + 4.14**: the owner-side RTX BGE-M3 batch and the real `vector`/`hybrid` eval arms. Non-negotiable: FTS-only is a **measured NO-GO** (hit-rate@5 `0.138`, MRR `0.091`, citation-precision `0.040`). No serving decision is legitimate before hybrid has numbers.
- **Protected Q&A endpoint** under `/api/v2/conocimiento/*`, `require_admin`, rate-limited.
- **Generation layer with citation enforcement**: the model sees only verbatim `texto` + provenance (`tipo`, `es_secundaria`, `estado_vigencia`, `relevancia_consorcio`) of the units in the **post-exclusion generation payload**; every claim must cite a key from **that payload**; uncited or invented-key answers are rejected and regenerated once, then abstain. Existing abstention policy (LOOCV, recall target 1.00) stays the outer gate. *(Corrected, bounded correction 2026-08-23: this line said "retrieved units" / "a **retrieved** citation key". The payload is the retrieved set MINUS whatever the per-request classification gate excluded, and a key belonging to a retrieved-but-excluded unit is an invented citation — so "retrieved" named a wider universe than the one enforcement actually uses.)*
- **Question router**: classify `legal` / `operational` / `geoespacial` / `mixto`; non-legal → deterministic redirect naming the platform surface (`/tramites`, `/finanzas`, `/denuncias`, `/mapa`); `mixto` → answer only the legal part, redirect the rest.
- **`consorcio-web` page**: question box, answer with clickable citations rendering verbatim source text, vigencia badges, explicit abstention/redirect states.
- **Eval extension**: answer-level *citation faithfulness* and *uncited-claim rate* (V0 measures retrieval R-precision only — it never scored a generated answer), plus router-classification accuracy.
- **Prod-image deploy step**: swap the box's Postgres to `consorcio-postgres:16-vector`, apply `conocimiento_002`'s vector branch, load vectors, verify PostGIS/pgRouting/Martin.

### Out of Scope

- Operational/geospatial **data joins** (`tramites`, `finanzas`, `padron`, `reuniones`) — a future change; V1 only redirects.
- Geospatial-aware retrieval (explore Approach 2), Telegram/Discord bots (Approach 4), citizen or `operador` access, actas/PII ingestion, voice.
- Corpus changes: the pinned SHA `12043582bf8016288a7e8084e85a4b713a97af2f` and the 12 `contenido-no-declarado` headings stay as-is.

## Capabilities

### New Capabilities
- `knowledge-answer-generation`: grounded answer synthesis, citation enforcement, regeneration/abstention, answer-level eval metrics.
- `knowledge-question-routing`: legal/operational/geospatial classification, honest redirect contract, no-answer-outside-corpus rule.

### Modified Capabilities
- `knowledge-hybrid-retrieval`: Requirement 4 (*No User-Facing Surface in V0*) is superseded by a gated-surface requirement; Requirement 6 gains the V1 serving thresholds.

## Approach

1. Run O.3/4.14; publish the hybrid ablation. If hybrid also misses the bar, V1 stops at the gate rather than shipping a measured-bad answerer.
2. Router first (cheap, deterministic-where-possible), so a non-legal question never reaches retrieval.
3. Reuse `service.recuperar` (extended per the design: optional precomputed `qvec`, tuple-checked embedder identity); the generation layer sits **above** it and may not bypass its provenance refusals.
4. Generation provider (self-hosted vs external API) is a **design-phase decision** — the cost/latency question rides with it: the box is CPU-only, and query-time BGE-M3 latency on it is still unmeasured. Privacy IS a first-order constraint of this decision *(corrected 2026-08-23: the ratified amendment + three-class rule make the per-unit shippable-set gate and provider no-training terms pin criteria)* — alongside latency and cost.
5. Deploy with ceremony: backup verification → image swap → migration → vector load → smoke of geo stack → enable page.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `gee-backend/app/domains/conocimiento/router.py` | New | Protected Q&A endpoint |
| `.../conocimiento/generacion.py`, `routing.py` | New | Generation + citation enforcement; classifier |
| `.../conocimiento/schemas.py`, `eval/` | Modified | Answer/redirect shapes; answer-level metrics |
| `gee-backend/app/api/v2/` | Modified | Mount router; OpenAPI contract |
| `gee-backend/tests/new/conocimiento/test_rag_no_router.py` | Removed/Replaced | V0 no-router contract is intentionally retired |
| `consorcio-web/src/components/` | New | CD-only Q&A page + route guard |
| Hetzner compose (outside repo) + `docker/postgres/Dockerfile` | Modified | Postgres image swap to `consorcio-postgres:16-vector` |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Hallucination despite citations (real key, wrong claim) | Med-High | Verbatim-only context; key-membership check against the **post-exclusion generation payload** *(corrected from "the retrieved page", bounded correction 2026-08-23 — same universe as the enforcement code and the eval metric)*; answer-level faithfulness metric; abstention outranks generation |
| Image swap breaks PostGIS/pgRouting/Martin on the shared box | Med | Verified backup first; derivative image already built on the pgrouting base; geo smoke test before enabling the page; documented restore |
| Router misclassifies operational as legal | Med | Bias toward redirect on doubt; labeled classification set; misclassification measured, not assumed |
| Hybrid arm also fails the bar | Med | Stop at the gate; V1 does not ship on FTS numbers |
| CPU-only query embedding too slow | Med | Measure on the box before the page ships; provider choice reopens in design |
| `require_admin` ≠ CD membership | Low | Documented as an approximation; a real CD gate is a follow-up |

## Rollback Plan

Ordering matters. **Surface first, database last**: unmount the router + hide the web page (feature flag / revert commit) → the system is inert again. Only if the database itself is implicated: `alembic downgrade conocimiento_001` (drops vector column/index, then `DROP EXTENSION vector`) **before** reverting the box's Postgres image — reverting the image with vector objects live leaves an unloadable database on the persistent volume. If the swap itself fails: restore from the 2026-08-22-verified backup onto the original pgrouting image. No existing table or API contract is modified, so rollback touches no other domain.

## Dependencies

- **O.3 RTX batch + 4.14 real eval** — hard blocker (still unchecked at V0 archive).
- `RAG_GOLD_PRIVADO_PATH` (26 of 52 gold items live owner-side) and `RAG_EVAL_PYTHON=venv-rag`.
- Verified box backup + a maintenance window on the single environment.
- Owner ratification of V1 serving thresholds and of the router redirect targets.

## Success Criteria

- [ ] Hybrid ablation published; V1 thresholds met or the change stops at the gate.
- [ ] A CD member asks a real legal question and gets an answer whose every citation resolves to a unit of the post-exclusion generation payload, rendered verbatim with vigencia state.
- [ ] Uncited-claim rate `0.00` and invented-citation rate `0.00` on the answer eval set.
- [ ] Abstention recall stays `1.00` end-to-end (held-out), precision ≥ `0.80`.
- [ ] An operational question ("¿cuánto debe Juan Pérez?") returns a redirect, never an answer; router accuracy measured on the labeled set.
- [ ] Endpoint returns 401/403 for anonymous, `ciudadano` and `operador`.
- [ ] Post-swap: `vector` extension present **and** PostGIS/pgRouting/Martin tiles verified working on the box.
- [ ] `pytest tests/` green (the real CI scope, not `tests/new/`).

## Open Questions (design-level only)

1. **Generation provider**: self-hosted small model on the CPU box vs external API — decided by measured latency/cost against a public-domain-only corpus.
2. **Router implementation**: LLM prompt vs keyword/embedding classifier, and whether `mixto` splits one answer or two responses.
3. **Regeneration budget**: one retry then abstain, or abstain immediately on any uncited claim.
4. **Feature-flag mechanism** for the page on a single-environment deployment.
