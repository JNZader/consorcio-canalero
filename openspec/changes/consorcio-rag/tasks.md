# Tasks: Consorcio RAG V0 — Cited Legal Retrieval Foundation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1650 total (380 + 400 + 430 + 440, per design PR Slicing) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | 4 slices, tracker `feat/consorcio-rag` → PR1 → PR2 → PR3 → PR4 |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Base | Notes |
|------|------|----|----|-------|
| 1 | Infra + schema: Dockerfile, compose, migrations 001/002, `models.py`, `ddl.py`, conftest/pytest.ini, `test-rag` Makefile target | PR1 | `feat/consorcio-rag` (tracker) | ~380 lines. Verify: `pg_extension` row exists; upgrade/downgrade idempotent both branches; existing suite green on vector-less image. |
| 2 | Parser + ingestion CLI + `corpus_expectations.yaml` + 3 gates | PR2 | PR1 branch | ~400 lines. Fixture-driven unit tests unblock independent of Ops-1; real-corpus run blocked on Ops-1. |
| 3 | Embed batch/load scripts + retrieval repository/service + fusion | PR3 | PR2 branch | ~430 lines. Split seam if it overruns: embed/load vs retrieval — two clean, independently-verifiable halves. |
| 4 | Eval harness + gold set + metrics + LOOCV + report writer | PR4 | PR3 branch | ~440 lines. Split seam if it overruns: harness/metrics vs report writer. |

Each PR targets the immediate previous PR's branch; only `feat/consorcio-rag` merges to main. Slices 1–2 are independently useful even if the vector legs were abandoned (FTS-only still works) — the point of the ablation.

---

## Slice 1 — Infra + Schema (PR1, base = `feat/consorcio-rag`)

- [x] 1.1 RED→GREEN: `gee-backend/tests/new/conocimiento/test_rag_migrations.py::test_upgrade_head_creates_three_tables` — create `gee-backend/app/db/migrations/versions/conocimiento_001_rag_corpus_schema.py` (`down_revision` = current `alembic heads`): `rag_corpus`, `rag_documento`, `rag_unidad` with composite PK `(corpus_sha, citation_key)` on `rag_unidad`, generated `tsv` via 2-arg `to_tsvector('spanish', …)` STORED + GIN index, per design D1.
- [x] 1.2 Doc/code micro-fix (CRA-102/CRB-102, in the same migration + `models.py`): name the count column `rag_corpus.articulos_declarados`, not `unidades_declaradas`; add a comment stating it counts `tipo_chunk='articulo'` only, distinct from the corpus's total unit count.
- [x] 1.3 RED→GREEN: `test_rag_migrations.py::test_migration_002_noop_on_vector_less_image` — create `conocimiento_002_pgvector_embeddings.py`: probes `pg_available_extensions`; absent → WARNING no-op; present → `CREATE EXTENSION IF NOT EXISTS vector`, `ADD COLUMN IF NOT EXISTS embedding vector(1024)`, HNSW `IF NOT EXISTS` index.
- [x] 1.4 RED→GREEN (marked `pgvector`): `test_rag_migrations.py::test_migration_002_guard_symmetry_on_vector_image` — upgrade twice, downgrade twice on `consorcio-postgres:16-vector`; every direction is a no-op after the first, none raises.
- [x] 1.5 Create `gee-backend/app/domains/conocimiento/ddl.py` — single source of truth for the embedding DDL statements, imported by migration 002 AND the test fixture (1.10).
- [x] 1.6 Create `docker/postgres/Dockerfile` — `FROM pgrouting/pgrouting:16-3.4-3.6.1` + pinned `postgresql-16-pgvector` from PGDG + build-time `RUN test -f /usr/share/postgresql/16/extension/vector.control`; tag `consorcio-postgres:16-vector`.
- [x] 1.7 Create `docker-compose.pgvector.yml` — opt-in override for the `postgres` service (`build: docker/postgres/Dockerfile`), used only via `-f`, never auto-merged into `docker-compose.yml`.
- [x] 1.8 Create `gee-backend/app/domains/conocimiento/models.py` — `RagCorpus`/`RagDocumento`/`RagUnidad` (Mapped/mapped_column); `embedding` deliberately NOT mapped — comment cites `create_all` vs the PostGIS test image (D7).
- [x] 1.9 RED→GREEN: `test_rag_migrations.py::test_create_all_unaffected_by_conocimiento_models` — import `conocimiento.models`, run `Base.metadata.create_all` on the default vector-less image; no `embedding` column anywhere, no exception.
- [x] 1.10 Modify `gee-backend/tests/new/conftest.py` — `TEST_POSTGRES_IMAGE` env var (default unchanged `postgis/postgis:16-3.4`), attempt `CREATE EXTENSION vector`, expose `HAS_PGVECTOR`, add a `pgvector_db` fixture importing `ddl.py`.
- [x] 1.11 Modify `gee-backend/pytest.ini` — register the `pgvector` marker (`--strict-markers` is on).
- [x] 1.12 Modify `Makefile` — add `rag-db` (build + start `docker-compose.pgvector.yml`); add `test-rag` (build vector image, export `TEST_POSTGRES_IMAGE=consorcio-postgres:16-vector`, `pytest -m pgvector --junitxml=rag-junit.xml`, then assert exit code ≠ 5 **and** parse the JUnit XML for `skipped="0"`, failing the target otherwise).
- [x] 1.13 Manual verification (no new file): dry-run `make test-rag` against a deliberately broken vector image (extension install failing) and confirm the `skipped==0` guard fails the target — proves it catches the silently-degraded-image failure mode the exit-code-5 check alone cannot (D7). Verified by exercising the guard's exact parsing logic against real JUnit output from a real degraded-skip run (pytest exit 0, 1 skipped) — see apply-progress.md for detail.
- [x] 1.14 Doc fix (CRA-103): `openspec/changes/consorcio-rag/design.md:365` — "drops both tables" → "drops all three tables" (Migration/Rollout section).

