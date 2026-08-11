# Gold set — provenance record

**Change:** consorcio-rag V0 · **Task:** 4.4 · **Date:** 2026-08-10

This is the traceability record for `gee-backend/app/domains/conocimiento/eval/gold_set.yaml`.
It exists so that a reader of a future eval report can answer three questions
without access to the owner's machine: where the questions came from, who
ratified them, and why some of them are not printed here.

## The ratified source

| field | value |
|---|---|
| document | `eval-preguntas-oro-DRAFT-2026-08-10.md` |
| location | owner-side (`~/Escritorio/consorcio/`), **not** in this repository |
| ratified | 2026-08-10, verbatim, by the owner (Ops O.2) |
| split | 29 answerable + 23 unanswerable = 52 |
| corpus revision | `12043582bf8016288a7e8084e85a4b713a97af2f` |

Composition of the 52:

| block | n | source |
|---|---:|---|
| directas (D-1..D-8) | 8 | drafted against the corpus, ratified |
| compuestas (C-1..C-9) | 9 | drafted against the corpus, ratified |
| trampa-superada (T-1..T-5) | 5 | drafted against the corpus, ratified |
| canal N°5 — 3 veredictos + 4 preguntas para el abogado | 7 | `analisis-legal-canal5-2026-08-05.md` |
| huecos del corpus (X-1..X-5) | 5 | drafted against the declared corpus gaps |
| preguntas para la comisión | 18 | `auditoria-obras-zona-10-de-mayo.md` §5 |

## Why the draft itself is not committed here

This repository is **public**; `consorcio-corpus-legal` is **private**, and every
document it holds is ingested with `clasificacion = 'privado'` under default-deny.
Twenty-six of the 52 questions were transcribed from documents carrying that
classification.

The rule applied is the corpus's own, one layer up: **a question inherits the
classification of the document it was transcribed from.** Committing them here
would be a larger and far more permanent disclosure than the external API call
that `assert_public_domain` already refuses by default.

So:

* the 26 public items carry their text inline in `gold_set.yaml`;
* the 26 private items carry a `pregunta_ref` source anchor and no text, and are
  resolved at run time from the YAML at `RAG_GOLD_PRIVADO_PATH`;
* `test_rag_eval_harness.py::test_no_private_question_text_is_committed_to_this_public_repo`
  asserts the split, so pasting a private question in becomes a deliberate act
  with a failing test attached rather than an accident;
* an unresolved item **blocks the go/no-go** exactly as a `validado_por: draft`
  item does. The privacy split must not become a quiet way to shrink the set.

**This is a safe default, not a ratified decision.** The owner ratified the SET;
the publication surface was never put to him, and none of the SDD artifacts
(proposal, design D6, tasks) mentions repository visibility. Flipping it is a
data move with no code change: paste the text into `pregunta`, drop
`pregunta_ref`, and delete the assertion above.

## Two caveats the source document raises about itself

Recorded rather than resolved, because re-classing a ratified item is the
owner's call and not the apply phase's.

1. **Q-1 (titular de concesión).** The draft's Descartes §1 rejects a duplicate
   of this question as having "no citable answer … zona gris real", while the
   count table lists it among the 7 answerable. Both statements are true of
   different things: V0 measures RETRIEVAL, not legal certainty. The units that
   frame the tension (`5589#238` enables without requiring a concession,
   `5589#239` allows opposing for the lack of one) exist and are retrievable.
   Kept answerable on that reading.
2. **Q-4 (dónde está la reglamentación del art. 235).** The reglamentación is
   not in the corpus — the analysis records it as unpublished. The retrievable
   answer is the article that makes the remission, so `citas_esperadas` is
   `5589#235`.

If the owner disagrees with either reading, both move to `unanswerable` and the
denominators become 27/25. That is a one-line edit per item.

## One key corrected against the corpus

The draft cites `res-dnv-908-2026#anexo2#norma10` / `#anexo2#norma22` as X-2's
declared distractors. The corpus keys those units `res-dnv-908-2026#anexo-ii#norma10`
and `#anexo-ii#norma22`. The corpus's own key wins — this is a key correction,
not a rewording, and `test_every_expected_citation_key_exists_in_the_pinned_corpus`
is what would have caught it had it reached `citas_esperadas`.

## Validation that runs

| check | where |
|---|---|
| 52 items, 29 answerable, 23 unanswerable | `test_loads_with_the_ratified_denominators` |
| every item `validado_por: owner` | `test_every_item_is_owner_validated` |
| ids unique | `test_ids_are_unique` |
| every expected citation key exists in the pinned corpus | `test_every_expected_citation_key_exists_in_the_pinned_corpus` (`corpus`-marked) |
| gold set and expectations pin the same corpus SHA | `test_the_gold_set_pins_the_same_corpus_sha_the_expectations_do` |
| unanswerable items declare no expected citation | `test_unanswerable_items_declare_no_expected_citation` |
| the three vigencia traps declare their caveat key | `test_trampa_vigencia_counts_as_answerable_and_declares_its_caveat_key` |
| T-3 keeps `9750#47` (días hábiles, not 31 March) | `test_the_t3_deadline_item_is_scored_as_ratified` |
| no private text committed | `test_no_private_question_text_is_committed_to_this_public_repo` |
