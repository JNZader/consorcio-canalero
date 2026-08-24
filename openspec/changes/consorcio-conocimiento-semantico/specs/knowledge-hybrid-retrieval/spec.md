# Delta for knowledge-hybrid-retrieval

## REMOVED Requirements

### Requirement: No User-Facing Surface in V0

(Reason: V0 deliberately shipped no surface and asserted its absence; V1's whole purpose is to put the measured layer in front of the Comisión Directiva. The prohibition is superseded by the gated-surface requirement added below, not merely relaxed.)
(Migration: `gee-backend/tests/new/conocimiento/test_rag_no_router.py` — the test that asserts the router's absence — is retired and replaced by tests for the gated surface: unauthenticated, `ciudadano` and `operador` callers are denied, and the surface is absent while the feature flag is off. Retiring that test without those replacements would leave the endpoint's access boundary unasserted.)

## ADDED Requirements

### Requirement: Gated CD-Only Serving Surface

The retrieval and answer surface MUST be reachable only under `require_admin`, MUST be rate-limited, and MUST be governed by a feature flag that is **OFF by default**. While the flag is off, the endpoint MUST behave as if it did not exist for every caller, including an admin. Authorization MUST be enforced server-side; hiding the page in `consorcio-web` MUST NOT be the only gate. `require_admin` is a documented approximation of Comisión Directiva membership, not an equivalence.

#### Scenario: Anonymous caller is denied

- GIVEN the feature flag is on and no credentials are presented
- WHEN the Q&A endpoint is called
- THEN the call is rejected with 401
- AND no retrieval or generation runs

#### Scenario: `operador` and `ciudadano` are denied

- GIVEN the feature flag is on and a valid `operador` (or `ciudadano`) token
- WHEN the Q&A endpoint is called
- THEN the call is rejected with 403
- AND no retrieval or generation runs

#### Scenario: Flag off means the surface is inert even for an admin

- GIVEN the feature flag is off
- WHEN an admin calls the Q&A endpoint
- THEN the endpoint does not serve an answer
- AND the deployment's default state, with no flag explicitly set, is off

#### Scenario: Hiding the web page is not the access boundary

- GIVEN the `consorcio-web` page is not rendered for a non-admin user
- WHEN that user calls the API directly with their own token
- THEN the API rejects the call on its own

### Requirement: Vector-Capable Database Enablement and Ordered Rollback

Enabling the vector leg on the deployed box requires swapping Postgres to the `consorcio-postgres:16-vector` image on a shared volume that also serves PostGIS, pgRouting and Martin. The swap MUST NOT proceed without a **verified** backup — existence of a backup file is not verification. After the swap, the vector extension AND the geo stack MUST both be verified before the surface is enabled. Rollback MUST follow the sealed order: **surface first (unmount router / flag off), then `alembic downgrade conocimiento_001`, then the image**. Reverting the image while vector objects are live MUST NOT be performed, as it leaves an unloadable database on the persistent volume.

#### Scenario: Unverified backup blocks the swap

- GIVEN a backup whose restorability has not been verified
- WHEN the image swap step is reached
- THEN the swap does not proceed

#### Scenario: Geo stack is verified before the surface is enabled

- GIVEN the image swap completed and the vector extension is present
- WHEN the enablement check runs
- THEN PostGIS, pgRouting and Martin tile serving are each verified working on the box
- AND the feature flag is turned on only after all of them pass

#### Scenario: Rollback runs surface, migration, image — in that order

- GIVEN a decision to roll back after the surface was enabled
- WHEN rollback executes
- THEN the surface is disabled first
- AND `alembic downgrade conocimiento_001` runs before any image change
- AND the Postgres image is reverted only after the vector objects are gone

#### Scenario: Image is never reverted with vector objects live

- GIVEN the vector column, index or extension still exists in the database
- WHEN a rollback of the Postgres image is attempted
- THEN it is refused until the downgrade has run

## MODIFIED Requirements

### Requirement: Go/No-Go Thresholds and Gold-Set Precondition

The report MUST NOT score any go/no-go threshold until the answerable gold set reaches n≥20. Once evaluable, the report MUST compute hit-rate@5 ≥ 0.85, MRR ≥ 0.70 (answerable set), citation-precision = 1.00, norma-vs-secundaria separation = 1.00, vigencia-correctness = 1.00, abstention recall = 1.00 (strict — a single false-confident answer fails go/no-go), and abstention precision ≥ 0.80.

The abstention threshold MUST be selected by leave-one-out cross-validation over the gold set, per ablation mode, and the abstention pair MUST be scored on the held-out predictions. A figure produced by selecting and scoring on the same sample MUST NOT decide go/no-go and MUST be labeled an upper bound wherever reported. The report MUST disclose the selection methodology, `n`, and which figures were fitted.

**V1 serving gate** *(AMENDED 2026-08-23, owner-ratified from measurement — `design.md:1118-1155`. The gated arm and the numeric bars both change; the cross-validation and disclosure rules above do not.)*

FTS-only remains a **measured NO-GO**: hit-rate@5 `0.138`, MRR `0.091`, citation-precision `0.040`. No serving surface MAY be enabled on those numbers.

The arm that MUST clear the gate is no longer `hybrid` but **`bm25_ce`** (configuration `B50`): real BM25 candidate generation with IDF over `es_secundaria = false` units at depth 50, ranked by `bge-reranker-v2-m3` over exactly those candidates. The vector leg is OUT of candidate generation, measured: the exhaustive cross-encoder ceiling over all 1398 norma units scores `0.724`, BELOW `B50`'s `0.759`, so a bounded pool is also a precision filter. `ts_rank_cd` MUST NOT be the candidate scorer (measured `0.655` against BM25's `0.759`). No lexical signal MAY enter the cross-encoder score (RRF `−0.035`/`−0.069`; CE×lexical `−0.104`/`−0.207`), and a per-document cap MUST NOT be applied (it lifts hit-rate@5 to `0.793` while collapsing vigencia-correctness to `0.333`).

