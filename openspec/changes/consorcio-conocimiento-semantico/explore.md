# Exploration: consorcio-conocimiento-semantico

## Current State

`consorcio-rag` V0 is merged, archived, and deployed to prod **dormant by design**. It delivered a measured legal-retrieval layer with no user-facing surface:

- **Code**: `gee-backend/app/domains/conocimiento/` — parser, ingestion gates, hybrid FTS + vector retrieval, embedding lifecycle, and offline eval harness (`gee-backend/app/domains/conocimiento/eval/`).
- **Schema**: `rag_corpus`, `rag_documento`, `rag_unidad` with natural composite keys, generated Spanish FTS, and a dev-only `vector(1024)` column added by conditional migration `conocimiento_002`.
- **Corpus**: 35 markdown documents, 1,383 article-shaped units + 65 non-article chunks, pinned at SHA `12043582bf8016288a7e8084e85a4b713a97af2f` (verified in the working copy at `~/Escritorio/consorcio/corpus-legal/.git`).
- **Measurement**: the V0 eval report established that FTS-only is a NO-GO on the gold set; vector/hybrid await the owner-side GPU batch (O.3 in the archive).
- **Boundary**: no HTTP router exists for `conocimiento`; `tests/new/conocimiento/test_rag_no_router.py` asserts that absence.

The broader platform already carries the operational and geospatial data that a "semantic knowledge" layer would naturally join to the legal corpus:

- **Operational domains**: `padron`, `tramites`, `reuniones`, `finanzas`, `denuncias`, `capas`, `monitoring`.
- **Geospatial data**: `denuncias.geom` (PostGIS POINT), `capas.geojson_data`, `geo.geo_layers`, `geo.geo_approved_zonings.feature_collection`, plus the KMZ `obra-tres-colonias-canal-santa-cecilia.kmz` in the corpus.
- **Auth model**: three roles (`admin`, `operador`, `ciudadano`) via `fastapi-users`.

The natural next step is therefore **not to rebuild retrieval**, but to expose it safely and, where useful, ground it in the consorcio's own operational/geospatial facts.

## Affected Areas

| Path | Why it is affected |
|------|--------------------|
| `gee-backend/app/domains/conocimiento/router.py` | New HTTP surface for query/answer (today missing by design). |
| `gee-backend/app/domains/conocimiento/service.py` | Generation/citation layer sits above existing `recuperar`. |
| `gee-backend/app/domains/conocimiento/schemas.py` | New request/response shapes for consumer-facing answers. |
| `gee-backend/app/api/v2/` | Mount the new router; affects API contract and OpenAPI docs. |
| `gee-backend/app/domains/padron/` | Whitelisting consumers (Telegram/Discord) needs `telegram_id` or similar linkage. |
| `gee-backend/app/domains/tramites/`, `reuniones/`, `finanzas/`, `denuncias/`, `capas/`, `monitoring/` | Potential sources for operational/geospatial answers and for enriching legal retrieval. |
| `gee-backend/app/db/migrations/versions/` | If operational/geospatial metadata is joined into `rag_*` tables or new semantic tables are added. |
| `gee-backend/tests/new/conocimiento/test_rag_no_router.py` | The V0 "no router" contract would need to be replaced/updated. |
| `docker/postgres/Dockerfile`, `docker-compose.pgvector.yml` | Production image swap becomes unavoidable once vectors are served to real users. |

## Approaches

### 1. Operational Q&A over the legal corpus (cited answers for the Comisión Directiva)

Expose the measured retrieval layer through a protected FastAPI endpoint that returns **source-grounded answers**: the LLM is given only the verbatim `texto` of retrieved units and is instructed to cite citation keys, flag `estado_vigencia`, and abstain when confidence is low.

- **Pros**: directly consumes V0, lowest incremental risk, clear eval path (same gold set plus generation metrics), solves the original pain point (CD reading 35 documents by hand).
- **Cons**: requires a generation model and citation-enforcement prompts; needs prod Postgres image swap to make vectors available at runtime; legal answers remain scoped to public-domain law only.
- **Effort**: Medium.
- **Reusability**: ingestion parser, retrieval service, embedders, eval harness, and gold set are all reusable.
- **New build**: router, schemas, answer-generation service, prompt templates, citation guardrails, rate limiting, and an expanded eval set.

### 2. Geospatial-aware legal retrieval

Add geospatial context to retrieval: tag legal units with canal/tramo/zone references extracted from the corpus KMZ and from `capas`/`geo_layers`, then allow queries like *"¿qué normas aplican al cruce del canal Santa Cecilia con la ruta nacional?"*. A geospatial pre-filter (PostGIS) reduces the legal search space before RRF runs.

