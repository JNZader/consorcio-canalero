```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:563bb5503fb453e60786b9dd6ce2df6a9c9fa4e16f03fd5fa09f77a68eec4fda
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 14/21
scenarios: 33/44
test_command: "cd gee-backend && venv/bin/python -m pytest tests/new/conocimiento/test_normas_kernel.py tests/new/conocimiento/test_normas_eval.py tests/new/conocimiento/test_normas_router.py tests/new/conocimiento/test_normas_cli.py tests/new/conocimiento/test_normas_mcp.py tests/new/conocimiento/test_normas_editor.py -q -p no:logging"
test_exit_code: 0
test_output_hash: sha256:6f318b1323103ade2dc1ce08fa5f917984f66fd9a3cde160145d7bac86a11610
build_command: "cd consorcio-web && npx tsc --noEmit"
build_exit_code: 0
build_output_hash: sha256:e8e07ab5cbdcdf6d61495569e3c36e541d722d41586adee3a27dabecc2fad92c
```

## Verification Report

**Change**: conocimiento-normas-editor
**Version**: N/A
**Mode**: Standard

Manual admission, 2026-10-22. `gentle-ai` 4.1.1 has no `sdd-verify-validate` command. The owner ordered the ceremony completed by hand and with OpenSpec. The YAML above is the candidate envelope. `evidence_revision` is the SHA-256 of the `sha256sum` listing of the six logs named in Build & Tests. Each log includes a trailing `exit:N` line added after the command. A production build was not run.

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 24 |
| Tasks complete | 24 checked |
| Tasks incomplete | 0 unchecked. Task 6.4 is checked and not satisfied as written (W1). |

### Build & Tests Execution

**Build**: local production build not run. Substitute typecheck passed.

```text
cd consorcio-web && npx tsc --noEmit
exit 0
sha256:e8e07ab5cbdcdf6d61495569e3c36e541d722d41586adee3a27dabecc2fad92c
```

**Tests**: ✅ 280 passed / 18 skipped on the app venv. ✅ 23 passed for the MCP file when `PYTHONPATH=/tmp/mcp-pkgs` (`mcp==2.3.0` already on disk; nothing installed). ✅ 60 passed in vitest.

```text
cd gee-backend && venv/bin/python -m pytest tests/new/conocimiento/test_normas_{kernel,eval,router,cli,mcp,editor}.py -q -p no:logging
280 passed, 18 skipped, 18 warnings in 5.22s
exit 0
sha256:6f318b1323103ade2dc1ce08fa5f917984f66fd9a3cde160145d7bac86a11610

PYTHONPATH=/tmp/mcp-pkgs venv/bin/python -m pytest tests/new/conocimiento/test_normas_mcp.py -q -p no:logging
23 passed, 4 warnings in 2.59s
exit 0
sha256:536a1c2102202a7e8066344e659c994085298bd9f0e175fbd57f4399f1ff27f4

cd consorcio-web && npx vitest run ConocimientoPanel
2 files, 60 passed
exit 0
sha256:1bdf1136f768b081a266e8fd8256e4179457310ebc9f8717eccf37b85a704d44

cd gee-backend && venv/bin/ruff check (normas.py, editor.py, barra_sin_gpu.py, router.py, service.py, rag_normas.py, rag_normas_mcp.py, rag_ingest.py)
All checks passed
exit 0
sha256:8fdb7268231b006f4d02b32c7e5cf15293c3771ddda64b36db31a80a3644d2c6

cd consorcio-web && npx biome check (conocimiento.ts, useConocimientoNormas.ts, ConocimientoPanel.tsx, ConocimientoPanelNormas.test.tsx)
Checked 3 files. No fixes applied. The test file is outside the Biome include.
exit 0
sha256:59231c29ff8537f3ee9a14033cf492140590a6098c778f3a44eceb87ab931db4
```

The 18 skips on the app venv are 17 MCP tests (`mcp` is not installed there) and 1 private-gold scan (`RAG_GOLD_PRIVADO_PATH` unset).

**Coverage**: not run. Mutation: not run (W1).

### Spec Compliance Matrix

