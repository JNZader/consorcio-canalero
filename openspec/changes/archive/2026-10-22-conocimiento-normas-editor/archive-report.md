# Archive Report: conocimiento-normas-editor

**Archived**: 2026-10-22
**Archived to**: `openspec/changes/archive/2026-10-22-conocimiento-normas-editor/`
**Artifact store**: hybrid (filesystem + Engram project `consorcio-canalero`)
**Branch**: `feat/conocimiento-normas-editor` (basis `f86965f0`), all work uncommitted. No commit SHA exists for this change.
**Archive status**: intentional-with-warnings (see "Partial scenarios")
**Review gate**: `reviewGate` absent, RDD off. Archive proceeded under ordinary repository policy.

## Gates

| Gate | Result |
|------|--------|
| Task Completion Gate | PASS. `tasks.md` has 24/24 implementation tasks checked, 0 unchecked. |
| CRITICAL in verify-report | None (per `verify-report.md` at verification time, line "CRITICAL: None"). |
| Native review receipt | Not applicable (`reviewGate` absent). |
| Action context | Repo-local change; no workspace-planning mode. |

## Final-State Authority

Facts below come from the orchestrator launch prompt (written 2026-10-22 after the verify report, rank 3) and outrank the intermediate `verify-report` (rank 4, Engram #37099) and `apply-progress` (Engram #37091) snapshots. They describe the state at close. None of it is committed.

1. `openspec/config.yaml` has `strict_tdd: true`. The historical apply RED phase was not reconstructed. The new `--entorno` tests went RED (3 failed, flag missing) and then GREEN.
2. `scripts/rag_ingest.py` accepts `--entorno {laboratorio,produccion}`, default `laboratorio`. `produccion` without `--exigir-barra` returns 1 before opening any file, database or pin check. The database URL does not choose the environment. The delta scenario "Production ingest names its environment" was added and `openspec validate --strict` passed afterwards.
3. Mutation was measured on Python 3.14 with `venv/bin/cosmic-ray`, no Postgres: 251/508 killed = 49.41% (floor 0.30). Per module: `normas.py` 48/93 = 51.61%, `editor.py` 106/240 = 44.17%, `eval/barra_sin_gpu.py` 97/175 = 55.43%. CI targets `normas-kernel`, `normas-editor`, `normas-barra` are in `gee-backend/scripts/cosmic_mutation_targets.json`, each running `tests/test_mutation_targets_normas.py`. The three modules stay commented in `gee-backend/.cosmic-ray.toml` on purpose, because that file's shared test-command does not import those tests. Task 6.4 stays checked on that basis.
4. The CI test job in `.github/workflows/backend.yml` downloads `mcp==2.3.0 --no-deps`, checks sha256 `dd0c44c089d16453e8ae31a3877a0054d7a2314caaa81f5e0541b9b1734b2377`, installs `requirements-mcp.txt`, and runs `test_normas_mcp.py`. The app venv still skips the 17 SDK tests by design.
5. The private-gold scanner reads the harness shape (`preguntas`: id -> text) and a `pregunta` key. It passed against the owner file. No question text is recorded here.
6. With `CONSORCIO_CORPUS_DIR` set, every legal slot span is a substring of `ley-8803-acceso-informacion-cordoba.md`. This is a source check, not a live ingest.
7. The kernel has no `redactar`. Only `POST /conocimiento/normas/buscar` and `POST /conocimiento/normas/pedidos/{pedido_id}/exportar` reach retrieval.
8. The QA pin test 500 came from this machine's env quota of 20 letting a stub user insert `rag_consulta`. The test now pins `conocimiento_quota_diaria_usuario` to 0 and expects `CuotaNoConfigurada`. `test_rag_worker.py` is 16 passed when the logging plugin is loaded.
9. `conocimiento_normas_enabled` stays false. The bar artifact stays `no_medido`. No commit.

The verify-report's earlier statements that strict TDD was off, cosmic-ray was not installed, mutation was not run, and lab versus production was distinguished only by `--database-url` were true at verification time and are superseded by facts 1-3 above.

## Partial scenarios (intentional-with-warnings)

The follow-up did not re-score these three scenarios. They are partial, not CRITICAL, and are carried forward as open follow-up:

1. Mailbox rollback after the norms flag goes off.
2. The three-mode gold run. It skips without pgvector.
3. The vigencia trap.

Out of scope for this change and not performed: corpus push, 57-item gold run, lab or production ingest, flag flip, box read, deploy, abstention retune.

## Specs Synced

Merge by requirement name; every requirement the delta does not mention was preserved.

| Domain | Action | Details |
|--------|--------|---------|
| knowledge-hybrid-retrieval | Updated | 1 added ("No-GPU Arm Bar Before Rank Order"), 2 modified ("No User-Facing Surface in V0", "Three-Mode Ablation Eval Harness"), 0 removed. Purpose clause "exposing no user-facing surface in V0" replaced with "exposing retrieval to callers only through the separately gated norms surface (conocimiento_normas_enabled, default false)". |
| knowledge-corpus-ingestion | Updated | 4 added ("Lab Measurement Before Production Ingest", "Deactivation Is Rollback, Not Measurement", "Operator Read Before Claiming Current", "Clean Pushed Corpus SHA Precondition"), 0 modified, 0 removed. |
| knowledge-norms-surface | Already live | New full spec, already in `openspec/specs/`. Not copied, moved or deleted. |
| knowledge-norms-kernel | Already live | Same. |
| access-request-editor | Already live | Same. |

Merge verification: ADDED blocks were appended mechanically with `tail`/`head` redirection from the delta and compared byte for byte with `diff` (identical). The two MODIFIED blocks were applied with targeted string replacements and compared against the delta text (identical apart from the blank separator line before the next requirement). `diff` of the pre-merge snapshot against the merged `knowledge-corpus-ingestion` spec shows the original 199 lines unchanged. In `knowledge-hybrid-retrieval` the only differences from the pre-merge snapshot are the two modified requirements, the one added requirement, and the one-sentence Purpose edit. `(Previously: ...)` annotations from the delta were kept, matching the existing convention in `openspec/specs/rainfall-analysis/spec.md`.

Note on the delta: the modified "Three-Mode Ablation Eval Harness" requirement keeps both the original scenario "Same gold set scored across all three modes" and the new "Same gold set scored across all modes". They coexist as written in the delta; a future spec cleanup may fold them into one.

Process note: a Python-scripted merge was denied by a shell guard before running (nothing changed). The merge was then done with targeted edits and the byte comparisons above.

## Validation

- Before the move: `openspec validate conocimiento-normas-editor --type change --strict --no-interactive` valid.
- After the move, live specs (`--type spec --strict --no-interactive`): `knowledge-hybrid-retrieval` valid, `knowledge-corpus-ingestion` valid, `knowledge-norms-surface` valid, `knowledge-norms-kernel` valid, `access-request-editor` valid. Only INFO notes about long requirement text on the two merged specs.

## Archive Contents

- exploration.md ✅
- proposal.md ✅
- specs/ ✅ (`knowledge-hybrid-retrieval`, `knowledge-corpus-ingestion` deltas)
- design.md ✅
- tasks.md ✅ (24/24 tasks complete)
- verify-report.md ✅ (intermediate snapshot, see Final-State Authority)
- archive-report.md ✅ (this file, written after the `diff -r` readback)

## Engram Traceability (project `consorcio-canalero`)

| Artifact | Observation ID |
|----------|----------------|
| explore | 37072 |
| pre-proposal | 37073 |
| proposal | 37074 |
| spec | 37075 |
| design | 37076 |
| tasks | 37079 |
| chain-strategy | 37081 |
| apply-progress | 37091 |
| apply-gate | 37092 |
| verify-gate | 37095 |
| verify (verify-report) | 37099 |
| verify-warnings (closure) | 37104 |

Filesystem artifacts were read from disk (tasks gate, deltas, main specs); the Engram observations were located by search and not re-read, since the on-disk files are the source of truth in hybrid mode.

## Move Readback

Moved with `mv` (change folder was untracked, so `git mv` was not applicable). Pre-move recursive snapshot compared with the archived folder before this report was added: `diff -r` printed nothing, exit 0.

## Risks

- Everything is uncommitted; the archive records a working-tree state with no commit SHA.
- Three scenarios above remain partial.
- The ranked order stays disabled until a lab run on the 57-item gold records the no-GPU arm bar for the exact corpus SHA.