## Slice 2 — Parser + Ingestion CLI + Gates (PR2, base = PR1 branch)

- [x] 2.1 RED→GREEN: `gee-backend/tests/new/conocimiento/test_rag_parser.py::test_v3_prefix_group_captures_compound_headings` — create `gee-backend/app/domains/conocimiento/parser.py` (`parse_document(markdown_text, frontmatter) -> list[Unidad]`, pure, zero DB): MANIFEST regex v3 em-dash prefix group (`Anexo|Anexo I+|Decreto|Resolutivo|Anexo II`) + `Art.|Artículo|Punto|Norma` alternation + `bis|ter|qu[aá]ter|quinques|sextus` suffix. Res. 4/2026 and Decreto 318/2007 compound headings captured as distinct `articulo` units (19%-loss regression class).
- [x] 2.2 RED→GREEN: `test_rag_parser.py::test_norma_tecnica_point_rule_scoped` — add `^## (\d)\. ` rule gated strictly on `tipo == 'norma-tecnica'` (D-10); the 5 secondary docs' 31 numbered commentary sections are NOT captured as `articulo`.
- [x] 2.3 RED→GREEN: `test_rag_parser.py::test_d9_collision_composite_key` — composite citation-key rule per D1: `10demayo#res189-2014#art1` / `10demayo#res005-2026#art1`, no collision.
- [x] 2.4 RED→GREEN: `test_rag_parser.py::test_guia_de_uso_tagged_not_articulo` + `test_ley10679_vigencia_section_indexed_as_nota_vigencia` — implement the non-article `tipo_chunk` table (`articulo`/`considerando`/`guia-de-uso`/`nota-vigencia`/`ficha-registral`/`seccion-secundaria`) + the `{documento}#{slug-de-sección}` key convention; Ley 8803's 4 closing sections tagged `guia-de-uso`, Ley 10679's `## Vigencia de los fondos` keyed `10679#vigencia-de-los-fondos` and indexed, never dropped.
- [x] 2.5 RED→GREEN: `gee-backend/tests/new/conocimiento/test_rag_ingest_frontmatter.py::test_d22_ley_synonym_treated_as_ley_provincial` — `tipo` normalization (`ley` ≡ `ley-provincial`, D-22) in `repository.py`; Ley 8803 treated identically to the 14 `ley-provincial` documents.
- [x] 2.6 Named trap tests, `gee-backend/tests/new/conocimiento/test_rag_parser_traps.py`: `test_ley5589_art276_dual_redaction_single_unit`, `test_ley5589_arts_4_6_82_84_dual_redaction`, `test_ley5589_art193ter_footnote_substitution`, `test_ley9750_art39_footnote_stays_inside_unit` (T-1 canary's third expected citation) — parser never splits a `Texto vigente`/`Redacción anterior` or footnote-substitution block across units.
- [x] 2.7 RED→GREEN: `test_rag_ingest_frontmatter.py::test_relevancia_consorcio_carried_verbatim_res4_2026` + `test_jurisdiccion_not_null_missing_key_aborts` — `repository.py` ingestion-write path carries `jurisdiccion`/`relevancia_consorcio` verbatim from frontmatter; missing `jurisdiccion` aborts before writing any row; `relevancia_consorcio` NULL when absent, never invented.
- [x] 2.8 RED→GREEN: `test_rag_ingest_frontmatter.py::test_ley8548_derogada_units_flagged_estado_vigencia` — `estado_vigencia` carried per document, surfaced on its units; Ley 8548 units remain retrievable, distinctly flagged `derogada`.
- [x] 2.9 Create `gee-backend/app/domains/conocimiento/corpus_expectations.yaml` — after re-running the corpus's own `_gate-consolidacion-final.py` (gate zero) to confirm 1383 is not blindly inherited: two inventories — per-document `articulo` counts (subtotal 1358+6+19+0=1383) and per-document non-article `tipo_chunk`+citation-key inventory.
- [x] 2.10 RED→GREEN: `gee-backend/tests/new/conocimiento/test_rag_gates.py::test_per_document_and_total_articulo_count_gate` + `test_all_counts_match_ingestion_succeeds` — count gate asserts total AND per-document `articulo` counts against `corpus_expectations.yaml`; a total-matches-but-one-doc-short run fails.
- [x] 2.11 RED→GREEN: `test_rag_gates.py::test_non_article_inventory_gated_separately` + `test_secondary_types_es_secundaria_true_zero_contribution` — non-article `tipo_chunk`s gated against their own per-document inventory, never folded into 1383; the 6 secondary documents carry `es_secundaria=true` and contribute 0.
- [x] 2.12 RED→GREEN: `test_rag_gates.py::test_verbatim_substring_gate` + `test_citation_key_uniqueness_including_d9` + `test_token_ceiling_aborts_not_truncates` — the three integrity gates wired into the pipeline; a unit over 8192 BGE-M3/XLM-R tokens aborts instead of silently truncating.
- [x] 2.13 RED→GREEN: `gee-backend/tests/new/conocimiento/test_rag_ingest_cli.py::test_idempotent_rerun_same_sha` + `test_unresolvable_sha_aborts_before_writing` — create `gee-backend/scripts/rag_ingest.py`: required `--corpus-path`/`--corpus-sha`, verifies `git rev-parse HEAD` at that path equals the declared SHA, refuses a dirty tree, `INSERT ... ON CONFLICT (corpus_sha, citation_key) DO UPDATE`.
- [x] 2.14 RED→GREEN: `test_rag_ingest_cli.py::test_verify_unchanged_reports_divergence_instead_of_overwriting` — optional `--verify-unchanged` flag (off by default): on a repeated `corpus_sha`, compare sha256(`texto`) per citation key first and report the divergence instead of overwriting it (D2 fold).
- [x] 2.15 Create `gee-backend/app/domains/conocimiento/schemas.py` — Pydantic v2 ingestion-result summary shapes (counts, gate outcomes); house pattern, no `router.py`.

## Slice 3 — Embedding Batch/Load + Retrieval (PR3, base = PR2 branch)

- [x] 3.1 Create `gee-backend/requirements-rag.txt` — `torch`/`FlagEmbedding`/`transformers`, ingestion extra only (mirrors `requirements-ml.txt`), never in the app runtime image. Also carries `sentence-transformers` for the local multilingual-e5-large baseline that replaced the hosted provider (O.5).
- [x] 3.2 RED→GREEN: `gee-backend/tests/new/conocimiento/test_rag_embed_batch.py::test_preflight_aborts_over_ceiling` — create `gee-backend/scripts/rag_embed_batch.py`: tokenizes every `texto_indexado`, aborts loudly over 8192 under `--strict-token-ceiling` (default: exempt + disclose, per the ratified V0 rule); GPU batch, L2-normalized, no query/document prefix (BGE-M3 symmetric); writes `vectors-{sha8}.copy` (COPY text format, pgvector literal, float32 `%.9g`) + sidecar `vectors-{sha8}.json` (model id + HF revision SHA, dims, normalized, corpus_sha, n_vectors, sha256, **over_ceiling key list**, torch/transformers versions, device).
- [x] 3.3 RED→GREEN: `gee-backend/tests/new/conocimiento/test_rag_load_vectors.py::test_copy_literal_roundtrip` — pgvector COPY-text literal round-trips a synthetic vector unchanged, no DB.
- [x] 3.4 RED→GREEN (marked `pgvector`): `test_rag_load_vectors.py::test_load_updates_every_row` + `test_load_aborts_on_orphan_key_leaves_embeddings_null` — create `gee-backend/scripts/rag_load_vectors.py`: pre-checks (dump sha256 vs sidecar, active `corpus_sha`, dims==1024, **exemption identity** per amendment A1 — `dump ∪ over_ceiling == every unit key`, not a bare count); `CREATE TEMP TABLE rag_embedding_staging (...) ON COMMIT DROP`; `COPY` into it; `UPDATE rag_unidad … FROM` staging; in-transaction post-checks (rowcount==n_vectors, orphan anti-join empty, NULL-embedding set == over_ceiling set) or abort — per D3.
- [x] 3.5 RED→GREEN: `gee-backend/tests/new/conocimiento/test_rag_fusion.py::test_rrf_fuses_without_blended_score` + `test_rrf_handles_missing_leg` + `test_rrf_tie_break_deterministic` — create `gee-backend/app/domains/conocimiento/fusion.py`: pure `reciprocal_rank_fusion(lists, k=60)`, tie-break `(-score, citation_key)` ascending.
- [x] 3.6 RED→GREEN (marked `pgvector`): `gee-backend/tests/new/conocimiento/test_rag_retrieval.py::test_fts_and_vector_legs_sort_deterministically` — `repository.py` retrieval: FTS leg (`ts_rank_cd(...) DESC, citation_key ASC LIMIT 50`), vector leg (raw SQL, `::vector` cast, `embedding <=> :qvec ASC, citation_key ASC LIMIT 50`); repeated identical queries over tied-rank fixtures (the "Sin Reglamentar" collision class) return the same leg order every run.
- [x] 3.7 RED→GREEN: `test_rag_retrieval.py::test_vector_leg_raises_when_unsupported` (default vector-less image, no marker) — `VectorSupportUnavailable` raised, never a silent FTS fallback. Companion `test_hybrid_mode_raises_rather_than_silently_becoming_fts` covers the service layer.
- [x] 3.8 RED→GREEN (marked `pgvector`): `test_rag_retrieval.py::test_hit_carries_full_provenance` + `test_secundaria_hit_distinguishable_from_norma` + `test_do_not_cite_warning_reaches_consumer_res4_2026` — create the retrieval half of `gee-backend/app/domains/conocimiento/service.py`: citation assembly returns `citation_key+tipo+es_secundaria+jurisdiccion+estado_vigencia+relevancia_consorcio+verificacion+fuente_url+texto`. Run in BOTH shapes (unmarked in `fts` mode so CI covers them, plus a marked hybrid-path variant).
- [x] 3.9 RED: `gee-backend/tests/new/conocimiento/test_rag_no_router.py::test_no_conocimiento_router_mounted` — static check: `app/domains/conocimiento/` has no `router.py`; `app/api/v2/` aggregator never imports/mounts it. No GREEN task — D8 absence-by-design.
- [x] 3.10 Create `gee-backend/scripts/rag_query_latency.py` — CPU-loaded BGE-M3 (once per process), reports p50/p95 over the gold questions (3 warm-ups, 3 repeats), records core count/thread settings (D3 Query-time row). Harness covered by `test_rag_query_latency.py`; the NUMBER is the owner's to measure.

### Slice 3 ledger amendments (from the slice-2 scoped re-review)

- [x] A1 (R3-104) `design.md` D3: Load pre-check is `dump ∪ over_ceiling == every unit key`, with the exempt keys PINNED in the sidecar — not `n_vectors == count(rag_unidad)` (which rejects every correct dump) and not a bare `count − |over_ceiling|` (which accepts any equally-sized shortfall). Implemented in `rag_load_vectors.preflight`.
- [x] A2 (R3-101) `test_rag_migrations.py::_seed_003_shaped_rows` — each of `downgrade()`'s two DELETEs now has its OWN witness row. Verified by removing each in turn: CheckViolation and ForeignKeyViolation respectively.
- [x] A3 (R3-102) `gates.corpus_file_inventory_gate` — `rglob` + relative-path matching + dot-directory skip; the 11 `.md` files under `fuentes-crudas/` are now seen and declared in `archivos_no_documento`.
- [x] A4 (R3-103) apply-progress deviation #5 corrected: the `corpus_sha != pin` branch IS reachable, and `TestCorpusAdvancedPastThePin` reaches it with a real corpus clone advanced by an empty commit.
- [x] A5 (R3-105) `Makefile` `test-rag-corpus` — backticks inside double quotes replaced with single quotes; the diagnostic no longer runs `corpus` as a command.
- [x] A6 (R3-106) two stale counts corrected: migration `conocimiento_003` says five `anexo-normativo` units (was four/three), apply-progress says 12 `contenido-no-declarado` headings (was 13).

## Slice 4 — Eval Harness + Gold Set + Report (PR4, base = PR3 branch)

- [ ] 4.1 RED→GREEN: `gee-backend/tests/new/conocimiento/test_rag_metrics.py::test_hit_rate_at_5_and_mrr` + `test_citation_precision_norma_secundaria_vigencia_correctness` — create `gee-backend/app/domains/conocimiento/eval/metrics.py`: pure set-comparison functions against gold citation keys, no LLM-as-judge.
- [ ] 4.2 RED→GREEN: `gee-backend/tests/new/conocimiento/test_rag_abstention.py::test_loocv_selection_differs_from_same_sample_fit` + `test_loocv_fallback_counted_when_no_threshold_reaches_recall_1` — create `gee-backend/app/domains/conocimiento/abstention.py`: `AbstentionPolicy(min_score, min_margin, require_both_legs)` + `select_threshold_loocv()` (per-mode leave-one-out; tie-break highest precision at recall 1.00, ties by lower threshold; no-threshold-reaches-1.00 fold-back counted, not silently dropped).
- [ ] 4.3 RED→GREEN (CRA-101/CRB-101 fold): `test_rag_abstention.py::test_abstention_denominator_from_gold_set_not_literal` — the unanswerable-count denominator reads `gold_set.yaml`'s `clase=='unanswerable'` count, never a hardcoded `18`.
- [ ] 4.4 Draft `docs/rag/eval-preguntas-oro-DRAFT-2026-08-10.md` — ~20 candidate answerable Q/A pairs with expected citation keys, including the T-1 canary (Ley 9750 art. 39 footnote) and T-2 canary (Ley 10679, `10679#vigencia-de-los-fondos`); agent-drafted, owner curates (see O.2).
- [ ] 4.5 Create `gee-backend/app/domains/conocimiento/eval/gold_set.yaml` — schema `id/pregunta/clase(answerable|unanswerable|trampa-vigencia)/citas_esperadas/fuente/validado_por(draft|owner)`; seeded from 4.4 plus canal N°5 (7 answerable) and obras-audit §5 (18 unanswerable); `validado_por: draft` until O.2 closes.
- [ ] 4.6 RED→GREEN: `gee-backend/tests/new/conocimiento/test_rag_eval_harness.py::test_n_lt_20_blocks_scoring` — create `gee-backend/app/domains/conocimiento/eval/harness.py` (`--mode fts|vector|hybrid`, one code path); refuses go/no-go unless every item is `owner`-validated and `answerable` ≥ 20.
- [ ] 4.7 RED→GREEN: `test_rag_eval_harness.py::test_three_modes_same_questions_separate_metric_blocks` + `test_unanswerable_question_triggers_abstention` + `test_answerable_question_above_threshold_returns_hit`.
- [ ] 4.8 RED→GREEN: `test_rag_eval_harness.py::test_vigencia_trap_surfaces_true_current_state` — Ley 8548 / Ley 10679-art.20-post-2023 adversarial questions return the true current `estado_vigencia`, not the historic text.
- [ ] 4.9 RED→GREEN: `test_rag_eval_harness.py::test_false_confident_answer_fails_go_no_go_regardless_of_other_metrics` + `test_same_sample_fit_cannot_carry_go_no_go` — go/no-go decided ONLY on the LOOCV-held-out pair (recall 1.00 AND precision ≥ 0.80); same-sample figure labeled `upper bound (fit on the scoring sample)` wherever reported.
- [ ] 4.10 RED→GREEN: `gee-backend/tests/new/conocimiento/test_rag_privacy.py::test_api_baseline_gated_by_assert_public_domain` + `test_private_document_excluded_from_external_payload` — `assert_public_domain(corpus_sha)` default-deny gate on the optional hosted-embedding baseline leg (provider TBD, see O.5).
- [ ] 4.11 Create `gee-backend/app/domains/conocimiento/eval/report.py` — writes `docs/rag/retrieval-eval-{sha8}-{YYYY-MM-DD}.md` + `results.json`; per-mode methodology-disclosure block (selection rule, LOOCV, `n`, shipped threshold, held-out precision/recall, same-sample upper bound); pins corpus SHA, model HF revision, torch version, device.
- [ ] 4.12 Create `gee-backend/scripts/rag_eval.py` (wires harness+metrics+abstention+report); modify `Makefile` — add `rag-ingest`, `rag-embed-load`, `rag-eval` targets delegating to the Slice 2–4 scripts.
- [ ] 4.13 Register `parser.py`/`fusion.py`/`abstention.py`/`metrics.py` in `gee-backend/.cosmic-ray.toml` as a **commented, unmeasured** `module-path` block — precedent: the rainfall policy/service/temporal entries. Note: "pending local `cosmic-ray init`+`exec` measurement, no DB dependency." Do NOT wire to CI until measured (repo rule: no numbers, no gate).
- [ ] 4.14 E2E verification (no new file): run `make rag-eval` once ingestion (Slice 2 + O.1), embeddings (Slice 3 + O.3), and the owner-curated gold set (O.2) all exist; confirm the report lands under `docs/rag/` and is reviewed by the owner (proposal Success Criteria).

## Ops (cross-cutting prerequisites, not slice-blocking unless noted)

- [x] O.1 **HARD prerequisite, blocks Slice 2's real-corpus run.** Create and push the `consorcio-corpus-legal` git repository (owner: Javier). RESOLVED 2026-08-10; Slice 2 ingested the pinned SHA `12043582bf8016288a7e8084e85a4b713a97af2f` for real (1383 articulo + 65 non-article units = 1448 rows; the non-article count moved 63 → 65 in the reliability fix round, when the heading-coverage gate surfaced Res. APRHI 3/2026's two anexos — ledger RAG2-001).
- [ ] O.2 **Blocks the eval RUN (4.14), not the Slice 4 PR.** Owner validates/curates `docs/rag/eval-preguntas-oro-DRAFT-2026-08-10.md` (4.4) into `gold_set.yaml` (4.5): set `validado_por: owner` on every item, reach `answerable` ≥ 20.
- [ ] O.3 **Blocks `rag-embed-load`/`rag-eval` execution, not Slice 3's code/tests.** Owner runs the one-shot BGE-M3 batch embedding on the RTX 5060 Ti workstation, producing `vectors-{sha8}.copy` + sidecar `.json` (3.2 uses synthetic fixtures for its own tests).
- [ ] O.4 Owner call: CX33 latency-measurement approach — throwaway on-box container (low-traffic window, `--cpus`/`--memory` caps, pull-then-measure-as-separate-step) vs. cpuset-matched local proxy labeled `ESTIMATE`. Needed before 4.11's report finalizes its query-latency section.
- [ ] O.5 Owner call: hosted-embedding baseline provider — Voyage-3 (`VOYAGE_API_KEY`) vs OpenAI `text-embedding-3-large` truncated to 1024 dims. Needed before 4.10's API-baseline leg runs; ships gated behind `assert_public_domain` either way.