Counts are from the five specs of this change: surface 5/10, kernel 4/9, editor 5/9, hybrid-retrieval delta 3/10, corpus-ingestion delta 4/6. Total 21 requirements, 44 scenarios. The two extra hybrid scenarios are the names OpenSpec strict validation requires a MODIFIED block to keep (see Admission).

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Independent Norms Gate | Default is closed | `test_normas_router.py` default 503 and flag-default | ✅ COMPLIANT |
| Independent Norms Gate | QA off, norms on | `test_normas_router.py` QA off / norms on | ✅ COMPLIANT |
| Independent Norms Gate | Gate refusals name their cause | `test_normas_router.py` 401, 403, `sin_corpus_activo` | ✅ COMPLIANT |
| Independent Norms Gate | Rollback leaves the mailbox untouched | Norms 503 with the flag off is proven. No test asserts the mailbox after rollback | ⚠️ PARTIAL |
| Norms Response Schema | Unit and response provenance | `test_normas_router.py` provenance; kernel `ingested_at` | ✅ COMPLIANT |
| Norms Response Schema | SHA badge needs no QA surface | `test_normas_router.py` `corpus_sha` with QA flag default | ✅ COMPLIANT |
| Empty Retrieval Is Not Abstention | Nothing recovered | `test_normas_router.py` empty result | ✅ COMPLIANT |
| Unranked Until the Bar Is Recorded | Bar not recorded or failed | `test_normas_router.py` and `test_normas_kernel.py` order policy | ✅ COMPLIANT |
| Unranked Until the Bar Is Recorded | Bar recorded and met | `test_normas_router.py` ranked response | ✅ COMPLIANT |
| Arm Labeling | Response never claims bm25_ce | `test_normas_router.py`, `test_normas_eval.py` | ✅ COMPLIANT |
| Exactly Three Tools | MCP lists three tools | `test_normas_mcp.py` with `PYTHONPATH=/tmp/mcp-pkgs`, 23 passed. Skipped on the app venv | ✅ COMPLIANT |
| Exactly Three Tools | redactar does not exist | CLI refusal test. No kernel-level test | ⚠️ PARTIAL |
| One Code Path | Surfaces agree | `test_normas_cli.py` and `test_normas_mcp.py` | ✅ COMPLIANT |
| buscar and leer | No-GPU arm runs without a reranker | `test_normas_kernel.py` | ✅ COMPLIANT |
| buscar and leer | bm25_ce without reranker is refused | `test_normas_kernel.py` | ✅ COMPLIANT |
| buscar and leer | Unknown key | `test_normas_kernel.py`, CLI, MCP | ✅ COMPLIANT |
| chequear Verdict | All four conditions hold | `test_normas_kernel.py` | ✅ COMPLIANT |
| chequear Verdict | Span from another unit | `test_normas_kernel.py` | ✅ COMPLIANT |
| chequear Verdict | Vigencia, stale SHA, empty span, missing key | `test_normas_kernel.py` one test each | ✅ COMPLIANT |
| V1 Scope Is the Eight 8803 Drafts | Out-of-scope request | `test_normas_editor.py` pedido 8 and obra notes | ✅ COMPLIANT |
| Slot Classes | Human-only placeholders survive | `test_normas_editor.py` ×8 | ✅ COMPLIANT |
| Slot Classes | Operational fact is not generated | `test_normas_editor.py` ×5 | ✅ COMPLIANT |
| Fail-Closed Export | Private unit | `test_normas_editor.py` | ✅ COMPLIANT |
| Fail-Closed Export | Invented citation or failed check | `test_normas_editor.py` | ✅ COMPLIANT |
| Fail-Closed Export | SHA moved after drafting | `test_normas_editor.py` | ✅ COMPLIANT |
| No Machine Submission | Export is local | `test_normas_editor.py` no socket | ✅ COMPLIANT |
| Regression Against the Hand-Written Notes | Eight drafts reproduce | `test_normas_editor.py` ×8 | ✅ COMPLIANT |
| Regression Against the Hand-Written Notes | Fixture hygiene | Private-gold scan skipped. Fixture count and planted-question self-test passed | ⚠️ PARTIAL |
| No-GPU Arm Bar Before Rank Order | Bar met | `test_normas_eval.py`, `test_normas_kernel.py` loader | ✅ COMPLIANT |
| No-GPU Arm Bar Before Rank Order | Any figure below the bar | `test_normas_kernel.py`, `test_normas_eval.py` | ✅ COMPLIANT |
| No-GPU Arm Bar Before Rank Order | Gold keys re-validated first | `test_normas_eval.py` migration misses | ✅ COMPLIANT |
| No User-Facing Surface in V0 | No retrieval route mounted | 503 with the flag off is proven. No route-inventory test that the norms route is the only one | ⚠️ PARTIAL |
| No User-Facing Surface in V0 | Retrieval route reachable only through the norms gate | 503 with the flag off is proven. No route-inventory test | ⚠️ PARTIAL |
| No User-Facing Surface in V0 | Norms flag on exposes only the norms route | Admin 200 is proven. No route-inventory test | ⚠️ PARTIAL |
| Three-Mode Ablation Eval Harness | Same gold set scored across all three modes | The three-mode test skips without pgvector. Not re-run here | ⚠️ PARTIAL |
| Three-Mode Ablation Eval Harness | Same gold set scored across all modes | Norms blocks passed. The three-mode test skips without pgvector | ⚠️ PARTIAL |
| Three-Mode Ablation Eval Harness | Vigencia trap surfaces the correct state | Existing harness test, not re-run in this ceremony. Prior verify run passed it | ⚠️ PARTIAL |
| Three-Mode Ablation Eval Harness | No-GPU arm never labeled bm25_ce | `test_normas_eval.py` | ✅ COMPLIANT |
| Lab Measurement Before Production Ingest | Bar met in lab | `test_normas_eval.py` `--exigir-barra` accepts | ✅ COMPLIANT |
| Lab Measurement Before Production Ingest | Bar failed or absent | `test_normas_eval.py` `no_medido` refuses | ✅ COMPLIANT |
| Lab Measurement Before Production Ingest | Production-DB eval is not gate evidence | Runbook text only. The flag cannot tell lab from prod | ⚠️ PARTIAL |
| Deactivation Is Rollback, Not Measurement | Bad SHA withdrawn | Inactive corpus returns `sin_corpus_activo`. The "remaining active corpus" half is not asserted | ⚠️ PARTIAL |
| Operator Read Before Claiming Current | Empty or different corpus on the box | `test_normas_router.py` plus runbook §4.4 | ✅ COMPLIANT |
| Clean Pushed Corpus SHA Precondition | SHA unpushed | Shipped artifact is `no_medido` and cannot be required. This change is uncommitted | ✅ COMPLIANT |

