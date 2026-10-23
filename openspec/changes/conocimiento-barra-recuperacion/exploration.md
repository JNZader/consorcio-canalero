# Exploration: conocimiento-barra-recuperacion

Phase: sdd-explore (investigation only; no product code, tests, bar file, gold or corpus touched; no ingest; no new `rag_eval`; no commit).
Corpus: `ecab0a0ed9cfbfb7bca0f7673f0283bc75bb406e` (checkout HEAD verified unchanged, working tree clean).
Mode under test: `bm25_sin_ce` only. Evidence grade: **executed** unless marked otherwise.

## Bottom line

- T-5 is **not** a corpus hole and **not** recoverable by BM25-level changes. `5589#276` is in the corpus with a full body, and so is the replacement regime. It sits at BM25 rank 54. No BM25 lever tested gets it into the top 10.
- hit@5 >= 0.72 is reachable **in-sample** with BM25-only changes, but at zero slack (25/34) and chosen from a grid on n=34 with no held-out split.
- vigencia = 1.00 is independent of hit@5. The only way to put `5589#276` on the k=10 page without touching corpus or gold is a new page-composition mechanism (citation follow). That is outside query construction, tokenization and chunking, and the owner has not authorized it.
- Recommendation: **stop** at an owner decision gate. `sdd-propose` only if the owner explicitly authorizes the citation-follow mechanism.

## Method and verification of the recorded measurement

