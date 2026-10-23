# Design: Norms surface, mute kernel and Ley 8803 editor

Basis: `origin/main` @ `f86965f0`. Approach C from `exploration.md`: one kernel (`normas.py`) behind the route, a CLI and an MCP mirror.

## Technical Approach

Add one no-GPU mode to `service.recuperar`. It uses the same BM25 candidate generation as `bm25_ce`, keeps BM25 order, and calls no reranker. `normas.buscar/leer/chequear` wrap retrieval and the reads over a `Session`. The router, `scripts/rag_normas.py` and `scripts/rag_normas_mcp.py` all call those functions and nothing else. Rank order comes from a checked-in bar artifact keyed by `corpus_sha`. This copies how `umbral_abstencion.yaml` already records a measured value. The editor composes the eight 8803 drafts from a slot YAML and exports only through `chequear`.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| No-GPU mode id | `MODO_SIN_GPU = "bm25_sin_ce"` in `service.py`, appended to `MODOS`. It is **not** in `MODOS_RRF`. | `bm25`, `bm25_ce` | `"bm25"` is already a **leg** id in `LEGS_POR_MODO`, so `leg_bm25_degradada` would mix the two up. The name says what is missing: no CE. |
| Reranker on HTTP | Never. Passing a `reranker` or `qvec` to `bm25_sin_ce` raises `ValueError`. `bm25_ce` and `RerankerRequerido` are unchanged. | CPU CE | 99 s/query. A CE that was handed in would also make people think CE produced the order. |
| Synthetic provenance | The norms route does **not** refuse it. `barra_sin_gpu.derivar_desde` refuses a synthetic snapshot or an `--allow-synthetic` run. | Refuse in the route | The arm reads no vector column. The gate is defined as "flag + corpus + admin only", and a fourth condition would break that spec. A synthetic run can never unlock rank order. |
| Unranked output | Units are sorted by `citation_key`. No `rango` or score field is present. `orden_presentado=false` is returned with a note. | Keep BM25 order and hide the score | The position in the list would itself imply rank. The spec bans any position that implies relevance. |
| Ranked output | Only when `barra_sin_gpu.yaml` has `estado: superada`, its `corpus_sha` equals the active SHA, and the loader re-checks hit@5 ≥ `BARRA_HIT_RATE`, separation and vigencia = 1.00. In that case the response adds `rango` and `orden_modo="bm25_sin_ce"`. Scores are never shown. | DB table | Same pattern as `umbral_abstencion.yaml`. It is reviewable and needs no migration. |
| Order policy location | Inside `normas.buscar`. A mode with no matching artifact is unranked, and that includes `bm25_ce` from the CLI. | Applied per surface | The spec requires identical units and fields on the route, the CLI and the MCP. |
| Gate | `enforce_conocimiento_normas` checks the flag (503 `funcionalidad_no_disponible`), then `require_admin`, then the active corpus (503 `base_de_conocimiento_no_lista`, cause `sin_corpus_activo`). | Reuse the QA AND | Terms, credential and sidecar do not apply here. |
| HTTP shape | `POST /conocimiento/normas/buscar` with `enforce_body_limit` and the body parsed by hand, like `encolar_pregunta`. `POST /conocimiento/normas/pedidos/{id}/exportar` returns `text/markdown`. Neither route takes a mode parameter. | GET with `?q=` | Keeps the query text out of access logs. |
| MCP dependency | `requirements-mcp.txt` with an exact pin, kept outside the app image and outside lock-sync. It is used from a separate venv, the same way as `requirements-rag.txt`. A missing install exits 2 with a message, following `SALIDA_SIN_DEPENDENCIA`. | Hand-written JSON-RPC | Writing our own protocol would drift from the standard. |
| Editor pins | Each legal slot in the YAML pins `(citation_key, span, vigencia, sha)`. The template body places legal text only through `{{legal:<slot>}}`. A lint rejects free-text `art.`/`Ley N` outside slots. | Resolve at export | A moved SHA must refuse the export, not silently re-pin. |
| Publish gate | `rag_ingest.py --exigir-barra` refuses unless the artifact is `superada` for `--corpus-sha`. The runbook requires this flag for production. | Procedure only | Gives the gate a mechanical check. Lab and prod are told apart only by `--database-url`. |

## Data Flow

```
admin ─POST /normas/buscar─> enforce_conocimiento_normas ─> normas.buscar(db, q, modo=MODO_SIN_GPU)
                                                              │ corpus_activo + ingested_at
                                                              │ service.recuperar(modo=bm25_sin_ce)  (BM25, no CE)
                                                              │ barra_sin_gpu.cargar() ─ match active sha?
                                                              └─> ResultadoNormas (ranked | key-sorted, sin_unidades)
CLI / MCP (workstation) ──────────────────────────────────> same normas.* functions
editor.exportar(db, id) ─> for slot: normas.chequear + CLASIFICACIONES_ENVIABLES ─> markdown | ExportacionRechazada(slot, causa)
```

## File Changes

