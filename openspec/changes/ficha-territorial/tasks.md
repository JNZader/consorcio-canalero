# Tasks: Ficha Territorial

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~4 060 across 11 PRs (2 chains) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Chain A: A1a→A1b→A2→A3a→A3b→A4→A5→A6→A7 · Chain B: B1→B2 |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain (stacked; roots target the integration branch) |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Per-PR line forecast

| PR | Phase | Base branch | Est. lines | Budget flag |
|---|---|---|---|---|
| A1a | 0 | `develop` (integration root) | ~230 | OK |
| A1b | 0 | A1a | ~400 | **At budget** — contingency: carve the admin refresh endpoint into A1c |
| A2 | 1a | A1b | ~340 | OK |
| A3a | 1b | A2 | ~500 | **OVER** — sub-split A3a-i (schemas/router/config/guards ~250) + A3a-ii (stub service + §2.6 contract tests ~250) |
| A3b | 1b | A3a | ~390 | Near budget |
| A4 | 1c | A3b | ~550 | **OVER** — sub-split A4a (hook + panel + tables ~310) + A4b (wiring + vitest + E2E ~240) |
| A5 | 2 | A4 | ~270 | OK |
| A6 | 3 | A5 | ~290 | OK |
| A7 | 5 | A6 | ~440 | **OVER** and BLOCKED on backlog D8 fix |
| B1 | 4a | `develop` (integration root) | ~440 | **OVER** — contingency: split B1a (GEE export + enum migration) / B1b (generator module + lookup helper) |
| B2 | 4b | A3b **and** B1 (merge base) | ~240 | OK |

Root PRs target the repo integration branch; the design names `main`. Confirm whether a
`develop` branch exists before apply — if not, roots target `main`. Children always target
their immediate parent PR branch.

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|---|---|---|---|
| 1 | Schema prep + prod prereq report | A1a | root; ops verification included |
| 2 | Soils ETL runnable in-container | A1b | base A1a |
| 3 | Zonal primitive + class breaks | A2 | base A1b; no DB |
| 4 | Endpoint contract + guards (stub compute) | A3a | base A2; freezes the wire contract for A4 |
| 5 | Real compute + perf gate | A3b | base A3a |
| 6 | Ficha card + wiring + E2E | A4 | base A3b; can start against the A3a contract |
| 7 | Free polygon | A5 | base A4 |
| 8 | Canal buffer | A6 | base A5 |
| 9 | Catchment | A7 | base A6; **BLOCKED** |
| 10 | CHIRPS normals | B1 | parallel root, independent of chain A |
| 11 | Precipitation in response + chart | B2 | needs A3b and B1 merged |

---

## PR A1a — Phase 0: migration + prerequisites (base: integration root)

- [x] A1a.1 Create `gee-backend/app/db/migrations/versions/00XX_ficha_territorial_prep.py`; `DROP MATERIALIZED VIEW mv_canales_por_zona` **then** `DROP TABLE canales_geo` (view before table). AC: `soils-etl` › "Twins are gone after upgrade". (~40)
- [x] A1a.2 Same migration: recreate `mv_suelos_por_zona` with `row_number() over (order by z.id, s.id) AS mv_id` + `CREATE UNIQUE INDEX IF NOT EXISTS ux_mv_suelos_por_zona_id`. AC: `soils-etl` › "Materialized view refresh strategy" delta (JDB-028 idempotence). (~55)
- [x] A1a.3 Same migration: `downgrade()` raises `RuntimeError("downgrade unsupported: …")` — never `pass`. AC: `soils-etl` › "Downgrade is explicit". (~10)
- [x] A1a.4 Create `gee-backend/app/domains/geo/etl/__init__.py` + `load_suelos_catastro.py` skeleton exposing `--check-prereqs` only: reports `parcelas_catastro` / `suelos_catastro` row counts, exits non-zero when `parcelas_catastro` is empty. AC: `soils-etl` › "Empty catastro reported" (JDB-019). (~60)
- [x] A1a.5 Test `gee-backend/tests/new/test_ficha_migration.py` (real PG): twins absent after upgrade, `canal_network` + `mv_suelos_por_zona` survive, unique index exists, `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_suelos_por_zona` succeeds, `downgrade()` raises. Import `app.main` inside the test body only. (~65)
- [ ] A1a.6 **OPS**: run `docker compose exec backend python -m app.domains.geo.etl.load_suelos_catastro --check-prereqs` against the target (Hetzner) deployment; paste the row counts into the PR body. Empty `parcelas_catastro` = named deployment blocker for `tipo=parcela`, not a silent pass. (~0)
      **PENDIENTE** — merge gate, no ejecutable desde el entorno de apply: el `app/` del
      contenedor está montado read-only (`docker cp` → "mounted volume is marked read-only"),
      así que el módulo nuevo sólo corre en Hetzner después de desplegar la rama. Dato de
      referencia del stack local (NO es el gate): `parcelas_catastro=1322`, `suelos_catastro=45`.

