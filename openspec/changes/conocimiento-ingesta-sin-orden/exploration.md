## Exploration: production ingest of an unranked corpus (conocimiento-ingesta-sin-orden)

Phase: sdd-explore (investigation only). No product code, test, bar file, gold or corpus was touched. No ingest, commit or push. Repo HEAD at read time: `e77c8790`.

### Decision already made by the owner (not reopened)

- Production ingest must be able to load the corpus when `barra_sin_gpu.yaml` is an honest `no_superada` for the exact SHA.
- The norms screen stays unranked: `citation_key` order, `orden_presentado: false`, no `rango`. Rank order still requires `superada_para`, which stays false.
- The path is a SEPARATE flag. `--exigir-barra` is not loosened. `exigir_superada` does not accept `no_superada`.
- Still refused: `superada` over failing figures, `no_medido`, SHA mismatch. Laboratorio keeps ingesting without the bar.

### Current State (verified in code)

**Entry point** `gee-backend/scripts/rag_ingest.py`, function `main` (lines ~245-275), in this order:

1. `if args.entorno == "produccion" and not args.exigir_barra:` print `INGESTION ABORTED`, return 1. No file, connection or pin is touched.
2. `if args.exigir_barra:` call `barra_sin_gpu.exigir_superada(barra_sin_gpu.cargar_barra(), args.corpus_sha)`. On `BarraInvalida` or `BarraNoSuperada` print `INGESTION ABORTED ... --exigir-barra: {abort}` and return 1. This runs before the database, the corpus and the pin, so `--dry-run` is refused too.
3. Only then the database URL check, `create_engine`, and `ingest(...)`.

`--entorno` has `choices=("laboratorio", "produccion")`, default `laboratorio`. `ingest()` itself knows nothing about the bar; the gate lives only in `main`. `Makefile` target `rag-ingest` (line ~387) passes neither flag, so it is laboratorio and is not affected.

**Loader** `gee-backend/app/domains/conocimiento/eval/barra_sin_gpu.py`:

- `cargar_barra(ruta=None) -> BarraSinGpu`: parses the YAML, rejects unknown `estado`, rejects figures under `no_medido`, rejects an incomplete header under `superada` / `no_superada`. Raises `BarraInvalida`.
- `exigir_superada(artefacto, corpus_sha)`: raises `BarraNoSuperada` in this order: `estado != "superada"`, `modo != MODO_SIN_GPU`, `corpus_sha` mismatch, `hit_rate_at_5 < BARRA_HIT_RATE (0.72)`, `separacion_norma_secundaria < BARRA_SEPARACION (1.0)`, `vigencia_correcta < BARRA_VIGENCIA (1.0)`. The state word is a claim and the figures are the evidence.
- `superada_para(corpus_sha, ruta=None) -> bool`: wraps `exigir_superada`, fail-closed on any refusal. This is the only thing that unlocks rank order.
- Constants `ESTADO_NO_MEDIDO / ESTADO_SUPERADA / ESTADO_NO_SUPERADA`, `RUTA_BARRA` (the file next to the module), `derivar_desde` (the only producer of the artifact), `volcar`, `a_yaml`.

**Serving side** `gee-backend/app/domains/conocimiento/normas.py`:

- `buscar` computes `ordenado = modo == MODO_SIN_GPU and bool(resultado.hits) and barra_sin_gpu.superada_para(activo.corpus_sha)`. True goes to `_ordenado` (BM25 order, 1-based `rango`, `NOTA_CON_ORDEN`). False goes to `_sin_orden(activo, modo, hits)`.
- `_sin_orden` sorts by `UnidadNorma.citation_key` and returns `ResultadoNormas` with `NOTA_SIN_ORDEN`. `ResultadoNormas.orden_presentado` is `Literal[False]` and `ResultadoNormasOrdenado.orden_presentado` is `Literal[True]` (`schemas.py` lines 481 and 489), so the type system already separates the two.
- Consequence: nothing in serving needs to change. With `no_superada`, `superada_para` is False, so the screen is unranked by construction.