- Read `docs/rag/retrieval-eval-ecab0a0e-2026-10-23.{md,results.json}` and `barra_sin_gpu.yaml`. Bar state `no_superada`, hit@5 22/34 = 0.6471, separacion 1.0, vigencia 2/3. Migration misses empty. The 12 retrieval failures match the prompt.
- Reproduced the `bm25_sin_ce` path read-only against the lab DB (container `consorcio-rag-lab`, `127.0.0.1:15433`, session forced `default_transaction_read_only=on`, asserted). It uses the real app code: `expandir_consulta_recuperacion` -> `lexemas_de_consulta` (Postgres `to_tsvector('spanish', ...)`) -> `IndiceBM25.buscar`, over the norma units.
- **Parity**: the reproduced top-10 equals `claves_devueltas` in the results JSON for all 34 answerable items, and hit@5 = 22/34. Probe scripts live in `/tmp` (outside the repo).
- Lab snapshot: 2005 units, 1917 norma units (`bm25.py`'s docstring still says 1398; stale, harmless).
- Prior probe verified against the JSON and the full ranking:

| item | expected key (BM25 rank) |
|---|---|
| C-1 | 9750#20 (6), 9750#6 (252), 10demayo#res005-2026#art1 (91) |
| C-3 | 9750#16 (8), 9750#33 (9) |
| V-1 | 9750#3 (8), 5589#202 (980) |
| D-8 | 8560#5#parte-5 (10), parte-10 (20), parte-9 (352) |
| D-2 | 9750#15 (20) |
| D-3 | 9750#24 (20) |
| D-4 | 1315-2012#4 (12) |
| D-6 | 9867#24 (52) |
| C-2 | 9750#22 (14), 9750#11 (18) |
| C-5 | 9750#3 (12), 9750#21 (18), 9750#39 (507) |
| T-4 | 11059#1 (1071), 11059#3 (247), 10936#12 (90) |
| T-5 | 5589#244 (**11**), 5589#276 (54), 5589#275 (477) |

  The "absent from top 10" claims hold. Correction: T-5's `5589#244` is rank 11, not deep. T-5 top 5 is exactly `6604#11, 11059#16, 8560#41bis, 5589#180, srh-2013#punto-3#parte-4`.
- Need +3 hits (22 -> 25) for 25/34 = 0.735. 24/34 = 0.706 fails.

## Q1. Is T-5 recoverable by BM25?

**No for vigencia; hit@5 is a near miss only for `5589#244` (rank 11).**

Query construction in this path: `pregunta` -> `expandir_consulta_recuperacion` (identity for T-5; none of the five appends fires) -> Postgres Spanish stemming -> 8 distinct lexemes -> BM25 (k1 1.2, b 0.75, epigraph weight 2) over norma units, top 50, first k=10 are the page. One of the 8 lexemes (a colloquial verb stem) does not exist in the norma corpus, so it contributes nothing.

Corpus text (`ley-5589-codigo-aguas-cordoba.md`, and the indexed `texto_indexado` in the lab DB):

- **The prompt's hypothesis is false.** `5589#276` is not "DEROGADO plus a pointer". Its indexed body is 191 words: the derogation note (Ley 11027 art. 32), the word DEROGADO, and the **full derogated text** of the article "kept for traceability". Its `tsv` contains the `derog` lexeme.
- `5589#244` (113 words) states the functional-exercise rule and cites arts. 275 and 276 in its last sentence. `5589#275` (129 words) is the fines article.

Query overlap (shared lexemes / 8): 244 shares 3, 276 shares 2 (one generic stem plus the epigraph stem), 275 shares 1 (one generic stem). The top-5 units win on high-idf incidental stems (a corporate-noun stem in `6604#11`/`11059#16`, a rare noun stem in `8560#41bis`, another in `srh-2013#punto-3#parte-4`), not on the legal subject.

Scores (BM25): rank 1 = 10.60, rank 5 = 8.63, rank 10 = 7.65. `5589#244` = 7.62 (rank 11, 1.01 below rank 5). `5589#276` = 5.82 (rank 54, 1.83 below the page edge). `5589#275` = 1.78.

**The "replacement regime is not in the corpus" comment in the public gold is stale at this SHA.**

- Ley 11027 (`ley-11027-tribunal-administrativo-ambiental.md`, art. 12 "Sanción conminatoria", art. 32 = the derogation) and Decreto 198/2025 Anexo I are in the corpus and ingested, `es_secundaria = false` (MANIFEST F-1 and NL-6 are marked closed; integrations 6 and 7).
- The gold simply never lists them in `citas_esperadas`. In the T-5 ranking `11027#12` is rank 60 and `11027#32` is rank 255.
- I did not change the gold. The owner should know that the comment, not the corpus, is what claims a hole.

Side observation (outside scope, no action): `estado_vigencia` is document-level (the whole 5589 reads VIGENTE), so `vigencia_correctness` only checks that the caveat key is on the page and that every norma hit has a non-null state. The DB check constraint `ck_rag_documento_estado_vigencia_derecho_aplicable` makes the second half always true for norma units. For T-5 only key presence matters.

## Q2. The four near misses

| item | gap to rank 5 | what outranks it | classification |
|---|---|---|---|
| C-1 `9750#20` (6) | **0.18** (10.19 vs 10.37) | `9750#11, res4-2026#anexo#art28, 9750#43, 6604#40, res4-2026#anexo#art50`: same 4 matched lexemes, shorter or higher-tf | movable only at a tie, via `b = 0.9`; fragile |
| C-3 `9750#16` (8) | 3.17 | `10417#13, 8614#20, 10417#14, 8614-consolidada#20, 6604#26` | **movable, general lever** |
| V-1 `9750#3` (8) | 1.88 | `5589#193sextus, 5589#53, 5589#36, 198-2025#anexo-i#art18, res-srh-157-2013#considerandos-pasajes-verificables` | content/lexical dispersion, not movable |
| D-8 `8560#5#parte-5` (10) | 1.82 | `res-dnv-908-2026#anexo-ii#norma10, res-bioagro-147-2026#art1, res-srh-157-2013#art1, 5589#220, 318-2007#anexo#art27` | movable only by length normalization, with collateral cost |

Mechanisms and falsifiable hypotheses (all results in-sample on the ratified gold):

- **C-3, H-interrogative.** The Postgres `spanish` config drops *qué/para/ante/hay* but keeps *dónde, cuánto, cuándo, cuál, quién, cómo* (verified with `to_tsvector`). C-3 carries two of them. They carry about 10 of 24 idf points of the query and match incidentally in `10417#13` / `8614#20` / `6604#26` (not the legal subject). *Falsified if* removing the closed set {com, cual, cuand, cuant, dond, quien} from the parsed query lexemes did not move `9750#16` into the top 5, or lost a passing item. *Result*: C-3 rank 8 -> 4, 0 items lost, +1 hit (12 of 34 items carry such a stem). This is query construction after Postgres stemming, so the analyzer stays untouched.
- **C-1, H-tie.** The gap is 0.18 and the outrankers share the same lexemes. They are shorter, so stronger length normalization favors them less. *Falsified if* no principled change moved it to <= 5. Tested: twin collapse, idf floors 0.5-2.0, interrogative drop and epigraph weight 1-10 do not move it. In the 63-cell k1/b grid exactly 2 cells reach rank 5: `b = 0.9` with k1 0.9 or 1.2. Neither loses a passing item (23/34). So C-1 is movable, but by a 0.18 tie that flips with one parameter, and `b = 0.9` pulls **against** D-8, which wants low `b`.
- **V-1, H-dispersion.** The query has 13 lexemes (1 absent from the corpus, 3 below idf 0.2). The expected unit matches 5/13; the top five match 4-6/13 with more idf mass. Dropping low-idf lexemes (floors 0.5-2.0) or interrogatives does not move it (best rank over the 63-cell k1/b grid is 7). Only a keyed vocabulary append could move it. That is gold fitting (see Risks). Numbers only here: V-1 is `origen: privado`.
- **D-8, H-length.** `8560#5` is the traffic law's definitions article, split into 11 parts of about 3.7k characters by the reranker-window splitter. The expected parts have doclen 337-357 against 74-183 for the outrankers, and the long-tail lexeme with the highest idf (7.15) matches no expected part. Lowering `b` helps (27 of 63 k1/b cells reach rank <= 5), but low `b` costs others. The only other lever is the chunk boundary, which changes the citation keys. That breaks the gold-key pin that `derivar_desde` refuses to bridge, and it needs a re-ingest. Not legal here.

Other levers measured, none of which moves a near miss:

- **Exact-twin collapse**: Ley 8614 and `8614-consolidada` give 58 exact-text twin pairs and occupy up to 4 top-10 slots (D-4). Collapsing them gives D-4 12 -> 8 and C-5 12 -> 11, still misses. No gold expected key belongs to those documents.
- **Epigraph weight** 1/2/3/5/10: never gains, loses Q-2 at 5 and 10.
- **idf floor** >= 1.5: loses D-5 and Q-2.

## Q3. Independence result

`vigencia_correctness` for T-5 requires `5589#276` in the first 10 hits (`metrics.py:218-235`). Clearing hit@5 does not touch that.

Executed reachability sweeps on the 252 configurations of {interrogative drop} x {twin collapse} x {7 k1 x 9 b values}:

| outcome | result |
|---|---|
| best rank of `5589#276` over all configs | 15 |
| configs with `5589#276` <= 10 | **0 / 252** |
| max hit@5 | 26 |
| configs with hit@5 >= 25 | 4 |
| rank of 276 in those 4 configs | 83-92 (worse than baseline 54) |

So the answer to "does clearing hit@5 clear vigencia" is **no**, and the two bar halves pull in opposite directions in the k1 = 0.4 region.

hit@5 >= 25 does exist in-sample, but it is fragile:

- Ridge at k1 = 0.3-0.5, b >= 0.6-0.75, with interrogative drop + twin collapse. At k1 0.4 / b 0.75 it gains D-4, D-8, C-3 and loses nothing (25/34).
- The k1 0.4 row runs 19-26 across b, and its neighbours drop to 21-25. The current constants (k1 1.2, b 0.75) with both fixes give 23, and 24 with `b = 0.9`. One item short of the bar without moving k1.
- The margin over the bar is exactly one item. The ratified constants are described in `bm25.py` as "constants of the ratified configuration, not knobs". The grid has 252 cells on 34 items, with no held-out split.

What *can* put `5589#276` on the page:

1. **Citation follow** (new page-composition mechanism). In the T-5 top 10, `5589#180` (rank 4) and `5589#187` (rank 6) both literally cite "art. 276 de este código". Surfacing the unit cited by a page member would put 276 on the page from the page's own evidence. About a dozen units in 5589 cite art. 276 (the MANIFEST counts twelve dangling remissions), and `11027#32` is the derogating article. Not query construction, tokenization or chunking. It is not a ranker, reranker, embedding or vector arm, so it is not on the owner's excluded list. It would change page size or composition (hit@10 / MRR / citation-precision exposure, with citation-precision 0.407 against a 0.33 bar).
2. **A keyed append that names the answer** (for example the article's own epigraph words). That is the answer fed back into the query, a retrieval trick for the metric. Not recommended and not tested.

## Approaches

| # | Approach | Pros | Cons | Effort |
|---|---|---|---|---|
| A | Stop. Keep `no_superada`, rank order off | Honest; nothing to unwind | Bar stays unmet for this SHA | None |
| B | BM25 package: interrogative stoplist + twin collapse (+ k1/b change) | General language-level levers; +1 to +3 hits in-sample, 0 lost | Reaches the hit@5 half at best; zero slack; in-sample selection; moves ratified constants; does **not** fix vigencia | Low-Med |
| C | B + citation follow for 276 | Only path that clears both halves without touching corpus or gold | New mechanism the owner has not authorized; page contract and metric exposure; looks built for the metric | Med-High |
| D | Item-keyed appends in `expansion.py` | Fits the existing pattern (5 appends already) | Pure gold fitting at n=34; certificate would attest memorization; not tested by design | Low |

## Recommendation

Approach A now. If the owner wants to continue, the question is one decision, not a code phase: authorize or reject citation follow (C). Without that, B alone cannot flip the bar (vigencia stays 0.667) and would only change a shipped query path for an in-sample gain.

## Risks

- **In-sample only.** The gold (n=34) is the only evaluation set. Every figure above was produced by looking at it. The interrogative hypothesis was formed after reading C-3.
- **Gold fitting is already a pattern.** `expansion.py` holds five item-conditioned appends, each validated as "fires only on item X". More of them would not be neutral engineering.
- **Metric blind spot.** vigencia checks key presence and non-null state; the 5589 document reads VIGENTE although art. 276 is derogated.
- **Stale gold comment** about the missing replacement regime (Ley 11027 and Decreto 198/2025 are ingested at this SHA). Gold is locked; owner awareness only.
- **Test name drift.** `test_solo_bm25_ce_expande` only pins `bm25_ce`; `_recuperar_bm25_sin_ce` also calls the expander. No test in `tests/` references `_recuperar_bm25_sin_ce` by name.
- **Probe fidelity.** The probe re-implements BM25 ranking over the same index and reproduces the recorded top-10 exactly, but variants (stoplist, collapse, grid) are probe code, not product code.

## Ready for Proposal

No, not without an owner decision. Tell the owner: T-5 is not a corpus hole (Ley 11027 is in the corpus); vigencia needs `5589#276` on the page and no BM25 change does that; hit@5 can reach 25/34 only in-sample at zero slack. The one open question is whether to authorize citation follow.

## Skill resolution

`paths-injected`. From `rag-advanced` only the evaluation discipline was kept (measure retrieval separately; no reranker, second ranker, embeddings, HyDE or hybrid vector arm).