## PR A1b — Phase 0: soils ETL (base: A1a)

- [x] A1b.1 Implement `gee-backend/app/domains/geo/etl/load_suelos_catastro.py`: full-refresh in one tx (`DELETE` → bulk insert → assertions → COMMIT), `--source`, `--dry-run`. AC: `soils-etl` › "First run populates the table" + "Re-run is idempotent". (~150)
- [x] A1b.2 Implement the 6 load-time assertions inside the tx: row count == source features (45), `ST_IsValid` per row (source repaired with `ST_MakeValid`, unrepairable → abort naming `gid`), SRID 4326, Σ ha in 32720 within 1 % of source, `ip` int→str coercion, NULL `cap` tolerated. AC: `soils-etl` › "Invalid source geometry aborts the load" + "Row-count mismatch aborts the load" (JDB-015). (~60)
- [x] A1b.3 Post-commit `REFRESH MATERIALIZED VIEW CONCURRENTLY` in autocommit (outside the load tx) + module docstring stating the stale-view consequence. AC: `soils-etl` › "ETL refreshes the view". (~30)
- [x] A1b.4 Add package data `gee-backend/app/domains/geo/etl/data/suelos_cu.geojson` (2.2 MB copy). Binary-ish artifact — exclude from the review line count, note it in the PR body. (~0 reviewed)
- [x] A1b.5 Create `gee-backend/app/domains/geo/router_admin_suelos.py` — `POST /api/v2/admin/geo/suelos/refresh-mv`, admin-only — and mount it. AC: `soils-etl` › "Stale view is recoverable" (JD-A-004/JDB-016). (~55)
- [x] A1b.6 **Ledger regression test** (JDB-002): `tests/new/test_suelos_etl_packaging.py` — the loader resolves its packaged geojson via `importlib.resources` with no repo-root path, and the module is importable as `python -m …`. AC: `soils-etl` › "Loader runs inside the deployed container". (~35)
- [x] A1b.7 Drift test: packaged `suelos_cu.geojson` is byte-identical to `consorcio-web/public/data/suelos_cu.geojson` (JD-A-011). (~20)
- [x] A1b.8 Real-PG ETL tests: first run, idempotent re-run, invalid-geometry rollback, row-count-mismatch rollback, NULL `cap` preserved, `ip` stored as str, ha within 1 %, MV non-zero after refresh, admin refresh endpoint requires admin. (~120)
- [ ] A1b.9 **OPS**: document the invocation `docker compose exec backend python -m app.domains.geo.etl.load_suelos_catastro` in the module docstring and the PR body; run it against staging/target and record the resulting row count + ha total. (~0)
      Documentación **HECHA** (docstring del módulo, con los tres modos y los
      códigos de salida; test `test_docstring_documents_the_container_invocation`
      lo fija). **PENDIENTE** la corrida contra el entorno objetivo: mismo
      bloqueo que A1a.6 — el `app/` del contenedor está montado read-only, así
      que el módulo nuevo sólo corre en Hetzner después de desplegar la rama.
      Es gate de merge, no tarea de código.

## PR A2 — Phase 1a: zonal primitive (base: A1b)

- [x] A2.1 Create `gee-backend/app/domains/geo/class_breaks.py` with `RANGE_CONFIGS` moved out of `tile_service_support.py:113-125`; re-export from `tile_service_support` for back-compat. Leaf module — MUST NOT import the tile service. (~60)
      Nota: el bloque real era `tile_service_support.py:113-209` (7 tipos, no 2). Movido íntegro;
      `tile_service_support` lo importa y lo sigue usando en su línea 483, así que
      `tile_service.py` (único importador externo) queda sin tocar.
