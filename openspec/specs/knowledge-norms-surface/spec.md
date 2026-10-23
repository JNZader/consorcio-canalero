# Knowledge Norms Surface Specification

## Purpose

Expose cited legal units, with vigencia, norma-vs-secundaria status and the served corpus SHA, through a synchronous admin-only route that is gated independently from the question mailbox and generates no prose.

## Requirements

### Requirement: Independent Norms Gate

`conocimiento_normas_enabled` MUST default to `false`. `enforce_conocimiento_normas` MUST be satisfied only by the norms flag AND an active corpus AND an admin caller. It MUST NOT require the QA terms record, a provider credential or the embedder sidecar. `enforce_conocimiento_qa_enabled` and the question mailbox MUST be unchanged.

#### Scenario: Default is closed

- GIVEN a settings object with no override
- WHEN the norms route is called by an admin
- THEN it answers 503 and `conocimiento_normas_enabled` is `false`

#### Scenario: QA off, norms on

- GIVEN `conocimiento_qa_enabled=false`, `conocimiento_normas_enabled=true`, an active corpus, and no terms record, credential or sidecar
- WHEN an admin calls the norms route and the question mailbox
- THEN the norms route answers 200 and the mailbox answers 503

#### Scenario: Gate refusals name their cause

- GIVEN the norms flag is on
- WHEN the caller is not an admin, or no active corpus exists
- THEN the route refuses (never 200) and, for the missing corpus, names the no-active-corpus cause

#### Scenario: Rollback leaves the mailbox untouched

- GIVEN the norms flag is set back to `false`
- WHEN both surfaces are called
- THEN the norms route answers 503 and the mailbox behaves exactly as before

### Requirement: Norms Response Schema

Every returned unit MUST carry its verbatim `texto`, citation key, `tipo`, `es_secundaria`, `estado_vigencia`, `jurisdiccion` and `relevancia_consorcio` as ingested. The response MUST carry `modo`, `corpus_sha` and `ingested_at` of the active corpus row. `es_secundaria` units MUST remain distinguishable from norma units.

#### Scenario: Unit and response provenance

- GIVEN a query that recovers units
- WHEN the response is returned
- THEN each unit has the fields above and the response has `modo`, `corpus_sha` and `ingested_at`

#### Scenario: SHA badge needs no QA surface

- GIVEN the QA flag is off
- WHEN the norms response is returned
- THEN `corpus_sha` and `ingested_at` are present without calling any QA-gated route

### Requirement: Empty Retrieval Is Not Abstention

When no unit is recovered the route MUST answer 200 with an empty unit list and an explicit "no units recovered" indication. It MUST NOT emit an abstention signal, apply an abstention threshold, or claim that no norm applies. Abstention retuning is out of scope and decision 0.1 stays open.

#### Scenario: Nothing recovered

- GIVEN a query that matches no unit
- WHEN the route responds
- THEN the status is 200, units are empty, "no units recovered" is stated, and no abstention field is set

### Requirement: Unranked Until the Bar Is Recorded

The route MUST NOT present a rank order (rank, score or relevance-implying position) unless a recorded measurement of the no-GPU arm shows hit@5 ≥ 0.72 on the answerable items of the 57-item gold, norma-vs-secundaria = 1.00 and vigencia-correctness = 1.00. Otherwise it MUST still return units, MUST omit rank order, and MUST say that no rank order is presented.

#### Scenario: Bar not recorded or failed

- GIVEN no recorded result, or one below any of the three bars
- WHEN the route returns units
- THEN units are present and no rank, score or equivalent field is

#### Scenario: Bar recorded and met

- GIVEN a recorded result meeting all three bars for the active `corpus_sha`
- WHEN the route returns units
- THEN rank order MAY be shown and is labeled with the no-GPU arm id

### Requirement: Arm Labeling

The route MUST serve only the no-GPU arm, whose id MUST differ from `bm25_ce` and every other existing mode id. The CUDA `bm25_ce` result (31/34) MUST NOT label this arm; if shown, it MUST appear only next to the `bm25_ce` arm that produced it.

#### Scenario: Response never claims bm25_ce

- GIVEN any norms response
- WHEN `modo` is read
- THEN it is the no-GPU arm id and not `bm25_ce`, and no 31/34 figure is attached to it
