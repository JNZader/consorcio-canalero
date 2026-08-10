# Review Ledger — consorcio-rag

## Judgment Day Round 1 — design.md (post-sdd-phase: design)

Date: 2026-08-10. Judges A+B, blind, parallel (sonnet, rag-advanced + pytest skills loaded). Both verified the two structural claims SOUND (unmapped Vector column truly necessary — create_all vs postgis testcontainer; CI truly runs alembic against the vector-less pgrouting image) and the parser design faithful to MANIFEST traps (D-9/D-10/D-22/DNV-anexos). Findings are the deltas.

### Synthesis

| Finding | A | B | Severity | Synthesis | Status | Resolution (round 1, 2026-08-10) |
|---|---|---|---|---|---|---|
| COPY load into existing PK rows cannot execute (COPY has no upsert) | ✅ CRA-001 BLOCKER | ✅ CRB-008 SUGGESTION (fails loudly, fix obvious) | BLOCKER/SUGGESTION | Both-judge mechanism; severity disputed; fix identical and one paragraph: COPY → staging temp table → UPDATE ... FROM joined on (corpus_sha, citation_key), one transaction. CONFIRMED for fix. | fixed | `design.md` D3 **Load** row rewritten: states why direct COPY cannot work (rows exist, PK, no `ON CONFLICT` for COPY), then TEMP `rag_embedding_staging` ON COMMIT DROP → `UPDATE rag_unidad … FROM staging` → in-transaction post-checks (rowcount == n_vectors, orphan anti-join empty → abort). Testing Strategy integration row gains the orphan-key abort case; PR slice 3 renamed. |
| Leg queries lack deterministic secondary sort (tie at LIMIT-50 boundary flips gold outcomes; corpus has 45 near-identical "Sin Reglamentar" units) | ✅ CRA-002 CRITICAL | — | CRITICAL | Single-judge → triage vs PG semantics + MANIFEST:658-660: REAL. Fix: citation_key secondary ORDER BY on both legs. | fixed | `design.md` D4: diagram + new **Deterministic legs** bullet — `ts_rank_cd DESC, citation_key ASC` and `embedding <=> :qvec ASC, citation_key ASC`, motivated by the 45 "Sin Reglamentar" units (`MANIFEST.md:658-660`). D6 Determinism bullet now names the leg sort as what the claim rests on; Testing Strategy integration row asserts repeated-run leg order. |
| relevancia_consorcio frontmatter (the "NO debe citarse como fundamento" safety signal, 30+/35 docs) architecturally unrepresentable — no column, JSONB explicitly rejected; tipo=resolucion-ministerial derives es_secundaria=False | — | ✅ CRB-001 CRITICAL | CRITICAL | Triage: REAL and premise-level (the exact "derecho + LLM sin cita = peligro" risk). Fix: typed column on rag_documento, ingested from frontmatter, surfaced in EVERY retrieval hit next to tipo/vigencia. | fixed | `design.md` D1 Legal-metadata row + new carriage rationale (cites `resolucion-4-2026-…md:3,:46-51`); D4 diagram + citation assembly surface both fields. Ingestion spec: new **Frontmatter Field Carriage** requirement + Res. 4/2026 scenario + jurisdiccion scenario. Retrieval spec: provenance requirement widened + do-not-cite scenario. Canary follow-through: D2 gains the non-article `tipo_chunk` table (incl. `nota-vigencia` for Ley 10679 `## Vigencia de los fondos`), the non-article key convention, and the article-scoped count gate; ingestion spec gains the non-article scenarios. |
| Eval leakage: abstention threshold swept and scored on the SAME ~38-item gold set — textbook post-hoc overfit read as rigor | — | ✅ CRB-002 CRITICAL | CRITICAL | Triage: REAL. Fix: LOOCV for threshold selection at n≈38 (cheap, honest) + report discloses methodology; same-sample fit labeled upper bound if LOOCV unclears. | fixed | `design.md` D5: LOOCV selection per mode, go/no-go pair on held-out predictions, same-sample labelled upper bound, `select_threshold_loocv()` in `abstention.py` (already a mutation target). D6: metrics + new methodology-disclosure bullet in the report contract. Retrieval spec: Go/No-Go requirement gains the LOOCV MUST + two scenarios. Testing Strategy unit row gains the LOOCV fixture. |
| pytest exit-code-5 guard does not catch skipif-skipped tests → silently-degraded vector image reads green | — | ✅ CRB-003 CRITICAL | CRITICAL | Triage: REAL (exit 5 = zero COLLECTED; skipif skips at execution, exit 0). Fix: assert skipped==0 under the vector image (or passed>=N). | fixed | `design.md` D7 Tests row: `pytest -m pgvector --junitxml=…`, enforcing exit ≠ 5 **and** `skipped == 0`; new paragraph explains collection-time vs execution-time skips and names the hook alternative. |
| Migration 002 no-op-once strands the shared dev volume (alembic records applied; later opting into vector image → no path); downgrade not stated no-op-symmetric | ✅ CRA-003 WARNING | ✅ CRB-004 CRITICAL | CRITICAL | Both-judge mechanism, severity escalated by B (single persistent dev volume + transition untested by construction). CONFIRMED. Fix: IF EXISTS/IF NOT EXISTS symmetric guards both directions + documented recovery (downgrade -1 → upgrade head under vector image). | fixed | `design.md` D7 Migrations row + new symmetry paragraph (explicit `IF [NOT] EXISTS` DDL both directions), stranded-volume recovery runbook (`alembic downgrade -1 && alembic upgrade head` under the vector image) repeated in Migration/Rollout, and an explicit statement that CI never exercises the transition. Testing Strategy integration row gains the guard-symmetry test on both images. |
| CX33 latency measurement framed without contention risk ("prod untouched" true for state, not CPU/net during run) | ✅ CRA-007 | ✅ CRB-007 | WARNING | info — reframe the Open Question with contention + low-traffic-window guidance; owner call stays open. | info | Annotated: Open Question rewritten with the CPU/net contention risk, ~2.5 GB RSS + 2-vCPU shared instance, low-traffic window, `--cpus`/`--memory` caps and wall-clock recording; D3 Query-time row no longer claims a bare "prod stays untouched". Owner call remains open. |
| es_secundario (design) vs es_secundaria (specs) naming drift | — | ✅ CRB-005 | WARNING | info — adopt the specs' es_secundaria. | info | Annotated: `es_secundaria` now used throughout `design.md` (D1, D4); zero occurrences of `es_secundario` remain. |
| jurisdiccion (provincial/nacional) load-bearing per MANIFEST:82-88, absent from schema → V1 re-ingest if deferred | — | ✅ CRB-006 | WARNING | info — add the column NOW (same ingestion pass, cheap). | info | Annotated: folded into the CRB-001 fix — `jurisdiccion Text NOT NULL` on `rag_documento`, surfaced per hit, with an ingestion-spec scenario. |
| ON CONFLICT DO UPDATE silently overwrites cross-run content divergence | ✅ CRA-004 | — | WARNING | info — note + optional content-hash equality check on re-runs of the SAME corpus_sha. | info | Annotated: `design.md` D2 Idempotency paragraph names the cross-run overwrite case and adds the optional `--verify-unchanged` content-hash comparison (off by default). |
| D1 privacy cross-ref points at D5 (abstention) instead of D3 | ✅ CRA-005 | — | SUGGESTION | info — fix ref. | info | Annotated: `design.md:30` now cites D3 (where `assert_public_domain` lives). |
| 19%-trap vs D-10 label conflated in one parenthetical (opposite-signed traps) | ✅ CRA-006 | — | SUGGESTION | info — prose fix. | info | Annotated: `design.md` D2 splits them into "Under-capture — the 19 % loss" (v3 prefix group) and "Over-capture — D-10 applied globally" (scoped rule), each with its MANIFEST line range. |
| Dual-redaction preservation has no NAMED test case unlike every other trap | ✅ CRA-008 | — | WARNING | info — name the ley-5589 art.276 case in the Testing Strategy. | info | Annotated: Testing Strategy gains a "Unit — named trap cases" row naming Ley 5589 art. 276 (`DEROGADO.` + preserved prior text), its siblings (arts. 4/6/82/84, 193 ter) and the Ley 10679 vigencia chunk. |