## Coverage Table (every delta-spec scenario → task/test)

| Requirement | Scenario | Task | Test |
|---|---|---|---|
| ING: Corpus Source Pinning and Idempotency | Re-run against unchanged pin is idempotent | 2.13 | `test_idempotent_rerun_same_sha` |
| ING: Corpus Source Pinning and Idempotency | Unresolvable pin aborts before writing | 2.13 | `test_unresolvable_sha_aborts_before_writing` |
| ING: Regex v3 Chunking and Section Exclusion | Compound-heading documents captured in full | 2.1 | `test_v3_prefix_group_captures_compound_headings` |
| ING: Regex v3 Chunking and Section Exclusion | norma-tecnica rule stays scoped | 2.2 | `test_norma_tecnica_point_rule_scoped` |
| ING: Regex v3 Chunking and Section Exclusion | Guía-de-uso tagged, not counted | 2.4 | `test_guia_de_uso_tagged_not_articulo` |
| ING: Regex v3 Chunking and Section Exclusion | Non-article vigencia section indexed, not discarded | 2.4 | `test_ley10679_vigencia_section_indexed_as_nota_vigencia` |
| ING: Frontmatter Field Carriage | Do-not-cite warning survives (Res. 4/2026) | 2.7 | `test_relevancia_consorcio_carried_verbatim_res4_2026` |
| ING: Frontmatter Field Carriage | Jurisdiccion ingested for every document | 2.7 | `test_jurisdiccion_not_null_missing_key_aborts` |
| ING: Citation Key Identity Preservation | D-9 collision resolved by composite key | 2.3 | `test_d9_collision_composite_key` |
| ING: Citation Key Identity Preservation | Duplicate key rejected | 2.12 | `test_citation_key_uniqueness_including_d9` |
| ING: Derecho-Aplicable vs Fuente-Secundaria | D-22 synonym normalized | 2.5 | `test_d22_ley_synonym_treated_as_ley_provincial` |
| ING: Derecho-Aplicable vs Fuente-Secundaria | Secondary types excluded from unit count | 2.11 | `test_secondary_types_es_secundaria_true_zero_contribution` |
| ING: Vigencia State and Dual-Redaction | Derogated law retrievable but flagged | 2.8 | `test_ley8548_derogada_units_flagged_estado_vigencia` |
| ING: Vigencia State and Dual-Redaction | Dual-redaction article stays whole | 2.6 | `test_ley5589_art276_dual_redaction_single_unit` |
| ING: Per-Document and Total Unit Count Gate | Total matches but one document is short | 2.10 | `test_per_document_and_total_articulo_count_gate` |
| ING: Per-Document and Total Unit Count Gate | Non-article units gated separately | 2.11 | `test_non_article_inventory_gated_separately` |
| ING: Per-Document and Total Unit Count Gate | All counts match | 2.10 | `test_all_counts_match_ingestion_succeeds` |
| ING: Integrity Gates | Full-corpus substring gate passes | 2.12 | `test_verbatim_substring_gate` |
| ING: Integrity Gates | Over-ceiling unit aborts instead of truncating | 2.12 | `test_token_ceiling_aborts_not_truncates` |
| RET: Independent FTS/Vector Fusion by RRF | Hybrid query fuses via RRF only | 3.5 | `test_rrf_fuses_without_blended_score` |
| RET: Independent FTS/Vector Fusion by RRF | Either sub-query can fail without corrupting fusion | 3.5 | `test_rrf_handles_missing_leg` |
| RET: Provenance and Norma/Secundaria Separation | Hit carries full citation provenance | 3.8 | `test_hit_carries_full_provenance` |
| RET: Provenance and Norma/Secundaria Separation | Secundaria hit distinguishable from norma | 3.8 | `test_secundaria_hit_distinguishable_from_norma` |
| RET: Provenance and Norma/Secundaria Separation | Do-not-cite warning reaches the consumer | 3.8 | `test_do_not_cite_warning_reaches_consumer_res4_2026` |
| RET: Confidence-Threshold Abstention | Unanswerable question triggers abstention | 4.7 | `test_unanswerable_question_triggers_abstention` |
| RET: Confidence-Threshold Abstention | Answerable question above threshold returns a hit | 4.7 | `test_answerable_question_above_threshold_returns_hit` |
| RET: No User-Facing Surface in V0 | No retrieval route mounted | 3.9 | `test_no_conocimiento_router_mounted` |
| RET: Three-Mode Ablation Eval Harness | Same gold set scored across all three modes | 4.7 | `test_three_modes_same_questions_separate_metric_blocks` |
| RET: Three-Mode Ablation Eval Harness | Vigencia trap surfaces the correct state | 4.8 | `test_vigencia_trap_surfaces_true_current_state` |
| RET: Go/No-Go Thresholds and Precondition | n<20 blocks scoring | 4.6 | `test_n_lt_20_blocks_scoring` |
| RET: Go/No-Go Thresholds and Precondition | Threshold selection is cross-validated, not fitted | 4.2 | `test_loocv_selection_differs_from_same_sample_fit` |
| RET: Go/No-Go Thresholds and Precondition | Same-sample figure cannot carry a go/no-go | 4.9 | `test_same_sample_fit_cannot_carry_go_no_go` |
| RET: Go/No-Go Thresholds and Precondition | Any false-confident answer fails go/no-go | 4.9 | `test_false_confident_answer_fails_go_no_go_regardless_of_other_metrics` |
| RET: Privacy Boundary on External Services | API-embedding baseline stays bounded to public text | 4.10 | `test_api_baseline_gated_by_assert_public_domain` |
| RET: Privacy Boundary on External Services | Private document content never reaches an external call | 4.10 | `test_private_document_excluded_from_external_payload` |

