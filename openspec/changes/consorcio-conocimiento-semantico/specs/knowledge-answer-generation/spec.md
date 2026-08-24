# knowledge-answer-generation Specification

## Purpose

Turn retrieved legal units into an answer a Comisión Directiva member can verify without trusting the model: every claim carries a citation, every citation resolves to a unit that was actually retrieved for that question, and anything the corpus cannot ground is refused out loud instead of written smoothly. Generation sits **above** `knowledge-hybrid-retrieval` and never substitutes for it: a retrieval refusal or abstention is surfaced as such, never converted into prose.

Scope fixed by the approved proposal (2026-08-23): legal corpus only, mandatory citations, Comisión Directiva only, single existing environment. Generation provider and regeneration budget are design-phase decisions and are not fixed here.

## Requirements

### Requirement: Grounded Context — Verbatim Retrieved Units Only

The generation layer MUST build its context exclusively from units returned by the retrieval call for that question, passing each unit's verbatim `texto` together with its citation key and provenance (`tipo`, `es_secundaria`, `estado_vigencia`, `jurisdiccion`, `relevancia_consorcio`). It MUST NOT inject corpus text obtained by any other path, MUST NOT paraphrase a unit before showing it to the model, and MUST NOT drop or summarize provenance fields that retrieval marked as travelling with the hit.

#### Scenario: Context is exactly the retrieved page, filtered by the classification gate

*(AMENDED — bounded correction, 2026-08-23. This is a COMPLETION, not a weakening: the requirement's point is that no corpus text may enter the context by any path other than this question's retrieval call, and that is untouched. What the original scenario omitted is the step that sits between retrieval and the context — the per-request classification gate of `knowledge-hybrid-retrieval`'s Privacy Boundary, which removes any retrieved unit outside the shippable set `{publico, institucional}` before the context is assembled. Read literally, "it contains those five units" contradicted that gate whenever it excluded one, so the two requirements could not both be satisfied. The context is therefore a SUBSET of the retrieved page, never a superset and never a different set.)*

- GIVEN a question that retrieves five units, of which one is excluded by the per-request classification gate
- WHEN the generation context is assembled
- THEN it contains exactly the four surviving units and no other corpus text
- AND each of them appears as its verbatim `texto` with its citation key and provenance attached
- AND the excluded unit's text and provenance appear nowhere in the context
- AND when the gate excludes nothing, the context is exactly the five retrieved units

#### Scenario: Do-not-cite provenance reaches the generator

- GIVEN a retrieved unit whose document `relevancia_consorcio` states it must not be cited as grounds for a consorcio obligation
- WHEN the context is assembled
- THEN that text travels with the unit into the context
- AND it is not reduced to a boolean or omitted for brevity

### Requirement: Every Citation Resolves to a Retrieved Unit

Every citation key appearing in a served answer MUST be a member of the retrieved set for that same question. An answer containing a key that was not retrieved — including a well-formed key that exists elsewhere in the corpus — MUST NOT be served. Key membership MUST be checked mechanically against the retrieved set, not inferred from the model's own assertion. *(Clarified after fix round 1, 2026-08-23: the membership universe is the POST-EXCLUSION generation payload — the retrieved set minus any unit excluded by the per-request classification gate. A key belonging to a retrieved-but-excluded unit counts as an invented citation and MUST NOT be served.)* *(Bounded correction, 2026-08-23: that gate admits the shippable set `{publico, institucional}`, so an `institucional` unit's key is a legitimate member of the payload and MUST NOT be treated as invented.)*

#### Scenario: Invented citation key is never served

- GIVEN a generated answer citing `10demayo#res189-2014#art1`, a key that exists in the corpus but was not in this question's retrieved set
- WHEN the citation check runs
- THEN the answer is rejected
- AND no answer containing that key reaches the caller

#### Scenario: Malformed citation key is rejected, not repaired

- GIVEN a generated answer citing a key matching no unit at all
- WHEN the citation check runs
- THEN the answer is rejected
- AND the system does not silently rewrite the key to the nearest retrieved one

#### Scenario: Served answer's citations all resolve