### Round 1 state
All 6 confirmed/triaged-real findings **fixed** (design artifacts only; no application code exists yet). 7 info folds annotated in place. Files amended: `openspec/changes/consorcio-rag/design.md`, `specs/knowledge-corpus-ingestion/spec.md`, `specs/knowledge-hybrid-retrieval/spec.md`. No new ledger rows were added; anything surfaced while fixing is reported to the orchestrator instead. Pending: scoped re-judge against this ledger and the fix diff.

## Round 1 scoped re-judge — TERMINAL: JUDGMENT: APPROVED ✅

Both re-judges CLEAN, unanimous. Judge A: all 6 resolutions verified with independent MANIFEST arithmetic cross-checks (1358+6+19+0=1383, the 19 summed act-by-act); LOOCV separation confirmed; staging counting-argument airtight. Judge B (original finder): CRB-001..004 genuinely closed at both design-prose and spec-binding levels; the T-1/T-2 canary CONFIRMED reachable against ley-10679:109-362 + MANIFEST:857-860 ("hay que exponerla") — not a stale claim; the LOOCV fallback count verified diagnostic-not-decision-bearing (no second-order leak).

Round-2 micro-fix candidates recorded WARNING/SUGGESTION/info (below severity floor — folded as doc tasks, no fix loop): CRA-101/CRB-101 (parameterize abstention denominator from gold_set.yaml — the literal 18 goes stale the moment curation lands; candidate pool is 29+23=52), CRA-102/CRB-102 (rename/split unidades_declaradas for article-only clarity), CRA-103 ("both tables" vs 3 wording at design:365), plus B's info note (the ingestion base requirement's "exclude OR tag" disjunction is closed at the gate level by the per-document non-article inventory — dedicated scenarios exist for nota-vigencia and guia-de-uso; considerando/ficha-registral/seccion-secundaria rely on the generic gate).

