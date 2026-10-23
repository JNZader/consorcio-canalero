# Delta for Knowledge Corpus Ingestion

## MODIFIED Requirements

### Requirement: Lab Measurement Before Production Ingest

Ingest activates the new corpus row (`activo=true`) and the eval reads the database, so measuring in the serving database would serve an unmeasured SHA. Therefore any re-ingest MUST first be ingested into a lab database and scored on the 57-item gold with the no-GPU arm (`modo` `bm25_sin_ce`). Production ingest (`--entorno produccion`) MUST name exactly one of two mutually exclusive flags, and each flag MUST read the recorded bar artifact for the exact corpus SHA:

- Ranked path, `--exigir-barra`: MUST proceed only if the artifact is `estado: superada` AND its figures meet every constant (hit@5 >= 0.72, `separacion_norma_secundaria` 1.00, `vigencia_correcta` 1.00) AND `modo` is `bm25_sin_ce` AND the SHA matches. A `superada` word over failing figures MUST be refused.
- Unranked path, `--produccion-sin-orden`: valid only with `--entorno produccion`. It MUST proceed only if the artifact is `estado: no_superada`, `modo` is `bm25_sin_ce`, the SHA matches, and at least one figure fails its constant. This is NOT a cleared bar and MUST never be reported as one.

The check MUST run before any corpus file, database connection, or pin is touched, and `--dry-run` MUST get the same check. A gate refusal MUST print `INGESTION ABORTED — nothing was written.`, write nothing, and exit 1. A usage error (both flags together, or `--produccion-sin-orden` with `--entorno laboratorio`) is argparse's mutually exclusive group: it exits 2, reads no artifact, writes nothing, and does not print the ingest-abort banner. The unranked success banner MUST NOT contain the word `superada`.

(Previously: production ingest MUST happen only if the recorded run for the SHA had hit@5 >= 0.72; no unranked path existed and `--entorno produccion` required `--exigir-barra`.)

#### Scenario: Bar met in lab

- GIVEN a lab ingest of SHA `X` with a recorded hit@5 >= 0.72
- WHEN the operator decides on production
- THEN production ingest of `X` is permitted through `--exigir-barra` only, when the artifact also satisfies the ranked-path conditions

#### Scenario: Ranked path unchanged

- GIVEN `--entorno produccion --exigir-barra` and an artifact `estado: superada` for the SHA, `bm25_sin_ce`, hit@5 >= 0.72, separacion 1.00, vigencia 1.00
- WHEN the command runs
- THEN ingest proceeds
- AND the same flag over `no_superada`, `no_medido`, a SHA mismatch, wrong `modo`, or `superada` with any failing figure aborts with exit 1

#### Scenario: Bar failed or absent on the ranked path

- GIVEN no recorded lab run for `X`, or hit@5 < 0.72
- WHEN production ingest of `X` is requested with `--exigir-barra`
- THEN the publish gate is not satisfied and production ingest MUST NOT proceed

#### Scenario: Production-DB eval is not gate evidence

- GIVEN a run measured only after ingesting into the serving database
- WHEN the gate is assessed
- THEN that run does not satisfy it

#### Scenario: Production ingest names its environment

- GIVEN an ingest invoked with `--entorno produccion` and neither `--exigir-barra` nor `--produccion-sin-orden`
- WHEN the command runs
- THEN it refuses before opening a database, a corpus file, or a pin check, with exit 1
- AND the message names both `--exigir-barra` and `--produccion-sin-orden`

#### Scenario: Honest no_superada allows unranked production ingest

- GIVEN `--entorno produccion --produccion-sin-orden` and an artifact `estado: no_superada`, `bm25_sin_ce`, matching SHA, hit@5 0.6470588235294118 (below 0.72)
- WHEN the command runs
- THEN ingest proceeds and exits 0

#### Scenario: Success banner never claims a cleared bar

- GIVEN a successful `--produccion-sin-orden` ingest
- WHEN the output is read
- THEN it states the outcome is unranked and contains no occurrence of `superada`

#### Scenario: Superada on the unranked flag is refused

- GIVEN `--produccion-sin-orden` and an artifact `estado: superada` for the SHA
- WHEN the command runs
- THEN it aborts with exit 1, and the message names `--exigir-barra`

#### Scenario: no_medido or invalid artifact is refused

