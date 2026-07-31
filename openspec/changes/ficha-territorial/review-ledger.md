# Review Ledger — ficha-territorial (SDD design phase)

Lens: `judgment-day` (two blind judges, both REJECTED). Rows merged from both judge ledgers and
deduplicated; orchestrator resolutions **[R1] [R2] [R3]** are recorded inline. `status: fixed` means
the confirmed finding is resolved in `design.md` (and, where the design decision wins, in the
affected `specs/*/spec.md` under a "Delta (post-JD)" note). `status: info` = reported once, never
blocking, incorporated where cheap.

## BLOCKER

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| JD-A-001 / JDB-001 | judgment-day | design.md — Technical Approach "pilar verde ── join by nro_cuenta" | BLOCKER | fixed | No backend BPA source existed; **[R1]** client-side join against the already-public `bpa_enriched.json` via `usePilarVerde` + the `nro_cuenta` tile property (`martin/config.yaml:35`); backend returns no BPA block |
| JDB-002 | judgment-day | design.md — `scripts/load_suelos_catastro.py`, `scripts/generate_chirps_normals.py` | BLOCKER | fixed | `gee-backend/Dockerfile:107` copies only `app/` + `alembic.ini`; neither scripts dir is in the image and the deployed host has no venv → both scripts unrunnable anywhere. Moved under `app/domains/geo/etl/` as `python -m` entry points, source geojson packaged, run via `docker compose exec backend`; `/data/geo` reachable because the backend mounts the volume (`docker-compose.yml:99`) |
| JD-A-002 / JDB-006 | judgment-day | design.md — "caps are pure Pydantic validators" | BLOCKER | fixed | Schema validators never see server-derived geometry (parcel, buffer, catchment) → caps bypassable. Added `assert_within_caps(geom)` after every resolution before the first raster open (422), `ficha_max_buffer_m`, and cost=5 for `canal_buffer` |

## CRITICAL

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| JD-A-003 / JDB (phase-5 sync-async) | judgment-day | design.md §5 + PR 9 "Celery job + poll" | CRITICAL | fixed | An async envelope for one `tipo` breaks the "byte-compatible response schema" the catchment spec mandates. **[R2]** catchments precomputed offline per canal into `canal_catchment`; request time = lookup + the same sync zonal stats; cap applied at precompute, 422 on oversized |
| JDB-003 | judgment-day | design.md §2 "router-level `dependencies=[enforce_ficha_rate_limit]`" on `router_analysis` | CRITICAL | fixed | Would throttle every existing operator analysis route (`router_analysis.py` hosts `/zonal-stats` et al.). Dedicated `router_ficha` APIRouter isolates limiter and the missing auth dep; route-table test guards sibling auth |
| JDB-004 | judgment-day | design.md §1 — only `composites.py:361-366` handled | CRITICAL | fixed | Two silent-skip branches exist; the `except Exception: continue` at `:344-350` (non-overlap `ValueError`) was unhandled. Now: catch `ValueError` → `coverage="none"`; anything else propagates → 503. No bare except |
| JDB-005 / JD-A-005 | judgment-day | design.md §1 — coverage from valid/total pixels | CRITICAL | fixed | `rasterio_mask(crop=True)` clips the window to the raster extent, so partial coverage is undetectable by pixel ratio. Coverage now `valid_pixels*pixel_area_ha` vs geometry area in EPSG:32720, clamped, 0.99 threshold |
| JD-A-006 | judgment-day | design.md — no error contract | CRITICAL | fixed | 404/409/413/422/429/503 table with `codigo`, payload shape and one integration-test row each (§2.6) |
| JDB-007 | judgment-day | design.md §2 — no body-size guard | CRITICAL | fixed | Vertex cap fires only after full-body parse. `Content-Length` guard → 413 before parsing, `ficha_max_body_bytes` = 1 MiB, chunked bodies read through a counting guard |
| JDB-008 | judgment-day | design.md — drawn polygons unvalidated | CRITICAL | fixed | Self-intersecting `DrawControl` rings reach `ST_Intersection`/`rasterio_mask` and yield wrong areas silently. `ST_MakeValid` + `ST_CollectionExtract(…,3)` or 422 `geometria_invalida` |
| JDB-009 / JDB-010 / JD-A-014 | judgment-day | design.md §3 soils | CRITICAL | fixed | Soils do not tile the consorcio → `pct` implied full knowledge. Residual `sin dato = area_ha − Σ ha` (>0.5 %), grouping by normalized roman prefix (`IVws → IV`) with subclass as tooltip, NULL `cap` → `sin clasificar` (2 of 45 source features) |
| JD-A-007 / JD-A-008 / JDB-011 / JDB-017 / JDB-018 | judgment-day | design.md §4 + geo-analysis-endpoint spec:86 | CRITICAL | fixed | Precipitation cannot be `{clase,ha,pct}`; typed `serie` of mean mm + `anual_mm` (spec delta). 13 rasters (12+annual), `version` metadata key, warp stated (32720 @ 5 000 m nearest), month-scoped layer lookup instead of the latest-layer idiom, relative per-raster confidence rule replacing the global `valid_pixels<10` |
| JD-A-004 / JDB-016 | judgment-day | design.md §3 "MV refresh cadence is a non-issue" vs soils-etl spec | CRITICAL | fixed | Spec demands non-blocking refresh + operator action; MV has no unique index (`0015`), and `(zona_id, simbolo)` is not unique. Migration rebuilds the MV with `mv_id` surrogate + unique index; refresh runs outside the load tx; admin refresh endpoint added; ficha never reads the MV |
| JDB-012 | judgment-day | design.md §6 — `useFichaMode` alongside `measurementMode` | CRITICAL | fixed | Two machines can both be non-idle and both bind clicks with no invariant. Existing union widened to `MapInteractionMode` — one machine, structural exclusion, no new zustand slice |
| JDB-013 | judgment-day | design.md §6 `'canal'` mode | CRITICAL | fixed | Clickable canal layers are static sources with no `canal_network` id → `canal_id` unobtainable. Render `vt_canal_network` (Martin `id_column: id`) as the canal-mode clickable layer; prod population verification added as a phase-3 prerequisite |
| JD-A-013 / JDB-014 | judgment-day | design.md §6 — panel mounts only when `fichaMode !== 'idle'` | CRITICAL | fixed | Phase 1 was hidden behind a mode with no documented entry point. Parcel click now works by default in `'idle'`; drawing/canal modes have explicit toolbar entry; idle click routing untouched |
| JD-A-012 | judgment-day | design.md §6 card tree vs ficha-frontend spec:58 | CRITICAL | fixed | Spec requires a table per dataset; R1 was charts-only. Tables are the contract, charts are the complement (spec delta) |
| JD-A-015 | judgment-day | design.md §5 `JensenSnapPourPoints` | CRITICAL | fixed | Jensen snapping is defined for point pour locations; applied to a rasterized line trace it collapses all seed cells onto one drainage cell. Dropped in favour of raster seed cells, matching `calculations_hydrology_support.py:249-254` |