- GIVEN an answer that passes the citation check and is served
- WHEN each of its citation keys is resolved
- THEN every one resolves to a unit present in that question's retrieved set

### Requirement: No Uncited Claim Is Served

Every substantive claim in a served answer MUST carry at least one citation. An answer containing an uncited claim MUST be rejected. On rejection the system MUST either regenerate within a bounded budget or abstain; when the budget is exhausted it MUST abstain. It MUST NOT serve a partially-cited answer, and it MUST NOT strip the offending sentence and serve the remainder as if it had been generated that way.

#### Scenario: Uncited claim triggers rejection, never silent trimming

- GIVEN a generated answer whose second paragraph asserts a procedural deadline with no citation
- WHEN the enforcement check runs
- THEN the answer is rejected
- AND it is not served with that paragraph deleted

#### Scenario: Exhausted regeneration budget abstains

- GIVEN an answer rejected for an uncited claim and a regeneration budget that is then exhausted
- WHEN the budget runs out
- THEN the system abstains
- AND the caller receives an explicit abstention, not the last rejected draft

### Requirement: Retrieval Refusal and Abstention Surface Honestly

When retrieval refuses (for example `EmbeddingsNoCargadas`, `EmbedderRequerido`, `EmbedderMismatch`, or vector support unavailable) or abstains under its calibrated confidence threshold, the generation layer MUST surface that outcome as a distinct, explicit state and MUST NOT generate an answer. A refusal MUST be distinguishable by the caller from an abstention, and both MUST be distinguishable from an answer. The generation layer MUST NOT retry a refusal by silently downgrading to a mode retrieval did not authorize.

*(AMENDED — fix round 1, 2026-08-23. The requirement already demands that these outcomes be mutually distinguishable; this names the state that distinguishability was missing.)* A **generation failure** — grounded context existed and passed the privacy gate, but the answer could not be produced or certified because the provider failed, timed out, or truncated — MUST be surfaced as its own terminal state, `generacion_fallida`, distinguishable by the caller from an abstention, from a service refusal, from a redirect and from an answer. It MUST NOT be reported as an abstention: an abstention asserts that the corpus holds no applicable norm, which is a claim about the law and is false in this case. `generacion_fallida` MUST carry no answer prose and MUST NOT surface the last rejected draft. A dependency that is unavailable or not ready (feature flag off, missing provider credential, embedder sidecar unreachable or not ready, provider quota/authorization exhausted) is a service-unavailability state, not `generacion_fallida` and never an abstention.

#### Scenario: Provider failure is not reported as an abstention

- GIVEN a question whose retrieval cleared the abstention threshold and whose generation payload is non-empty
- WHEN the generation provider times out and the bounded transport retry is exhausted
- THEN the caller receives `generacion_fallida`
- AND that state is distinguishable from `abstencion`, from a service refusal, from a redirect and from an answer
- AND no answer prose and no rejected draft is returned

#### Scenario: Exhausted regeneration budget still abstains

- GIVEN an answer rejected twice for a citation-enforcement violation, with the regeneration budget exhausted
- WHEN the outcome is produced
- THEN the caller receives an explicit abstention, not `generacion_fallida`
- AND the distinction is that enforcement violations are the model failing to ground a claim, while `generacion_fallida` is the answer never being produced at all

#### Scenario: Unembedded snapshot refuses instead of answering from FTS

- GIVEN a corpus snapshot with no vectors loaded, so retrieval raises `EmbeddingsNoCargadas`
- WHEN a legal question is asked
- THEN the caller receives an explicit unavailability state naming that the knowledge base is not ready
- AND no generated answer is produced
- AND the system does not fall back to a lexical-only answer presented as a normal result

#### Scenario: Retrieval abstention is reported as abstention

- GIVEN a question whose fused top result falls below the calibrated abstention threshold
- WHEN the answer is produced
- THEN the caller receives an explicit "no norma aplicable encontrada" state
- AND that state is distinguishable from a service refusal and from a cited answer

### Requirement: Vigencia and Secundaria State Are Carried Into the Answer

A served answer MUST carry, for every cited unit, its `estado_vigencia` and its `es_secundaria` flag, and MUST render the unit's verbatim source text available to the reader. A derogated or superseded unit MUST NOT be cited as if currently in force, and a fuente-secundaria unit MUST NOT be presented as derecho aplicable.