**Checked-in bar** `eval/barra_sin_gpu.yaml`: `estado: no_superada`, SHA `ecab0a0ed9cfbfb7bca0f7673f0283bc75bb406e`, n=34, `hit_rate_at_5` 0.6470588235294118, `separacion_norma_secundaria` 1.0, `vigencia_correcta` 0.6666666666666666 (pre-citation-follow measurement).

**Tests that pin the abort** (named for the proposal):

- `gee-backend/tests/new/conocimiento/test_normas_eval.py`, class `TestExigirBarra` (~line 436):
  - `test_el_flag_existe_y_no_es_el_default`
  - `test_el_artefacto_enviado_no_superada_rechaza_antes_de_ingerir` (this is the one the owner means: the shipped artifact is refused with exit 1, `nothing was written`, `ingest` never called)
  - `test_rechaza_un_sha_que_no_es_el_de_la_barra`
  - `test_con_la_barra_superada_para_ese_sha_ingesta`
  - `test_tambien_rige_con_dry_run`
  - `test_sin_el_flag_el_comportamiento_no_cambia` (asserts `cargar_barra` is NOT read without the flag)
  - `test_el_default_es_laboratorio`, `test_produccion_sin_exigir_barra_no_abre_nada` (asserts stderr contains `produccion` and `exigir-barra`), `test_laboratorio_sigue_pudiendo_ingerir_sin_la_barra`
  - helper `_espia` monkeypatches `rag_ingest.ingest` and `create_engine`; `_NullEngine`, `_corrida`, `_procedencia`, `_gold_evaluable` are reused.
- `gee-backend/tests/new/conocimiento/test_normas_kernel.py`, class `TestCargadorDeLaBarra`: `test_el_artefacto_enviado_registra_la_medicion_no_superada` (pins the CURRENT shipped figures: hit 22/34, vigencia 2/3), `test_el_artefacto_enviado_no_se_puede_exigir`, `test_rechaza_lo_que_no_esta_superada` (parametrised `no_medido` / `no_superada`, `match="estado"`), SHA, hit@5, separation and vigencia refusals, mode refusal. Helper `_barra(**cambios)`.
- `gee-backend/tests/test_mutation_targets_normas.py` (lines ~205-230): mutation-pinned `exigir_superada` refusals and `test_superada_para_falla_cerrado`. Any refactor of `exigir_superada` changes this mutation surface.
- Rank-order side, unaffected: `test_normas_kernel.py` (`orden_presentado` asserts ~574-659), `test_normas_router.py` (`test_con_barra_superada_un_resultado_vacio_sigue_sin_orden`), `test_normas_cli.py`, `test_normas_mcp.py`.

**Spec**: `openspec/specs/knowledge-corpus-ingestion/spec.md`, requirement "Lab Measurement Before Production Ingest". It says "A production ingest MUST happen only if that recorded run for the same SHA has hit@5 >= 0.72" and the scenario "Bar failed or absent ... production ingest MUST NOT proceed". The owner decision contradicts this text, so it needs a MODIFIED delta, not just code. Scenario "Production ingest names its environment" also needs to name the second flag.

### Confirmation: the loader still refuses `exigir_superada` on the post-follow lab figures

Figures: `vigencia_correcta` 1.0, `hit_rate_at_5` 0.6470588235294118, `separacion` 1.0, `estado` `no_superada`, same SHA `ecab0a0e...`.

- As is (`no_superada`): `exigir_superada` raises `BarraNoSuperada` on the first check (`estado`). `superada_para` is False.
- Hypothetically hand-edited to `superada` over the same figures: estado, modo and SHA pass; the `hit_rate_at_5 < 0.72` check raises (0.647 < 0.72). Vigencia 1.0 and separation 1.0 do not rescue it.
- Method: read from the code above. A direct Python probe was blocked by a local guard policy, so this was NOT executed. The proposal's tests should assert it (a `_barra(estado="superada", hit_rate_at_5=0.6470588235294118, vigencia_correcta=1.0)` refusal with `match="hit@5"`).
- Note: the checked-in YAML is NOT updated by this exploration. Refreshing it to the post-follow figures is a proposal task (values to record: vigencia 1.0, hit@5 0.6470588235294118, separation 1.0, `no_superada`, SHA `ecab0a0ed9cfbfb7bca0f7673f0283bc75bb406e`). It forces the update of `test_el_artefacto_enviado_registra_la_medicion_no_superada`, which pins `2/3`.

