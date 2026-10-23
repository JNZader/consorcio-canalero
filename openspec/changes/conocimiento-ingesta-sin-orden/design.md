# Design: Production Ingest Under an Honest Failed Bar (Served Unranked)

## Technical Approach

Exploration approach 1, locked. `rag_ingest.main()` gains `--produccion-sin-orden`, checked by a new predicate `exigir_no_superada_honesta` in `barra_sin_gpu.py`. `exigir_superada`, `superada_para` and serving stay unchanged, so the screen stays unranked by construction. The YAML is refreshed from the post-follow report block that `derivar_desde` produced.

## Architecture Decisions

| Decision | Options | Tradeoff | Choice |
|---|---|---|---|
| Predicate | widen `exigir_superada`; new function | widening loosens the strict gate and changes `superada_para` | new `exigir_no_superada_honesta(artefacto, corpus_sha) -> None` |
| Exception | reuse `BarraNoSuperada`; new class | `BarraNoSuperada` means "not cleared", which is wrong for refusing a `superada` | new `BarraSinOrdenRechazada(RuntimeError)` |
| Shared modo/SHA helper | extract lines 155-164 of `exigir_superada` into `_exigir_modo_y_sha`; duplicate the two checks | extraction moves the mutation-pinned body and forces one exception type; duplication costs about 8 lines | **no extraction**. `exigir_superada` stays byte-identical |
| Usage errors | gate abort (exit 1); `parser.error` (exit 2) | argparse already owns invalid flag combinations | both flags: `add_mutually_exclusive_group`. Laboratorio plus flag: `parser.error`. Both exit 2 before anything else runs |
| Report filename | overwrite the existing basename; new suffix | overwriting destroys the pre-follow artifact (vigencia 0.6666666666666666) | `docs/rag/retrieval-eval-ecab0a0e-2026-10-23-seguimiento-citas.{md,results.json}` |

This deviates from the proposal's helper on purpose: `TestBarra` in `test_mutation_targets_normas.py` (lines 209-233), `TestExigirBarra` and `TestCargadorDeLaBarra` stay green without edits. A later extraction would move lines 155-164, and those public refusals must stay green.

## Predicate Contract

Checks run in this order and the first failure raises `BarraSinOrdenRechazada`:

1. `estado == superada`: refused. The message names `--exigir-barra`.
2. `estado != no_superada` (that is, `no_medido`): refused.
3. `modo != MODO_SIN_GPU`: refused.
4. `corpus_sha` mismatch: refused.
5. Any figure is `None`: refused, because a missing figure is not evidence of failure.
6. None of `hit_rate_at_5 < BARRA_HIT_RATE`, `separacion < BARRA_SEPARACION`, `vigencia < BARRA_VIGENCIA` holds: refused as inconsistent.

`BarraInvalida` from `cargar_barra` covers an invalid file.

## Data Flow

```
argv ─→ argparse (exclusive group; laboratorio+flag → parser.error, exit 2)
     ─→ produccion and neither flag → abort, names both flags, exit 1
     ─→ --exigir-barra        → exigir_superada            (unchanged)
     ─→ --produccion-sin-orden → cargar_barra → exigir_no_superada_honesta
            refused → abort, exit 1
            passes  → banner on stderr
     ─→ DATABASE_URL / create_engine / ingest (dry-run included)
```

The gate runs before corpus files, the database and the pin, so `--dry-run` gets the same refusal and the same banner.

**Abort** (same shape as today; after the leading newline, stderr starts with):
`INGESTION ABORTED — nothing was written.\n--produccion-sin-orden: {abort}`.
Production with neither flag: `--entorno produccion exige --exigir-barra o --produccion-sin-orden.`

**Success banner** (stderr, exact sentence; it never contains `superada`):
`PRODUCTION INGEST UNDER A FAILED LAB BAR: the norms surface stays unranked (orden_presentado=false); this is not a cleared bar.`
It is followed by `hit@5 {h}, norma-vs-secundaria {s}, vigencia {v}, corpus_sha {sha}`. The final summary adds `barra                : failed lab bar, served unranked`.

## File Changes

| File | Action | Description |
|---|---|---|
| `gee-backend/app/domains/conocimiento/eval/barra_sin_gpu.py` | Modify | Add `BarraSinOrdenRechazada` and `exigir_no_superada_honesta`. Existing functions untouched |
| `gee-backend/scripts/rag_ingest.py` | Modify | Exclusive group, `parser.error`, new abort text, gate, banner, summary line, `--entorno` help text |
| `gee-backend/app/domains/conocimiento/eval/barra_sin_gpu.yaml` | Modify | Body replaced verbatim by the report's YAML block. Header comment updated (vigencia 1.00, names the new report and `--produccion-sin-orden`) |
| `docs/rag/retrieval-eval-ecab0a0e-2026-10-23-seguimiento-citas.md` and `.results.json` | Create | Copied from `/tmp/rag-eval-seguimiento-citas/`, renamed |
| `gee-backend/tests/new/conocimiento/test_normas_kernel.py` | Modify | Pin test to `22/34`, `1.0`, `1.0`; add predicate unit tests |
| `gee-backend/tests/new/conocimiento/test_normas_eval.py` | Modify | New `TestProduccionSinOrden` class |
| `gee-backend/tests/test_mutation_targets_normas.py` | Modify | Add a mutation target for each predicate refusal |
| `docs/rag/runbook-encendido.md` | Modify | §4.4: stale `no_medido` sentence (line 861); step 5 split into 5a (`--exigir-barra`, unchanged) and 5b (`--produccion-sin-orden`, stated as not a cleared bar). Rest untouched |

**How `derivar_desde` gets pointed at the report.** `derivar_desde` reads no report file. `rag_eval.py` calls it through `report.bloque_barra_sin_gpu` and prints its `a_yaml` output inside the report. The post-follow run already wrote that block into `/tmp/.../retrieval-eval-ecab0a0e-2026-10-23.md`, and its `.results.json` `barra_sin_gpu.medido` agrees with it. Steps: copy both files under the new basename, never onto the existing one. Then paste the block verbatim into the YAML body and diff the result against the json's `medido`. Never type a figure.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | each predicate refusal and the honest pass | `_barra(...)` fixtures in the kernel file |
| Unit | `exigir_superada` unchanged | existing tests, no edits |
| CLI | full invocation matrix, including `--dry-run` | `_espia`: `ingest`/`create_engine` never called on refusal; `SystemExit(2)` on usage errors; exit 1 plus abort prefix; banner present and `"superada" not in` stdout+stderr on success |
| Regression | `test_produccion_sin_exigir_barra_no_abre_nada` | new text still contains `produccion` and `exigir-barra` |
| Mutation | `test_mutation_targets_normas.py` | run it; existing targets unchanged |

## Threat Matrix

N/A. One argparse flag; no routing, subprocess, VCS or executable boundary.

## Migration / Rollout

No migration. The YAML stays `no_superada`, so `superada_para` remains false. Rollback: revert the commit.

## Open Questions

None blocking.