**Compliance summary**: 33/44 scenarios compliant. 11 PARTIAL. 0 FAILING. 0 UNTESTED. 14/21 requirements have every scenario compliant. The vigencia-trap row and the restored three-mode row were not re-run in this ceremony.

The vigencia-trap row is PARTIAL in this ceremony because that harness file was not re-executed here. The prior verify pass reported it green. This report does not reuse that as a fresh COMPLIANT.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| `conocimiento_normas_enabled` default false | ✅ Implemented | `app/config.py`. Test asserts the field default. |
| Bar artifact ships `no_medido` | ✅ Implemented | `eval/barra_sin_gpu.yaml`. |
| Mode id `bm25_sin_ce` | ✅ Implemented | In `MODOS`, not in `MODOS_RRF`. HTTP hardcodes `MODO_SIN_GPU`. |
| Empty result is `sin_unidades` | ✅ Implemented | No abstention field. |
| Editor refuses pedido 8 and obra notes | ✅ Implemented | Export 422. |
| Fail-closed export | ✅ Implemented | 409 names slot and cause. No document. |

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| `MODO_SIN_GPU="bm25_sin_ce"`, out of `MODOS_RRF` | ✅ Yes | |
| `ValueError` on reranker or qvec | ✅ Yes | |
| Unranked output is key-sorted and has no `rango` | ✅ Yes | |
| Rank only when the artifact is `superada` for the active SHA | ✅ Yes | Loader re-checks the figures. |
| Order policy lives in `normas.buscar` | ✅ Yes | |
| Gate order: flag, admin, active corpus | ✅ Yes | |
| MCP pin outside the app image | ✅ Yes | `requirements-mcp.txt` pins `mcp==2.3.0`. |
| Editor slots and free-text lint | ✅ Yes | |
| `--exigir-barra` | ✅ Yes | Refuses before the database write. |
| Cosmic-ray modules wired into the gate | ❌ No | W1. Commented paths only. |

