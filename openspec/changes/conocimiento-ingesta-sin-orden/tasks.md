# Tasks: Production Ingest Under an Honest Failed Bar (Served Unranked)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~520 hand-written (src ~150, tests ~325, runbook ~45) + ~1,773 generated (report `.md` 193, `.results.json` 1,580) = ~2,300 |
| 400-line budget risk | High |
| Chained PRs recommended | No. Owner chose one PR. |
| Suggested split | Not used. The three units ship together. |
| Delivery strategy | exception-ok |
| Chain strategy | size:exception (single PR, owner 2026-10-23) |

Decision needed before apply: Resolved
Chained PRs recommended: No
Chain strategy: size:exception (single PR, owner 2026-10-23)
400-line budget risk: High. Accepted.

The owner accepted one PR on 2026-10-23. The generated report pair ships in that PR as measurement evidence. Do not split the apply.

### Suggested Work Units

Test command base: `cd gee-backend && venv/bin/python -m pytest <file> -q -p no:logging`.

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Predicate + exception + kernel and mutation tests (~185) | PR 1 (base: main or tracker) | `test_normas_kernel.py`, `tests/test_mutation_targets_normas.py` | N/A: pure function, no runtime surface | `barra_sin_gpu.py` + two test files |
| 2 | `--produccion-sin-orden` in `rag_ingest.py` + `TestProduccionSinOrden` (~275) | PR 2 (base: PR 1) | `test_normas_eval.py -k "ExigirBarra or ProduccionSinOrden"` | `rag_ingest.py --corpus-path /nonexistent --corpus-sha <40 x a> --entorno produccion --produccion-sin-orden --dry-run`: exit 1 + abort banner; add `--exigir-barra`: exit 2 | `rag_ingest.py` + eval test file |
| 3 | Report pair, YAML, pin test, runbook (~100 hand + 1,773 generated) | PR 3 (base: PR 2) | `test_normas_kernel.py -k CargadorDeLaBarra`, `test_normas_eval.py -k ProduccionSinOrden` | N/A: shipped artifact is exercised by tests; no real-SHA run (would approach production ingest) | data files + runbook; reverts to the pre-follow YAML |

## Phase 1: Predicate (`barra_sin_gpu.py`)

- [x] 1.1 Safety net: run `test_normas_kernel.py -k CargadorDeLaBarra`, `test_mutation_targets_normas.py`, `test_normas_eval.py -k ExigirBarra`; record baseline counts.
- [x] 1.2 RED, `test_normas_kernel.py`: class `TestExigirNoSuperadaHonesta` using `_barra(estado="no_superada", ...)`. Honest pass returns `None` (hit 0.6470588235294118). Triangulate: each figure failing alone (hit 0.71, separacion 0.99, vigencia 0.99) passes.
- [x] 1.3 RED, same class: each refusal raises `BarraSinOrdenRechazada`. `superada` message contains `--exigir-barra`; `no_medido`; `modo="bm25_ce"`; `OTRO_SHA` (match `corpus_sha`); a `None` figure (three cases); all-passing `no_superada` (match `inconsistent`). Order: `superada` with wrong modo still names `--exigir-barra`.
- [x] 1.4 GREEN, `barra_sin_gpu.py`: add `BarraSinOrdenRechazada(RuntimeError)` and `exigir_no_superada_honesta(artefacto, corpus_sha) -> None` after `exigir_superada`, in the locked check order. No shared helper; `exigir_superada` and lines 155-164 untouched.
- [x] 1.5 Mutation targets, `tests/test_mutation_targets_normas.py` (DB-free, reuse its `_barra`): class `TestBarraSinOrden`, one assertion per refusal branch, plus boundaries (0.72, 1.0 and 1.0 exactly on the constants do not count as failing). Spot-check: flip one `<` in the predicate, confirm red, revert.
- [x] 1.6 REFACTOR gate: rerun the 1.1 set. `TestBarra`, `TestExigirBarra`, `TestCargadorDeLaBarra` green; `git diff` shows `exigir_superada` unchanged.

## Phase 2: CLI (`rag_ingest.py`)