Round 1 closed within budget; no round 2 needed. Next: sdd-tasks (fold the micro-fixes as explicit doc tasks; slices 3/4 split seams named, decision at apply time).

## Slice 1 — resilience lens (PR1 diff, `feat/consorcio-rag-01-infra` @ `e76747a`)

**Verdict: PASS — no BLOCKER, no CRITICAL.** Standard tier, one lens
(`review-resilience`: the diff is shell/process integration — Docker image,
compose overlay, Makefile guard, conditional migration — with partial-failure and
degraded-dependency surface). Sweep budget: 1 exhaustive pass. The reviewer was
read-only; the rows below are persisted here by the Slice 2 apply, which also
carried the fixes.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| RAG1-001 | resilience | `Makefile` (`test-rag` recipe) | WARNING | fixed | `test-rag` exported `TEST_POSTGRES_IMAGE` but `conftest._resolve_database_url()` honors `TEST_DATABASE_URL` FIRST. With that variable exported, the target built the vector image, never touched it, ran against the developer's own database and still printed "all pgvector tests ran for real against consorcio-postgres:16-vector" — the exact false-green the `skipped == 0` guard exists to prevent, one layer up. |
| RAG1-002 | resilience | `docker-compose.pgvector.yml` header; `Makefile` (`rag-db`) | WARNING | fixed | The overlay swaps the server binary over the SAME persistent dev volume. Reverting to the vector-less image while vector objects exist leaves an unloadable database. `design.md` names the hazard and mandates `alembic downgrade` first, but neither the overlay nor `rag-db` said so at the point of use, which is where the mistake is made. |
| RAG1-003 | resilience | `app/domains/conocimiento/ddl.py::extension_available` | WARNING | fixed | Docstring claimed "Never raises" with no `try/except`; a broken connection propagates. A contract that is documented backwards is worse than an undocumented one — slice 3 consumes this to decide whether to raise `VectorSupportUnavailable`. |
| RAG1-004 | resilience | stamp workaround / `deploy.yml` full-chain replay | — | info | **Cleared attack surface, recorded so it is not re-litigated.** Slice 1's `throwaway_db` fixture stamps `lluvia_v2_005` instead of replaying from empty (the pre-existing `pgrouting` gap). Verified this does NOT hide a broken chain: `alembic heads` reports a SINGLE head, and CI's `alembic upgrade head` (`.github/workflows/deploy.yml:103`) still replays the FULL chain on a fresh database, which is the prod-shaped case. The workaround is scoped to one test fixture, not to the migration graph. |

