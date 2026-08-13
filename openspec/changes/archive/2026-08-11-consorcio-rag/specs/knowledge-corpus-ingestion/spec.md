# Knowledge Corpus Ingestion Specification

## Purpose

Ingest the SHA-pinned `consorcio-corpus-legal` markdown corpus into `rag_documento` + `rag_unidad`, applying the corpus's own MANIFEST v3 chunking rules exactly, preserving its citation-key identity, separating derecho aplicable from fuente secundaria, carrying vigencia state, and gating on per-document unit counts to catch the documented 19%-of-corpus silent-loss regression class.

## Requirements

### Requirement: Corpus Source Pinning and Idempotency
The pipeline MUST read from a corpus revision pinned by git SHA (or an equivalent checksum manifest) recorded in ingestion config, and MUST be re-runnable against the same pinned revision without duplicate or drifted rows.

#### Scenario: Re-run against unchanged pin is idempotent
- GIVEN ingestion already completed against corpus SHA `X`
- WHEN ingestion re-runs against the same SHA
- THEN row counts and content are identical to the first run

#### Scenario: Unresolvable pin aborts before writing
- GIVEN a config referencing an unresolvable SHA/checksum
- WHEN ingestion is invoked
- THEN it fails before writing any row

#### Scenario: `--verify-unchanged` reports every difference and writes nothing
- GIVEN a stored snapshot under corpus SHA `X` and a re-run of `X` with `--verify-unchanged`
- WHEN the stored key set and the parsed key set differ in ANY way — content changed under an existing key, a key added, or a key the parse no longer produces
- THEN the run reports the three classes separately, writes nothing at all (no upsert and no prune), and exits non-zero

#### Scenario: `--verify-unchanged` never prunes a key it did not examine
- GIVEN a key present in the stored snapshot and absent from the new parse
- WHEN ingestion runs with `--verify-unchanged`
- THEN that key is reported as removed and the row still exists afterwards; comparing only the key intersection MUST NOT let it be deleted while the report claims no divergence

### Requirement: Type-Scoped Regex v3 Chunking and Section Exclusion
The pipeline MUST implement the MANIFEST `UNIDAD` regex v3 (article plus optional `Anexo—/Decreto—/Resolutivo—/Anexo II—` compound prefixes) as the primary extractor, MUST apply the `norma-tecnica` point rule (`^## (\d)\. `) ONLY when `tipo == norma-tecnica`, and MUST exclude non-article `##` sections (procedencia, visto y considerando, guía-de-uso) from the article index or tag them with a distinct `tipo_chunk`.

#### Scenario: Compound-heading documents captured in full
- GIVEN documents with independent act/annex numbering (Res. 4/2026, Decreto 318/2007)
- WHEN ingested
- THEN both numbering series are captured as distinct units, avoiding the 19%-loss class

#### Scenario: norma-tecnica rule stays scoped
- GIVEN 5 fuente-secundaria documents with numbered commentary sections (`## 1.`…)
- WHEN ingested with the point-rule scoped to `norma-tecnica`
- THEN none of those 31 sections are captured as normative units

#### Scenario: Guía-de-uso tagged, not counted as articulado
- GIVEN Ley 8803's four closing "guía de uso" sections
- WHEN ingested
- THEN they carry `tipo_chunk = guia-de-uso` and are excluded from the normative count

#### Scenario: Non-article vigencia section is indexed, not discarded
- GIVEN Ley 10679's `## Vigencia de los fondos` section, which carries the text that substituted arts. 17, 20 and 24 and is not part of the articulado
- WHEN ingested
- THEN it is indexed as a retrievable unit with `tipo_chunk = nota-vigencia`, excluded from the normative unit count, and NOT dropped as a non-article section