## WARNING / SUGGESTION (info — incorporated where cheap, never blocking)

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| JD-A-009 | judgment-day | design.md §2 "≈300-600 ms" | WARNING | info | Unmeasured estimate presented as measurement; replaced with an explicit perf gate (20 runs, p95 ≤ 1.5 s) in PR A3b |
| JDB-015 | judgment-day | design.md §3 ETL assertions | WARNING | info | Assertion list incomplete: added ha-within-1 %, `ip` int→str coercion (source is int, column `String(50)` at `0015:42`), NULL `cap` tolerated, MV-before-table drop order, `downgrade()` raises |
| JDB-019 | judgment-day | design.md — `parcelas_catastro` prerequisite | WARNING | info | Spec requires prod verification; now explicitly in PR A1a scope via `--check-prereqs` |
| JDB-020 | judgment-day | design.md §2 rate limit | WARNING | info | `_check_redis` does ZCARD then a loop of awaited ZADDs (`rate_limit.py:166-195`) — check-then-act is not atomic. Mitigation: single pipelined `zadd`; residual accepted and bounded by the in-flight semaphore; Lua-CAS rewrite deferred to backlog. Redis-down policy stated (degrades to per-process in-memory, does not fail open) |
| JDB-022 | judgment-day | design.md §2 concurrency | WARNING | info | No bound on simultaneous raster memory; `threading.BoundedSemaphore(ficha_max_concurrency=4)` + 503 `sobrecarga` on timeout |
| JD-A-010 | judgment-day | design.md — namespace posture | WARNING | info | Public route under the operator `/api/v2/geo` namespace; kept deliberately (spec states the path) and made safe structurally: separate no-auth router + route-table test asserting every sibling still requires operator auth |
| JD-A-011 | judgment-day | design.md §3 "10 MB payload" | WARNING | info | Factual: `suelos_cu.geojson` is 2.2 MB (2 216 776 bytes), 45 features |
| JDB-023 | judgment-day | design.md §6 `useMapInteractionEffects` path | WARNING | info | Factual: the file is `consorcio-web/src/components/map2d/useMapInteractionEffects.ts`, not under `src/hooks/` |
| JDB-024 | judgment-day | design.md §3 "`scripts/` precedent exists" | WARNING | info | Ambiguous: three `scripts/` dirs exist (repo root, `gee-backend/`, `consorcio-web/`); the root one is the host-run ETL precedent and is explicitly not extended |
| JDB-025 | judgment-day | design.md §2 "keeps the router under ~300 lines" | WARNING | info | Factual: `router_analysis.py` is 271 lines today; the ficha gets its own router regardless (JDB-003) |
| JDB-026 | judgment-day | design.md §1 bins | WARNING | info | Bin-edge convention was unstated; now half-open `[min,max)` with the last bin closed, asserted by an on-edge unit test |
| JDB-027 | judgment-day | design.md §5 WBT citation | WARNING | info | Citation made precise: `calculations_hydrology_support.py:255` is `get_wbt().watershed(dem_path, pour_points, basins)` — the DEM-in-pointer-slot miscall not to copy |
| JDB-028 | judgment-day | design.md — migration idempotence | WARNING | info | `CREATE UNIQUE INDEX IF NOT EXISTS` used for the MV key |
| JDB-021 | judgment-day | design.md — Phase → PR mapping | SUGGESTION | fixed | 9-deep single chain with a 380-line PR 3. **[R3]** PR 3 split into A3a (contract + guards vs stub) / A3b (compute), PR 1 split into A1a (migration) / A1b (ETL), CHIRPS moved to a parallel chain B off `main` |
