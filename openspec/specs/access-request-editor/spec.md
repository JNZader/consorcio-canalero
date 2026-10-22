# Access Request Editor Specification

## Purpose

Compose the eight Ley 8803 access-to-information drafts from slots, with every legal citation verified by `chequear`, so that nothing unverified, private or machine-invented leaves the system. The machine never submits.

## Requirements

### Requirement: V1 Scope Is the Eight 8803 Drafts

The editor MUST support exactly the eight Ley 8803 drafts. Ley 27.275 (pedido 8) and obra notes MUST be out of scope and refused.

#### Scenario: Out-of-scope request

- GIVEN a request for pedido 8 / Ley 27.275 or an obra note
- WHEN composition is requested
- THEN it is refused as unsupported

### Requirement: Slot Classes

Each draft MUST be composed of legal slots, document-identification slots and a human-only block. Legal slots MUST each pin `(citation_key, span, vigencia, sha)`. Document-identification slots MUST be human-confirmed data, not retrieval output. The human-only block (requerente, DNI, domicilio/correo, destinatario address, channel choice, operational facts) MUST NOT be filled by the machine.

#### Scenario: Human-only placeholders survive

- GIVEN a draft with `[REQUERENTE]`, `[DNI]` and `[DOMICILIO / CORREO]`
- WHEN it is composed and exported
- THEN those placeholders are unchanged

#### Scenario: Operational fact is not generated

- GIVEN a draft needing a canal, meters or hectares value
- WHEN composed
- THEN the value stays in the human-only block, unfilled

### Requirement: Fail-Closed Export

Export MUST fail when any cited unit is `privado` (its `clasificacion` is outside `CLASIFICACIONES_ENVIABLES`), any citation is not a key at the active SHA, or any `chequear` does not pass. Failure MUST name the slot and cause and MUST produce no output document. Every exported citation MUST trace to a passing `chequear` at the active SHA; free-text legal citations MUST NOT be exported.

#### Scenario: Private unit

- GIVEN a legal slot pinned to a `privado` fixture unit
- WHEN export runs
- THEN it fails and no document is produced

#### Scenario: Invented citation or failed check

- GIVEN a slot with a key absent at the SHA, or a span or vigencia that fails `chequear`
- WHEN export runs
- THEN it fails naming that slot

#### Scenario: SHA moved after drafting

- GIVEN a draft checked against SHA `A` and the active SHA is now `B`
- WHEN export runs
- THEN it re-checks, refuses, and exports nothing

### Requirement: No Machine Submission

The editor MUST NOT submit, send or upload any document to CIDI or any recipient. Export MUST yield a document for human sending only.

#### Scenario: Export is local

- GIVEN a successful export
- WHEN network calls are observed
- THEN none targets CIDI or any recipient

### Requirement: Regression Against the Hand-Written Notes

Composing each of the eight drafts from its slots MUST reproduce its hand-written note, comparing with human placeholders masked. Fixtures MUST NOT contain private gold-question text.

#### Scenario: Eight drafts reproduce

- GIVEN the eight slot sets and their hand-written notes
- WHEN each is composed and placeholders are masked
- THEN each equals its note

#### Scenario: Fixture hygiene

- GIVEN the regression fixtures
- WHEN scanned against the private gold set
- THEN no private gold text appears