| File | Action | Description |
|---|---|---|
| `gee-backend/app/config.py` | Modify | `conocimiento_normas_enabled: bool = False` |
| `gee-backend/app/domains/conocimiento/service.py` | Modify | `MODO_SIN_GPU`, `_recuperar_bm25_sin_ce`, `MODOS` entry, re-export `citation_keys` |
| `gee-backend/app/domains/conocimiento/repository.py` | Modify | Read the active row with `ingested_at`. `leer_unidad` with `clasificacion`. `HYDRATE_SQL` stays untouched. |
| `gee-backend/app/domains/conocimiento/normas.py` | Create | Kernel: `buscar`, `leer`, `chequear` |
| `gee-backend/app/domains/conocimiento/editor.py` + `pedidos_8803.yaml` | Create | Slots, compose, fail-closed export, refusal for pedido 8 and obra notes |
| `gee-backend/app/domains/conocimiento/schemas.py` | Modify | `UnidadNorma`, `ResultadoNormas`, `VeredictoChequeo` |
| `gee-backend/app/domains/conocimiento/router.py` | Modify | Gate dependency and the two routes |
| `gee-backend/app/domains/conocimiento/eval/barra_sin_gpu.py` + `.yaml` | Create | Bar artifact. Ships `estado: no_medido`. |
| `gee-backend/app/domains/conocimiento/eval/harness.py` | Modify | `LEGS_POR_MODO` and `MODOS_SIN_SENAL_RATIFICADA` entries. Gold key re-validation that counts migration misses. |
| `gee-backend/app/domains/conocimiento/eval/report.py` | Modify | A separate no-GPU bar block plus the seed block. Leaves `MODO_GATEADO="bm25_ce"` unchanged. |
| `gee-backend/scripts/rag_eval.py`, `rag_ingest.py` | Modify | Arm runs with no reranker; `--exigir-barra` |
| `gee-backend/scripts/rag_normas.py`, `rag_normas_mcp.py`, `requirements-mcp.txt` | Create | CLI and MCP with exactly three tools |
| `consorcio-web/src/lib/api/conocimiento.ts`, `components/admin/ConocimientoPanel.tsx`, `hooks/useConocimientoNormas.ts` | Modify/Create | Norms client, SHA badge, empty and unranked states, export download |
| `gee-backend/tests/new/conocimiento/test_normas_*.py`, `fixtures/pedidos-8803/` | Create | Tests and masked notes |
| `docs/rag/runbook-encendido.md` | Modify | Publish gate, operator `rag_corpus` read, gold re-validation step |

## Interfaces / Contracts

```python
def buscar(db, consulta: str, *, modo: str, k: int = 10, reranker=None) -> ResultadoNormas: ...
def leer(db, citation_key: str) -> UnidadLeida            # raises UnidadNoEncontrada
def chequear(db, citation_key, span, vigencia, sha) -> VeredictoChequeo
# VeredictoChequeo(pasa: bool, condicion_fallida: Literal["sha","clave","span","vigencia"] | None, clasificacion: str | None)
# ResultadoNormas(modo, corpus_sha, ingested_at, unidades, sin_unidades: bool, orden_presentado: bool, nota_orden: str)
```

`chequear` checks in this order: SHA active, then key at that SHA, then a non-empty span that is a substring of `texto`, then `vigencia == estado_vigencia`. Every refusal names its condition.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | Each `chequear` condition, key-sort when unranked, artifact loader refusals, template lint, refusal of pedido 8 and obra notes | pytest with seeded `rag_*` rows, following `test_eval_bm25_arm.py` |
| Integration | Gate matrix: QA off + norms on gives norms 200 and mailbox 503; no corpus; non-admin. `bm25_ce` without a reranker still refuses. Route, CLI and MCP return identical output. MCP lists exactly three tools. | TestClient, CLI `main(argv)`, MCP `list_tools` |
| Regression | All eight drafts reproduce with placeholders masked. Export refuses a `privado` unit, an invented key, and a moved SHA. No socket is opened during export. Fixtures contain no private gold text. | Fixture compare, socket monkeypatch, scan against `RAG_GOLD_PRIVADO_PATH` when set |
| Web | Unranked, empty and SHA states | vitest |

## Threat Matrix

The CLI and the MCP stdio server add a process entry point. They spawn no subprocess and touch no VCS. Database access comes only from `DATABASE_URL`.

| Boundary | Applicability | Response | RED tests |
|---|---|---|---|
| Documentation-like paths | N/A: nothing is classified or executed by path | none | none |
| Git repository selection | N/A: `verify_corpus_pin` is unchanged; `--exigir-barra` reads a YAML file and does not run git | none | none |
| Commit state | N/A: no commits | none | none |
| Push state | N/A: no push | none | none |
| PR commands | N/A: no PR automation | none | none |

## Migration / Rollout

There is no DB migration. Order:

1. Merge with the flag off.
2. **Precondition (owner work):** a pushed, clean corpus SHA exists.
3. If the pin moves, re-validate the expected-citation keys in the public and private gold at the new SHA. The bar is not decided while any item is a migration miss.
4. Lab ingest, then `rag_eval --modo bm25_sin_ce`, then seed `barra_sin_gpu.yaml` from the report and commit it.
5. Run the production ingest with `--exigir-barra` only if the bar passes.
6. The operator reads `rag_corpus` on the box before calling the index current. Nothing assumes the box already holds the August pin.
7. Flip `conocimiento_normas_enabled`.

If the bar fails, units are still served without rank order. Rollback: set the flag to false, or set `activo=false` on the bad row.

## Open Questions

- [ ] Decision 0.1 (abstention) stays open and out of scope.
- [ ] The exact `mcp` version is chosen at apply, after a supply-chain check.