- **Pros**: answers the consorcio's most concrete disputes (canal N°5 boundaries, trazas, servidumbres); differentiates the product from a generic legal chatbot.
- **Cons**: high data-integration cost (linking unstructured legal text to structured geometry), requires geocoding/normalization of legal references, and needs a maintained map between administrative identifiers and spatial features.
- **Effort**: High.
- **Reusability**: retrieval/fusion engine and embedding pipeline are reusable; ingestion needs new geospatial metadata extractor.
- **New build**: geo-tag ingestion, PostGIS-enabled search filters, enriched `rag_unidad` metadata, and a geospatially-aware query grammar.

### 3. Classification / routing of questions

Before retrieval, classify each incoming question into `legal`, `operational`, `geoespacial`, or `mixed`. Route legal questions to `conocimiento`, operational questions to the relevant domain repository, and mixed questions to a blended answer.

- **Pros**: cheap to prototype, avoids asking legal RAG questions it cannot answer (e.g., *"¿cuánto debe Juan Pérez?"*), and gives a clean extension point for later data sources.
- **Cons**: a misclassified question produces a wrong domain answer; needs a small labeled query set.
- **Effort**: Low-Medium.
- **Reusability**: can reuse the eval harness for labeling and scoring.
- **New build**: classifier service (small model or LLM prompt), routing table, and per-domain answer assemblers.

### 4. Slack / Discord bot consumer

Wrap the Q&A endpoint in an external chat adapter. Use a whitelist that maps `telegram_id` / Discord user ID to `padron` rows so only consorcistas and operators can ask questions.

- **Pros**: low friction for the CD, reuses any backend Q&A endpoint without touching core logic.
- **Cons**: external platform integration, webhook security, and identity mapping are operational work, not core R&D.
- **Effort**: Medium.
- **Reusability**: fully reuses backend Q&A service.
- **New build**: bot adapter, identity mapping table/column, and webhook handler.

## Recommendation

**Lead with Approach 1** (Operational Q&A over the legal corpus) for the next SDD change. It is the direct continuation of `consorcio-rag`: V0 built and measured the retrieval engine; V1 should put it in front of a controlled user group with citations and abstention enforced.

**Add Approach 3** (classification/routing) as a small companion if the CD's real questions routinely mix legal and operational facts; otherwise it can be deferred.

**Defer Approach 2** (geospatial-aware retrieval) until the operational Q&A path is proven, because the spatial linkage work is high-effort and depends on stable identifiers that the legal corpus does not yet normalize.

**Defer Approach 4** (bot consumer) until the backend endpoint exists and the identity-mapping policy is decided.

## Open Product Questions

The following questions must be answered before a proposal can size scope accurately:

1. **Target users**: Is this for the Comisión Directiva only, or also for operators, citizens, or external advisors?
2. **Query types**: What are the real recurring questions? Are they mostly legal interpretation, procedural status, budget obligations, or geospatial disputes?
3. **Data sources beyond legal**: Should the answerer also see operational tables (`tramites`, `reuniones`, `finanzas`, `padron`) and, if so, under what privacy rules?
4. **Geospatial relevance**: Is the immediate need to answer "where does this norm apply?" or simply "what does this norm say?"
5. **UI surface**: Will the first consumer be a web page inside `consorcio-web`, a Telegram/WhatsApp bot, or an API for other domains?
6. **Eval set**: Will the owner expand the 52-question gold set beyond legal questions to include operational/geospatial cases?
7. **Latency / cost**: What is the acceptable latency and embedding cost for a production query? Does it justify the prod Postgres pgvector image swap?
8. **Operational vs legal scope**: Should the system answer questions like *"¿cuánto se gastó en obras en 2025?"* by querying `finanzas.gastos_v2`, or stay strictly legal?

## Risks

- **Hallucination with citations**: a generation layer can still invent citations even when given verbatim text. The V0 provenance fields (`estado_vigencia`, `es_secundaria`, `relevancia_consorcio`) must be exposed to the prompt and verified in eval.
- **Production Postgres image swap**: vectors are currently dev-only. Moving them to prod means swapping the Hetzner Postgres image, which affects PostGIS/pgRouting/Martin tiles — the exact risk the V0 Scope Decision deferred.
- **PII boundary**: once actas or operational data enter the corpus, the current public-domain-only privacy rule must be enforced mechanically, not just by convention.
- **Embedding latency/cost on CPU-only prod**: the CX33 is CPU-only; query-time BGE-M3 latency must be measured and budgeted before go-live.
- **Scope creep into "general assistant"**: without classification/routing, users will ask operational questions and the legal-only engine will either abstain or hallucinate.
- **Eval credibility**: V0 showed FTS-only fails. Any hybrid go/no-go must be run on the real GPU batch; using synthetic/estimate vectors would invalidate the measurement.

## Ready for Proposal

**Yes — with assumptions documented.** The next recommended SDD phase is a focused change that mounts a protected Q&A endpoint over the existing legal corpus, adds a generation layer with citation enforcement, and extends the eval set. The open product questions above should be answered by the owner in the proposal's question round; if any remain open, the proposal must state explicit assumptions rather than defer them silently.