### Requirement: Frontmatter Field Carriage — Jurisdiccion and Relevancia-Consorcio
Every `rag_documento` MUST carry `jurisdiccion` (NOT NULL) and `relevancia_consorcio` (nullable) ingested verbatim from the document frontmatter. The pipeline MUST NOT derive, summarize, or reinterpret `relevancia_consorcio`; it MUST be stored as the source text so retrieval can surface it (see `knowledge-hybrid-retrieval`). A document whose frontmatter lacks `relevancia_consorcio` MUST store NULL, never an invented value.

#### Scenario: Do-not-cite warning survives ingestion of a derecho-aplicable document
- GIVEN `resolucion-4-2026-bioagroindustria-reglamento-11059.md`, whose frontmatter declares `tipo: resolucion-ministerial` (therefore `es_secundaria = false`) and whose `relevancia_consorcio` states "RÉGIMEN HERMANO — CONTEXTO COMPARATIVO, NO DERECHO APLICABLE AL CONSORCIO CANALERO … NO debe citarse como fundamento de ninguna obligación ni facultad de un consorcio canalero"
- WHEN ingested
- THEN `rag_documento.relevancia_consorcio` holds that text verbatim, so a hit on one of its 78 units is distinguishable from a hit on a Ley 9750 article even though both are derecho aplicable by `tipo`

#### Scenario: Jurisdiccion ingested for every document
- GIVEN the corpus's common frontmatter schema, in which `jurisdiccion` is one of the mandatory keys
- WHEN ingestion completes
- THEN every `rag_documento` row has a non-null `jurisdiccion`, and a document missing the key aborts ingestion instead of defaulting

### Requirement: Citation Key Identity Preservation
Every `rag_unidad` id MUST reuse the corpus's own citation key verbatim, including composite keys for duplicate-numbering collisions (D-9) and prefixed keys for compound headings, never an invented scheme.

#### Scenario: D-9 collision resolved by composite key
- GIVEN a file with two resolutions each having an "Art. 1°"
- WHEN ingested
- THEN it produces `10demayo#res189-2014#art1` and `10demayo#res005-2026#art1`, not a collision

#### Scenario: Duplicate key rejected
- GIVEN a citation key already present
- WHEN ingestion attempts to insert it again
- THEN a UNIQUE constraint rejects the insert

### Requirement: Derecho-Aplicable vs Fuente-Secundaria Separation
Every `rag_documento` MUST carry `tipo` and a derived `es_secundaria` flag; `tipo: ley` MUST be treated as a synonym of `ley-provincial` (D-22); the five fuente-secundaria types MUST never be flagged as derecho aplicable.

#### Scenario: D-22 synonym normalized
- GIVEN `ley-8803` declares `tipo: ley`
- WHEN classified
- THEN it is treated identically to the other 14 `ley-provincial` documents

#### Scenario: Secondary types excluded from unit count
- GIVEN the 6 fuente-secundaria documents
- WHEN ingested
- THEN each carries `es_secundaria = true` and contributes 0 to the normative unit-count gate

### Requirement: Vigencia State and Dual-Redaction Preservation
Ingestion MUST carry `estado_vigencia` per document, MUST keep any dual-redaction block (vigente + redacción anterior) whole inside one unit, and MUST preserve in-body vigencia caveats as unit metadata.

#### Scenario: Derogated law retrievable but flagged
- GIVEN `ley-8548`, DEROGADA per frontmatter
- WHEN ingested
- THEN its units carry `estado_vigencia = derogada` and remain retrievable, distinctly marked

#### Scenario: Dual-redaction article stays whole
- GIVEN `ley-5589` art. 276 (`DEROGADO.` with the prior text conserved below)
- WHEN ingested
- THEN it is one unit; the pipeline never splits vigente from redacción anterior

### Requirement: Per-Document and Total Unit Count Gate
Ingestion MUST assert both the corpus total AND each document's individual unit count against the MANIFEST's declared counts; any single-document mismatch MUST abort ingestion. The declared total (1383) counts article-shaped units only, so the gate MUST scope it to `tipo_chunk = articulo`, and non-article units MUST be asserted against their own separate per-document inventory with the same strictness — neither inflating the normative total nor escaping the gate entirely.

