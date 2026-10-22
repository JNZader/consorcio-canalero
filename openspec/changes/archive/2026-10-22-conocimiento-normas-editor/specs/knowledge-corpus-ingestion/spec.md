# Delta for Knowledge Corpus Ingestion

## ADDED Requirements

### Requirement: Lab Measurement Before Production Ingest

Ingest activates the new corpus row (`activo=true`) and the eval reads the database, so measuring in the serving database would serve an unmeasured SHA. Therefore any re-ingest MUST first be ingested into a lab database and scored on the 57-item gold with the no-GPU arm. A production ingest MUST happen only if that recorded run for the same SHA has hit@5 ≥ 0.72.

#### Scenario: Bar met in lab

- GIVEN a lab ingest of SHA `X` with a recorded hit@5 ≥ 0.72
- WHEN the operator decides on production
- THEN production ingest of `X` is permitted

#### Scenario: Bar failed or absent

- GIVEN no recorded lab run for `X`, or hit@5 < 0.72
- WHEN production ingest of `X` is requested
- THEN the publish gate is not satisfied and production ingest MUST NOT proceed

#### Scenario: Production-DB eval is not gate evidence

- GIVEN a run measured only after ingesting into the serving database
- WHEN the gate is assessed
- THEN that run does not satisfy it

#### Scenario: Production ingest names its environment

- GIVEN an ingest invoked with `--entorno produccion` and without `--exigir-barra`
- WHEN the command runs
- THEN it refuses before opening a database, a corpus file, or a pin check
- AND `--entorno laboratorio` remains allowed to ingest without that flag, because the measurement happens there

### Requirement: Deactivation Is Rollback, Not Measurement

Setting `activo=false` on a `rag_corpus` row MUST be the documented rollback for a bad SHA and MUST NOT be used as the measurement method.

#### Scenario: Bad SHA withdrawn

- GIVEN an active row whose SHA must be withdrawn
- WHEN `activo=false` is set on that row
- THEN the norms route serves the remaining active corpus, or refuses with the no-active-corpus cause if none remains

### Requirement: Operator Read Before Claiming Current

An operator MUST read `rag_corpus` on the target database before any served index is called current. Documentation MUST NOT state that the production box holds the August pin.

#### Scenario: Empty or different corpus on the box

- GIVEN `rag_corpus` is empty, or holds a SHA different from the intended pin
- WHEN the operator reads it
- THEN the index is not called current, and an empty one makes the norms route refuse as no-active-corpus

### Requirement: Clean Pushed Corpus SHA Precondition

A pushed, clean corpus SHA MUST exist before any pin migration or production ingest. Creating or pushing it is owner work and is NOT performed by this change.

#### Scenario: SHA unpushed

- GIVEN a corpus SHA that is unpushed or whose tree is dirty
- WHEN the publish gate is assessed
- THEN it is not satisfiable, and this change performs no push or cleanup
