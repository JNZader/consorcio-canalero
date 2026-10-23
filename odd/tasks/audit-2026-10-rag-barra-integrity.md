# audit-2026-10-rag-barra-integrity

Integrity binding of `eval/barra_sin_gpu.yaml` — audit finding RAG-2 (WARNING).

## In

- [x] `integridad_sha256`: canonical sha256 digest over the artifact's load-bearing fields — `CAMPOS_INTEGRIDAD = (estado, modo, corpus_sha, n_respondibles, hit_rate_at_5, separacion_norma_secundaria, vigencia_correcta)`. `metodologia`/`motivo` are deliberately outside the seal: prose no predicate reads, and rewording prose must not force re-deriving a measurement.
- [x] Verified in `cargar_barra` (`barra_sin_gpu.py`), the single choke point all three predicates load through (`exigir_superada`, `exigir_no_superada_honesta`, `superada_para` in normas). Verification runs AFTER the per-field shape checks so a missing pin is still reported by field name; missing or mismatched seal raises `BarraInvalida` naming the covered field set. Per-field checks unchanged — they still catch sloppy inconsistency, and against a forged digest they are what holds the direction consistency (estado vs figures).
- [x] Generation path stamps the seal: `volcar` (the dump behind `a_yaml`, the block `scripts/rag_eval.py` prints and the runbook pastes) now ends with `integridad_sha256`, computed by the same `integridad_sha256()` the loader verifies — no duplicated canonicalization (`_desde_datos` shared by loader and stamper). `sellar(datos)` re-seals an edited dump through the same coercions.
- [x] Checked-in `barra_sin_gpu.yaml` stamped (`db83af2a…`) + header comment; runbook-encendido step 4 now says to paste the block whole (the seal is its last line).
- [x] Honesty stance, same as `regla_sha256` (`repository.regla_clasificacion_sha256`, asserted by the unit suite): sha256 is unkeyed — this is NOT cryptographic proof that a figure was measured. It raises the bar to "the edit must also forge the digest, and both lines then sit in the review diff of the commit that flips serving".
- [x] RED-CHECK tests (`test_rag_barra_integridad.py`, 16 tests): tampered field with stale seal → `BarraInvalida` (parametrized over all 7 covered fields, both serving directions of the fabrication: superada-over-a-real-failure and no_superada-over-a-real-pass); tampered/absent seal → `BarraInvalida`; derived artifact loads with its own seal; checked-in artifact re-verifies. Red evidence pre-fix: 15 failed / 1 passed — "DID NOT RAISE BarraInvalida" — plus a probe showing the fabricated-superada artifact loading AND passing `exigir_superada` on the old module.

## Out

- Keyed/MAC signing (would need secret management on a public repo — rejected for the same reason `regla_sha256` is unkeyed).
- Sealing `umbral_abstencion.yaml` (same shape, different finding; copy this pattern if audited).
- Any change to the three predicates' own field logic, `derivar_desde` refusals, or the ingest gates.
- Binding the artifact to the eval report file or a run id (corpus_sha + metodologia already name the run; the report path is in the yaml header).

## Files

- `gee-backend/app/domains/conocimiento/eval/barra_sin_gpu.py` — digest, loader verify, volcar stamp, sellar.
- `gee-backend/app/domains/conocimiento/eval/barra_sin_gpu.yaml` — stamped + header.
- `gee-backend/tests/new/conocimiento/test_rag_barra_integridad.py` — new, RED-CHECK suite.
- `gee-backend/tests/new/conocimiento/test_normas_kernel.py`, `test_normas_eval.py`, `test_recuperacion_citas.py` — existing hand-written artifacts now sealed via `sellar` (predicates still tested against forged-digest artifacts).
- `docs/rag/runbook-encendido.md` — step 4 paste instruction.

## Checks

```bash
cd gee-backend
TEST_DATABASE_URL='postgresql://consorcio:consorcio_dev@localhost:15432/test_audit_rag2' \
  <owner venv>/bin/pytest tests/new/conocimiento/ -q -p no:cacheprovider
# 1584 passed, 80 skipped (pgvector image + mcp SDK skips), 0 failed
# ruff check <changed files>: All checks passed
```