- [x] A2.2 Add `extract_zonal_profile(raster_path, geom, geom_crs, breaks, geom_area_m2)` to `gee-backend/app/domains/geo/composites.py`, returning the full dict always. Leave `extract_composite_zonal_stats` untouched; `compute_zonal_stats` stays banned. AC: `geo-analysis-endpoint` › "Composite nodata honored". (~90)
- [x] A2.3 Handle **both** silent-skip branches: catch `ValueError` only (non-overlap) → `coverage="none"`, empty bins; any other exception propagates. No bare `except`. AC: `geo-analysis-endpoint` › "Zone fully outside raster extent" (JDB-004). (~25)
- [x] A2.4 Geometry-relative coverage: `covered_area_ha = valid_pixels * pixel_area_ha`, `coverage_ratio = min(1.0, covered/geom_area_ha)`, thresholds none/0.99/partial. AC: `geo-analysis-endpoint` › "Partial coverage flagged" (JDB-005/JD-A-005). (~30)
- [x] A2.5 Relative per-raster `low_confidence = (geom_area_m2 / pixel_area_m2) < K`, `K` from `ficha_low_confidence_pixel_ratio`, per-dataset override (`precip_normal` → 0). AC: `geo-analysis-endpoint` › "Low-confidence flag on sub-pixel parcel" (JDB-017). (~25)
      `K` entra como parámetro `low_confidence_pixel_ratio` (default 10.0 en
      `DEFAULT_LOW_CONFIDENCE_PIXEL_RATIO`). El setting `ficha_low_confidence_pixel_ratio` lo agrega
      **A3a.5**; el servicio lo pasa ahí y `precip_normal` pasa `K=0` en B2.1. `composites.py` no
      importa `app.config` a propósito: es código de pipeline/geo-worker, no de la capa API.
- [x] A2.6 Bin-edge convention half-open `[min,max)` with the last bin closed, stated in the docstring. (JDB-026) (~10)
- [x] A2.7 **Ledger regression tests** — `tests/new/test_extract_zonal_profile.py`, synthetic 10×10 float32 GeoTIFFs in `tmp_path`, no DB: (a) full coverage exact pct; (b) **partial coverage where the crop window is entirely valid** — the JDB-005 regression; (c) disjoint geometry → `ValueError` → `coverage="none"`; (d) all-nodata → `coverage="none"`; (e) non-`ValueError` failure propagates — the JDB-004 regression; (f) value exactly on a bin edge — JDB-026; (g) `low_confidence` true/false either side of `K`, and `K=0` never flags. (~150)
      12 tests, todos verdes sin DB. Extra sobre el pedido: última bandeja cerrada `[min,max]` con
      valor 100.0, y dos guardas del A2.1 (identidad del re-export y `class_breaks` sin imports
      fuera de `__future__`).

## PR A3a — Phase 1b: contract + guards vs stub compute (base: A2)

> Forecast ~500 lines. Sub-split recommended: **A3a-i** = tasks A3a.1-A3a.5, **A3a-ii** = tasks A3a.6-A3a.10.
>
> **A3a-i applied** (branch `feat/ficha-a3a-i-contrato`): A3a.1-A3a.5 + A3a.10 done, plus the
> non-compute half of A3a.7 (caps helper, audit, semaphore, placeholder). A3a.6 / A3a.8 / A3a.9 and
> the geometry resolution of A3a.7 stay in A3a-ii. **Measured: ~910 reviewed lines** — 689 new
> source (`schemas_ficha` 188, `router_ficha` 179, `ficha_errors` 165, `ficha_service` 157) + 173
> test + 48 on tracked files (`config.py` 37, `router.py` 4, `main.py` 7). Well over the ~250-300
> forecast for A3a-i: `ficha_errors.py` (165) is a whole module the forecast did not name, and the
> four files are comment-dense by design. Decide the review tier on the measured number.

- [x] A3a.1 Create `gee-backend/app/domains/geo/schemas_ficha.py`: Pydantic v2 discriminated union on `tipo` (`parcela|poligono|canal_buffer|canal_cuenca`) + response models, including the typed `precipitacion_mensual` shape and the Spanish wire vocabulary (`cobertura`, `clase`, `pixel_count`). No geometry echo, no `nro_cuenta`. AC: `geo-analysis-endpoint` › "Unknown tipo is rejected". (~110)
- [x] A3a.2 Cheap `poligono` schema validators only: vertex count, ring count, coordinate sanity. AC: "Vertex cap rejected before raster read". (~30)
- [x] A3a.3 Create `gee-backend/app/domains/geo/router_ficha.py` — dedicated public `APIRouter`, `POST /analisis-zona`, sync `def` handler, async limiter dependency (30/min per IP, `key_prefix="ratelimit:ficha:"`, cost=5 for `poligono`/`canal_buffer`/`canal_cuenca`); include it from `router.py`. MUST NOT touch `router_analysis.py`. AC: `geo-analysis-endpoint` › "Existing geo endpoints unaffected" (JDB-003). (~85)
- [x] A3a.4 Body-size guard on the ficha router: reject `Content-Length > ficha_max_body_bytes` with 413 `cuerpo_excedido` before parsing; chunked bodies read through a counting guard. AC: "Oversized body rejected before parsing" (JDB-007). (~50)
- [x] A3a.5 `gee-backend/app/config.py`: add `ficha_rate_limit_*`, `ficha_max_area_ha` (20 000), `ficha_max_envelope_ha` (60 000), `ficha_max_vertices` (1 000), `ficha_max_buffer_m` (2 000), `ficha_max_body_bytes` (1 MiB), `ficha_max_concurrency` (4), `ficha_low_confidence_pixel_ratio` (10). (~25)
- [x] A3a.6 `gee-backend/app/core/rate_limit.py`: replace the `cost` loop of awaited `zadd` calls with a single pipelined `zadd` mapping; document the residual non-atomicity and the Redis-down (in-memory degrade, not fail-open) policy. (JDB-020) (~25)
      **A3a-ii**: `_check_redis` now builds one `{f"{now}:{i}": now for i in range(cost)}` mapping
      and pipelines the `zadd` with the `expire` (one round-trip instead of `cost` awaited zadds).
      The check-then-act residual non-atomicity + the in-memory-degrade (never fail-open) policy are
      documented inline. `test_rate_limit_recovery` still green (it only exercises `_get_redis`).