## Folded Micro-Fixes (round-2 review, below severity floor — traced here, not a fix loop)

| Ledger id | Fix | Task |
|---|---|---|
| CRA-101/CRB-101 | Parameterize abstention denominator from `gold_set.yaml`, kill the literal `18` | 4.3 |
| CRA-102/CRB-102 | Rename `unidades_declaradas` → `articulos_declarados`, document article-only scope | 1.2 |
| CRA-103 | `design.md:365` "both tables" → "all three tables" | 1.14 |
| — | Content-hash `--verify-unchanged` option | 2.14 |
| — | Ley 5589 art. 276 dual-redaction named test | 2.6 |

## Ops resolutions (2026-08-10, owner round 2)
- O.2 ✅ RESOLVED: gold set ratified verbatim (29+23=52) — task 4.x converts the draft as-is; denominators 29/23.
- O.4 ✅ RESOLVED: CX33 measurement deferred to the V1 gate; V0 measures locally (GPU + CPU-capped estimate, labeled).
- O.5 ✅ RESOLVED: local baseline multilingual-e5-large replaces the API baseline; zero external calls in V0.
- O.1 (corpus repo) and O.3 (RTX batch run) remain with the owner, unchanged.
- O.1 ✅ RESOLVED (2026-08-10): private repo https://github.com/JNZader/consorcio-corpus-legal created and pushed by owner order; initial corpus snapshot SHA `12043582bf8016288a7e8084e85a4b713a97af2f` (35 docs + KMZ + fuentes-crudas, 182MB, largest file 17MB). Slice 2 pins this SHA as the first official corpus revision. Incremental-growth loop confirmed with owner: new doc → commit → re-ingest by new SHA → re-batch → abstention questions flip to answerable (the eval grows with the corpus).
