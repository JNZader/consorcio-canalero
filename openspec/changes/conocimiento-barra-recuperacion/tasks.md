# Tasks: Same-Statute Citation Follow on the No-GPU Page

Strict TDD: ON (`openspec/config.yaml` `strict_tdd: true`; init obs #1530 records no flag or command, only "Pytest backend, real PostgreSQL"). Test command: `cd gee-backend && pytest tests/new/conocimiento/<file> -v`. Each GREEN follows its RED.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 430-520 (prod ~140, tests ~330) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (pure + schema) → PR 2 (service wiring) |
| Delivery strategy | ask-on-risk |
| Chain strategy | size:exception (single PR, owner 2026-10-23) |

Decision needed before apply: Resolved
Chained PRs recommended: Yes
Chain strategy: size:exception
400-line budget risk: High

| Unit | Goal | PR | Focused test command | Runtime harness | Rollback |
|------|------|----|----------------------|-----------------|----------|
| 1 | Phases 1-2 | PR 1 | `pytest tests/new/conocimiento/test_recuperacion_citas.py` | N/A: pure code, not wired | Revert `citas.py`, `__init__`, `schemas.py` |
| 2 | Phase 3-4 | PR 2 | same file + `test_normas_kernel.py` | N/A: no ingest, no rag_eval | Revert `service.py` hunk |

## Phase 1: Pure functions (`recuperacion/citas.py`)

- [x] 1.1 RED: `test_recuperacion_citas.py` grammar table. Accept: NBSP `Art.\u00a01º`, `193 ter`→`193ter`, `de este código`, `de esta ley`, case, textual order, repeats. Reject: `arts. 6 y 82`, ranges, `de la Ley 11015`, `Ley 9867 art. 30`, `Artículo N`.
- [x] 1.2 GREEN: create `citas.py` `extraer_citas` (design regex; suffixes from `parser.UNIDAD_RE`, `_normalise_suffix`).
- [x] 1.3 RED: `clave_destino`: `5589#180`+`276`→`5589#276`; `X#art180`→`X#art276`; other segment style→`None`.
- [x] 1.4 GREEN: `clave_destino`.
- [x] 1.5 RED: `componer_pagina` table with boundary cases on `len(follows)+1 == k-1-p` and one over: first overflow ends selection (later fitting citation ignored), `p=k-1` admits none, citer and higher ranks kept, dedup takes no slot, selection order, prefix BM25 order, size ≤ k.
- [x] 1.6 GREEN: `componer_pagina`; export the three names in `recuperacion/__init__.py`.

## Phase 2: Schema

- [x] 2.1 RED: `CitaRecuperada.seguida_desde` defaults `None`; not on `UnidadNorma`.
- [x] 2.2 GREEN: add `seguida_desde: str | None = None` in `schemas.py`.

## Phase 3: Service wiring (`_recuperar_bm25_sin_ce` only)

- [x] 3.1 RED (seeded snapshot, small `profundidad`): T-5 shape, cited target outside the pool enters the tail once, displaces lowest rank.
- [x] 3.2 RED: cross-statute (same number, other `documento_id`) dropped; absent number dropped; no second hop; on-page target keeps position, no slot.
- [x] 3.3 RED: follow has `rango_bm25 is None`, `seguida_desde`=citer key, `valor_bm25` real pool value or `None`; prefix order untouched; exactly k distinct on a full page.
- [x] 3.4 RED: `normas.buscar` without superada: `citation_key` order, `orden_presentado` False. Characterization guard: `bm25_ce` with reranker applies no follow.
- [x] 3.5 GREEN: `service.py`: `textos_indexados`, one `hydrate_citations` call (page ∪ targets), same `documento_id`, `IngestionAbort` on missing page key, `n_bm25` unchanged; amend docstring only.

## Phase 4: Regression and scope

- [x] 4.1 Run `test_normas_kernel.py`, `test_recuperacion_bm25.py`, `tests/test_mutation_targets_normas.py`. Their seeds have no citations: keep `:155` (`rango_bm25 is not None`) and `:559` (sort by `rango_bm25`) as is. Only if a seed there gains a citation, filter those two to `seguida_desde is None`; never weaken the citation-free assertions.
- [x] 4.2 `ruff` + `mypy` on touched files.
- [x] 4.3 `git diff --stat` shows no change to `bm25.py`, `expansion.py`, `_candidatos_bm25`, `bm25_ce`, `barra_sin_gpu.yaml`, gold, corpus, spec, design.

Out of scope: measuring or writing the bar, `rag_eval`, ingest. Mutation thresholds: none for backend; boundary cases in 1.5 are the targets.