- [~] A3a.7 (PARCIAL en A3a-i: `assert_within_caps` + audit `zona.analisis` commiteada + `BoundedSemaphore` 2 s → 503 `sobrecarga` + placeholder ya estan; falta la resolucion de geometria por `tipo`) Create `gee-backend/app/domains/geo/ficha_service.py` **stub**: geometry resolution per `tipo` (parcela + poligono only in this PR), `assert_within_caps(geom, *, tipo)` after **every** resolution and before any I/O, `audit_log` row committed before compute (action `zona.analisis`, `user_id` NULL, `client_ip` set), module-level `threading.BoundedSemaphore` with 2 s timeout → 503 `sobrecarga`. Compute returns a fixed placeholder. AC: `geo-analysis-endpoint` › "Caps are enforced on server-derived geometries" + "One audit row per accepted request" (JD-A-002/JDB-006/JDB-022). (~120)
- [~] A3a.8 **Ledger-mandated error-contract tests** — `tests/new/test_ficha_error_contract.py`, one test per §2.6 row (JD-A-006): 404 `parcela_no_encontrada`, 404 `canal_no_encontrado`, 409 `variante_no_disponible`, 413 `cuerpo_excedido`, 422 `tipo_desconocido`, 422 `geometria_invalida`, 422 `cap_excedido` ×3 (area / buffer / oversized catchment), 429 `limite_de_tasa`, 503 `dataset_no_cargado`, 503 `raster_ilegible`, 503 `sobrecarga`. Rows whose `tipo` ships later assert the union/cap path only and are completed in A5/A6/A7. (~150)
      **A3a-ii (partial by design — the rest are gated on later slices):** created
      `tests/new/test_ficha_error_contract.py`, all behavioral (TestClient), feature-flag ON via
      monkeypatch. DONE now: 413 `cuerpo_excedido`, 429 `limite_de_tasa` (+ `Retry-After`), 422
      `tipo_desconocido` (through the wire → `parse_ficha_body`), 422 `geometria_invalida`
      (malformed-polygon class the schema owns; true bow-tie self-intersection is A5/PostGIS), 422
      `cap_excedido` for `vertices` + `buffer_m` on the wire and for `area_ha` as a unit assertion on
      `assert_within_caps` (area is server-derived → wire path lands in A3b/A5), 503 `sobrecarga`
      (semaphore drained). DEFERRED (need geometry resolution / a raster loop, not in this slice):
      404 `parcela_no_encontrada` (A3b), 404 `canal_no_encontrado` (A6), 409 `variante_no_disponible`
      (A7), 503 `dataset_no_cargado` (A3b), 503 `raster_ilegible` (A3b). Their `FichaError`
      constructors are already shape-covered in `ficha_errors`.
- [x] A3a.9 **Ledger-mandated limiter-isolation test** (JDB-003): exhaust the ficha limiter, then assert `/api/v2/geo/zonal-stats` is not throttled. (~30)
      **A3a-ii**: `test_el_limitador_de_ficha_no_estrangula_a_las_hermanas` — behavioral: exhausts the
      ficha limiter with real ficha POSTs, then asserts a public sibling (`/api/v2/geo/layers/public`)
      is not 429'd. A public sibling avoids a 401 masking the check; `zonal-stats` is operator-only
      (401 without a token), so the isolation property is proven on a route whose response is not
      gated by auth. Plus the ordering test `test_429_precede_a_422` proves the limiter fires before
      the parser.