The bars the `bm25_ce` arm MUST clear are the **re-ratified** ones: hit-rate@5 ≥ `0.72`, hit-rate@10 ≥ `0.80`, MRR ≥ `0.55`, citation-precision ≥ `0.33`, norma-vs-secundaria = `1.00`, vigencia-correctness = `1.00`. Citation-precision = `1.00` is unreachable by construction on this gold set and its former bar is superseded rather than waived; the two `1.00` bars are NOT relaxed and MUST NOT regress. The report MUST publish the `bm25_ce` arm side by side with the recorded FTS-only baselines so the margin is visible rather than asserted, and MUST carry the honesty rider that the answerable gold set is `n = 29`, where one question is worth `0.034` hit-rate@5. If the arm does not clear the bar, the change MUST stop at this gate; a lower threshold MUST NOT be substituted to make it pass.

The abstention pair is explicitly **OPEN** (owner decision 0.1) and MUST NOT be scored from an unratified signal: reranker confidence measured worse than cosine (LOOCV precision `0.489` at recall `1.000`). Until a signal is ratified, the `bm25_ce` abstention row is `not-evaluable` and the surface is not enabled.
(Previously: the same thresholds and cross-validation rules, with no V1 serving gate — V0 had no surface to gate. Before this amendment the V1 gate named the `hybrid` arm and the pre-measurement bars hit-rate@5 ≥ 0.85, MRR ≥ 0.70, citation-precision = 1.00.)

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

#### Scenario: Serving is not enabled on FTS-only numbers

- GIVEN only the FTS-only arm has been scored, at hit-rate@5 `0.138`, MRR `0.091`, citation-precision `0.040`
- WHEN enablement is considered
- THEN the surface is not enabled
- AND the change stops at the gate rather than shipping a measured-bad answerer

#### Scenario: Hybrid arm is published against the recorded baseline

- GIVEN a scored hybrid arm on real BGE-M3 vectors
- WHEN the report is published
- THEN it shows hit-rate@5, MRR and citation-precision for the hybrid arm next to the FTS-only baselines `0.138` / `0.091` / `0.040`
- AND the comparison is computed from the same gold set

#### Scenario: The gated arm is `bm25_ce`, on its re-ratified bars

*(ADDED — owner-ratified amendment, 2026-08-23.)*

- GIVEN a `bm25_ce` run whose candidates are BM25 top-50 over norma units and whose order is the cross-encoder score alone
- WHEN the serving gate is evaluated
- THEN it is scored against hit-rate@5 ≥ `0.72`, hit-rate@10 ≥ `0.80`, MRR ≥ `0.55`, citation-precision ≥ `0.33`, norma-vs-secundaria = `1.00` and vigencia-correctness = `1.00`
- AND a run whose candidate scorer is `ts_rank_cd`, whose ranking blends any lexical signal, or which applies a per-document cap does NOT satisfy the gate, whatever its hit-rate