**Fixes (all landed in Slice 2, `feat/consorcio-rag-02-ingestion`):**
- RAG1-001 → `TEST_DATABASE_URL=` cleared inside the `test-rag` recipe, so image selection is the only DB path; comment states why.
- RAG1-002 → rollback-order warning in the `docker-compose.pgvector.yml` header AND an echo on `make rag-db`.
- RAG1-003 → docstring corrected to state that connection/query errors PROPAGATE, with the reasoning: converting an unreachable database into `False` would surface an infrastructure failure as a *capability* signal, which is the same silent degradation D4 forbids for the vector leg. `conftest._probe_pgvector` remains the deliberately never-raising wrapper, because there a failure legitimately means "this environment cannot run the pgvector suite".

Severity floor honored: all three are WARNING, reported once, status `info`-class
— they drove no fix loop and no re-review round. They were fixed opportunistically
because Slice 2 was already editing all three files.

---

## Slice 2 — reliability lens + general refuter

Range: `feat/consorcio-rag-02-ingestion` @ `83fd37c` (parser, gates, repository,
service, ingestion CLI, migration `conocimiento_003`, corpus expectations).
Standard tier escalated to a single deep lens — `review-reliability`, because the
diff's whole risk surface is behaviour, state, determinism and regression: an
ingestion pipeline whose correctness claim IS its gates. Sweep budget: 1
exhaustive pass. Adversarial verification: ONE general refuter over the complete
merged BLOCKER/CRITICAL candidate list; **all four CRITICALs STAND**, none
refuted. Two WARNINGs were promoted into the fix round because they sit in the
same code the CRITICALs touched, not because the severity floor demanded it.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| RAG2-001 | reliability | `app/domains/conocimiento/corpus_expectations.yaml:400-407` | CRITICAL | fixed | `no_articulos: []` for `resolucion-aprhi-3-2026`, whose `# ANEXO I` (line 162 of the source — 25 afectaciones with nomenclatura, titular and valuación, content that exists NOWHERE else in the indexed set) and `# ANEXO II` (line 218) its own art. 1° declares to "integrar el presente instrumento legal". Both were in no inventory, therefore in no index, with every count gate green. The parser's H1 branch (`parser.py:306-313`) already handled this exact class for the DNV-908 anexos. **Refuter: STANDS** — privacy is a non-issue *textually*, the document itself states "no hay aquí dato reservado alguno. No contiene D.N.I." |
| RAG2-002 | reliability | `conocimiento_003_estado_vigencia_scoped.py::downgrade` | CRITICAL | fixed | `downgrade()` restored `SET NOT NULL` (and the narrower `tipo_chunk` CHECK) with no data remediation, while 3 secondary documents write `estado_vigencia = NULL` by design and 4 units are `anexo-normativo`. NotNullViolation / CheckViolation on any ingested database. **Refuter: STANDS** — downgrades run **newest-first**, so this fires before 001 drops the tables: it breaks `-1`, `base`, `proposal.md:89`, the compose header and the Makefile echo alike. |
| RAG2-003 | reliability | `scripts/rag_ingest.py:137-146` | CRITICAL | fixed | `--verify-unchanged` computed divergence over the key INTERSECTION and returned early only `if divergentes`. Otherwise it fell through to the upserts and `prune_unidades`, which DELETED pre-existing keys absent from the new parse — then reported `divergencias: []`, committed, exit 0. The flag's documented contract is "REPORT the divergence instead of overwriting it". **Refuter: STANDS** — verified by execution, not inspection: RED probe printed `divergencias=[] committed=True eliminadas=1 ghost_row_survives=False`. |
| RAG2-004 | reliability | `gates.py::GateReport.over_ceiling` → `schemas.py` → `rag_ingest.main` | CRITICAL | fixed | `over_ceiling` was populated and its own docstring promised "always reported — never silently dropped", while nothing carried it: not `GateOutcome`, not `IngestionSummary`, not `main()`'s printout. 3 real units exceed the ceiling at the pinned SHA. **Refuter: STANDS** — `--strict-token-ceiling` is opt-in, and an opt-in abort is not the same thing as reporting; the default path disclosed nothing at all. |
| RAG2-005 | reliability | `tests/new/conocimiento/conftest.py::requires_real_corpus` | WARNING (promoted) | fixed | Every content test gates on `RAG_CORPUS_PATH`, which CI never sets, so the 35-document check, the 1383/65 counts, the canary, verbatim, determinism, prune and idempotency all skip green. (The corpus holds 35 documents; the "39/39" figure belongs to gate zero, a different check.) CI genuinely CANNOT hold the corpus (private repo, all-local V0 rule), so the fix is disclosure plus a real local gate, not heroics. |
| RAG2-006 | reliability | `test_rag_ingest_cli.py::test_idempotent_rerun_same_sha`; `rag_ingest.main` | WARNING (promoted) | fixed | The determinism assertion projected 5 of 10 columns, so a re-run rewriting `epigrafe`, `documento_id` or `source_file` still passed. Separately, `main()` — argument handling, all abort branches, every exit code, the printed report — was invoked by no test at all. |
| RAG2-007 | reliability | `parser.py::_parse_non_articles` (`seen` guard) | SUGGESTION | info | Latent duplicate-heading dedup: the `seen` set is keyed on `citation_key`, so a SECOND occurrence of an allow-listed heading in one document would be silently dropped rather than reported. Not reachable today — every duplicated heading in the pinned corpus (`Visto y considerandos` in `consorcio-10-de-mayo-registro-aprhi`) is unlisted, hence excluded on both occurrences. Recorded, not fixed: it would need a real second occurrence to specify the right behaviour. |

