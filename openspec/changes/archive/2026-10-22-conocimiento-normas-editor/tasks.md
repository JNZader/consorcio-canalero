# Tasks: Norms surface, mute kernel and Ley 8803 editor

## Review Workload Forecast

Estimated changed lines: ~2,000-2,600. Owner chose one PR (`size-exception`) on 2026-10-22. The six units below are implementation order inside that PR, not separate PRs. Delivery: ask-on-risk.

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: High

Order policy: bar `superada` for the active SHA → units ordered by `rango` (BM25 order of `bm25_sin_ce`), no scores. Otherwise sorted by `citation_key`, `orden_presentado=false`, no `rango` or score.

Ships flag false, bar `no_medido`. Not apply work: corpus push, 57-gold run, lab/prod ingest, flag flip, box read, deploy, CIDI, pedido 8, obra notes, abstention retune, second ranker, CUDA reranker over HTTP.

### Suggested Work Units

Test = `cd gee-backend && pytest tests/new/conocimiento/<file>`.

- U1 Kernel. Test `test_normas_kernel.py`. Harness N/A: library. Rollback: revert kernel.
- U2 Eval. Test `test_normas_eval.py`. Harness N/A: run is owner work. Rollback: revert eval.
- U3 Route. Test `test_normas_router.py`. Harness: TestClient 503. Rollback: revert router.
- U4 CLI, MCP. Test `test_normas_cli.py`, `test_normas_mcp.py`. Harness: `list_tools`. Rollback: delete scripts.
- U5 Editor. Test `test_normas_editor.py`. Harness N/A: offline. Rollback: delete editor.
- U6 Web. Test `npx vitest run ConocimientoPanel`. Harness N/A: flag off. Rollback: revert web.

## Phase 1: Kernel (unit 1, same PR)

- [x] 1.1 RED `test_normas_kernel.py`: `bm25_sin_ce` needs no reranker; reranker or qvec raises `ValueError`; `bm25_ce` without reranker still raises `RerankerRequerido`.
- [x] 1.2 `service.py`: `MODO_SIN_GPU`, `_recuperar_bm25_sin_ce`, `MODOS` (not `MODOS_RRF`), re-export `citation_keys`.
- [x] 1.3 RED loader refuses non-`superada`, SHA mismatch, hit@5 below `BARRA_HIT_RATE`, separation below 1.00.
- [x] 1.4 Create `eval/barra_sin_gpu.py`, `.yaml` (`no_medido`).
- [x] 1.5 RED `chequear` per condition (sha, clave, span, vigencia); `leer` byte-exact, unknown key refused.
- [x] 1.6 RED order policy (both branches); empty result has `sin_unidades`, no abstention field.
- [x] 1.7 `repository.py`, `schemas.py`, `normas.py`.

## Phase 2: Eval arm (unit 2, same PR)

- [x] 2.1 RED `test_normas_eval.py`: `derivar_desde` refuses synthetic; migration misses counted apart; arm never labeled `bm25_ce`; `--exigir-barra` refuses unless `superada`.
- [x] 2.2 `eval/harness.py` (`LEGS_POR_MODO`, `MODOS_SIN_SENAL_RATIFICADA`), `eval/report.py` (`MODO_GATEADO` unchanged), `derivar_desde`.
- [x] 2.3 `rag_eval.py` (no reranker), `rag_ingest.py` (`--exigir-barra`).

## Phase 3: Route (unit 3, same PR)

- [x] 3.1 RED `test_normas_router.py`: default 503; QA off, norms on → norms 200, mailbox 503; non-admin refused; `sin_corpus_activo`; empty 200.
- [x] 3.2 `config.py` flag (false); `router.py` gate and `POST .../normas/buscar`.

## Phase 4: CLI and MCP (unit 4, same PR)

- [x] 4.1 RED: route, CLI, MCP return identical units; exactly three tools.
- [x] 4.2 `rag_normas.py` CLI.
- [x] 4.3 `rag_normas_mcp.py`, `requirements-mcp.txt` (exact pin, supply-chain check first).

## Phase 5: Editor (unit 5, same PR)

- [x] 5.1 RED `test_normas_editor.py`: eight drafts reproduce, placeholders masked; pedido 8 and obra notes refused; free-text citation lint.
- [x] 5.2 RED export refuses `privado`, invented key, moved SHA; names slot; no output, no socket.
- [x] 5.3 `editor.py`, `pedidos_8803.yaml`, `fixtures/pedidos-8803/`.
- [x] 5.4 `router.py` export route (`.../pedidos/{id}/exportar`).
- [x] 5.5 Scan fixtures against `RAG_GOLD_PRIVADO_PATH` when set.

## Phase 6: Web and docs (unit 6, same PR)

- [x] 6.1 RED vitest: unranked, empty, SHA.
- [x] 6.2 `conocimiento.ts`, `useConocimientoNormas.ts`, `ConocimientoPanel.tsx`.
- [x] 6.3 `docs/rag/runbook-encendido.md`: `--exigir-barra`, operator read, gold re-validation.
- [x] 6.4 Add `normas.py`, `editor.py`, `barra_sin_gpu.py` to `.cosmic-ray.toml`.