### Affected Areas

- `gee-backend/scripts/rag_ingest.py` — new flag, the `produccion` guard (line ~251), a new gate block next to the `--exigir-barra` block, a printed banner.
- `gee-backend/app/domains/conocimiento/eval/barra_sin_gpu.py` — a new explicit predicate for "honest `no_superada`" (new function, `exigir_superada` untouched in behaviour).
- `gee-backend/tests/new/conocimiento/test_normas_eval.py` — new test class beside `TestExigirBarra`; one existing test's stderr assertion may need the second flag name.
- `gee-backend/tests/new/conocimiento/test_normas_kernel.py` and `tests/test_mutation_targets_normas.py` — loader tests for the new predicate; the post-follow figures pin.
- `gee-backend/app/domains/conocimiento/eval/barra_sin_gpu.yaml` — figures refresh (proposal scope, not here).
- `docs/rag/runbook-encendido.md` §4.4 — step 5 amendment and a stale sentence (see below).
- `openspec/specs/knowledge-corpus-ingestion/spec.md` — delta for "Lab Measurement Before Production Ingest".
- NOT affected: `normas.py`, `schemas.py`, router, CLI, MCP, `service.py`, migrations, `Makefile`.

### Approaches

1. **New flag + new predicate in `barra_sin_gpu` (recommended)**
   - Add `exigir_no_superada_honesta(artefacto, corpus_sha)` (name to be settled in design). It requires: `estado == ESTADO_NO_SUPERADA`; `modo == MODO_SIN_GPU`; `corpus_sha` equal; and that the figures really fail the bar (at least one of hit@5, separation, vigencia under its constant). A `no_superada` over passing figures is refused as inconsistent. `no_medido` is refused (it carries no measurement; header already enforced by `cargar_barra`). `superada` is refused with a message pointing to `--exigir-barra`.
   - Reuse of the mode and SHA checks should come from a private helper shared with `exigir_superada` so the two cannot drift. The behaviour of `exigir_superada` must not change; the existing refusals and mutation tests stay green.
   - In `main`: the `produccion` guard accepts either flag; the two flags are mutually exclusive; the new flag requires `--entorno produccion`; the check runs at the same position as `--exigir-barra` (before the database, the corpus and the pin), so it also applies to `--dry-run`.
   - Pros: smallest change; one file for the policy; serving untouched; fail-closed; each flag has one meaning.
   - Cons: a second production flag to document; helper extraction touches the mutation-pinned surface.
   - Effort: Low-Medium.
2. **Third `--entorno` choice** (for example `produccion-sin-orden`)
   - Pros: no new flag.
   - Cons: contradicts the owner decision ("a SEPARATE flag"); changes the meaning of the guard `args.entorno == "produccion"` and every place that tests it; `entorno` stops being a clean two-value axis.
   - Effort: Medium. Rejected.
3. **Make `--exigir-barra` take a value** (`--exigir-barra=no_superada`)
   - Pros: one flag.
   - Cons: it loosens the existing flag's surface, which the owner ruled out, and a typo or a changed default turns the strict gate into the permissive one.
   - Effort: Low. Rejected.
4. **Drop the production gate or add an `--i-know` bypass**
   - Cons: removes the safety property the whole bar exists for; `no_medido` and SHA mismatch would no longer be refused. Rejected.

### Recommendation

Approach 1, with the flag named **`--produccion-sin-orden`**.