- [x] A3a.10 **Ledger-mandated route-table guard test** (JD-A-010, judge-forced): `tests/new/test_ficha_router_contract.py` walks the geo router mounted in a locally built app (NUNCA `app.main` ni el agregador — regla de identidad de modulos en CI) y congela el conjunto de rutas `/api/v2/geo` sin auth. **Correccion factual**: `analisis-zona` NO es la unica ruta sin dependencia de operador — ya habia 7 publicas en `develop` (catalogo publico de capas, proxy de tiles, lecturas + PDF de approved-zones); el test congela esa lista y falla si aparece una nueva. AC: `geo-analysis-endpoint` › "No auth regression on sibling routes". (~30)

## PR A3b — Phase 1b: real compute (base: A3a)

- [x] A3b.1 Soils in `ficha_service.py`: run the `0015:94-113` SQL parameterized by the request geometry (`ST_Intersection` in 32720), never reading `mv_suelos_por_zona`. AC: `geo-analysis-endpoint` › "Per-class breakdown returned". (~80)
      `_SUELOS_SQL` re-parameterizes the MV SHAPE by `ST_SetSRID(ST_GeomFromGeoJSON(:geojson),4326)`;
      `_suelos_dataset` groups + takes pct against the whole parcel area.
- [x] A3b.2 Residual row: `sin_dato_ha = max(0, area_ha - Σ clase.ha)` emitted as `clase: "sin dato"` when > 0.5 % of `area_ha`. AC: `geo-analysis-endpoint` "suelos residual" delta (JDB-009/JD-A-014). (~30)
- [x] A3b.3 Class grouping by normalized roman prefix (`IVws → IV`) with the full subclass in `detalle`; NULL `cap` → `"sin clasificar"`, never dropped, never merged into `sin dato` (JDB-010). (~35)
      `_normalizar_cap` strips the subclass suffix server-side; NULL/blank → `"sin clasificar"`.
- [x] A3b.4 Raster loop over `flood_risk` + `drainage_need` via `extract_zonal_profile`, mapping primitive → wire vocabulary (`full/partial/none` → `total/parcial/sin_cobertura`). Empty `suelos_catastro` → 503 `dataset_no_cargado`. AC: "Empty suelos table" + "Nodata pixels are excluded from percentages". (~90)
      Decision: empty `suelos_catastro` is the 503 hard dependency; a missing/unregistered
      SECONDARY raster (flood/drainage) is `sin_cobertura` per schema R3-007 (never a dropped key,
      never a 503); an unreadable raster is 503 `raster_ilegible`.
- [x] A3b.5 Integration tests (real PG, 3-polygon fixture geojson): per-class breakdown sums within 1 %, residual present, NULL cap row, `sin_cobertura` with empty breakdown and `pixel_count` 0, `parcial` on a straddling polygon, 404 unknown nomenclatura, parcel with NULL `nro_cuenta` returns 200 with no BPA field. (~150)
      `tests/new/test_ficha_compute.py` — 10 behavioral TestClient tests, real PG, savepoint-isolated
      fixture (endpoint commits audit mid-request). BPA absence asserted (`nro_cuenta`/`pilar_verde`
      not in body — client-side join [R1]).
- [x] A3b.6 **Ledger-mandated audit-durability test**: force a compute failure and assert the `audit_log` row still exists (committed before compute). AC: "One audit row per accepted request" second clause. (~30)
      `test_auditoria_persiste_tras_falla_de_compute`: corrupt raster → 503 `raster_ilegible`, audit
      row still present.
- [x] A3b.7 Perf gate (JD-A-009): 20 sequential requests on the fixture parcel, assert p95 ≤ 1.5 s, record the measured number in the PR body. No "300-600 ms" claim anywhere. (~40)
      `test_perf_gate_p95`: **measured p95 ≈ 15–19 ms** over 20 sequential requests (synthetic
      rasters); asserts ≤ 1.5 s. Number to be re-recorded against real rasters in the PR body.

## PR A4 — Phase 1c: ficha card + wiring (base: A3b)

> Forecast ~550 lines. Sub-split recommended: **A4a** = A4.1-A4.4, **A4b** = A4.5-A4.9.