#### Scenario: Total matches but one document is short
- GIVEN a run where the total equals 1383 but one document under-captured
- WHEN the per-document gate runs
- THEN ingestion fails loudly, even though a total-only check would pass

#### Scenario: Non-article units gated separately, never folded into the total
- GIVEN a run where every article count matches but an expected non-article unit (e.g. Ley 10679's vigencia section) was not produced
- WHEN the gate runs
- THEN ingestion fails on the non-article inventory, and no non-article unit is ever counted toward the 1383 article total

#### Scenario: All counts match
- GIVEN every document's count equals its MANIFEST-declared count
- WHEN the gate runs
- THEN ingestion is marked successful

### Requirement: Exhaustive Inventory — No Silently Absent Section or File
The count gates compare produced units against DECLARED ones, so anything declared nowhere escapes all of them. Ingestion MUST therefore additionally assert that every `#`/`##` heading in every corpus document is either inside a captured unit's span, declared in that document's non-article inventory, or listed in an explicit per-document exclusion inventory whose every entry carries a declared exclusion class; and that every `.md` file in the corpus checkout is either a declared document or an explicitly declared non-document. An undeclared heading or an unlisted file MUST abort ingestion.

#### Scenario: A section in no inventory aborts instead of vanishing
- GIVEN Res. APRHI 3/2026's `# ANEXO I` and `# ANEXO II`, which its own art. 1° declares to "integrar el presente instrumento legal" and which carry the 25 afectaciones found in no other document
- WHEN they are in neither the non-article inventory nor the exclusion inventory
- THEN ingestion fails naming them, rather than completing with every count gate green and the anexos absent from the index

#### Scenario: Deliberate exclusions must state a reason
- GIVEN a heading listed in a document's exclusion inventory
- WHEN expectations are loaded
- THEN its exclusion class MUST be one declared at corpus level with its reason; an exclusion under an undeclared class is rejected

#### Scenario: An undeclared corpus file aborts instead of being skipped
- GIVEN a `.md` file present in the pinned checkout and listed neither as a document nor as a non-document
- WHEN ingestion runs
- THEN it fails naming the file, rather than never opening it and reporting success

### Requirement: Integrity Gates — Verbatim Substring and Token Ceiling
Every `rag_unidad.texto` MUST be a byte-exact substring of its source file, verified by an automated test; every unit's token count MUST be measured against the embedding model's context ceiling (8192), and a unit over that ceiling MUST NEVER be truncated. The ceiling is an EMBEDDING constraint, not a storage one: an over-ceiling unit MUST still be ingested whole and MUST remain fully retrievable by FTS, MUST be excluded from embedding rather than truncated to fit, and MUST be disclosed in the ingestion output on every run. `--strict-token-ceiling` MUST promote it to a hard abort for operators who want ingestion to stop instead.

#### Scenario: Full-corpus substring gate passes
- GIVEN all ingested units
- WHEN the substring gate runs
- THEN 100% verify as literal substrings of their source file

#### Scenario: Over-ceiling unit is ingested whole, reported, and excluded from embedding
- GIVEN a unit whose token count exceeds 8192 (e.g. an intentionally-unsplit long article)
- WHEN the token-ceiling gate runs
- THEN the unit is stored whole and stays retrievable by FTS, is listed in the run's printed report with its estimated token count, and the abort applies to the EMBEDDING leg — the unit is excluded from embedding in slice 3, never truncated to fit

#### Scenario: Over-ceiling units are never silently dropped from the report
- GIVEN a run over the pinned corpus, in which 3 real units exceed the ceiling
- WHEN ingestion completes
- THEN the printed output names every one of them, states that they will be FTS-only in V0, and says they were not truncated

#### Scenario: Strict mode turns the report into a refusal
- GIVEN `--strict-token-ceiling`
- WHEN any unit exceeds the ceiling
- THEN ingestion aborts before writing a single row
