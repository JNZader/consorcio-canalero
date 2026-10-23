# Knowledge Norms Kernel Specification

## Purpose

One mute library over a database `Session` with exactly three tools (`buscar`, `leer`, `chequear`), shared by the norms route, a CLI and an MCP mirror. It finds, reads and verifies legal units and never writes prose.

## Requirements

### Requirement: Exactly Three Tools

The kernel, the CLI and the MCP server MUST each expose `buscar`, `leer` and `chequear` and nothing else. They MUST NOT expose `redactar` or any generation tool, and MUST NOT call a generation provider.

#### Scenario: MCP lists three tools

- GIVEN the MCP mirror is started
- WHEN its tools are listed
- THEN the list is exactly `buscar`, `leer`, `chequear`

#### Scenario: redactar does not exist

- GIVEN the kernel, CLI and MCP
- WHEN `redactar` is invoked or looked up
- THEN it is absent or rejected on all three

### Requirement: One Code Path

The norms route, CLI and MCP MUST delegate to the same kernel functions. For the same query, mode and active SHA they MUST return the same units.

#### Scenario: Surfaces agree

- GIVEN one query, mode and active corpus
- WHEN route, CLI and MCP `buscar` run
- THEN the unit keys and fields are identical

### Requirement: buscar and leer

`buscar` MUST take an explicit mode. The no-GPU arm MUST NOT require a reranker. `bm25_ce` MUST still refuse without a real reranker (`RerankerRequerido` unchanged). `leer` MUST return the byte-exact unit and its provenance, including `clasificacion`, for a key at the active SHA, and MUST refuse an unknown key.

#### Scenario: No-GPU arm runs without a reranker

- GIVEN no reranker and the no-GPU mode
- WHEN `buscar` runs
- THEN it returns units without error

#### Scenario: bm25_ce without reranker is refused

- GIVEN mode `bm25_ce` and no reranker
- WHEN `buscar` runs
- THEN it refuses with the existing reranker-required error

#### Scenario: Unknown key

- GIVEN a key not present at the active SHA
- WHEN `leer` runs
- THEN it refuses as not found and returns no text

### Requirement: chequear Verdict

`chequear(citation_key, span, vigencia, sha)` MUST pass only when ALL hold: the key exists at `sha`; `span` is a non-empty substring of that unit's `texto`; `vigencia` equals the unit's stored `estado_vigencia`; `sha` is the active corpus SHA. Any failure MUST return a refusal naming the failed condition. A non-active SHA MUST be a refusal, never a warning. The verdict MUST carry the unit's `clasificacion`.

#### Scenario: All four conditions hold

- GIVEN an existing key, an exact span of its text, the stored vigencia and the active SHA
- WHEN `chequear` runs
- THEN it passes

#### Scenario: Span from another unit

- GIVEN a span that occurs in a different unit but not in the cited unit
- WHEN `chequear` runs
- THEN it refuses naming the span condition

#### Scenario: Vigencia mismatch, stale SHA, empty span, missing key

- GIVEN respectively a wrong vigencia, a non-active SHA, an empty span, a key absent at the SHA
- WHEN `chequear` runs for each
- THEN each refuses and names its own failed condition
