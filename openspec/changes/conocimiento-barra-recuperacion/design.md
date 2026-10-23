# Design: Same-Statute Citation Follow on the No-GPU Page

## Technical Approach

A composition step runs inside `service._recuperar_bm25_sin_ce` after `_candidatos_bm25` returns the pool. It reads the indexed text of the BM25 top-k, extracts same-statute article citations, resolves them against the active snapshot, and lets the resolved units displace the lowest BM25 ranks. `_candidatos_bm25`, `_recuperar_bm25_ce`, `recuperacion/bm25.py` (`BM25_K1`, `BM25_B`), `recuperacion/expansion.py`, `normas.py` and `eval/barra_sin_gpu.py` do not change.

The package `gee-backend/app/domains/conocimiento/recuperacion/` already exists (`bm25.py`, `expansion.py`, `reranker.py`). The pure logic goes in a new module there: `recuperacion/citas.py`.

## Architecture Decisions

| Topic | Choice | Rejected | Rationale |
|---|---|---|---|
| Where logic lives | Pure `extraer_citas` + `componer_pagina` in `recuperacion/citas.py`; DB calls stay in `service.py` | Logic inline in `service.py`; new SQL in `repository.py` | Pure functions get fast tests with no DB. `textos_indexados` and `hydrate_citations` already cover every read. |
| Resolution set | The snapshot, through `hydrate_citations(db, sha, target_keys)` | Lookup in `candidatos` | `5589#276` sits at BM25 rank 54. A pool lookup only works because the default pool depth happens to reach 54. |
| Same statute | Resolved row `documento_id` == citing row `documento_id` | Comparing key prefixes only | `hydrate_citations` returns `documento_id` from the INNER JOIN, so statute identity comes from the snapshot, not from string matching. |
| Free tail slots | A follow cited from page position `p` (0-based) is admitted only while `len(follows)+1 <= k-1-p` | Unbounded up to k | A follow never displaces its citing unit or anything ranked above it. Positions only increase in selection order, so the first overflow ends selection. This fills in "free tail slots" in the locked contract; it is not a second tie-break. |
| Score fields | `rango_bm25=None` on every follow. `valor_bm25` keeps the real pool value if the target is in `candidatos`, otherwise `None`. New `seguida_desde: str \| None` | Synthetic rank (e.g. page position) or interpolated score | The real pool rank is always ≥ k and is never used to reorder. `None` sorts last in `normas._ordenado`, and that sort is stable, so the tail keeps selection order. |

## Citation Grammar

Accepted (case-insensitive, over `texto_indexado`), in textual order:

```
\bart\.\s*(?P<numero>\d+)\s*[º°]?\s*(?P<sufijo>bis|ter|qu[aá]ter|quinques|sextus)?\b
```

`\s` covers the NBSP seen in seeded text (`Art.\u00a01º`). The suffix set is `parser.UNIDAD_RE`'s, normalized with `parser._normalise_suffix`, so `193 ter` becomes `193ter`.

Rejected:

- Plural lists and ranges (`arts. 6 y 82`, `arts. 206-227`). These appear in the corpus. Including them would add multi-target expansion, which this change does not need.
- A match followed by `de la Ley`, `del Decreto`, `de la Resolución`, `Ley N`, `Dec.` or `Res.`, or preceded on the same line by `Ley|Decreto|Res.|Resolución <number>`. This covers `art. 7º de la Ley 11015` and `Ley 9867 art. 30` in `tests/new/conocimiento/fixtures/ley-5589-fragmento.md`.
- `Artículo N`. It was not observed as an inline remission.

`de este código` and `de esta ley` are accepted (same statute). Example fixture: a 5589 unit whose text contains `art. 276 de este código` yields token `276`. The target key is the citing key with its last segment replaced: `5589#180` gives `5589#276`, and a key whose last segment starts with `art` gives `…#art276`. Any other last-segment style produces no target.

## Data Flow

```
_candidatos_bm25 ──► candidatos ──► pagina = candidatos[:k]
        │
        ├─ textos_indexados(pagina keys)             (IngestionAbort if a page key is missing)
        ├─ extraer_citas(texto) per page unit, page order × textual order
        ├─ hydrate_citations(pagina keys ∪ target keys)   (one query)
        ├─ keep target: row exists ∧ same documento_id ∧ not on page ∧ not selected
        └─ componer_pagina ──► prefix = pagina[:k-n] (BM25 order) + tail = follows
                                (one hop: follow texts are never scanned)
```

## File Changes

| File | Action | Description |
|---|---|---|
| `gee-backend/app/domains/conocimiento/recuperacion/citas.py` | Create | `extraer_citas`, `clave_destino`, `componer_pagina` (pure) |
| `gee-backend/app/domains/conocimiento/recuperacion/__init__.py` | Modify | Export the new names |
| `gee-backend/app/domains/conocimiento/service.py` | Modify | `_recuperar_bm25_sin_ce` composition and docstring |
| `gee-backend/app/domains/conocimiento/schemas.py` | Modify | `CitaRecuperada.seguida_desde: str \| None = None` (not on `UnidadNorma`) |
| `gee-backend/tests/new/conocimiento/test_recuperacion_citas.py` | Create | Pure and DB-seeded tests |

## Interfaces / Contracts

```python
def extraer_citas(texto_indexado: str) -> list[str]: ...           # ["276", "193ter"], textual order, may repeat
def clave_destino(clave_citante: str, token: str) -> str | None: ...
def componer_pagina(
    pagina: Sequence[str], seguidas: Sequence[tuple[int, str]], k: int
) -> tuple[list[str], list[tuple[str, int]]]: ...                  # (prefix, [(target, citing_pos)])
```

Docstring amendment: the property "the order is BM25's alone" becomes "the prefix order is BM25's alone; the displaced tail holds same-statute follows in selection order and is not a ranking". This is the only amendment. `n_bm25` stays `len(candidatos)`.

Display: `normas.buscar` is unchanged. Without superada, units are still sorted by `citation_key` with `orden_presentado` False. Follow changes which units make up the 10, not rank exposure.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | Grammar accept/reject, suffix normalization, cross-statute lookahead/lookbehind, `componer_pagina` capacity, dedup, overflow | Table tests in `test_recuperacion_citas.py` |
| Integration | A target outside the pool resolves; cross-statute dropped; no second hop; size stays k; prefix order; `valor_bm25` None outside pool; `bm25_ce` unchanged | Seeded snapshot with a small `profundidad` so the target is beyond the pool |
| Regression | Existing `test_normas_kernel.py`, `test_recuperacion_bm25.py`, `test_mutation_targets_normas.py` | Run unchanged |

## Threat Matrix

N/A: no routing, shell, subprocess, VCS/PR automation, executable-file classification or process-integration boundary.

## Migration / Rollout

No migration. Rollback: revert the commit, and `_recuperar_bm25_sin_ce` returns `candidatos[:k]` again.

## Open Questions

- [x] Free tail slots. Owner continued on 2026-10-23. The spec now uses the same rule: admit a follow from 0-based position `p` only while `len(follows)+1 <= k-1-p`. The first overflow ends selection.