#### Scenario: Derogated unit is cited with its state visible

- GIVEN an answer citing a unit of a derogated law
- WHEN it is served
- THEN the citation carries an `estado_vigencia` value that begins with `DEROGADA` *(clarified 2026-08-23: `estado_vigencia` is free prose in this corpus; the check is a normalized prefix match, never literal equality)*
- AND the answer does not assert the provision as currently binding

#### Scenario: Secundaria citation is labeled — RESERVED, unreachable for generation in V1

*(AMENDED — bounded correction, 2026-08-23. Under the classification rule ratified the same day, EVERY fuente-secundaria document is classified `privado`, so every secundaria unit is excluded from the generation payload before any provider call, and a served answer therefore CANNOT cite one. This scenario is unreachable for generation in V1.)*

*(Disposition — the secundaria half is marked RESERVED FOR FUTURE rather than rewritten, and the reason is that the alternative would be worse: rewriting it into a `publico`/`institucional` marker scenario would delete the only written statement of what must happen the day a fuente secundaria becomes shippable, and re-deriving that rule from scratch later is exactly how a label quietly stops being applied. The enclosing requirement stays fully in force and fully testable: a served answer MUST still carry the `es_secundaria` flag for every cited unit — in V1 it is always `false`, which is a fact the caller is entitled to see rather than an omission — and the pre-serve marker check of the design's G3 keeps the code path live. The vigencia half of this requirement is NOT reserved and IS reachable today: `ley-8548` is `publico` and `DEROGADA`, so the sibling scenario below exercises the same enforcement machinery on live data.)*

- GIVEN a fuente-secundaria unit is admitted to the generation payload by a future classification decision
- WHEN an answer citing it is served
- THEN that citation is marked as secundaria
- AND it is not presented as the normative grounds of the answer
- AND until such a decision exists, no served answer cites a fuente-secundaria unit at all, because the classification gate excludes it from the payload

### Requirement: Answer-Level Eval Metrics With Ratified Thresholds

The eval harness MUST measure, on a labeled answer set and separately from retrieval metrics, **citation faithfulness** (share of served claims whose cited unit supports them), **uncited-claim rate**, and **invented-citation rate**. Serving MUST NOT be enabled unless uncited-claim rate is `0.00`, invented-citation rate is `0.00`, and end-to-end abstention recall stays `1.00` with precision ≥ `0.80` on held-out decisions. These figures MUST be reported with their `n`, and the owner MUST ratify the answer set before any threshold is scored.

*(Clarified — bounded correction, 2026-08-23.* The **invented-citation** universe is the POST-EXCLUSION generation payload, matching the enforcement that actually runs and the clarified membership requirement above; scoring it against the unfiltered retrieved page measures a different function than production and errs toward reporting `0.00` for a system that would reject. The **end-to-end abstention** pair is likewise measured POST-exclusion, on the served outcome, and is NOT the retrieval-level `AbstentionPolicy` pair: an exclusion-driven abstention is produced downstream of that policy and MUST be counted where it happens. It MUST be reported as its own figure alongside the retrieval-level pair, never merged into or substituted by it. Because a reclassification changes payloads without changing corpus bytes, these end-to-end figures MUST be re-measured whenever the classification rule or its expected-classification artifact changes, even when `corpus_sha` is unmoved.*)

#### Scenario: A single invented citation blocks serving

- GIVEN an eval run whose invented-citation rate is above `0.00`
- WHEN the go/no-go is determined
- THEN serving is not enabled
- AND the failure is reported even if faithfulness and retrieval metrics clear their bars

#### Scenario: Unratified answer set blocks scoring

- GIVEN an answer eval set the owner has not reviewed
- WHEN the report is generated
- THEN answer-level thresholds are marked not-evaluable rather than scored

#### Scenario: Answer metrics are reported separately from retrieval metrics

- GIVEN a completed eval run
- WHEN the report is read
- THEN citation faithfulness, uncited-claim rate and invented-citation rate appear as their own block with their `n`
- AND they are not merged into or substituted by the retrieval R-precision figures
