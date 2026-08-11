# Verification Report — consorcio-rag

**Verdict: PASS-with-notes** — 0 CRITICAL · 2 WARNING · 5 SUGGESTION. Archive-ready.
Branch `feat/consorcio-rag-04-eval` @ `a6f00138` (git-verified). Produced by the read-only `sdd-verify` agent (full traceability table at Engram `sdd/consorcio-rag/verify-report`, id 13792); landed as a file by the orchestrator, who also closed V-1 and V-6 in the ledger in the same commit.

## Executed evidence (verifier's own runs)

| gate | result | recorded | reconciles |
|---|---|---|---|
| `pytest tests/` (real CI scope) | **exit 0 · 2927 passed / 66 skipped / 0 failed** | 2927/66/0 | digit-for-digit |
| `pytest tests/new/conocimiento/` (CI shape) | **exit 0 · 389 / 61 / 0** | 389/61/0 | digit-for-digit |
| `make test-rag` / `make test-rag-corpus` | not runnable in the verify sandbox | 29/0 and 32/0, exit 0 — executed by the orchestrator at the tip (2026-08-11) | cited |
| ruff / mypy | not on the verify allow-list | exit 0 recorded; CI enforces both | cited |

All 66 skips are mechanically gated and disclosed (61 corpus/pgvector + 5 pre-existing live-backend). Both `make` targets fail on any skip, so their "passed" cannot mean "did not run".

## Traceability

All 20 ingestion scenarios + all 15 retrieval scenarios map to implementation + a test that passed at runtime in at least one executed shape. No unpinned requirement, no untested path. D8's absence-by-design is real: `test_no_conocimiento_router_mounted` passes and no `router.py` exists under the domain.

## tasks.md — 73 checked / 2 unchecked

The 2 unchecked are exactly the owner-gated ops: **4.14** (real eval) and **O.3** (RTX batch). 18 test-less tasks spot-checked against the tree; A6's recounts verified independently (anexo-normativo → 5, contenido-no-declarado → 12); gold set verified at 52 owner-validated / 29 respondibles / 23 unanswerable / 26 pregunta_ref.

## Design conformance

Every amendment reached code and the code matches the amended text: D4 OR-of-lexemes via `CAST(… AS tsquery)`; D5 per-mode signals incl. the load-bearing `/2` cosine transform; D7 non-destructive recovery (measured three-path table); D8 AST split rethink; RJDA-102's root-cause fix at `env.py:55`. No silent divergence.

## Ledger closure

2 BLOCKER + 18 CRITICAL across the change, all `fixed` with downstream verdicts. Refuter STANDS ×4 on RAG2-001..004. JD used exactly 2 fix rounds (budget respected); per-slice reviews 1 lens + 1 batched refuter + 1 fix round each. PII trail coherent: SHA remapping table consistent with the live log, three independent purge verifications, working-tree read confirms 12 `[DNI-OMITIDO]` with zero dotted-ID patterns.

Verify findings V-1 (stale `open` on the original RAG4-001 row) and V-6 (nine info findings with unrecoverable content) were **closed by the orchestrator in this landing commit** — the original-finding row now reads `fixed` with a pointer, and the nine rows are written out in full in the ledger's "Info bequest" section. V-2..V-5, V-7 (File Changes omissions, Coverage Table staleness, task 4.1 test names, cosmic-ray counts, version.json hygiene) remain SUGGESTION/info for the archive backlog.

## Owner runway (post-merge)

1. **O.3 — RTX batch** (owner's machine): `venv-rag` setup → `rag_embed_batch.py --preflight-only` → real batch → `make rag-embed-load` → `make rag-eval RAG_EVAL_PYTHON=../venv-rag/bin/python` with `RAG_GOLD_PRIVADO_PATH` set. Latency label defaults LOCAL; ESTIMATE per O.4 for the CPU-capped figure.
2. **4.14 — the real eval**: already measured for the lexical arm — the 52-question `--modo fts` run returned **NO-GO on all seven bars with healthy diagnostics** (`sin_candidatos_fts` 0/52, `leg_fts_degradada: false`): `proposal.md:32`'s premise is falsifiable and FALSE — FTS-only does not clear the bar. The vector/hybrid arms await O.3's real vectors.
3. The 12 `contenido-no-declarado` headings decision (owner default: V0.1).
4. Info bequest: the guard-hardening follow-ups (RJDB-201..203), the unpinned rendering cap (RJDB-204), RAG4-002 (torch/device provenance), and the doc-hygiene suggestions above.