Grounding in the existing vocabulary: the parser already speaks `--entorno {laboratorio, produccion}` and `--exigir-barra`; the guard text says "`--entorno produccion` exige `--exigir-barra`". `--produccion-sin-orden` reads as "the production ingest that serves without order": it names the environment it is valid for (`produccion`) and the consequence (`sin orden`, the same words as `_sin_orden` in `normas.py` and `NOTA_SIN_ORDEN`). It deliberately does NOT contain `barra`, `exigir` or `superada`, so nobody can read it as a cleared bar.

Alternatives considered, with tradeoff:

- `--exigir-barra-medida`: closest to the existing flag, but "barra" in the name invites exactly the confusion to avoid (reads as a lighter version of the gate).
- `--admitir-barra-no-superada`: honest and explicit, but long, and it puts the failure in the operator's hands as an "admit", which sounds like a waiver.
- `--sin-orden`: shortest, but does not say it is a production-only path, and it could be read as an option that changes serving output.

Behaviour contract for the design:

| Invocation | Result |
|---|---|
| `--entorno produccion` alone | refused, names both flags |
| `--entorno produccion --exigir-barra` | unchanged |
| `--entorno produccion --produccion-sin-orden`, honest `no_superada` for this SHA | allowed |
| same, `superada` | refused ("use --exigir-barra") |
| same, `no_medido`, invalid file, SHA mismatch, wrong `modo` | refused |
| same, `no_superada` with all figures passing | refused as inconsistent |
| `--produccion-sin-orden` with `--entorno laboratorio` | usage error, nothing runs |
| both flags together | usage error |
| `--entorno laboratorio` without flags | unchanged |

Refusals use the same shape as today: `INGESTION ABORTED — nothing was written.`, exit 1, named condition.

### Red-team of the flag

1. **Confused with a cleared bar.**
   - `main` returns 0 and prints `committed : True` for both paths. An operator reading only the exit code cannot tell them apart. Add a distinct banner on stderr AND a line in the final summary, for example `barra : no_superada — la superficie de normas queda SIN ORDEN (orden_presentado=false)`. The banner must not use the word `superada` alone or `OK`.
   - The banner names the SHA and the figures read from the file (hit@5, vigencia), so the operator sees the measured shortfall at the moment of the ingest.
   - `rag_corpus` has no column recording the bar state, and adding one is a migration and out of scope. The API response already carries `orden_presentado: false` and `NOTA_SIN_ORDEN` on every call, which is the durable signal. Runbook step 6/7 must tell the operator to expect it.
   - Commit messages, runbook and spec text must never say "bar passed" for this path. The proposal should say "ingested under a failed bar, served unranked".
2. **Dry-run.** The gate sits before the database, the corpus and the pin, exactly like `--exigir-barra`, so a dry run is refused whenever the real run would be. A dry run must also print the same banner, so rehearsing it shows what will be said. It must never mean "skip the check" or "check less": `test_tambien_rige_con_dry_run` is the model. With no `DATABASE_URL`, `main` already takes the `engine is None` branch with `dry_run=True`, which keeps working.
3. **Silent downgrade of the strict gate.** If both flags were allowed together, a reader could assume the stricter one wins, or that the lenient one wins. Make them mutually exclusive (argparse group) so there is no precedence to guess.
4. **Wrong file read.** The ingest reads `RUTA_BARRA` from the checkout it runs in (`venv-rag` on the box). The API reads the copy baked into the deployed image. They can differ if the image was not republished. With `no_superada` the worst case is still unranked, because `superada_para` is False on either copy unless that copy is a genuine `superada` for the same SHA, which needs passing figures. Note it in the runbook so step 6 stays the source of truth.
5. **Honest means consistent.** If the new predicate only checked `estado == no_superada`, a hand-edited file with passing figures and the word `no_superada` would pass. Re-derive the verdict from the figures, as `exigir_superada` does in the other direction.
6. **Stale checked-in figures.** The YAML still records vigencia 0.667. Ingest does not depend on the exact failing figure, only on honest failure, so this is not a blocker; but the proposal must refresh it (post-follow figures above) and update the figure-pinning kernel test in the same change, otherwise the repo documents a measurement that is no longer the latest.
7. **Spec contradiction.** The spec says production ingest MUST NOT proceed below 0.72. Shipping the flag without amending it leaves code and spec disagreeing. Delta needed: MODIFIED requirement with a new scenario "Failed bar, explicit unranked production ingest".
8. **Scope creep.** No second ranker, no threshold change, no change to `BARRA_*` constants, no change to `derivar_desde`, no `superada_para` change.

