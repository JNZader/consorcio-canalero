# Work Unit: audit-2026-10-rag-docs-drift

Docs-only drift pass over the RAG ceremony surfaces, from the 2026-10-23
audit (`docs/auditorias/AUDITORIA_CONSORCIO_CANALERO_2026-10-23.md`, drift
notes). The operator on the box follows these documents literally during
the ceremonia de encendido — stale figures there are executable risk, not
cosmetics.

## In

- `docs/rag/runbook-encendido.md`: the 8 "current pin" citations of the
  August SHA `12043582…` (steps 6b–9, §4.2 commands, the classification
  check, the vectors artifact name, the provenance SQL) now cite the
  Makefile's live pin `ecab0a0e…`. The one historical mention
  ("nothing assumes the box already holds the August pin") is kept as
  history.
- `openspec/specs/knowledge-corpus-ingestion/spec.md`: the article-total
  gate requirement no longer hard-codes `1383`; it points at
  `corpus_expectations.yaml` as the single source of truth (recording the
  current figures, 49/1806/65, and why the frozen number rotted).
- `openspec/specs/knowledge-hybrid-retrieval/spec.md`: the go/no-go
  requirement now states the owner's re-ratified 2026-08-23 bars
  (hit@5 ≥ 0.72, hit@10 ≥ 0.80, MRR ≥ 0.55, citation-precision ≥ 0.33,
  separations 1.00) and names `BARRA_*` in `eval/harness.py` as the source
  of truth, with the V0 aspirations preserved as recorded history.
- `Makefile` (`test-rag-corpus` comment): 35/1383 → 49/1806, with a note
  that the comment is illustrative, not a second source of truth.
- `docs/ROADMAP.md`: the "openspec/changes is untracked by convention"
  claim is corrected (tracked since the 2026-10 audit waves); header date
  bumped.

## Out

- No code changes; no behavior changes; no test changes.
- The runbook's ceremony revision count is NOT touched here — if RAG-5
  (mailbox dead-letter) lands a new Alembic revision, that unit updates
  the ceremony step itself.
- `conocimiento-hit5-faltantes/` exploration folder remains untracked by
  design (owner decision pending on its recommendation).