### Issues Found

**CRITICAL**: None.

**WARNING** (closed in the follow-up on this same uncommitted tree, 2026-10-22):

- W1. Closed. Python 3.14 + `venv/bin/cosmic-ray`, no Postgres: 251/508 killed = 49.41% (floor 0.30). Per module: `normas.py` 48/93 = 51.61%, `editor.py` 106/240 = 44.17%, `barra_sin_gpu.py` 97/175 = 55.43%. They stay commented in `.cosmic-ray.toml` because that file's shared test-command does not import the new tests (uncommenting them there is the 0.00% finanzas failure). CI reads `scripts/cosmic_mutation_targets.json`: `normas-kernel`, `normas-editor`, `normas-barra`, each running `tests/test_mutation_targets_normas.py`, floor still 0.30.
- W2. Closed going forward. `openspec/config.yaml` now has `strict_tdd: true`. The historical CLI/editor red of the apply was not reconstructed. The new `--entorno` tests were run red (3 failed: missing flag) and then green.
- W3. Closed for CI. The test job downloads `mcp==2.3.0` with `--no-deps`, checks sha256 `dd0c44c089d16453e8ae31a3877a0054d7a2314caaa81f5e0541b9b1734b2377` (re-checked locally against the wheel, match), then installs `requirements-mcp.txt` and runs `test_normas_mcp.py`. The app venv still skips the 17 SDK tests; that is the separate-venv design.
- W4. Closed. The scanner now reads the harness shape (`preguntas`: id -> text), not only a `pregunta` key. Run against the owner file next to the corpus. It passed. No question text was printed.
- W5. Closed as a source check. With `CONSORCIO_CORPUS_DIR` pointed at the local corpus, every legal slot span is a substring of `ley-8803-acceso-informacion-cordoba.md`. That is not a live ingest snapshot. Export still fails closed on a live mismatch.
- W6. Closed. `TestNoHayRedactar` and `test_solo_las_rutas_de_normas_llegan_al_nucleo` passed.
- W7. Closed. `rag_ingest.py --entorno {laboratorio,produccion}` defaults to laboratorio. `produccion` without `--exigir-barra` returns 1 before any file or connection. The three tests went red, then green. The delta gained the scenario "Production ingest names its environment". `openspec validate --strict` passed.
- W8. Closed. The pin test returned 500 because this machine's env sets `conocimiento_quota_diaria_usuario` to 20, so the request passed the fail-closed default and inserted a `rag_consulta` for a user `_como` never seeds. The test now pins the quota to 0 and expects `CuotaNoConfigurada`. It passes. `test_rag_worker.py` is 16 passed; the setup errors appear only when the logging plugin is turned off (`caplog` disappears). They are not a foreign-key failure.

**SUGGESTION**:

- Re-run the vigencia-trap harness test in the same ceremony as the norms suite before treating that scenario as COMPLIANT.

### Verdict

PASS WITH WARNINGS

The eight warnings above are closed on this tree. The envelope stays `pass_with_warnings` because the scenario table still has partials that this follow-up did not re-score (mailbox rollback, the three-mode gold run without pgvector, the vigencia trap). The hashes in the header are the previous ceremony. They do not cover this follow-up.

### Admission

`gentle-ai sdd-verify-validate` is not a command on gentle-ai 4.1.1. OpenSpec strict validation is the gate this ceremony ran. The first pass failed because the MODIFIED blocks for "No User-Facing Surface in V0" and "Three-Mode Ablation Eval Harness" dropped scenario names the live spec still has. Those names were copied back into the delta. The second pass exited 0:

```text
openspec validate conocimiento-normas-editor --type change --strict --no-interactive
Change 'conocimiento-normas-editor' is valid

openspec validate knowledge-norms-surface --type spec --strict --no-interactive
Specification 'knowledge-norms-surface' is valid

openspec validate knowledge-norms-kernel --type spec --strict --no-interactive
Specification 'knowledge-norms-kernel' is valid

openspec validate access-request-editor --type spec --strict --no-interactive
Specification 'access-request-editor' is valid
```
