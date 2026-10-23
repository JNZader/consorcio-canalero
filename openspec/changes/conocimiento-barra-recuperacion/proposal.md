# Proposal: Same-Statute Citation Follow on the No-GPU Page

## Intent

On T-5, `5589#276` sits at BM25 rank 54; no BM25 lever reaches the top 10 (0/252 configs), yet `5589#180` and `5589#187` on the page cite art. 276. The page cannot surface an article its own members cite.

## Scope

### In Scope
- One-hop follow in `bm25_sin_ce`: an article cited by number by a page unit, resolving inside the citing unit's own statute. Deduped.
- Page stays k=10; followed units displace the tail, never appended past 10.
- Composition after BM25 order only.

### Out of Scope
- Interrogative stoplist, twin collapse, k1/b changes.
- Editing corpus, gold or `barra_sin_gpu.yaml`; writing estado superada.
- Rebuilding `bm25_ce`; retuning abstention, entailment, OOD (decision 0.1 open).
- Production ingest, flipping `conocimiento_normas_enabled`, publishing an image.
- Item-keyed appends in `expansion.py`.
- Second hop, cross-statute follow (no Ley 11027 on a 5589 page), k > 10.
- Any ranker, reranker, embedding, vector arm or second score.

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `knowledge-norms-kernel`: "buscar and leer" gains the no-GPU page-composition rule (one hop, same statute, fixed k).

## Approach

After `_candidatos_bm25`, extract article-number citations from the top-k members' indexed text, keep targets resolving to a same-statute unit in the snapshot, dedupe, and let followed units displace the lowest-ranked BM25 members. Followed units carry no invented score. The extractor is a new pure function under `recuperacion/` (design names it).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `gee-backend/app/domains/conocimiento/service.py` (`_recuperar_bm25_sin_ce`) | Modified | Page composition step |
| `gee-backend/app/domains/conocimiento/recuperacion/` | New | Same-statute citation extractor |
| `gee-backend/app/domains/conocimiento/repository.py` (`textos_indexados`, `hydrate_citations`) | Reused | Text and provenance |
| `bm25.py`, `expansion.py` | Unchanged | Contract |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Displaced tail lowers MRR/citation-precision (0.407 vs 0.33) | Med | Measure before any bar claim |
| Looks like metric fitting | Med | General rule, no item keys |
| Ambiguous "art. N" | Med | Resolve within citing law, else drop |

## Rollback Plan

Revert the commit; `_recuperar_bm25_sin_ce` returns to `candidatos[:k]`. No data, corpus, gold or schema to unwind.

## Dependencies

- None

## Success Criteria

- [ ] A cited same-statute article can occupy one of the 10 slots; for T-5, `5589#276` can enter via `5589#180`/`5589#187`.
- [ ] Page stays 10; no cross-statute or second-hop units; `bm25_ce` and BM25 constants unchanged.
- [ ] Honest limit: superada is NOT promised. hit@5 is 22/34, needs 25; citation follow was not shown to gain those hits. Vigencia moves only if 276 lands in the 10. Only a later, separately authorized lab measurement may change the bar.