**Clean checks — swept and found correct, recorded so they are not re-litigated:**

| area | verdict |
|---|---|
| Unit boundaries incl. the T-1/T-2 canary span | Correct. `CLOSING_HEADING_RE` closes at the next SAME-OR-HIGHER heading, so `10679#vigencia-de-los-fondos` keeps its three `###` children and the "31 de diciembre de 2032" payload. |
| Byte fidelity | Correct. `verbatim_substring_gate` checks at the unit's DECLARED offset rather than with `in`, so a text matching elsewhere still fails — `source_offset` is what provenance rests on. Enrichment is confined to `texto_indexado`. |
| Prune ordering vs gates | Correct. Pin verification and every gate run BEFORE the transaction opens; `prune_unidades` cannot run on a corpus that failed a gate. (Its interaction with `--verify-unchanged` was the separate defect RAG2-003.) |
| Determinism | Correct. Parse is byte-identical across runs; re-ingest yields an identical row set. Now asserted over the whole row, not a projection (RAG2-006). |
| Migration upgrade direction | Correct. 001→002→003 applies cleanly on a fresh database; a single `alembic heads`. Only the DOWN direction was broken (RAG2-002). |
| No half-write | Correct. One transaction, all-or-nothing; `test_bad_pin_writes_nothing` asserts an unchanged row count after an abort against real PostgreSQL. |

**Fixes landed** (same branch, fix round from `83fd37c`) — see
`apply-progress.md` § "Fix round" for the per-finding change table, the four
explicit deviations (exclusion CLASSES instead of 248 free-text motives; 12
headings recorded as `contenido-no-declarado` for the next round; RAG2-002's
second instance in the same function; the two knowingly-uncovered branches) and
the four-shape verification counts.

---

## Slice 2 scoped re-review → amendments carried by the Slice 3 apply

