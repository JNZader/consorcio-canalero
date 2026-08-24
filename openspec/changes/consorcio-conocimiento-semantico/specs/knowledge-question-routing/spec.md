# knowledge-question-routing Specification

## Purpose

Decide, before retrieval runs, whether a question is one the legal corpus can honestly answer. A question about what a norm says goes to retrieval and generation; a question about a debt, a trámite, a denuncia or a location on the map gets a **deterministic redirect naming the real platform surface** and never a generated answer — because the corpus holds no such data and an answer about it would be invention regardless of how well it cites.

Scope fixed by the approved proposal (2026-08-23): classification only, no operational or geospatial data joins in V1. The classifier's implementation (LLM prompt vs keyword/embedding) is a design-phase decision and is not fixed here.

## Requirements

### Requirement: Every Question Is Classified Before Retrieval

The system MUST classify each incoming question into exactly one of `legal`, `operational`, `geoespacial` or `mixto` before any retrieval or generation runs. A question classified `operational` or `geoespacial` MUST NOT reach the retrieval service at all.

#### Scenario: Legal question proceeds to retrieval

- GIVEN the question "¿qué procedimiento fija la norma para constituir un consorcio?"
- WHEN it is classified
- THEN it is classified `legal`
- AND it proceeds to retrieval and generation

#### Scenario: Operational question never reaches retrieval

- GIVEN the question "¿cuánto debe Juan Pérez?"
- WHEN it is classified
- THEN it is classified `operational`
- AND no retrieval call is made for it

### Requirement: Non-Legal Questions Get a Deterministic Redirect, Never an Answer

A question classified `operational` or `geoespacial` MUST produce a redirect response naming the platform surface that actually holds the data — `/tramites`, `/finanzas`, `/denuncias` or `/mapa` — and MUST NOT produce any generated prose that answers the question, in whole or in part, with or without citations. The mapping from classification to named surface MUST be deterministic: the same classification for the same subject MUST always name the same surface.

#### Scenario: Debt question redirects to finanzas with no answer text

- GIVEN the question "¿cuánto debe Juan Pérez?"
- WHEN the router responds
- THEN the response is a redirect naming `/finanzas`
- AND it contains no generated answer, no figure and no citation

#### Scenario: Geospatial question redirects to the map

- GIVEN the question "¿por dónde pasa el canal N°5?"
- WHEN the router responds
- THEN the response is a redirect naming `/mapa`
- AND no answer is generated from the legal corpus

#### Scenario: Redirect target is stable across repeats

- GIVEN the same operational question asked twice
- WHEN both are routed
- THEN both name the same surface

### Requirement: Mixed Questions Answer Only the Legal Part

A question classified `mixto` MUST have its legal part answered under the full citation and abstention contract of `knowledge-answer-generation`, and its non-legal part redirected. The response MUST make both parts explicit. The system MUST NOT answer the operational part from the legal corpus, and MUST NOT drop the redirect because a legal answer was produced.

#### Scenario: Legal part answered, operational part redirected

- GIVEN "¿qué dice la norma sobre la cuota y cuánto debo yo?"
- WHEN the question is routed
- THEN the norm part is answered with citations
- AND the debt part is returned as a redirect naming `/finanzas`
- AND the answer text makes no claim about the caller's balance

#### Scenario: Legal part abstains but the redirect still stands

- GIVEN a `mixto` question whose legal part falls below the abstention threshold
- WHEN the response is produced
- THEN the legal part is an explicit abstention
- AND the redirect for the non-legal part is still present

### Requirement: Bias Toward Redirect Under Doubt

When classification confidence is below the calibrated threshold, or the classifier's outcome is ambiguous, the system MUST redirect rather than answer. A doubtful question MUST NOT be routed to generation on the assumption that citation enforcement will catch the mistake downstream.

#### Scenario: Low-confidence classification redirects

- GIVEN a question the classifier scores below the confidence threshold for `legal`
- WHEN it is routed
- THEN it produces a redirect
- AND no generated answer is served

### Requirement: Classification Is Measured and Misclassification Is Observable

Router accuracy MUST be measured on a labeled classification set whose items carry a `legal` / `operational` / `geoespacial` / `mixto` label, ratified by the owner before any threshold is scored, and MUST be reported as a confusion matrix rather than a single accuracy figure — the `operational → legal` cell is the one that produces a fabricated answer and MUST be reported explicitly. Every routing decision MUST be recorded at runtime with the question, the assigned class and the confidence, so a misclassification observed in use can be traced rather than reconstructed.

#### Scenario: Confusion matrix names the dangerous cell

- GIVEN a completed router eval run
- WHEN the report is read
- THEN it shows per-class results as a confusion matrix
- AND the count of operational questions classified `legal` is reported explicitly

#### Scenario: A routing decision is traceable after the fact

- GIVEN a CD member reports that an operational question was answered instead of redirected
- WHEN the routing record for that request is inspected
- THEN it shows the question, the class assigned and the confidence at decision time

#### Scenario: Unratified classification set blocks scoring

- GIVEN a labeled classification set the owner has not reviewed
- WHEN the report is generated
- THEN router thresholds are marked not-evaluable rather than scored
