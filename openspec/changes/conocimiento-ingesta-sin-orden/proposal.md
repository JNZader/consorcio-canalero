# Proposal: Production Ingest Under an Honest Failed Bar (Served Unranked)

## Intent

Production ingest is only possible through `--exigir-barra`, which requires `superada`. The lab bar for `ecab0a0e…` is an honest `no_superada` (hit@5 below 0.72). The owner wants the corpus loaded and served **unranked**, without loosening the strict gate or claiming a cleared bar.

## Scope

### In Scope
- `--produccion-sin-orden` flag in `rag_ingest.main()`: valid only with `--entorno produccion`, mutually exclusive with `--exigir-barra` (usage error, nothing written). `--entorno produccion` alone is still refused and names both flags.
- New predicate in `barra_sin_gpu.py` accepting only: `estado == no_superada`, `modo == bm25_sin_ce`, SHA match, and ≥1 of hit@5 / separacion / vigencia failing its constant. All-passing `no_superada` → refused as inconsistent; `superada` → refused, pointing at `--exigir-barra`; `no_medido`, SHA mismatch, wrong `modo` → refused.
- Check runs before corpus read, DB connection and pin; `--dry-run` refused identically. Exit 1, `INGESTION ABORTED — nothing was written.` Success banner names the unranked outcome and never contains `superada`.
- Refresh `barra_sin_gpu.yaml` via `derivar_desde` / `volcar` (not by hand): `no_superada`, `bm25_sin_ce`, SHA `ecab0a0ed9cfbfb7bca0f7673f0283bc75bb406e`, hit@5 0.6470588235294118, separacion 1.0, vigencia 1.0, n_respondibles 34. Update `test_el_artefacto_enviado_registra_la_medicion_no_superada`.
- Runbook `docs/rag/runbook-encendido.md` §4.4 step 5 → 5a (`--exigir-barra`, unchanged) / 5b (`--produccion-sin-orden`, explicitly "not a cleared bar"); fix the stale "ships `no_medido`" sentence.

### Out of Scope
- Running production ingest; flipping `conocimiento_normas_enabled`; publishing the image (publish is `workflow_dispatch` of `deploy.yml` from `main`); reading `rag_corpus` on the box.
- `rag_corpus` columns/migrations; `normas.py`, schemas, router, CLI, MCP, `service.py`.
- `BARRA_*` constants (0.72 / 1.00), `exigir_superada` / `superada_para` behaviour, k1/b, stoplists, citation follow, gold, corpus repo, sibling changes.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `knowledge-corpus-ingestion`: requirement "Lab Measurement Before Production Ingest" — ranked path still requires the bar; unranked production ingest may proceed only via `--produccion-sin-orden` on an honest `no_superada` for the exact SHA. Scenario "Production ingest names its environment" names both flags.

## Approach

Exploration approach 1: separate flag plus a dedicated predicate. Mode/SHA checks shared via a private helper so `exigir_superada` stays semantically identical. Serving unchanged: `superada_para` stays false, screen keeps `citation_key` order, `orden_presentado: false`, no `rango`.

## Affected Areas

| Area | Impact |
|------|--------|
| `gee-backend/scripts/rag_ingest.py` | Modified |
| `gee-backend/app/domains/conocimiento/eval/barra_sin_gpu.py` | Modified |
| `gee-backend/app/domains/conocimiento/eval/barra_sin_gpu.yaml` | Regenerated |
| `gee-backend/tests/new/conocimiento/test_normas_eval.py`, `test_normas_kernel.py`, `gee-backend/tests/test_mutation_targets_normas.py` | Modified |
| `docs/rag/runbook-encendido.md` §4.4 | Modified |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Operator reads exit 0 as cleared bar | Med | Distinct banner, mutual exclusion, runbook 5b wording |
| Helper extraction shifts mutation surface | Med | Re-run mutation targets; `exigir_superada` tests stay green |
| Checkout YAML ≠ image YAML | Low | Worst case still unranked; noted in runbook |

## Rollback Plan

Revert the commit: flag, predicate, YAML and runbook return together. Nothing is ingested here. A later bad ingest rolls back with `activo=false`.

## Success Criteria

- [ ] Behaviour matrix (allowed / refused / usage error) covered by tests, including `--dry-run`.
- [ ] Existing `TestExigirBarra` and `exigir_superada` mutation tests pass unchanged.
- [ ] YAML holds the post-follow figures and is produced by `derivar_desde`.
- [ ] Spec delta and runbook 5a/5b never call this path a passed bar.