- [ ] A4.1 Create `consorcio-web/src/hooks/useFichaTerritorial.ts`: key `['ficha-territorial', tipo, refKey]`, `staleTime` 5 min, `gcTime` 30 min, `retry: (n,e) => n < 1 && ![413,422,429].includes(e.status)`, **no** `placeholderData: keepPreviousData`. AC: `ficha-frontend` › "Switching modes discards previous result". (~70)
- [ ] A4.2 Create `consorcio-web/src/components/map2d/FichaTerritorialPanel.tsx` + `FichaResumen.tsx` (area_ha, per-dataset cobertura, low-confidence badges). AC: `ficha-frontend` › "Small parcel badge" + "No badge on large areas". (~90)
- [ ] A4.3 Create `SuelosBreakdown.tsx`: **table** clase/ha/% incl. `sin dato` and `sin clasificar`, subclass tooltip, stacked bar as complement only (colors from `useSoilMap.ts:11-47`). AC: `ficha-frontend` › "Full ficha rendered" (JD-A-012). (~90)
- [ ] A4.4 Create `RiesgoBins.tsx` (×2 datasets): **table** clase/ha/% per bin + colored bar complement; percentages rendered from the server, never recomputed from hectares. (~70)
- [ ] A4.5 Create `PilarVerdeBadges.tsx`: client-side join of `usePilarVerde()` (`consorcio-web/src/hooks/usePilarVerde.ts:46`) against the clicked feature's `nro_cuenta` tile property; "sin vinculación" when absent; section omitted entirely for `poligono`/`canal_*`. AC: `ficha-frontend` › "Parcel with null nro_cuenta" ([R1]). (~60)
- [ ] A4.6 Wire `MapWorkspace.tsx` (fetch owner) → `MapUiPanels.tsx` (props) → sibling `<FichaTerritorialPanel>`. `InfoPanel.tsx` stays pure — no hook, no fetch. AC: `ficha-frontend` › "Parcel click routes through the container". (~60)
- [ ] A4.7 Parcel click is the default: in `'idle'`, `useMapInteractionEffects.ts` click routing and Pilar Verde precedence are UNCHANGED; a resolved `parcelas_catastro` feature additionally fires `tipo:'parcela'`. No gate, no new entry point. AC: `ficha-frontend` › "Three interaction modes" delta (JD-A-013/JDB-014). (~30)
- [ ] A4.8 Vitest: `InfoPanel` renders with no data provider and issues no request; `sin_cobertura` renders text and no `0 %` row; error states 404/422/429/503 surface the server message. AC: `ficha-frontend` › "InfoPanel purity is enforced", "No coverage is not zero", "Rate limited", "Soils dataset not loaded", "Loading state". (~120)
- [ ] A4.9 Playwright spec `consorcio-web/tests/e2e/ficha-territorial.spec.ts`: click parcel → ficha renders; skips gracefully when `parcelas_catastro` is empty (precedent `afectados.spec.ts:166`). (~60)

## PR A5 — Phase 2: free polygon (base: A4)

- [ ] A5.1 `ficha_service.py`: `tipo=poligono` normalization `ST_CollectionExtract(ST_MakeValid(ST_GeomFromGeoJSON(:g)), 3)`; empty or zero-area → 422 `geometria_invalida`. AC: `geo-analysis-endpoint` › "Self-intersecting drawn polygon" (JDB-008). (~60)
- [ ] A5.2 `consorcio-web/src/components/map2d/measurement/useMeasurement.ts:62`: widen the union to `MapInteractionMode = 'idle'|'measuring-distance'|'measuring-area'|'ficha-dibujo'|'ficha-canal'` + `MeasurementMode` back-compat alias. NO second zustand slice. AC: `ficha-frontend` › "one interaction-mode machine" delta (JDB-012). (~50)
- [ ] A5.3 `useMapInteractionEffects.ts`: `'ficha-dibujo'` → `buildClickableLayers()` returns `[]`, `DrawControl` owns clicks; toolbar button beside the measurement buttons. (~60)
- [ ] A5.4 Tests: integration bow-tie polygon → 422 `geometria_invalida` with no raster opened; 30 000 ha polygon → 422 `cap_excedido` naming `area_ha`; vitest — starting a drawing clears the previous parcel ficha. AC: `ficha-frontend` › "Free polygon drawn" + "Switching modes discards previous result". (~100)

## PR A6 — Phase 3: canal buffer (base: A5)

- [ ] A6.1 `ficha_service.py`: `tipo=canal_buffer` → `canal_network` lookup + `ST_Buffer` in EPSG:32720, `buffer_m` capped by `ficha_max_buffer_m`, then `assert_within_caps`. AC: `geo-analysis-endpoint` › "Buffer distance cap" (JDB-006). (~70)
- [ ] A6.2 `consorcio-web/src/components/map2d/mapLayerEffectHelpers.ts`: render `vt_canal_network` as a line layer, clickable only in `'ficha-canal'`; use the feature's `id` property as `canal_id`. AC: `ficha-frontend` › "Canal selection" (JDB-013). (~80)
- [ ] A6.3 Toolbar entry for `'ficha-canal'` + buffer-distance input; clickable set filtered to canal layers only. (~50)
- [ ] A6.4 Tests: `buffer_m` over cap → 422 naming `buffer_m`; unknown `canal_id` → 404 `canal_no_encontrado`; limiter cost=5 applied to `canal_buffer`; vitest — canal mode clickable set excludes parcels. (~90)
- [ ] A6.5 **OPS** (judge-forced, JDB-013): verify `vt_canal_network` is populated in the target environment before merge; an empty view is a deployment blocker for both canal modes. Record the row count in the PR body. (~0)