### Runbook amendment, `docs/rag/runbook-encendido.md` §4.4 step 5

Do not delete the `superada` path. Restructure step 5 into two branches, keep the existing text as 5a.

- **5a (unchanged in substance).** If step 4 produced a `superada` artifact for this SHA: `--entorno produccion --exigir-barra`. Keep the paragraph on `--entorno`, "checked before the database, the corpus or the pin", dry-run refusal and exit 1.
- **5b (new).** If step 4 produced an honest `no_superada` for this SHA (the current state for `ecab0a0e...`): `--entorno produccion --produccion-sin-orden`. State explicitly that it is not a cleared bar, that the screen stays unranked, that rank order still needs a committed `superada` for the exact SHA, that `no_medido`, a SHA mismatch and `superada` over failing figures are still refused, that the check also governs `--dry-run`, and that the two flags are mutually exclusive.
- Change the lead sentence "and only if step 4 produced a `superada` artifact" to cover both outcomes, and say that `no_medido` blocks both.
- Steps 6 and 7 gain one line each: after 5b the operator expects `orden_presentado: false` and the unranked `nota_orden` on the first admin call; seeing `rango` would be a defect.
- **Stale sentence to fix in the same edit** (line ~861): "ships `estado: no_medido`". The file now ships `no_superada`. Section 5 ("does not quote a single measured figure") stays: do not paste figures into the runbook.

### Non-goals (state in the proposal)

- This change does NOT run the production ingest.
- It does NOT flip `conocimiento_normas_enabled`.
- It does NOT publish an image. Pushing to `main` does not publish to GHCR; publishing is the `workflow_dispatch` of `deploy.yml` from `main` (verified: `deploy.yml` has `push: branches: [main]` for gates only; build/scan/GHCR jobs are gated by `github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'`).
- It does NOT change the bar constants, `derivar_desde`, `exigir_superada` behaviour, `superada_para`, the serving order policy, or add a ranker.
- It does NOT add a migration or a `rag_corpus` column.
- It does NOT touch the sibling changes `conocimiento-barra-recuperacion`, `conocimiento-hit5-faltantes`, `consorcio-conocimiento-semantico`.

### Risks

- Spec/code divergence until the delta is written (item 7).
- Mutation-pinned `exigir_superada`: extracting a shared helper changes mutation targets; keep the public function body semantically identical and re-run the mutation targets file.
- Operator confusion between `--exigir-barra` and `--produccion-sin-orden` (items 1, 3); mitigated by banner, mutual exclusion and runbook wording.
- Checkout copy vs image copy of the YAML (item 4).
- Refreshing the YAML breaks `test_el_artefacto_enviado_registra_la_medicion_no_superada` by design; the proposal must schedule that edit.
- The post-follow figures live in an uncommitted lab remeasure; the proposal records them as reported by the owner, and the YAML must be produced by `derivar_desde` from a committed-run report, not hand-typed ("do not edit them by hand" in the YAML header). That is a procedure risk for whoever writes the file.
- Verification gap: the loader refusal on the post-follow figures was confirmed by code reading, not by execution (a probe was blocked by a local guard).

### Ready for Proposal

Yes. Tell the owner: one new flag `--produccion-sin-orden`, valid only with `--entorno produccion`, exclusive with `--exigir-barra`, backed by a new predicate in `barra_sin_gpu.py` that accepts only a consistent `no_superada` for the exact SHA and `bm25_sin_ce`; serving untouched; spec delta and runbook 5a/5b needed; YAML figures refresh and its pin test in the same change; production ingest, flag flip and image publish are non-goals.