#### Scenario: A synthetic ranker cannot open the gate

*(ADDED — owner-ratified amendment, 2026-08-23.)*

- GIVEN a `bm25_ce` run ranked by a deterministic stand-in rather than `bge-reranker-v2-m3`
- WHEN the serving gate is evaluated
- THEN that run does not satisfy the gate, for the same reason a synthetic-embedding run does not

#### Scenario: A synthetic-embedding hybrid run cannot open the gate

- GIVEN a hybrid arm scored against smoke or synthetic vectors rather than the real BGE-M3 batch
- WHEN the serving gate is evaluated
- THEN that run does not satisfy the gate

### Requirement: Privacy Boundary on External Services

*(MODIFIED — owner-ratified amendment, 2026-08-23. V0 permitted external services only as a bounded eval baseline; the owner explicitly ratified hosted GENERATION for the V1 answer surface, with the strict per-request classification condition below. Embeddings and question routing remain LOCAL — the question text leaves the deployment only for the final answer-generation call.)*

*(WIDENED — sealed owner product decision, 2026-08-23, bounded correction. The shippable set is `{publico, institucional}`, not `{publico}` alone: what may travel is published public law (gazette/registry-sourced) AND the consorcio's OWN normative instruments — estatuto, resoluciones del Consejo Directivo, registro administrativo. Technical reports and every other fuente secundaria stay private. The first wording admitted only gazette-published law and therefore classified the consorcio's own constitutive act as private, which made questions about the consorcio's own rules unanswerable by construction. This widening changes the admitted SET, not the mechanism: derivation is still from frontmatter, verification is still per unit and per request, and exclusion is still per unit rather than a whole-request refusal.)*

The system MUST NOT send private consortium document content to any external embedding, inference, or judge service. Sending public-domain law text to an external service is permitted (a) as an explicit, bounded eval comparison baseline, and (b) *(amended)* as the input context of the production ANSWER-GENERATION call, under these conditions, all mandatory: document classification is derived from corpus frontmatter (never hardcoded); every retrieved unit in the generation payload MUST individually verify at request time (`assert_unidades_publicas`) that its `clasificacion` is in the shippable set `{publico, institucional}` — a single non-shippable unit in the retrieval set excludes that unit and, if exclusion leaves the context empty, the system abstains rather than widening; every fuente-secundaria document MUST be classified `privado` and is therefore never shippable; the CD-authored question text travels ONLY to the generation provider, never to any embedding, routing, or judge service; and no LLM-as-judge external call exists on any path. The production embedding and retrieval paths remain strictly local.

*(The eval comparison baseline of clause (a) is NOT widened: it stays bounded to public-domain, SAIJ/BO-sourced corpus text, per its own scenario below. An `institucional` document is cleared for the answer path, not for a corpus-wide comparison against a third-party embedding service.)*

#### Scenario: Generation payload is verified per request against the shippable set

- GIVEN a question whose retrieval set contains a unit whose frontmatter-derived classification is neither `publico` nor `institucional`
- WHEN the answer-generation call is assembled
- THEN that unit is excluded from the payload before any external call
- AND if exclusion empties the context, the system abstains with the honest no-answer state instead of calling the provider

#### Scenario: A consorcio instrument is shippable and a fuente secundaria is not

*(ADDED — sealed owner product decision, 2026-08-23.)*

- GIVEN a retrieval set containing one `institucional` unit (the consorcio's own normative instrument) and one unit of a fuente-secundaria document
- WHEN the generation payload is assembled
- THEN the `institucional` unit is included in the payload
- AND the fuente-secundaria unit is excluded from it
- AND the answer may cite the `institucional` unit, whose key is a valid member of the payload

#### Scenario: Question text reaches only the generation provider

- GIVEN any incoming question
- WHEN it is embedded, routed, and (if legal) answered
- THEN the embedding and routing computations run locally
- AND the question text appears in exactly one external payload: the generation call

#### Scenario: API-embedding baseline stays bounded to public law text

- GIVEN the eval harness's optional API-embedding comparison baseline
- WHEN it runs
- THEN it operates only on the current public-domain (SAIJ/BO-sourced) corpus text, never on private documents

#### Scenario: Private document content never reaches an external call

- GIVEN a hypothetical private document (e.g. a future actas record)
- WHEN any embedding/inference/judge call is made
- THEN its content is excluded from that call's payload