## PR A7 — Phase 5: catchment (base: A6) — **BLOCKED**

> **BLOCKED-on-backlog**: do NOT start until the backlog D8-pointer fix lands
> (`calculations_hydrology_support.py:255` passes a DEM where `watershed` expects the D8
> pointer). Every task below is gated on that ticket being merged first.

- [ ] A7.1 *(blocked)* Migration `00YY_canal_catchment.py`: table `canal_catchment(id, canal_id, variante, geometria MULTIPOLYGON/4326, area_ha, oversized, flow_dir_layer_id, version, created_at)`. (~60)
- [ ] A7.2 *(blocked)* Create `gee-backend/app/domains/geo/intelligence/catchment_precompute.py`: per canal × variant, rasterize the LINESTRING as int16 seed cells, call `watershed(d8_pntr=<flow_dir>, pour_pts, output)` — **never** a DEM in the pointer slot — polygonize, store, register the raster artifact. `JensenSnapPourPoints` MUST NOT be used. AC: `catchment-analysis` › "Catchment computed from flow_dir" (JD-A-015). (~150)
- [ ] A7.3 *(blocked)* Apply the area cap at precompute time: catchments above `ficha_max_area_ha` stored with `oversized = true`. AC: "Oversized catchment rejected". (~25)
- [ ] A7.4 *(blocked)* `ficha_service.py`: `tipo=canal_cuenca` → `SELECT … WHERE canal_id AND variante` → `assert_within_caps` → the same sync raster loop. Outcomes: `oversized` → 422 `cap_excedido`; variant missing but sibling present → 409 `variante_no_disponible` with `variantes_disponibles`; no rows at all → 503 `dataset_no_cargado`. Default variant `natural`. AC: "Requested variant missing" + "Uniform response shape". (~70)
- [ ] A7.5 *(blocked)* **Ledger regression test**: passing a DEM path where the pointer is expected raises an explicit input-type error. AC: `catchment-analysis` › "DEM passed as pointer is rejected". (~40)
- [ ] A7.6 *(blocked)* Integration tests: byte-compatible schema vs `tipo=parcela`, oversized → 422 with no raster opened, degenerate single-cell basin → 200 with tiny `pixel_count` + `low_confidence: true`, missing variant → 409, no rows → 503. (~110)
- [ ] A7.7 *(blocked)* **OPS** (judge-forced): container-invocation scenario for the precompute batch — document and exercise `docker compose exec backend python -m app.domains.geo.intelligence.catchment_precompute`, confirming it reads/writes the `geo-data:/data/geo` volume mounted by the backend (`docker-compose.yml:99`). (~20)

## PR B1 — Phase 4a: CHIRPS normals (parallel root, base: integration root)

- [ ] B1.1 `gee-backend/app/domains/geo/models.py`: add `TipoGeoLayer.PRECIP_NORMAL = "precip_normal"` + migration `ALTER TYPE tipo_geo_layer ADD VALUE 'precip_normal'`; the new value MUST NOT be used in the transaction that adds it. (~50)
- [ ] B1.2 `gee_service.py` (+ `_support`): `export_chirps_monthly_normals()` delegating to a `*_payload` helper, mirroring `compute_ndwi_baselines_gee` (`gee_service.py:540-555`); source `UCSB-CHG/CHIRPS/DAILY`, monthly sums averaged 1991-2020, fetched with `getDownloadURL`. AC: `precip-normals-pipeline` › "Full set generated". (~120)
- [ ] B1.3 Create `gee-backend/app/domains/geo/etl/generate_chirps_normals.py` (`python -m` entry point): 13 outputs (`precip_normal_{MM}.tif` ×12 + `precip_normal_anual.tif`) to `/data/geo/{area_id}/output/`, warped to EPSG:32720 at **5 000 m** with `Resampling.nearest`, nodata `-9999.0`; register each as a `geo_layers` row with `metadata_extra = {mes, normal_period, fuente, version (UTC ISO8601), resolucion_m}`. AC: "Registration as geo_layers" + "Regeneration versions the metadata" (JDB-011/JDB-018). (~120)
- [ ] B1.4 Month-scoped lookup helper: select `tipo=PRECIP_NORMAL AND area_id=:area`, group by `metadata_extra->>'mes'`, take the newest `version` per month. The "most recent layer of tipo X" idiom MUST NOT be used. AC: "Layers discoverable by the ficha" (JD-A-008). (~40)
- [ ] B1.5 Missing/invalid GEE credentials fail loudly with no partial layer registered. AC: "Missing credentials fail loudly". (~25)
- [ ] B1.6 Module docstring: static cadence, regenerate only on a period or extent change, exact manual command + expected outputs. AC: "On-demand regeneration documented". (~15)
- [ ] B1.7 Tests: 13 rasters produced, credentials failure registers nothing, `version` changes on regeneration, the lookup helper returns 12 distinct rasters (the regression against the single-row idiom). (~110)
- [ ] B1.8 **OPS** (judge-forced): container-invocation scenario — run `docker compose exec backend python -m app.domains.geo.etl.generate_chirps_normals` and confirm the outputs land on the `geo-data` volume the geo-worker reads. (~10)

