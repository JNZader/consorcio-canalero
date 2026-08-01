# Design: Ficha Territorial

> **Revision R2 (post Judgment Day).** Both blind judges REJECTED R1. This revision applies the
> confirmed findings only; every changed decision carries the ledger id that forced it
> (`review-ledger.md`). Three orchestrator resolutions are binding and are marked **[R1]**,
> **[R2]**, **[R3]** where they land.

## Technical Approach

One endpoint, one computation shape: **N rasters × 1 geometry** (rasterio) + **1 vector overlay × 1
geometry** (PostGIS). Every raster read goes through a single new primitive that never silently
skips a zone. Geometry resolution differs per `tipo`; everything downstream is identical — including
`tipo=canal_cuenca`, whose catchment is **precomputed offline** so the request path stays sync
**[R2]**.

```
POST /api/v2/geo/analisis-zona          (dedicated public APIRouter — no auth dep, own limiter)
  │
  ├─[middleware] Content-Length guard        ── 413
  ├─[dep]        rate limit (async, Redis)   ── 429   (router-scoped: existing geo routes untouched)
  ├─[pydantic]   poligono-only cheap caps    ── 422   (vertices, ring count, coord sanity)
  ├─ resolve geometry (4326)     parcela       → parcelas_catastro
  │                              poligono      → body → ST_MakeValid + ST_CollectionExtract(...,3)
  │                              canal_buffer  → canal_network + ST_Buffer(32720)
  │                              canal_cuenca  → canal_catchment lookup (precomputed)
  ├─ assert_within_caps(geom)                 ── 422   ← AFTER **every** resolution, before any I/O
  ├─ audit_log row + COMMIT                            ← before compute, survives failures
  ├─[semaphore] acquire 1 of N in-flight      ── 503
  ├─ soils   ── PostGIS ST_Intersection/32720 (0015 SQL, parameterized) + residual "sin dato"
  ├─ rasters ── extract_zonal_profile × {flood_risk, drainage_need, precip_normal×13}
  └─ FichaTerritorialResponse (percentages + cobertura, no geometry echo, NO pilar-verde block)
```