- [x] 2.1 Safety net: `test_normas_eval.py -k ExigirBarra` baseline (includes `test_produccion_sin_exigir_barra_no_abre_nada`).
- [x] 2.2 RED, `test_normas_eval.py`: class `TestProduccionSinOrden` (reuse `ARGS`, `_NullEngine`; helper writes an artifact via `volcar(derivar_desde(...))` and patches `RUTA_BARRA`). Flag exists, default `False`.
- [x] 2.3 RED, usage errors: both flags, `--entorno laboratorio --produccion-sin-orden`, and laboratorio with both all `SystemExit(2)`. `INGESTION ABORTED` absent from stderr; `cargar_barra`, `create_engine` and `ingest` never called.
- [x] 2.4 RED, neither flag with produccion: exit 1; stderr contains `produccion`, `exigir-barra` and `produccion-sin-orden`; `ingest` never called.
- [x] 2.5 RED, refusal matrix (parametrized, each also with `--dry-run`): `superada` (names `--exigir-barra`), `no_medido`, invalid YAML, SHA mismatch, wrong modo, all-passing `no_superada`. Exit 1, `INGESTION ABORTED — nothing was written.`, `--produccion-sin-orden:` prefix, no engine, no ingest.
- [x] 2.6 RED, success: honest `no_superada` exits 0, `ingest` called once (also with `--dry-run`). stderr has the exact banner sentence, figures and SHA; stdout has `barra                : failed lab bar, served unranked`; `superada` absent from stdout+stderr. Triangulate: the `--exigir-barra` success shows no `failed lab bar`.
- [x] 2.7 GREEN, `rag_ingest.py` parser: add `--produccion-sin-orden`; put it and `--exigir-barra` in `add_mutually_exclusive_group`; update `--entorno` help; in `main()` use `parser.error` when the flag is not with produccion. Runs 2.3.
- [x] 2.8 GREEN, `rag_ingest.py` gate: neither-flag abort names both flags and keeps `produccion` and `exigir-barra`; leave the `--exigir-barra` block as is; add the unranked block (`cargar_barra` → `exigir_no_superada_honesta`, catch `BarraInvalida` and `BarraSinOrdenRechazada`, exit 1) before the `database_url` check; print banner; add the summary line.
- [x] 2.9 REFACTOR gate: `test_normas_eval.py -k "ExigirBarra or ProduccionSinOrden"` green with no edits to existing tests.

## Phase 3: Recorded artifact and runbook

- [x] 3.1 RED, `test_normas_kernel.py`: change `test_el_artefacto_enviado_registra_la_medicion_no_superada` to hit `approx(22/34)` (0.6470588235294118) and vigencia `== 1.0`. Fails against the old YAML.
- [x] 3.2 RED, `TestProduccionSinOrden`: shipped artifact with `PINNED_CORPUS_SHA`: `exigir_superada` raises `BarraNoSuperada`, `exigir_no_superada_honesta` returns; `main()` with `--produccion-sin-orden` exits 0 (spied `ingest`).
- [x] 3.3 Copy `/tmp/rag-eval-seguimiento-citas/retrieval-eval-ecab0a0e-2026-10-23.{md,results.json}` to `docs/rag/retrieval-eval-ecab0a0e-2026-10-23-seguimiento-citas.{md,results.json}`. The original pair stays byte-identical (`git status`).
- [x] 3.4 GREEN, `barra_sin_gpu.yaml`: paste the report's YAML block verbatim as the body. Update header lines 3-7 (vigencia 1.00; names the new report; `--exigir-barra` refuses, `--produccion-sin-orden` accepts).
- [x] 3.5 Verify with `jq`: the YAML equals `barra_sin_gpu.medido` (`no_superada`, 0.6470588235294118, 1.0, 1.0, 34, SHA `ecab0a0e…`). Rerun 3.1 and 3.2 green.
- [x] 3.6 Runbook §4.4 only (`docs/rag/runbook-encendido.md`): replace the stale `no_medido` sentence (~line 861) with the current `no_superada` state.
- [x] 3.7 Runbook step 5 → 5a (existing text unchanged) and 5b (`--produccion-sin-orden`; states it is not a cleared bar; surface stays unranked; exit 1 vs exit 2; checkout YAML vs image YAML note).
- [x] 3.8 Docs check: `rg no_medido` finds nothing in §4.4; `5a`, `5b` and `not a cleared bar` present; the diff stays inside §4.4.

## Phase 4: Final verification (no new code)

- [x] 4.1 Run the three focused files together; all green.
- [x] 4.2 `ruff check`, `ruff format --check` and mypy on changed Python files. No build.
- [x] 4.3 Mutation gate (verify phase): `scripts/cosmic_gate.py --config .cosmic-ray.normas.toml --session /tmp/cr-normas.sqlite --min-kill-rate 0.30`; record the `normas-barra` kill rate. Config and targets JSON unchanged.
- [x] 4.4 Scope guard: `git diff --name-only` matches the design's file table. No `normas.py`, schemas, router, CLI, MCP, `service.py`, gold, constants; no production ingest, flag flip or image publish.