Six rows raised against the slice-2 fix diff and its artifacts. All **fixed** on
`feat/consorcio-rag-03-retrieval` before any slice-3 code was written, per the
orchestrator's instruction. R3-104 is the load-bearing one: it is a contradiction
between two ratified decisions, not a defect in either.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| R3-101 | reliability | `tests/new/conocimiento/test_rag_migrations.py::_seed_003_shaped_rows` | WARNING | fixed | The seed put both row shapes migration 003 legalized on ONE document and ONE unit, so either of `downgrade()`'s two DELETEs removed it. The `tipo_chunk` DELETE — the instance the RAG2-002 fix round discovered SECOND and which the finding never named — had no independent witness. **Reproduced behaviourally**: with that DELETE commented out, both downgrade tests still passed. Fixed by giving each DELETE its own witness (a `seccion-secundaria` unit under the NULL-vigencia document, an `anexo-normativo` unit under a document that has vigencia); removing either DELETE now raises `CheckViolation` or `ForeignKeyViolation` respectively. |
| R3-102 | reliability | `app/domains/conocimiento/gates.py::corpus_file_inventory_gate` | WARNING | fixed | Docstring claimed "every `.md` in the checkout"; the glob was `*.md`, top level only. The real corpus already had 11 `.md` files under `fuentes-crudas/` that the gate could not see — the same class of blind spot as RAG2-001, one directory level down. Fixed with `rglob` + relative-path matching (so a nested `README.md` cannot ride in on the top-level declaration) + a dot-directory skip; the 11 raw sources are now declared. RED test first: `test_unlisted_md_in_a_subdirectory_fails`. |
| R3-103 | reliability | `apply-progress.md` fix-round deviation #5 | WARNING | fixed | The disclosure claimed the `corpus.corpus_sha != corpus_sha` branch was "unreachable from the CLI without doctoring the packaged YAML". It reasoned only about an *unrelated* checkout. A corpus **advanced by one commit** — clean tree, HEAD equal to `--corpus-sha`, every declared document present — reaches it, and that is the classic operator error. Disclosure struck through and corrected; `TestCorpusAdvancedPastThePin` now covers `ingest()` and `main()` against the real corpus. |
| R3-104 | reliability | `design.md` D3 (Load row) → `scripts/rag_load_vectors.py` | CRITICAL | fixed | D3 required `n_vectors == count(rag_unidad WHERE corpus_sha=…)`, which **contradicts the ratified V0 over-ceiling decision**: three units are ingested whole and never embedded, so a correct artifact is always three vectors short and the stated check rejects every real dump. The obvious repair (`count − \|over_ceiling\|`) is worse than the bug: it accepts **any** three missing vectors, so a batch that lost a shard loads clean and leaves three unrelated articles silently unreachable through the vector leg while every eval number looks right. Fixed by pinning the exempt KEYS in the sidecar and checking identity in both directions (`dump ∪ exempt == every unit key`), plus an in-transaction post-check that the `embedding IS NULL` set EQUALS the exempt set. `test_arbitrary_missing_vector_is_rejected_where_a_count_would_pass` asserts the naive check would have passed the same artifact. |
| R3-105 | resilience | `Makefile` (`test-rag-corpus` recipe) | WARNING | fixed | Backticks inside double quotes in the exit-code-5 diagnostic: sh would run `corpus` as a command substitution and corrupt the message an operator reads at the moment the target is telling them their marker expression is wrong. Single-quoted. |
| R3-106 | readability | `conocimiento_003_estado_vigencia_scoped.py`; `apply-progress.md` | SUGGESTION | fixed | Two counts left stale by the RAG2-001 fix, which added two `anexo-normativo` units: the migration said "three"/"four" (actual **5**) and apply-progress said 13 `contenido-no-declarado` headings (actual **12**). Both recounted from `corpus_expectations.yaml`, not re-copied. |

### Open item recorded here so it is not re-discovered

`tests/new/test_run_blocking.py::test_run_blocking_runs_concurrent_calls_in_parallel`
(pre-existing, untouched) flakes in the **local corpus-enabled** full-suite shape
only. Measured: CI shape 4/4 green; corpus shape 6 failures in 9 runs; the test
alone 5/5 green; `make test-rag-corpus` green. Three hypotheses falsified
(tmpfs/memory, background `git gc`, fixture I/O weight — a 150× fixture
reduction left the rate unchanged). Not root-caused, and deliberately not
papered over by editing someone else's assertion. Recommended fix for its owner:
assert the parallelism RATIO (`elapsed < sum(durations) * 0.75`) instead of an
absolute 0.18 s wall-clock budget. Full measurement table in `apply-progress.md`.