**Pilar Verde is not in the backend response [R1].** `PilarVerdeBadges` joins client-side against the
already-public static `/data/pilar-verde/bpa_enriched.json` using the clicked feature's `nro_cuenta`
— a published tile property (`martin/config.yaml:35`) — through the existing `usePilarVerde()` hook
(`consorcio-web/src/hooks/usePilarVerde.ts:46`). Zero backend work, zero new ETL, and the endpoint
stops carrying a per-parcel account identifier. `proposal.md` phase-1 wording ("BPA/forestación join
by `nro_cuenta`") is superseded by this note: the join is a UI concern.

## Architecture Decisions

### 1. Zonal-stats primitive

| Option | Tradeoff | Decision |
|---|---|---|
| Add `bins=` param to `extract_composite_zonal_stats` | Breaks its contract: existing callers rely on "skip nodata zones" and DB-insert-shaped dicts | Rejected |
| New `extract_zonal_profile()` beside it in `composites.py` | Slight duplication of the mask/reproject block | **Chosen** |

`extract_zonal_profile(raster_path, geom, geom_crs="EPSG:4326", breaks=None, geom_area_m2=None)`
returns ONE dict, always:

```
{mean, max, p90, valid_pixels, pixel_area_ha, covered_area_ha, coverage_ratio,
 coverage: "full"|"partial"|"none", low_confidence,
 bins: [{label, min, max, color, pixels, pct, ha}]}
```

#### 1.1 Both silent-skip branches are handled (JDB-004)

`extract_composite_zonal_stats` drops a zone in **two** places, not one. The primitive handles both:

| Existing branch | Cause | `extract_zonal_profile` behavior |
|---|---|---|
| `composites.py:344-350` — `except Exception: … continue` | `rasterio_mask(crop=True)` raises `ValueError` when the shape does not overlap the raster | Catch **`ValueError` only** → `coverage="none"`, `valid_pixels=0`, empty `bins`. Any other exception **propagates** (→ 503 `raster_ilegible`). No bare `except`. |
| `composites.py:361-366` — `if valid.size == 0: … continue` | Window overlaps but every pixel is nodata | `coverage="none"`, `valid_pixels=0`, empty `bins` |

`compute_zonal_stats` stays BANNED from this path (`zonal_stats.py:89` hardcodes nodata `-32768`).
`extract_composite_zonal_stats` is left untouched (its callers are the DEM pipeline).

#### 1.2 Coverage is measured against the geometry, not against the crop window (JDB-005, JD-A-005)

`rasterio_mask(crop=True)` returns a window **already clipped to the raster extent**, so
`valid_pixels / total_pixels` is ≈1.0 even when half the geometry lies outside the raster — partial
coverage would be undetectable. Coverage is therefore computed against the request geometry:

```
covered_area_ha = valid_pixels * pixel_area_ha
coverage_ratio  = min(1.0, covered_area_ha / geom_area_ha)      # geom_area_ha from ST_Area(32720)
coverage = "none"     if valid_pixels == 0
           "full"     if coverage_ratio >= 0.99
           "partial"  otherwise
```

The 0.99 tolerance absorbs the `all_touched=True` edge inflation (which pushes the ratio *above* 1.0,
hence the clamp). `geom_area_m2` is passed in by the service — it is already computed once in
EPSG:32720 for `area_ha`, so there is no second projection.

#### 1.3 Confidence is per-raster and relative (JD-A-007, JDB-017)

The R1 rule `low_confidence = valid_pixels < 10` is wrong across rasters of different ground
resolution: at CHIRPS 0.05° (~5.5 km) **every** parcel in the consorcio is under 10 pixels, and a
normals mean over 1 pixel is a legitimate value, not a defect. Replaced by a relative rule evaluated
per raster:

```
low_confidence = (geom_area_m2 / pixel_area_m2) < K        # K = ficha_low_confidence_pixel_ratio
```

`K` defaults to **10** and is overridable per dataset. `precip_normal` overrides `K = 0` (never
low-confidence on the pixel-ratio rule) because monthly normals are a smooth interpolated field:
sub-pixel sampling of it is exact, not approximate. Documented in the config table.

#### 1.4 Class breaks

Extract `RANGE_CONFIGS` (`tile_service_support.py:113-125`) into a new leaf module
`app/domains/geo/class_breaks.py`; `tile_service_support` re-exports it. Rationale: ficha percentages
MUST match the legend the user is reading on the map — two configs would drift. A leaf module avoids
importing the tile service (geo-worker code) into the API process.

**Bin-edge convention**: half-open `[min, max)` for every bin except the last, which is closed
`[min, max]` so the raster maximum is never dropped. Stated in the primitive docstring and asserted
by a unit test with a value exactly on an edge.

### 2. Endpoint

| Question | Decision | Rationale |
|---|---|---|
| Location | `router_ficha.py`, a **dedicated `APIRouter`** included into the geo router | JDB-003: hanging `dependencies=[enforce_ficha_rate_limit]` on `router_analysis` (`router_analysis.py:19`) would throttle `/zonal-stats` and every other operator analysis route. A separate router isolates both the limiter and the missing auth dependency. `router_analysis.py` is 271 lines today — the ficha does not go there. |
| Sync vs Celery | **All phases sync. No Celery, no job envelope** | **[R2]** Phases 1-4 are a masked read; phase 5's watershed is precomputed offline (§5), so `canal_cuenca` at request time is a table lookup plus the same zonal stats. The response schema stays uniform across all four `tipo` values — which the spec requires ("byte-compatible with `tipo=parcela`") and which a poll/job envelope would have broken. |
| Blocking I/O | Handler stays `def` (not `async def`) | Starlette offloads sync path ops to the threadpool, so rasterio never blocks the loop. The rate-limit dependency is `async def` — FastAPI allows async deps on sync handlers |
| Body | Pydantic v2 discriminated union on `tipo` | One schema, one UI code path |

**Namespace posture (deliberate exception).** The route stays at `POST /api/v2/geo/analisis-zona`
even though `/api/v2/public/*` is this repo's marker for unauthenticated routes (CLAUDE.md). Reason:
the ficha is a *geo* capability whose siblings (tiles, layers, zonal stats) all live under `/geo`,
and the spec's stated path is `/api/v2/geo/analisis-zona` — moving it would fork the spec for a
cosmetic gain. The exception is made safe structurally, not by convention: the ficha router is a
separate `APIRouter` with no auth dependency, and an integration test walks `app.routes` asserting
that **every other** route under `/api/v2/geo` still carries an operator dependency. That test is
the guard against the real risk (an auth dependency accidentally dropped from the shared router).

#### 2.1 Caps: schema validators are not enough (JD-A-002, JDB-006)

Pydantic validators only ever see a caller-supplied polygon. Three of the four `tipo` values produce
a **server-derived** geometry that no schema can bound: a large `parcelas_catastro` parcel, an
unbounded `ST_Buffer`, a precomputed catchment. The service therefore calls
`assert_within_caps(geom, *, tipo)` **after every geometry resolution and before the first raster
open**, raising 422 with the exceeded cap name and its limit:

| Cap | Config key | Value | Applies to | Justification |
|---|---|---|---|---|
| Area | `ficha_max_area_ha` | 20 000 ha | all four `tipo` | ≈23 % of the ~88 000 ha consorcio — a legitimate sub-basin, ~100× the median parcel; at 30 m that is ~222 k px/raster (<2 MB float64) |
| Envelope | `ficha_max_envelope_ha` | 60 000 ha | all four `tipo` | Blocks a thin diagonal sliver whose bbox window explodes `rasterio_mask(crop=True)` |
| Vertices | `ficha_max_vertices` | 1 000 | `poligono` (schema) + all (service) | Hand-drawn `DrawControl` polygons are <100; 1 000 admits a pasted parcel outline while bounding `ST_Intersection` cost |
| Buffer distance | `ficha_max_buffer_m` | 2 000 m | `canal_buffer` | **New (JDB-006)**: without it, `buffer_m` is an unbounded amplification knob. 2 km each side of a canal is already a generous influence zone; the area cap remains the backstop |
| Body size | `ficha_max_body_bytes` | 1 MiB | all | See §2.3 |
| Concurrency | `ficha_max_concurrency` | 4 in-flight | all | See §2.4 |
| Confidence ratio | `ficha_low_confidence_pixel_ratio` | 10 (precip: 0) | all rasters | §1.3 |

Pydantic keeps the **cheap** `poligono` pre-checks (vertex count, ring count, coordinate sanity) so
an obviously abusive body dies before any DB round-trip. `assert_within_caps` is the authority.

#### 2.2 Rate limit

| Knob | Value | Justification |
|---|---|---|
| Rate | 30 req/min per IP, `key_prefix="ratelimit:ficha:"` | A human clicking parcels peaks ~10/min; 30 leaves headroom and still caps a scraper at ~1 req/2 s |
| Cost | `check(key, cost=5)` for `poligono`, **`canal_buffer`** and `canal_cuenca` | JDB-006: `canal_buffer` is as expensive as a drawn polygon and was priced at 1 in R1. The limiter already takes `cost` (`rate_limit.py:126-151`) |

**Non-atomicity, acknowledged and bounded.** `_check_redis` does `ZREMRANGEBYSCORE`+`ZCARD` in a
pipeline, then issues the cost increments in a *separate* loop of `await zadd` calls
(`rate_limit.py:166-195`). Check-then-act is not atomic: N concurrent requests can all read the same
`current_count` and all pass. Mitigations, in order:
1. Issue the `cost` increments as a **single pipelined `zadd`** with a `{member: score}` mapping
   instead of `cost` sequential awaits — shrinks the window and removes `cost-1` round-trips.
2. Accept the residual: worst case a burst overshoots by (concurrent requests − 1), which is bounded
   by the in-flight semaphore (§2.4) at 4.
Rewriting the limiter as a Lua CAS script is **out of scope for this change** — it is shared
infrastructure and belongs in a backlog ticket.

**Redis-down policy (explicit).** `DistributedRateLimiter` degrades to a per-process in-memory
window (`_check_memory`) and logs a warning; it does not fail open and does not fail the request.
With one backend replica today that is equivalent protection; with N replicas the effective limit
becomes N×30/min. This is accepted because the limiter is the *third* line of defense — the caps
(§2.1) and the semaphore (§2.4) are what actually bound cost per request and per process.

#### 2.3 Body-size guard (JDB-007)

A `poligono` body is caller-controlled JSON; Pydantic's vertex cap only fires **after** the whole
body is parsed. A dependency on the ficha router rejects `Content-Length > ficha_max_body_bytes`
with **413** before parsing. A request with no `Content-Length` (chunked) is read through a counting
guard that aborts at the same threshold. Integration test: 2 MiB body → 413, no parse, no DB hit.

#### 2.4 Concurrency semaphore

The handler is sync and runs on Starlette's threadpool; rasterio holds real memory per call. The
service acquires a module-level `threading.BoundedSemaphore(ficha_max_concurrency)` with a short
timeout (2 s); on timeout it returns **503** with `Retry-After`. This is the hard bound on
simultaneous raster memory, independent of Redis availability.

#### 2.5 Enforcement order and audit

Content-Length guard → rate limit (router dependency) → cheap Pydantic validators → geometry
resolution → `assert_within_caps` → `audit_log` row **committed** → semaphore → compute. A failed
computation still leaves a Ley 25.326 trace. New audit action `zona.analisis`, resource
`tipo=<tipo>,ref=<nomenclatura|canal_id|geom-hash>`; `client_ip` is the existing nullable column
(`audit_log.py:60`), `user_id` stays NULL by design.

#### 2.6 Error contract (JD-A-006)

Every failure returns `{"detail": <human message, Spanish>, "codigo": <stable machine code>, …}`.

| Status | `codigo` | Extra payload | Trigger | Integration test |
|---|---|---|---|---|
| 404 | `parcela_no_encontrada` | `nomenclatura` | unknown nomenclatura | POST unknown nomenclatura → 404, no raster opened |
| 404 | `canal_no_encontrado` | `canal_id` | unknown `canal_id` | POST unknown canal id → 404 |
| 409 | `variante_no_disponible` | `variantes_disponibles: []` | requested catchment variant absent | only `relevado` precomputed, ask `natural` → 409 listing `["relevado"]` |
| 413 | `cuerpo_excedido` | `max_bytes` | body over `ficha_max_body_bytes` | 2 MiB body → 413 before parse |
| 422 | `tipo_desconocido` | `tipos_validos` | `tipo` outside the union | `tipo:"provincia"` → 422 |
| 422 | `geometria_invalida` | `motivo` | non-repairable / non-polygonal geometry | bow-tie polygon that `ST_MakeValid` reduces to a line → 422 |
| 422 | `cap_excedido` | `cap`, `limite`, `valor` | any `assert_within_caps` failure | 30 000 ha polygon → 422 naming `area_ha`; 5 000 m buffer → 422 naming `buffer_m`; oversized precomputed catchment → 422 naming `area_ha` |
| 429 | `limite_de_tasa` | `retry_after` (+ `Retry-After` header) | limiter exhausted | limiter dep overridden to `max_requests=2` → 3rd call 429, no audit row, no raster |
| 503 | `dataset_no_cargado` | `dataset` | `suelos_catastro` empty, precip layers missing, catchments not precomputed | truncate `suelos_catastro` → 503 naming `suelos` |
| 503 | `raster_ilegible` | `dataset` | non-`ValueError` raster failure | chmod-000 raster fixture → 503, audit row still present |
| 503 | `sobrecarga` | `retry_after` | semaphore timeout | N+1 concurrent requests → one 503 |

#### 2.7 Drawn-polygon repair (JDB-008)

For `tipo=poligono` the geometry is normalized in PostGIS before anything else touches it:
`ST_CollectionExtract(ST_MakeValid(ST_GeomFromGeoJSON(:g)), 3)`. If the result is empty or has zero
area, the request is **422 `geometria_invalida`** — self-intersecting hand-drawn rings are common
with `DrawControl` and must not reach `ST_Intersection` or `rasterio_mask` raw (where they yield
silently wrong areas, not errors).

### 3. Soils

#### 3.1 Percentages must account for the uncovered remainder (JDB-009, JD-A-014)

`suelos_cu.geojson` does not tile the consorcio: 45 features, and a geometry can overlap a gap. The
soils breakdown therefore always includes a residual row:

```
sin_dato_ha = max(0, area_ha - Σ clase.ha)      → emitted as clase "sin dato" when > 0.5 % of area_ha
```

Without it, `pct` sums to 100 over the *covered* part only and the UI silently claims full soil
knowledge of the parcel.

#### 3.2 Class grouping (JDB-010)

Source `cap` values are capability class + subclass (`IVws`, `VIws`, `IIIsc`, `I`, `VIII`) with 2 of
45 features NULL. Grouping key = the **normalized roman prefix** (`IVws → IV`), so the ficha shows
the 8-class capability scale the legend uses; the full subclass string is carried as a per-row
`detalle` and rendered as a tooltip. NULL `cap` is grouped under the explicit label
`"sin clasificar"` — never dropped, never merged into `sin dato`.

#### 3.3 ETL: how it actually runs (JDB-002 — BLOCKER)

`gee-backend/Dockerfile:107` copies only `app/` and `alembic.ini` into the runtime image. Neither
`gee-backend/scripts/` nor the repo-root `scripts/` (`etl_pilar_verde.py`, `etl_canales.py`) exists
inside the backend container, and the host has no venv in the deployed environment. An R1
"`scripts/load_suelos_catastro.py`" would have been unrunnable everywhere. Resolution:

| Concern | Decision |
|---|---|
| Location | `app/domains/geo/etl/load_suelos_catastro.py`, executable as `python -m app.domains.geo.etl.load_suelos_catastro` — inside `app/`, therefore inside the image |
| Same for CHIRPS | `app/domains/geo/etl/generate_chirps_normals.py`, `python -m app.domains.geo.etl.generate_chirps_normals` |
| Source data | Packaged copy at `app/domains/geo/etl/data/suelos_cu.geojson` (**2.2 MB**, not 10 MB as R1 claimed). `--source PATH` overrides it. A unit test asserts the packaged copy is byte-identical to `consorcio-web/public/data/suelos_cu.geojson` (drift guard) |
| Invocation | `docker compose exec backend python -m app.domains.geo.etl.load_suelos_catastro` |
| `/data/geo` access | The **backend** container mounts `geo-data:/data/geo` (`docker-compose.yml:99`), so the CHIRPS generator writes to the same volume the geo-worker reads |
| Repo-root `scripts/` | Left alone. It is the *host-run* ETL precedent (`etl_pilar_verde.py`), a different execution model; this design does not extend it |

Idempotency = **full refresh in one transaction**: `DELETE FROM suelos_catastro` → bulk insert →
assertions → COMMIT. `--dry-run` prints the delta without writing.

**Assertions, complete (spec `soils-etl` "Load-time assertions")**, all inside the load transaction:

| # | Assertion | Note |
|---|---|---|
| 1 | `COUNT(*) == len(source features)` (45 today) | |
| 2 | `ST_IsValid(geometria)` for every row | source is repaired with `ST_MakeValid` first; unrepairable → abort naming `gid` |
| 3 | `ST_SRID(geometria) = 4326` for every row | |
| 4 | Σ ha in EPSG:32720 within 1 % of the source total | the proposal's success criterion |
| 5 | `ip` coerced int → str | source `ip` is an **int** (`{"gid":889,"simbolo":"Sr3","ip":39,"cap":"IVws"}`); the column is `String(50)` (`0015:42`). Without the cast the insert is a driver-dependent coin flip |
| 6 | `cap` NULL tolerated | 2 of 45 features have no `cap` |

Any failure → rollback → non-zero exit.

#### 3.4 Materialized view: reconciled with the spec (JD-A-004, JDB-016)

R1 declared "MV refresh cadence is a non-issue"; the `soils-etl` spec requires a non-blocking refresh
and an operator-triggered action. Both are true and were left contradictory. Reconciliation:

- **The ficha does not read `mv_suelos_por_zona`.** That MV is keyed to `zonas_operativas`
  (`0015:107`) and cannot serve arbitrary geometry. The ficha runs the same SQL (`0015:94-113`)
  parameterized by the request geometry. So the MV never blocks a ficha request.
- **The MV still has to be refreshable**, because it powers the existing zone dashboards and would
  otherwise go stale the moment the ETL loads soils. `REFRESH MATERIALIZED VIEW CONCURRENTLY`
  requires a unique index and the MV has none (`0015` creates only two non-unique indexes). The
  phase-0 migration therefore **recreates the MV** with a surrogate key
  `row_number() over (order by z.id, s.id) AS mv_id` and adds
  `CREATE UNIQUE INDEX IF NOT EXISTS ux_mv_suelos_por_zona_id ON mv_suelos_por_zona (mv_id)`.
  `(zona_id, simbolo)` is *not* unique — the same symbol can intersect a zone as two disjoint
  polygons — so a surrogate is the only correct key.
- **The refresh runs OUTSIDE the load transaction.** `REFRESH … CONCURRENTLY` cannot run inside a
  transaction block. The ETL commits the load first, then refreshes in autocommit. Consequence,
  documented: the "assertion failure leaves the table untouched" guarantee covers the load only; a
  refresh failure leaves data loaded and the MV stale.
- **Operator recovery**: `POST /api/v2/admin/geo/suelos/refresh-mv` (admin-only) runs the concurrent
  refresh. This is the spec's "stale view is recoverable" scenario.

#### 3.5 Dead twin removal

Same migration drops `mv_canales_por_zona` **then** `canales_geo` (view before table — the reverse
order fails on dependency). `canal_network` is the real table. `downgrade()` **raises**
`RuntimeError("downgrade unsupported: canales_geo/mv_canales_por_zona were dead schema")` — it does
not `pass`, per the `rainfall_records` precedent and the spec's "downgrade is explicit" scenario.

#### 3.6 `parcelas_catastro` prerequisite

Verifying that `parcelas_catastro` is populated in the target environment is **in scope for PR 1a**
(spec `soils-etl` "Prerequisite verification"): the phase ships a `--check-prereqs` mode that reports
row counts for `parcelas_catastro` and `suelos_catastro` and exits non-zero if `parcelas_catastro` is
empty, so an empty catastro is a named deployment blocker for `tipo=parcela` rather than a runtime
404 storm.

### 4. CHIRPS normals

`gee_service.export_chirps_monthly_normals()` delegating to a `*_payload` helper — mirrors
`compute_ndwi_baselines_gee` (`gee_service.py:540-555`). Source `UCSB-CHG/CHIRPS/DAILY`, monthly sums
averaged over 1991-2020, fetched with `getDownloadURL` (the clip is tiny at 0.05°).

| Aspect | Decision | Note |
|---|---|---|
| Count | **13 rasters: 12 monthly + 1 annual total** | JDB-011: R1 said 12 and the spec requires 13 |
| Output | `/data/geo/{area_id}/output/precip_normal_{MM}.tif` and `precip_normal_anual.tif` | written from the backend container, which mounts the volume |
| Warp | EPSG:32720, **5 000 m** target resolution, `Resampling.nearest` | JDB-018: CHIRPS native is 0.05° ≈ 5.5 km. Nearest at ~native resolution keeps source values; bilinear upsampling to 30 m would fabricate detail the ficha would then report as if measured |
| Nodata | **-9999.0** | matches the composites convention (`composites_support.py:176-183`) so it enters `extract_zonal_profile` unchanged |
| Registration | `TipoGeoLayer.PRECIP_NORMAL = "precip_normal"` + migration `ALTER TYPE tipo_geo_layer ADD VALUE 'precip_normal'` | native PG enum: the new value must not be *used* in the transaction that adds it |
| `metadata_extra` | `{"mes": 1..12 \| "anual", "normal_period": "1991-2020", "fuente": "CHIRPS", "version": "<UTC ISO8601 of the export run>", "resolucion_m": 5000}` | JDB-011: `version` is what makes a regeneration distinguishable, per the spec |
| Cadence | Static. Regenerate only on a period or extent change | documented in the module docstring; no scheduled job |

**Layer lookup idiom (JD-A-008).** All 13 rasters share `tipo=PRECIP_NORMAL`. The geo domain's usual
"most recent layer of tipo X for this area" idiom returns ONE row and would hand the same raster back
for all twelve months. The ficha instead selects `tipo=PRECIP_NORMAL AND area_id=:area`, groups by
`metadata_extra->>'mes'`, and takes the newest `version` **within each month**. Missing months →
`precipitacion_mensual.cobertura = "sin_cobertura"` for the whole dataset plus a 503
`dataset_no_cargado` only if *zero* months are registered.

**Response shape is a typed exception (JD-A-007).** Monthly normals are mean millimetres, not a
class partition — `{clase, ha, pct}` is meaningless for them and `pct` cannot sum to 100. The
`precipitacion_mensual` dataset therefore carries its own shape (spec delta on
`geo-analysis-endpoint:86`):

```
precipitacion_mensual: {
  cobertura, low_confidence, pixel_count,
  unidad: "mm",
  serie: [{mes: 1..12, mm: <float>}],     # calendar order, always 12 entries when covered
  anual_mm: <float>
}
```

### 5. Catchment (phase 5) — precomputed, not async **[R2]**

| Option | Tradeoff | Decision |
|---|---|---|
| Celery job + poll for `canal_cuenca` | Breaks the uniform response schema the spec mandates; one `tipo` returns a job envelope, the UI needs a second code path | Rejected |
| Compute the watershed in the request | WBT `watershed` over a full DEM is tens of seconds | Rejected |
| **Precompute per canal, look up at request time** | Needs a batch step and a table | **Chosen** |

`canal_network` is finite and its geometry changes only when the topology is reloaded, so catchments
are derived **offline**, as a batch step after each DEM pipeline run:

1. For each `canal_network` row × each available variant (`natural`, `relevado`):
2. Rasterize the canal LINESTRING onto the variant's `flow_dir` grid as int16 seed cells — the whole
   trace is the pour geometry, which is what "cuenca del canal" means. WBT's `pour_pts` argument is
   a raster of seed cells, exactly as the existing code already builds one
   (`calculations_hydrology_support.py:249-254`).
3. `watershed(d8_pntr=<flow_dir raster>, pour_pts, output)` — the **D8 pointer, explicitly not the
   DEM**. `calculations_hydrology_support.py:255` currently calls
   `get_wbt().watershed(dem_path, pour_points, basins)`, i.e. a DEM in the pointer slot. That call
   MUST NOT be copied; phase 5 stays blocked until the backlog fix lands.
4. Polygonize → store in a new table `canal_catchment(id, canal_id, variante, geometria
   MULTIPOLYGON/4326, area_ha, oversized bool, flow_dir_layer_id, version, created_at)` and register
   the raster artifact as a GeoLayer.
5. **The area cap is applied at precompute time**: a catchment above `ficha_max_area_ha` is stored
   with `oversized = true`.

At request time `tipo=canal_cuenca` is a `SELECT … WHERE canal_id AND variante` → the same
`assert_within_caps` → the same sync raster loop. Outcomes:

| Situation | Response |
|---|---|
| Row found, `oversized = false` | 200, identical schema to `tipo=parcela`, `variante` echoed |
| Row found, `oversized = true` | **422 `cap_excedido`** naming `area_ha` — no raster opened |
| Row missing for that variant, other variant present | **409 `variante_no_disponible`** with `variantes_disponibles` — never a silent fallback to the burned DEM |
| No rows at all for that canal | **503 `dataset_no_cargado`** (`dataset: "cuencas"`) — catchments not precomputed for this deployment |
| Degenerate (single-cell) basin | 200 with the tiny `pixel_count` and `low_confidence: true` per §1.3 |

Default variant when both exist: `natural`.

**`JensenSnapPourPoints` is dropped (JD-A-015).** Jensen snapping moves *point* pour locations to the
nearest high-accumulation cell; snapping an entire rasterized line trace is undefined — every seed
cell would migrate to the same drainage cell, collapsing the trace into one point and producing a
plausible-but-wrong basin. The rasterized trace is used directly as the seed set.

### 6. Frontend

`InfoPanel` stays pure (`InfoPanel.tsx:29-30`). The fetch lives in `MapWorkspace` (already the
stateful container) via `useFichaTerritorial()`; `MapUiPanels` receives `ficha`/`fichaStatus` as props
and renders a **sibling** `<FichaTerritorialPanel>`, not a card inside `InfoPanel`.

#### 6.1 ONE interaction-mode machine (JDB-012)

R1 added a `useFichaMode` zustand slice alongside the existing `measurementMode`
(`useMapInteractionEffects.ts:10,83`). Two independent machines can both be non-idle — measuring a
distance *and* drawing a ficha polygon — and both bind map clicks. There is no invariant that stops
it. Decision: **extend the existing enum, add no second machine.**

```ts
// measurement/useMeasurement.ts:62 — the union is widened, the name generalized
export type MapInteractionMode =
  | 'idle' | 'measuring-distance' | 'measuring-area' | 'ficha-dibujo' | 'ficha-canal';
export type MeasurementMode = MapInteractionMode;   // back-compat alias, one release
```

`useMapInteractionEffects` keeps its single `mode` prop and its existing
`if (mode !== 'idle') return;` guard shape. Mutual exclusion is structural: a union has one value.

#### 6.2 Parcel click is the DEFAULT, not a mode (JD-A-013, JDB-014)

R1 gated the parcel ficha behind `mode === 'parcela'` while the panel "only mounts when
`fichaMode !== 'idle'`" — which hides the entire phase-1 deliverable behind a mode the design never
gave the user a way to enter. Corrected:

- In `'idle'` (the default), the existing click routing is **untouched**: `buildClickableLayers()`
  ordering and Pilar Verde precedence stay exactly as they are today
  (`useMapInteractionEffects.ts:35-62`).
- When a click resolves a `parcelas_catastro` feature, the container additionally fires
  `useFichaTerritorial({tipo:'parcela', nomenclatura})`. No gate, no new entry point, no regression
  in existing behavior.
- `'ficha-dibujo'` → `DrawControl` owns clicks, `buildClickableLayers()` returns `[]`; entered from a
  toolbar button next to the existing measurement buttons.
- `'ficha-canal'` → clickable layers filtered to canal layers only; entered from the same toolbar.

#### 6.3 Canal clicks need a layer that carries `canal_network.id` (JDB-013)

The currently clickable canal layers (`CANALES_RELEVADOS`, `CANALES_PROPUESTOS`) come from static
sources and do **not** carry `canal_network` identifiers, so `tipo=canal_buffer` had no way to
produce a `canal_id`. `martin/config.yaml:66-79` already publishes `vt_canal_network` with
`id_column: id` and an `id` property. Phase 3 therefore:

1. Adds `vt_canal_network` as a rendered line layer, clickable only in `'ficha-canal'` mode.
2. Uses the clicked feature's `id` property directly as `canal_id` (it is `canal_network.id`).
3. **Verifies `vt_canal_network` is populated in the target environment** as an explicit PR-6
   prerequisite check, the same way `parcelas_catastro` is verified in PR 1a. An empty view makes the
   whole canal mode dead on arrival.

#### 6.4 Card tree — tables first, charts as complement (JD-A-012)

The `ficha-frontend` spec requires "one table per dataset with columns clase / ha / % and the total
hectares". R1's tree was charts-only (stacked bar, bins, recharts). Corrected:

| Component | Renders |
|---|---|
| `FichaResumen` | `area_ha`, per-dataset `cobertura`, low-confidence badges |
| `SuelosBreakdown` | **table** clase / ha / % (incl. `sin dato` and `sin clasificar`), subclass in a tooltip; stacked bar above it as a visual complement (colors from `useSoilMap.ts:11-47`) |
| `RiesgoBins` ×2 | **table** clase / ha / % per bin; colored bar as complement (colors from `class_breaks`) |
| `PrecipChart` | 12-bar chart in calendar order **plus** a mes/mm table and `anual_mm` |
| `PilarVerdeBadges` | client-side join of `usePilarVerde()` against the clicked feature's `nro_cuenta` **[R1]**; renders "sin vinculación" when the tile has no `nro_cuenta`; the section is **omitted entirely** for `poligono`/`canal_*` (no single account to join) |

Percentages come from the server and are never recomputed client-side from hectares (spec).
Every block renders "sin cobertura" on `cobertura === "sin_cobertura"` — never a `0 %` row.

#### 6.5 Query and staleness

- **Query key**: `['ficha-territorial', tipo, refKey]`, `refKey` = nomenclatura / canal id + variant
  or buffer / a stable hash of the rounded polygon coordinates.
- `staleTime: 5min`, `gcTime: 30min`, `retry: (n, e) => n < 1 && ![413,422,429].includes(e.status)`.
- **Stale-on-switch (spec "Switching modes discards previous result")**: the hook does **not** use
  `placeholderData: keepPreviousData`. Changing mode, clicking a different parcel, or clearing the
  drawing changes `refKey`, so the card immediately shows the loading state instead of the previous
  area's numbers. Leaving a ficha mode clears the selection and unmounts the panel.

### 7. Testing

| Layer | What | How |
|---|---|---|
| Unit (no DB) | `extract_zonal_profile` | Synthetic 10×10 float32 GeoTIFFs in `tmp_path` with known values → exact expected `pct`; cases: full, **partial where the crop window is fully valid** (the JDB-005 regression), disjoint (`ValueError` → `coverage="none"`), all-nodata → `coverage="none"`, non-`ValueError` failure propagates, value exactly on a bin edge |
| Unit | Cap validators, discriminated union, `assert_within_caps` for each `tipo` | Pydantic round-trip + direct service calls, no I/O |
| Unit | Packaged geojson matches the frontend artifact | byte comparison, drift guard |
| Integration (real PG) | ETL loader (6 assertions + rollback), MV unique index + concurrent refresh, soils SQL incl. residual and NULL `cap`, endpoint | `tests/new/` with the `db` / `db_session_factory` fixtures; 3-polygon fixture geojson. **`app.main` is imported INSIDE the test/fixture body, never at module level** (VTK segfault rule) |
| Integration | Full error contract | one test row per §2.6 line |
| Integration | Limiter isolation | assert a 429-exhausted ficha limiter does **not** affect `/api/v2/geo/zonal-stats` |
| Integration | Auth posture | walk `app.routes`: every `/api/v2/geo` route except `analisis-zona` carries an operator dependency |
| Integration | Audit durability | force a compute failure → assert the `audit_log` row still exists (committed first) |
| Perf gate | Latency | 20 sequential requests on the fixture parcel; p95 ≤ 1.5 s (proposal success criterion) asserted in PR 3b and recorded in the PR body. **R1's "300-600 ms" estimate is withdrawn — it was never measured** (JD-A-009) |
| E2E | Click parcel → ficha renders | One Playwright spec; skips gracefully when `parcelas_catastro` is empty (precedent `afectados.spec.ts:166`) |

## File Changes

| File | Action | Description |
|---|---|---|
| `app/db/migrations/versions/00XX_ficha_territorial_prep.py` | Create | Drop `mv_canales_por_zona` then `canales_geo`; recreate `mv_suelos_por_zona` with `mv_id` + unique index; `downgrade()` raises |
| `app/domains/geo/etl/__init__.py` | Create | ETL package (inside the image) |
| `app/domains/geo/etl/load_suelos_catastro.py` | Create | `python -m` soils ETL: 6 assertions, `--dry-run`, `--check-prereqs`, post-commit concurrent MV refresh |
| `app/domains/geo/etl/data/suelos_cu.geojson` | Create | Packaged 2.2 MB source copy + drift test |
| `app/domains/geo/etl/generate_chirps_normals.py` | Create | `python -m` normals driver (13 rasters) |
| `app/domains/geo/class_breaks.py` | Create | `RANGE_CONFIGS` moved out of `tile_service_support.py` |
| `app/domains/geo/composites.py` | Modify | Add `extract_zonal_profile` (both skip branches, geometry-relative coverage, relative confidence) |
| `app/domains/geo/schemas_ficha.py` | Create | Discriminated-union request + response (incl. the typed `precipitacion_mensual` shape) |
| `app/domains/geo/ficha_service.py` | Create | Geometry resolution, `assert_within_caps`, semaphore, soils SQL, raster loop, assembly |
| `app/domains/geo/router_ficha.py` | Create | Dedicated public `APIRouter`: `POST /analisis-zona`, limiter dep, 413 guard |
| `app/domains/geo/router.py` | Modify | Include `router_ficha` |
| `app/domains/geo/router_admin_suelos.py` | Create | `POST /api/v2/admin/geo/suelos/refresh-mv` (admin) |
| `app/config.py` | Modify | `ficha_rate_limit_*`, `ficha_max_area_ha`, `ficha_max_envelope_ha`, `ficha_max_vertices`, `ficha_max_buffer_m`, `ficha_max_body_bytes`, `ficha_max_concurrency`, `ficha_low_confidence_pixel_ratio` |
| `app/core/rate_limit.py` | Modify | Single pipelined `zadd` for `cost` increments (§2.2) |
| `app/domains/geo/models.py` + migration | Modify | `TipoGeoLayer.PRECIP_NORMAL` + `ALTER TYPE` |
| `app/domains/geo/gee_service.py` (+ `_support`) | Modify | CHIRPS normals export (12 + annual) |
| `app/db/migrations/versions/00YY_canal_catchment.py` | Create | `canal_catchment` table (phase 5) |
| `app/domains/geo/intelligence/catchment_precompute.py` | Create | Offline per-canal watershed batch (phase 5) |
| `consorcio-web/src/hooks/useFichaTerritorial.ts` | Create | TanStack Query hook |
| `consorcio-web/src/components/map2d/measurement/useMeasurement.ts` | Modify | Widen the mode union (`MapInteractionMode`) |
| `consorcio-web/src/components/map2d/FichaTerritorial*.tsx` | Create | Panel + card tree (tables + charts) |
| `consorcio-web/src/components/map2d/MapUiPanels.tsx` / `MapWorkspace.tsx` | Modify | Wire props + fetch; parcel click by default |
| `consorcio-web/src/components/map2d/useMapInteractionEffects.ts` | Modify | New modes in the existing `mode` guard; canal-only clickable set |
| `consorcio-web/src/components/map2d/mapLayerEffectHelpers.ts` | Modify | Render `vt_canal_network` line layer (phase 3) |

## Phase → PR Mapping **[R3]**

Two short chains instead of one 9-deep chain. Chain B forks off `main` and only rejoins at B2.

**Chain A — core ficha**

| PR | Phase | Base | Scope | Est. lines |
|---|---|---|---|---|
| A1a | 0 | `main` | Migration: drop twins (view→table), MV rebuild + unique index, raising `downgrade()`; `--check-prereqs` reporting `parcelas_catastro` / `suelos_catastro` row counts | ~200 |
| A1b | 0 | A1a | Soils ETL module + packaged geojson + drift test + admin refresh endpoint + real-PG ETL tests | ~320 |
| A2 | 1a | A1b | `class_breaks.py` + `extract_zonal_profile` + unit tests | ~300 |
| A3a | 1b | A2 | Contract + guards vs a **stub** ficha service: schemas, dedicated router, limiter, 413, caps, audit, semaphore, full §2.6 error-contract integration tests | ~330 |
| A3b | 1b | A3a | Real compute replaces the stub: soils SQL + residual, raster loop, cobertura/confidence, perf gate | ~300 |
| A4 | 1c | A3b | `FichaTerritorialCard` tree + hook + `MapWorkspace` wiring + E2E | ~350 |
| A5 | 2 | A4 | `tipo=poligono` + `ST_MakeValid` repair + `DrawControl` + `ficha-dibujo` mode | ~240 |
| A6 | 3 | A5 | `tipo=canal_buffer` + `ficha_max_buffer_m` + `vt_canal_network` clickable layer + prod population check + `ficha-canal` mode | ~260 |
| A7 | 5 | A6 | `canal_catchment` table + offline precompute + lookup endpoint + 409/422/503 paths — **blocked on the D8 backlog fix** | ~380 |

**Chain B — precipitation (parallel, off `main`)**

| PR | Phase | Base | Scope | Est. lines |
|---|---|---|---|---|
| B1 | 4a | `main` | CHIRPS export (12 + annual) + `PRECIP_NORMAL` enum migration + generator module + month-scoped lookup helper | ~320 |
| B2 | 4b | A3b **and** B1 | `precipitacion_mensual` in the response (typed shape) + recharts chart + mm table | ~220 |

`Decision needed before apply: Yes` · `Chained PRs recommended: Yes (two chains)` ·
`400-line budget risk: Medium (A3 split, B parallelized)`

## Migration / Rollout

Phase 0 is forward-only for the twin DROP (`rainfall_records` precedent, `downgrade()` raises); the
soils load is reversible with `DELETE FROM suelos_catastro`; the MV rebuild is re-runnable. Phases
1-5 are additive: revert the PR. On the frontend, reverting removes the ficha panel and the widened
mode values; `'idle'` behavior — including parcel clicks and Pilar Verde precedence — is the
pre-existing path and is unchanged by this design, so a revert restores current behavior exactly.

Deployment order per environment: `alembic upgrade head` →
`docker compose exec backend python -m app.domains.geo.etl.load_suelos_catastro` → verify row count
and MV → deploy the API → deploy the frontend.

## Open Questions

- [ ] IDECOR upstream for `suelos_cu.geojson` — the repo file is treated as canonical until answered.
- [ ] `afectados.spec.ts` current pass/fail status (proposal Q4) — does not block this design.
- [ ] Confirm the CHIRPS normal period (1991-2020 assumed).
- [ ] Is `vt_canal_network` populated in the target environment? Blocks phase 3 (§6.3).
- [ ] Lua-CAS rewrite of `DistributedRateLimiter` — backlog ticket, not this change (§2.2).
