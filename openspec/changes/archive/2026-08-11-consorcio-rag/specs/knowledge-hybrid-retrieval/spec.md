# Knowledge Hybrid Retrieval Specification

## Purpose

Retrieve cited legal units from the ingested corpus by fusing independent FTS-español and vector queries via Reciprocal Rank Fusion, abstaining below a calibrated confidence threshold, exposing no user-facing surface in V0, and measuring retrieval quality via an offline three-mode ablation harness scored against owner-ratified go/no-go thresholds.

## Requirements

### Requirement: Independent FTS and Vector Fusion by RRF
The system MUST run FTS-español (`ts_rank_cd` over the GIN-indexed `tsvector`) and vector (cosine, HNSW) queries independently, and MUST fuse results solely via RRF (k=60). The system MUST NOT compute or expose a blended/weighted single score.

#### Scenario: Hybrid query fuses via RRF only
- GIVEN a query in hybrid mode
- WHEN FTS and vector queries both execute
- THEN their rankings are combined via RRF(k=60), with no blended score computed or returned

#### Scenario: Either sub-query can fail without corrupting fusion
- GIVEN one query path (FTS or vector) returns zero results
- WHEN fusion runs
- THEN RRF fuses over the available ranking(s) without treating the empty path as a zero score

### Requirement: Result Provenance and Norma/Secundaria Separation
Every retrieval hit MUST carry the unit's verbatim `texto`, its citation key, `tipo`, `es_secundaria`, `jurisdiccion`, `estado_vigencia`, and `relevancia_consorcio`. When both derecho-aplicable and fuente-secundaria units are retrieved for the same query, secundaria hits MUST be labeled distinctly and MUST NOT be presentable as if they were norm. `relevancia_consorcio` MUST be surfaced verbatim as ingested, never summarized or reduced to a derived boolean.

#### Scenario: Hit carries full citation provenance
- GIVEN any retrieval hit
- WHEN returned
- THEN it includes verbatim texto, citation key, tipo, es_secundaria, jurisdiccion, estado_vigencia, and relevancia_consorcio

#### Scenario: Secundaria hit distinguishable from norma
- GIVEN a query that retrieves both art. 3 of Ley 6394 and a secundaria document (e.g. caso-testigo, informe-auditoria) with comparable scores
- WHEN results are returned
- THEN the secundaria hit's `es_secundaria` flag is set and it is never indistinguishable from the norma hit

#### Scenario: Do-not-cite warning reaches the consumer on a derecho-aplicable hit
- GIVEN a query that retrieves a unit of Res. 4/2026 (`tipo: resolucion-ministerial`, therefore `es_secundaria = false`) whose document-level `relevancia_consorcio` states "RÉGIMEN HERMANO … NO debe citarse como fundamento de ninguna obligación ni facultad de un consorcio canalero"
- WHEN the hit is returned
- THEN that warning travels with the hit, so the consumer can tell it apart from a Ley 9750 hit that `tipo` and `es_secundaria` alone would rank as equivalent grounds

### Requirement: Confidence-Threshold Abstention
The system MUST abstain (signal "no norma aplicable encontrada" rather than returning a low-confidence hit) when the fused top result falls below a threshold calibrated against the answerable/unanswerable split of the gold set.

#### Scenario: Unanswerable question triggers abstention
- GIVEN a gold question with no answerable unit in the corpus (e.g. from the audit's institutional-knowledge questions)
- WHEN queried
- THEN the system abstains instead of returning a low-confidence hit

#### Scenario: Answerable question above threshold returns a hit
- GIVEN a gold question with a known correct citation (e.g. the canal N°5 set)
- WHEN queried
- THEN the system returns the hit rather than abstaining

### Requirement: No User-Facing Surface in V0
V0 MUST expose no router or externally reachable endpoint for retrieval; it MUST be invocable only by the offline eval harness or other internal callers.

#### Scenario: No retrieval route mounted
- GIVEN the V0 `conocimiento` domain
- WHEN the API surface is inspected
- THEN no router is mounted and no HTTP endpoint reaches the retrieval service

### Requirement: Three-Mode Ablation Eval Harness
The eval harness MUST run FTS-only, vector-only, and hybrid-RRF modes over the identical gold set, including MANIFEST-derived adversarial vigencia-trap questions, and MUST report metrics separately per mode.

#### Scenario: Same gold set scored across all three modes
- GIVEN the gold question set
- WHEN the harness runs
- THEN it produces three separate metric blocks (FTS-only, vector-only, hybrid) from the same questions

#### Scenario: Vigencia trap surfaces the correct state
- GIVEN an adversarial trap question referencing a derogated or superseded provision (e.g. Ley 8548, Ley 10679 art. 20 post-2023)
- WHEN queried
- THEN the returned hit's `estado_vigencia`/caveat metadata reflects the true current state, not silently the historic text

### Requirement: Go/No-Go Thresholds and Gold-Set Precondition
The report MUST NOT score any go/no-go threshold until the answerable gold set reaches n≥20. Once evaluable, the report MUST compute hit-rate@5 ≥ 0.85, MRR ≥ 0.70 (answerable set), citation-precision = 1.00, norma-vs-secundaria separation = 1.00, vigencia-correctness = 1.00, abstention recall = 1.00 (strict — a single false-confident answer fails go/no-go), and abstention precision ≥ 0.80.

The abstention threshold MUST be selected by leave-one-out cross-validation over the gold set, per ablation mode, and the abstention pair MUST be scored on the held-out predictions. A figure produced by selecting and scoring on the same sample MUST NOT decide go/no-go and MUST be labeled an upper bound wherever reported. The report MUST disclose the selection methodology, `n`, and which figures were fitted.

#### Scenario: n<20 blocks scoring
- GIVEN an answerable gold set with fewer than 20 questions
- WHEN the report is generated
- THEN thresholds are marked not-evaluable rather than scored

#### Scenario: Threshold selection is cross-validated, not fitted on the scoring sample
- GIVEN the gold set and a mode whose abstention threshold is swept over the observed fused-score grid
- WHEN the harness evaluates that mode
- THEN each item's abstention decision uses a threshold selected from the other n−1 items only, and the reported abstention precision/recall are computed over those held-out decisions

#### Scenario: Same-sample figure cannot carry a go/no-go
- GIVEN a mode whose same-sample fit clears recall 1.00 and precision ≥ 0.80 while its cross-validated pair does not
- WHEN go/no-go is determined
- THEN the mode does NOT pass, and the report shows the same-sample figure explicitly labeled as an upper bound alongside the cross-validated figure that decided the outcome

#### Scenario: Any false-confident answer fails go/no-go regardless of other metrics
- GIVEN an eval run where abstention recall is below 1.00 (at least one false-confident answer)
- WHEN go/no-go is determined
- THEN the system does NOT pass, even if every other metric clears its bar

### Requirement: Privacy Boundary on External Services
The system MUST NOT send private consortium document content to any external embedding, inference, or judge service. Sending public-domain law text to an external service is permitted ONLY as an explicit, bounded eval comparison baseline, never as the production embedding or retrieval path.

#### Scenario: API-embedding baseline stays bounded to public law text
- GIVEN the eval harness's optional API-embedding comparison baseline
- WHEN it runs
- THEN it operates only on the current public-domain (SAIJ/BO-sourced) corpus text, never on private documents

#### Scenario: Private document content never reaches an external call
- GIVEN a hypothetical private document (e.g. a future actas record)
- WHEN any embedding/inference/judge call is made
- THEN its content is excluded from that call's payload