- GIVEN `--produccion-sin-orden` and an artifact `estado: no_medido`, or one that fails to load
- WHEN the command runs
- THEN it aborts with exit 1 and nothing is written

#### Scenario: SHA mismatch is refused

- GIVEN `--produccion-sin-orden` and an honest `no_superada` recorded for a different SHA than `--corpus-sha`
- WHEN the command runs
- THEN it aborts with exit 1 and nothing is written

#### Scenario: Wrong modo is refused

- GIVEN `--produccion-sin-orden` and a `no_superada` artifact whose `modo` is not `bm25_sin_ce`
- WHEN the command runs
- THEN it aborts with exit 1 and nothing is written

#### Scenario: no_superada with all figures passing is refused as inconsistent

- GIVEN `--produccion-sin-orden` and `estado: no_superada` whose hit@5 >= 0.72, separacion 1.00 and vigencia 1.00
- WHEN the command runs
- THEN it aborts with exit 1, naming the artifact as inconsistent, and nothing is written

#### Scenario: Both flags together are a usage error

- GIVEN `--entorno produccion --exigir-barra --produccion-sin-orden`
- WHEN the command runs
- THEN it exits 2 with a usage error, reads no artifact, writes nothing, and does not print the ingest-abort banner

#### Scenario: Unranked flag with laboratorio is a usage error

- GIVEN `--entorno laboratorio --produccion-sin-orden` (including both flags with laboratorio)
- WHEN the command runs
- THEN it exits 2 with a usage error, writes nothing, and does not print the ingest-abort banner

#### Scenario: Dry-run is refused the same way

- GIVEN `--dry-run --produccion-sin-orden` and any artifact the real run would refuse
- WHEN the command runs
- THEN it aborts with the same banner and exit 1, before any corpus file, database, or pin is touched

#### Scenario: Laboratorio without flags is unchanged

- GIVEN `--entorno laboratorio` (or the default) and neither flag
- WHEN the command runs
- THEN it ingests without reading the bar artifact

## ADDED Requirements

### Requirement: Recorded Bar Artifact Derives From a Committed Report

The recorded bar artifact MUST be produced by `derivar_desde` from a committed report under `docs/rag/`, never hand-edited. This change MUST record, from a NEW report copied from `/tmp/rag-eval-seguimiento-citas/`: `estado: no_superada`, `modo: bm25_sin_ce`, `corpus_sha: ecab0a0ed9cfbfb7bca0f7673f0283bc75bb406e`, `hit_rate_at_5: 0.6470588235294118`, `separacion_norma_secundaria: 1.0`, `vigencia_correcta: 1.0`, `n_respondibles: 34`. The existing `docs/rag/retrieval-eval-ecab0a0e-2026-10-23.md` (pre-follow measurement) MUST NOT be overwritten. The constants 0.72 and 1.00 MUST NOT change, and `estado: superada` MUST NOT be written.

#### Scenario: Post-follow figures recorded without touching the pre-follow report

- GIVEN the new committed report and the regenerated artifact
- WHEN both are read
- THEN the artifact holds exactly the figures above, and the pre-follow report file is byte-identical to before

#### Scenario: Shipped artifact is refused by the ranked path and accepted by the unranked one

- GIVEN the shipped artifact and SHA `ecab0a0e…`
- WHEN `--exigir-barra` and `--produccion-sin-orden` are evaluated
- THEN the first refuses (hit@5 below 0.72) and the second accepts

### Requirement: Runbook Separates Ranked and Unranked Production Ingest

`docs/rag/runbook-encendido.md` §4.4 step 5 MUST be split into 5a (`--exigir-barra`, unchanged) and 5b (`--produccion-sin-orden`). 5b MUST state this is not a cleared bar. The stale sentence saying the shipped file is `no_medido` MUST be corrected.

#### Scenario: Runbook wording

- GIVEN the runbook after this change
- WHEN §4.4 is read
- THEN it has steps 5a and 5b, 5b says it is not a cleared bar, and no sentence says the shipped file is `no_medido`

## Design Constraints

- Serving is out of scope: `normas.py` untouched; rank order stays behind `superada_para`.
- `exigir_superada` / `superada_para` behavior and `BARRA_*` constants MUST NOT change.
- The Python predicate name is left to design; only CLI and artifact behavior is specified.