## PR B2 — Phase 4b: precipitation in the ficha (base: A3b **and** B1)

- [ ] B2.1 `ficha_service.py`: assemble `precipitacion_mensual` with its typed shape `{cobertura, low_confidence, pixel_count, unidad:"mm", serie:[{mes, mm}], anual_mm}` in calendar order, via `extract_zonal_profile` with `K = 0`. Zero months registered → 503 `dataset_no_cargado`; some months missing → `cobertura: "sin_cobertura"` for the dataset. AC: `precip-normals-pipeline` › "Monthly series for a zone" + "Zone outside precipitation coverage". (~70)
- [ ] B2.2 Create `consorcio-web/src/components/map2d/PrecipChart.tsx`: 12-bar recharts chart in calendar order **plus** a mes/mm table and `anual_mm`. AC: `ficha-frontend` › "Full ficha rendered" (JD-A-012). (~90)
- [ ] B2.3 Tests: `serie` always 12 entries in calendar order when covered; no fabricated zeros outside coverage; `low_confidence` false for a sub-pixel parcel (K=0 override — the JDB-017 regression); vitest renders both chart and table. (~80)

---

## Dependencies and parallelization

- **Chain A is strictly sequential** — A1a → A1b → A2 → A3a → A3b → A4 → A5 → A6 → A7. Each child PR bases on its immediate parent branch; if a child diff shows the parent's changes, retarget/rebase before review.
- **Chain B forks off the integration branch** and is fully independent of chain A until B2. B1 can be developed and merged at any time in parallel with A1a-A3b.
- **B2 is the only join point**: it needs A3b (the response assembly exists) and B1 (the rasters exist) both merged.
- **A4 can start early against the A3a contract** (schemas frozen there) using a mocked hook response, but it must not merge before A3b.
- **A7 is gated on an external backlog ticket** (D8 pointer fix), not on chain A itself. If that ticket slips, A6 is a valid stopping point for the whole change.
- Ops verifications (A1a.6, A6.5, B1.8, A7.7) are merge gates for their PRs, not code tasks — record the evidence in the PR body.

## Risks

- **A3a (~500), A4 (~550), A7 (~440), B1 (~440) exceed the 400-line review budget.** Delivery strategy is `ask-on-risk` → the orchestrator must consult the user on the sub-splits proposed above before apply.
- **A1b sits at ~400** — the admin refresh endpoint (A1b.5) is the natural carve-out if it tips over.
  **Measured after apply: ~931 reviewed lines** (419 diff on tracked files + 512 in three new
  Python files; the 2.2 MB geojson excluded). ~450 of those are tests. Carving A1b.5 into A1c
  removes only ~85 lines, so the split does not bring A1b under budget — decide the review tier
  on the measured number, not on the forecast.
- **A2 measured after apply: ~548 reviewed lines** (202 nuevas en `composites.py` + ~16 de cabecera
  en `class_breaks.py` + 330 de test; los ~97 de `RANGE_CONFIGS` son un movimiento 1:1 entre
  `tile_service_support.py` y `class_breaks.py` y no cuentan como revisión nueva). 330 de esas
  líneas son tests. Forecast era ~340 — decidir el tier de review sobre el número medido.
- **Chain A depth (9 PRs)** is a rebase-cost bottleneck: any fix in A2 or A3a rebases everything downstream.
- **Two ops answers still open** (design "Open Questions"): `vt_canal_network` population blocks A6; `parcelas_catastro` population blocks the value of A3b/A4 even though the code ships.
