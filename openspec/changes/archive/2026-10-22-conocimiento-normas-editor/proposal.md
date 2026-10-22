# Proposal: Norms surface, mute kernel and Ley 8803 editor

Basis: `origin/main` @ `f86965f0`. Exploration: `exploration.md` (approach C).

## Intent

The owner needs legal units with vigencia, norma-vs-secundaria and the served corpus SHA without unattended prose. Today every route sits behind `conocimiento_qa_enabled` and no route returns retrieval synchronously. The eight Ley 8803 access drafts are hand-written with no citation check.

## Scope

### In Scope (in order)
1. **Norms route** behind `conocimiento_normas_enabled` (default false) and `enforce_conocimiento_normas` (flag + active corpus + admin; no terms/credential/sidecar). Returns units with `estado_vigencia`, `es_secundaria`, `modo`, `corpus_sha`, `ingested_at`. Empty result = "no units recovered", never abstention.
2. **Measured no-GPU arm** (own `MODOS` id, e.g. `bm25`; never `bm25_ce`) on the 57-item gold. **Bar: hit@5 ≥ 0.72 on the answerable items**, plus norma-vs-secundaria and vigencia-correctness = 1.00. This is not the CUDA `bm25_ce` 31/34 (0.9118), which must never label this arm. Until measured and passing, the route returns units without rank order.
3. **Mute kernel**: `buscar`, `leer`, `chequear` library over a `Session`, used by the route, a CLI and an MCP mirror pinned to exactly those three tools. `chequear(citation_key, span, vigencia, sha)`: key exists at that SHA, span is a substring of that unit's text, vigencia matches, SHA is the active one.
4. **Editor v1**: eight 8803 drafts as slots (legal, document-id, human-only). Export fails closed on a `privado` unit, an invented citation or a failed `chequear`. Operational facts stay human-only. Regression: the eight hand-written notes, placeholders masked; no private gold text.
5. **Publish gate** for any re-ingest: lab ingest + 57-gold eval first, prod ingest only if hit@5 ≥ 0.72. Chosen over "ingest then roll back" because ingest sets `activo=True` and the eval reads the DB, so measuring in prod serves an unmeasured SHA. `activo=false` is the documented rollback only.

### Out of Scope
- Unattended prose, abstention retune (0.489 @ recall 1.000 stays), entailment, OOD; decision 0.1 stays open.
- A second ranker over raw markdown; rebuilding `bm25_ce`; `redactar` in the kernel.
- Ley 27.275 / pedido 8; obra notes; CIDI submission (never machine-submitted).
- Hetzner deploy.

## Capabilities

### New Capabilities
- `knowledge-norms-surface`: gated route, result schema, empty-result semantics, unranked-until-measured rule.
- `knowledge-norms-kernel`: `buscar`/`leer`/`chequear` contract, CLI, three-tool MCP mirror.
- `access-request-editor`: 8803 slots, fail-closed export, regression set, no submission.

### Modified Capabilities
- `knowledge-hybrid-retrieval`: "No User-Facing Surface in V0" becomes a separately gated norms surface; harness adds the named no-GPU arm and its bar.
- `knowledge-corpus-ingestion`: lab measurement before activation; `activo=false` rollback.

## Approach

One library (approach C). HTTP serves only the no-GPU arm; the reranker is CUDA-only and the box has none. `bm25_ce` and `RerankerRequerido` untouched.

## Affected Areas

| Area | Impact |
|---|---|
| `gee-backend/app/config.py`, `conocimiento/router.py` | Modified: flag, dependency, route |
| `conocimiento/service.py`, `eval/harness.py`, `scripts/rag_eval.py` | Modified: new arm |
| `conocimiento/` new kernel module, `scripts/` CLI, MCP mirror | New |
| `consorcio-web/.../ConocimientoPanel.tsx`, `lib/api/conocimiento.ts` | Modified: norms client, states |
| `docs/rag/runbook-encendido.md` | Modified: publish gate, operator check |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Arm fails 0.72 | Med | Stays unranked |
| Box holds no or stale corpus | High | Operator reads `rag_corpus` before calling it current |
| Gold keys move after pin migration | High | Key re-validation before hit@5 |
| Private unit exported | Low | `CLASIFICACIONES_ENVIABLES`, fail closed |

## Rollback Plan

Set `conocimiento_normas_enabled=false` (route 503, mailbox untouched). Bad SHA: `activo=false` on that `rag_corpus` row. Kernel, CLI and MCP are additive.

## Dependencies

- Pushed, clean corpus SHA (`f55b96fa` is unpushed, untracked dir) before any pin migration; owner work, a gate here.
- Workstation GPU only for `bm25_ce` comparison runs.

## Success Criteria

- [ ] Qa flag off + norms flag on: norms 200, mailbox 503.
- [ ] No-GPU arm hit@5 recorded on the 57 gold; order shown only if ≥ 0.72.
- [ ] MCP lists exactly three tools.
- [ ] Eight drafts reproduce; export refuses private and invented citations.
