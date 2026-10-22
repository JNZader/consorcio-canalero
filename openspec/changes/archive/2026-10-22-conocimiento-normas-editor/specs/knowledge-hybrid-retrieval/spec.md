# Delta for Knowledge Hybrid Retrieval

## ADDED Requirements

### Requirement: No-GPU Arm Bar Before Rank Order

The harness MUST measure a dedicated no-GPU arm on the answerable items of the 57-item gold and record hit@5, norma-vs-secundaria separation and vigencia-correctness. Rank order MAY be served only when the recorded hit@5 ≥ 0.72 and both separation figures = 1.00. This bar is additive: it MUST NOT replace the existing go/no-go thresholds, and it MUST NOT include or retune abstention (the committed 0.489 at recall 1.000 is unchanged).

#### Scenario: Bar met

- GIVEN a recorded run with hit@5 ≥ 0.72, norma-vs-secundaria = 1.00 and vigencia-correctness = 1.00
- WHEN the bar is evaluated
- THEN rank order may be served for that corpus SHA

#### Scenario: Any figure below the bar

- GIVEN hit@5 of 0.71, or either separation figure below 1.00
- WHEN the bar is evaluated
- THEN it fails and the surface stays unranked

#### Scenario: Gold keys re-validated first

- GIVEN a gold item whose expected key is absent from the active snapshot
- WHEN the arm is scored
- THEN that item is reported as a migration-induced miss, separately from retrieval misses, and the bar is not decided until the keys are re-validated

## MODIFIED Requirements

### Requirement: No User-Facing Surface in V0

V0 MUST expose no router or externally reachable endpoint for retrieval, EXCEPT the norms route defined in `knowledge-norms-surface`, which MUST be separately gated by `conocimiento_normas_enabled` and `enforce_conocimiento_normas`. Every other caller MUST remain internal (the offline eval harness or other internal callers).
(Previously: no router or endpoint for retrieval was allowed at all.)

#### Scenario: No retrieval route mounted

- GIVEN the V0 `conocimiento` domain with `conocimiento_normas_enabled=false`
- WHEN the API surface is inspected
- THEN the norms route is the only retrieval route mounted, and it answers 503 without reaching the retrieval service

#### Scenario: Retrieval route reachable only through the norms gate

- GIVEN the `conocimiento` domain with `conocimiento_normas_enabled=false`
- WHEN the API surface is inspected
- THEN the norms route answers 503 and no other HTTP endpoint reaches the retrieval service

#### Scenario: Norms flag on exposes only the norms route

- GIVEN `conocimiento_normas_enabled=true` and an active corpus
- WHEN the API surface is inspected
- THEN the norms route answers an admin with 200 and no other retrieval endpoint is added

### Requirement: Three-Mode Ablation Eval Harness

The eval harness MUST run FTS-only, vector-only, and hybrid-RRF modes over the identical gold set, including MANIFEST-derived adversarial vigencia-trap questions, and MUST report metrics separately per mode. It MUST also run the dedicated no-GPU arm over the same gold set as its own separately reported block, under its own mode id, never named `bm25_ce`.
(Previously: three modes only; no no-GPU arm.)

#### Scenario: Same gold set scored across all three modes

- GIVEN the gold question set
- WHEN the harness runs
- THEN it produces three separate metric blocks (FTS-only, vector-only, hybrid) from the same questions

#### Scenario: Same gold set scored across all modes

- GIVEN the gold question set
- WHEN the harness runs
- THEN it produces separate metric blocks (FTS-only, vector-only, hybrid, and the no-GPU arm) from the same questions

#### Scenario: Vigencia trap surfaces the correct state

- GIVEN an adversarial trap question referencing a derogated or superseded provision (e.g. Ley 8548, Ley 10679 art. 20 post-2023)
- WHEN queried
- THEN the returned hit's `estado_vigencia`/caveat metadata reflects the true current state, not silently the historic text

#### Scenario: No-GPU arm never labeled bm25_ce

- GIVEN a report that includes the no-GPU arm and a CUDA `bm25_ce` run
- WHEN figures are printed
- THEN each figure carries the id of the arm that produced it, and the CUDA 31/34 never appears under the no-GPU arm
