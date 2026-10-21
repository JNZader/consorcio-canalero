# rag-f1-rechunk

Objective: split every corpus unit whose indexed text exceeds the reranker window, flag off, then re-measure hit@5 on the same 29 questions.
Branch: `feat/rag-f1-rechunk`. Delivery: `single-pr` with `size:exception`. Owner, 2026-10-19: "un solo pr". Runner: `pytest tests/test_rag_f1_rechunk.py` from `gee-backend` (corpus cases need `RAG_CORPUS_PATH`).

## Specs

S1. Owner: "sisi arranca por f1". Scope is F1 only. `conocimiento_qa_enabled` stays false. No SSH, no F2–F5, no decision 0.1, no quota re-derivation.

S2. The accepted close of this slice is the sentence he answered by starting: "¿Arranco por F1, bandera apagada, y al terminar re-medimos el hit@5 sobre las mismas 29?" Re-measured 2026-10-20: 22/29 = 0.7586. The F1 box is checked from that measurement, not from unit tests. Do not invent a hit@5.

S3. Owner, choosing the set: "Las 49 (Recommended)". Membership is `token_count(texto_indexado) > 1024` with the pinned reranker tokenizer (`BAAI/bge-reranker-v2-m3`, revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`). Not a hardcoded list. Not `estimate_tokens` (that splits a different set). At corpus sha `12043582bf8016288a7e8084e85a4b713a97af2f` that count is 49.

S4. The parent unit is replaced. Keeping it would leave a truncated candidate that can still win. Child key is `{parent}#parte-{n}` starting at 1, source order. A key that already ends in `#parte-<digits>` is refused. Units at or under 1024 are returned unchanged, with no `#parte-` suffix.

S5. `texto` of the parts concatenates byte-exact to the parent `texto`. `source_offset` is the parent offset plus the local start. `tipo_chunk`, epígrafe and ubicación are copied. `texto_indexado` repeats the parent's prefix (everything before `texto`) on every part.

S6. Cut on the coarsest boundary that fits: `\n\n`, then `\n`, then `. ` (the period stays with the left piece), then a space. A single word that does not fit raises. Do not cut mid-word. Assumption, measured 2026-10-19: seven Ley 8560 lines exceed the part budget as a single line (worst `8560#5`, 7811 tokens) and each `. `-separated sentence fits (worst sentence 348 tokens). Paragraph-only splitting cannot do F1.

S7. Assumption, measured 2026-10-19, not an owner number: the pair encode length equals the sum of the two single-sequence encodes (4 specials: `<s> q </s></s> t </s>`). The longest gold question encodes to 62 tokens (`privado:A-1`). Part ceiling is 960 (`1024 - 64`), so that question fits with 2 tokens of slack. Membership stays "indexed text > 1024". A unit of 1006 tokens is not split; a long question can still clip it. Do not expand the parent set to close that residual.

S8. Article-count gate counts identities (strip one trailing `#parte-<digits>`), so one split article still counts as one toward 1383. Non-article inventory accepts parts as covering the declared key and does not inflate `no_articulos_declarados`. A parent stored beside its parts fails. `tipo_chunk` stays the parent's. No new CHECK, no new alembic.

S9. Gold keeps the same question text. Expected keys move to the part that contains the supporting span. Parent-key credit is rejected. D-8's ratified answer quotes three definitions inside `8560#5` (cuneta, titular de la vía, zona de camino); if they land in different parts, `citas_esperadas` lists those parts. T-1 and T-2 move `10679#vigencia-de-los-fondos` and `citas_vigencia` to the part that contains that item's span. hit@5 stays "any expected key in the first 5". Citation-precision's denominator grows with the key list. Private gold questions carry no citation keys; the public yaml is the only remap.

S10. After the split, `10593#1` and `8560#5` are not single units and must not be reported as over the 8192 embedding ceiling. The embedding gate still records and does not truncate. Fixture tests that pass a synthetic `8560#5` without loading the corpus keep that key.

## Tasks

- [x] T1 Splitter, parse hook, ingest loads the real tokenizer or raises, gates count identities. Route: inline. Tests: `tests/test_rag_f1_rechunk.py` — 17 passed, 2026-10-19, working-tree corpus. Openspec F1 stays open until T3. A re-ingest that changes keys clears embedding provenance in the same transaction.
- [x] T2 Remap D-8, T-1 and T-2 to the part keys the splitter actually emits. Route: inline. Commit: `57ce9c5a` (with T1, one work unit, one future PR). `tests/new` canary updated; that file was not executed here (its conftest exits without a database).
- [x] T3 Re-measure hit@5 on the same 29. 2026-10-20, local only. `bm25_ce`, reranker `bge` on CUDA, corpus pin `12043582`, 22/29 = 0.7586. Retrieval bars pass. Enablement verdict stays NO EVALUABLE because decision 0.1 is open. Openspec F1 checkbox checked from this measurement on 2026-10-20.

## Log

L1. 2026-10-19. "sisi arranca por f1".

L2. 2026-10-19. "Las 49 (Recommended)" — answer to which units to split, flag off.

L3. 2026-10-19. Measurement before the splitter: 49 units over 1024 real tokens; pair length equals the sum of the two encodes; max gold question 62 tokens; max repeated prefix 147 tokens; seven lines do not fit a 960 budget until split on `. `; those sentences then fit. `estimate_tokens` is not the membership test.

L4. 2026-10-19. Pin `12043582bf8016288a7e8084e85a4b713a97af2f` via `git show` (worktree not checked out): 1448 units, 49 over 1024, 0 heading failures. Pin is an ancestor of corpus HEAD `f55b96fa`. `ley-8560-transito-cordoba.md` and `ley-10679-modificatoria-ctp-fda.md` have no diff pin..HEAD. The F1 pytest ran on the working tree, which is 20 commits ahead and has one untracked path; its heading failures match the unsplit parse of that same tree and are not caused by the split. Do not edit corpus markdown to silence them. Ingest of this checkout still refuses the SHA mismatch.

L5. 2026-10-19. Gold remap, same question texts. D-8 `subclase: compuesta`, keys `8560#5#parte-5` (franja existente), `#parte-9` (titular de la vía), `#parte-10` (propiedades frentistas). T-1 vigencia `10679#vigencia-de-los-fondos#parte-1` (keeps `10679#17` and `9750#39`). T-2 vigencia `#parte-2` (keeps `10679#20`). `#parte-8` is a recap and is not a second key. `#parte-3` holds the 0.42% figure and is not an expected key. Parent keys are absent. Corpus test on the working tree found those spans. hit@5 not re-measured.

L6. 2026-10-19. Owner: "un solo pr". Delivery is one PR, `size:exception`, not a chain and not a stack onto main. Work-unit commit `57ce9c5a`. At this log line the branch was still local. Pre-commit lenses: readability found nothing; resilience found that a re-ingest which replaces keys deletes parent vectors and left `embedding_modelo` set, so vector/hybrid would skip the new NULL parts and still claim the snapshot was embedded. Fix: the same transaction clears that provenance and the CLI prints `embeddings: CLEARED`. Unchanged keys do not clear it. `bm25_ce` does not read the vector columns. risk and reliability lenses refused to read the worktree (no review binding); they are not a clean bill.

L7. 2026-10-20. Owner: "dale pushea y abri el pr". Pushed `feat/rag-f1-rechunk`. PR 575 against `main`: https://github.com/JNZader/consorcio-canalero/pull/575. Not auto-merged. hit@5 still not re-measured. Openspec F1 stays open.

L8. 2026-10-20. Owner: "dale" on measuring hit@5 locally. Ingest of pin `12043582` into a new local database `consorcio_rag_eval` on 127.0.0.1:15432 (not the app database, not the host in `.env`). 1578 rows, 179 `#parte-` rows, parents `8560#5`, `10593#1` and `10679#vigencia-de-los-fondos` absent, provenance empty. Eval `bm25_ce` + real `bge-reranker-v2-m3` on the RTX 5060 Ti (torch 2.11.0+cu128, capability 12.0). hit@5 22/29 = 0.7586 (bar 0.72, pasa). hit@10 0.8276, MRR 0.5556, citation-precision 0.368, norma-vs-secundaria 1.0, vigencia 1.0. D-8, T-1 and T-2 hit. Misses by id: D-7, C-6, C-9, T-4, T-5, V-3, Q-2. Go/no-go is NO EVALUABLE only because abstention recall/precision have no ratified signal (decision 0.1). Report left under `/tmp/f1-rag-eval/`, not committed. Openspec F1 checkbox not edited.

L9. 2026-10-20. Owner: "Asentar F1 y después F2". Checked the F1 box in `tasks.md` and replaced the design rider sentence that said hit@5 was not re-measured. Numbers are the L8 measurement. Decision 0.1 stays open. Flag stays off. Production index not re-ingested. F2 not started. L5 and L7 still say "not re-measured" because that was true on those dates.

L10. 2026-10-20. Owner: "sí a las cinco". D-9..D-13 are in `gold_set.yaml`, public, `validado_por: owner`. D-10 names Ley 8803 because the chat wording was anaphoric. Unanswerable stays 23. Local `bm25_ce` on the same pin and the same lab database: hit@5 27/34 = 0.7941. All five new items hit at rank 1. Miss ids unchanged. Retrieval bars pass. Enablement stays NO EVALUABLE. Flag off. F2 checkbox checked from this measurement. Not committed.
