# geo-analysis-endpoint Specification

## Purpose

`POST /api/v2/geo/analisis-zona` — one public endpoint that returns an integrated
territorial report card (soils, flood risk, drainage need, precipitation normals,
hectares) for a caller-supplied area of interest.

## Requirements

### Requirement: Discriminated-union request body

The endpoint MUST accept a single JSON body discriminated by `tipo` with exactly the
values `parcela`, `poligono`, `canal_buffer`, `canal_cuenca`. Unknown `tipo` values MUST
be rejected with HTTP 422 before any geometry or raster work.

- `parcela` → `{ tipo, nomenclatura }`; geometry resolved from `parcelas_catastro`.
- `poligono` → `{ tipo, geometry }` (GeoJSON Polygon/MultiPolygon, EPSG:4326).
- `canal_buffer` → `{ tipo, canal_id, buffer_m }`; buffer computed in EPSG:32720.
- `canal_cuenca` → `{ tipo, canal_id, variante }` where `variante` ∈ `natural|relevado`.

The response schema MUST be identical for all four variants so the UI renders one path.

#### Scenario: Parcel analysis succeeds

- GIVEN `parcelas_catastro` contains nomenclatura `X` and rasters cover it
- WHEN the client POSTs `{tipo: "parcela", nomenclatura: "X"}`
- THEN the response is HTTP 200 with the uniform ficha schema
- AND `area_ha` is computed in EPSG:32720

#### Scenario: Free polygon analysis succeeds

- GIVEN a valid GeoJSON polygon within the caps
- WHEN the client POSTs `{tipo: "poligono", geometry: {...}}`
- THEN the response is HTTP 200 with the same schema as `tipo=parcela`

#### Scenario: Unknown tipo is rejected

- GIVEN a body with `tipo: "provincia"`
- WHEN the request is submitted
- THEN the response is HTTP 422 and no raster file is opened

### Requirement: Mandatory pre-raster-read enforcement order

The endpoint MUST execute, in this exact order, BEFORE opening any raster or running any
PostGIS intersection: (1) rate limit check, (2) geometry validation (area cap, vertex
cap, ring validity), (3) `audit_log` write. Failing any earlier step MUST short-circuit
the request. The audit entry MUST be written even when the compute step later fails.

#### Scenario: Rate limit precedes validation and compute

- GIVEN the caller IP has exceeded the configured requests/minute
- WHEN it POSTs an otherwise valid body
- THEN the response is HTTP 429
- AND no geometry validation, no audit entry, and no raster read occur

#### Scenario: Oversized polygon rejected before raster read

- GIVEN a polygon whose EPSG:32720 area exceeds the configured max hectares
- WHEN the request is submitted
- THEN the response is HTTP 422 naming the exceeded cap and its limit
- AND no raster file is opened

#### Scenario: Vertex cap rejected before raster read

- GIVEN a polygon with more vertices than the configured maximum
- WHEN the request is submitted
- THEN the response is HTTP 422 naming the vertex cap
- AND no raster file is opened

#### Scenario: One audit row per accepted request

- GIVEN a valid request that passes rate limit and validation
- WHEN it is processed
- THEN exactly one `audit_log` row is written recording action, `tipo`, and requester IP
- AND the row exists even if the compute step subsequently raises

### Requirement: Uniform ficha response schema

The response MUST contain per-dataset breakdowns, each as an array of
`{ clase, ha, pct }`, plus `area_ha` total, and per-dataset `pixel_count` with a
`low_confidence` boolean. `pct` values within a dataset MUST sum to 100 ± 0.5 when
coverage exists. The response MUST NOT echo input geometry and MUST NOT expose any
attribute beyond what public vector tiles already publish.

Datasets: `suelos` (vector), `flood_risk`, `drainage_need`, `precipitacion_mensual`.

> **Delta (post-JD) — `precipitacion_mensual` is a typed exception to `{clase, ha, pct}`.**
> Monthly normals are mean millimetres, not a class partition of the area: there is no `ha` per
> class and `pct` cannot sum to 100. That dataset carries its own shape
> `{ cobertura, low_confidence, pixel_count, unidad: "mm", serie: [{mes: 1..12, mm}], anual_mm }`,
> with `serie` in calendar order. Every other dataset keeps `{clase, ha, pct}`. Rationale: design
> §4 (JD-A-007, JDB-011).
>
> **Delta (post-JD) — `low_confidence` is per-raster and relative.** The threshold is not a global
> `pixel_count < 10`; it is `(geometry_area_m2 / pixel_area_m2) < K` evaluated per raster
> (`ficha_low_confidence_pixel_ratio`, default 10), because CHIRPS pixels are ~5.5 km and 30 m
> composite pixels are not comparable. `precip_normal` overrides `K = 0` — a smooth interpolated
> field sampled sub-pixel is exact, not approximate. Rationale: design §1.3 (JD-A-007, JDB-017).
>
> **Delta (post-JD) — `cobertura` is measured against the request geometry.** `rasterio_mask(crop=True)`
> returns a window already clipped to the raster extent, so a valid/total pixel ratio can never
> detect partial coverage. `cobertura` is measured against the geometry itself
> (`sin_cobertura` at 0, `total` at ≥ 0.99, `parcial` otherwise). Rationale: design §1.2
> (JDB-004, JDB-005, JD-A-005).
>
> **Delta (post-4R A2) — raster areas and `cobertura` are FRACTIONAL-WEIGHT, not whole-pixel.**
> The post-JD formula counted whole pixels (`valid_pixels * pixel_area_ha`) over a mask taken with
> `all_touched=True`, and divided by the EPSG:32720 geometry area. Measured, that inflated reported
> hectares by **+4 % to +44 %** depending on parcel size and grid alignment (a 25.00 ha box read
> 29.16 ha; a 2.25 ha box read 3.24 ha) — and `ha` reaches the UI verbatim beside the true
> `area_ha`. Worse, the inflation was spent by the `min(1.0, ratio)` clamp: up to ~15 % (500 m
> parcel) / ~31 % (150 m parcel) of INTERIOR nodata was absorbed and still reported `total`.
>
> Every raster pixel therefore carries a coverage weight in `[0, 1]`: 1 or 0 for pixels the
> geometry's boundary does not cross (one `all_touched=False` center-in-polygon rasterization
> settles those exactly), and the EXACT areal fraction `geometry ∩ pixel / pixel_area` for the
> pixels it does cross. Cost scales with the geometry's perimeter, not its area.
>
> ```
> total_weight    = Σ ALL weights of the geometry
> valid_weight    = Σ weights over pixels INSIDE the raster that are not nodata/NaN
> covered_area_ha = valid_weight * pixel_area_ha
> ha   (per class) = Σ weights of that class's valid pixels * pixel_area_ha
> pct  (per class) = class weight / valid_weight * 100
> cobertura_ratio  = valid_weight / total_weight
> cobertura        = sin_cobertura if no valid pixel, or if the geometry has no rasterized
>                                     area at all (degenerate / self-intersecting collapse):
>                                     "total" over 0.0 ha would be a confident wrong answer
>                    total         if cobertura_ratio ≥ 0.99
>                    parcial       otherwise
> ```
>
> **Delta (post-4R round 3) — both sides of the ratio come from ONE rasterization.** The first
> implementation of this rule mixed accountings: `valid_weight` was rasterized, but `total_weight`
> was the analytic `geometry_area / pixel_area`. Any error in the rasterized numerator therefore
> showed up as fake missing data — measured, a 200 m box read `parcial` at 0.9875 and a 10 m x
> 3 000 m canal strip read 0.75 with hectares 25 % low, on complete data. The geometry is now
> rasterized ONCE, over a window aligned to the raster's grid but extended to cover the whole
> geometry (it may run past the raster's extent), and BOTH weights are read off that one array:
> the denominator is its full sum, the numerator its sum over pixels that are inside the raster and
> valid. A parcel fully inside the raster with no nodata therefore scores exactly 1.0 by
> construction, while the weights of the part hanging off the raster inflate only the denominator
> and still surface as `parcial`.
>
> The ratio is thus self-normalizing: it needs no caller-supplied projected area (a geographic
> raster with no `geom_area_m2` detects partial coverage instead of defaulting to `total`), and it
> cannot exceed 1 by construction. **`0.99` is a pure float-noise tolerance** — it absorbs neither
> `all_touched` edge inflation nor rasterization error, because there is neither. The EPSG:32720
> geometry area is still accepted, but only feeds `low_confidence`.
>
> `pixel_count` stays a RAW integer diagnostic (how many pixels were sampled, edge pixels
> included); `ha` and `pct` are weighted. The two are deliberately not proportional at the
> geometry edge. Rationale: 4R findings R3-001 / R3-002 (both 3/3 refuters, measured).
>
> **Delta (post-JD) — wire vocabulary.** The internal primitive returns English primitives; the
> wire contract is the Spanish vocabulary in this spec. Mapping:
>
> | Primitive (`extract_zonal_profile`) | Wire field |
> |---|---|
> | `coverage: "full" \| "partial" \| "none"` | `cobertura: "total" \| "parcial" \| "sin_cobertura"` |
> | `bins[].label` | `clase` |
> | `bins[].ha` / `bins[].pct` | `ha` / `pct` |
> | `valid_pixels` | `pixel_count` |
> | `low_confidence` | `low_confidence` |
>
> **Delta (post-JD) — the `suelos` breakdown includes an explicit residual.** `suelos_cu.geojson`
> does not tile the consorcio, so a geometry can overlap a gap. `suelos` MUST include a
> `clase: "sin dato"` row with `ha = area_ha - Σ clase.ha` whenever that residual exceeds 0.5 % of
> `area_ha`, and a `clase: "sin clasificar"` row for source features whose `cap` is NULL. Classes
> are grouped by the normalized roman prefix of `cap` (`IVws → IV`), with the full subclass string
> carried as `detalle`. Rationale: design §3.1-3.2 (JDB-009, JDB-010, JD-A-014).
>
> **Delta (post-JD) — the response carries NO BPA/forestación block.** BPA membership is joined
> client-side against the already-public `/data/pilar-verde/bpa_enriched.json` using the clicked
> feature's `nro_cuenta`, a published vector-tile property. The endpoint therefore never returns a
> `nro_cuenta`, a membership list, or a `sin_vinculacion` marker; "sin vinculación" is a UI state
> (see `ficha-frontend`). Rationale: design §"Technical Approach" [R1] (JD-A-001, JDB-001).

#### Scenario: Per-class breakdown returned

- GIVEN a parcel intersecting soil classes IV and VI
- WHEN the ficha is requested
- THEN `suelos` contains one entry per class with `clase`, `ha` and `pct`
- AND the sum of `ha` equals `area_ha` within 1%

#### Scenario: Raster hectares do not inflate on an off-grid parcel

- GIVEN a parcel whose edges do not align with the 30 m raster grid
- WHEN the ficha is requested
- THEN the sum of `ha` across a raster dataset's classes equals that dataset's covered area
  within 1%, and never exceeds `area_ha`
- AND for a fully covered parcel that sum equals `area_ha` within 1%, not the whole-pixel
  count times the pixel area
- AND this holds for ANY parcel size and grid alignment — from a 50 m parcel (under two
  pixels wide) to a 500 m one, at every offset within the pixel — and for a 20 m x 3 000 m
  canal strip, which is narrower than one pixel and therefore all edge

#### Scenario: Complete data is never reported as parcial

- GIVEN a parcel entirely inside the raster extent with no nodata pixel under it
- WHEN the ficha is requested
- THEN `cobertura` is `total` and `cobertura_ratio` is exactly 1.0, for any parcel size and
  grid alignment
- AND it is NOT `parcial` — numerator and denominator are read off the same rasterization,
  so rasterization error cancels instead of masquerading as missing data

#### Scenario: Interior missing data is reported as parcial

- GIVEN a parcel fully inside the raster extent with an interior nodata hole over ~11% of it
- WHEN the ficha is requested
- THEN `cobertura` is `parcial` and `cobertura_ratio` is ≈ 0.89
- AND it is NOT reported as `total` — the edge inflation that used to pay for the hole is gone

#### Scenario: Low-confidence flag on sub-pixel parcel

- GIVEN a parcel smaller than the configured minimum pixel count for 30 m rasters
- WHEN the ficha is requested
- THEN each raster dataset reports its `pixel_count`
- AND `low_confidence` is `true` for those datasets

#### Scenario: Nodata pixels are excluded from percentages

- GIVEN a zone partially covered by raster nodata
- WHEN class percentages are computed
- THEN nodata pixels are skipped, not counted as a class
- AND `pct` is computed over valid pixels only, with `pixel_count` reflecting valid pixels

### Requirement: "No coverage" is distinct from zero

Each dataset MUST report a `cobertura` state of `total`, `parcial`, or `sin_cobertura`.
A zone fully outside a raster's extent MUST return `sin_cobertura` with an empty
breakdown — it MUST NOT return `0%` for every class and MUST NOT be silently omitted.

#### Scenario: Zone fully outside raster extent

- GIVEN a valid polygon entirely outside the flood-risk raster extent
- WHEN the ficha is requested
- THEN the response is HTTP 200
- AND `flood_risk.cobertura` is `sin_cobertura` with an empty breakdown and `pixel_count` 0

#### Scenario: Partial coverage flagged

- GIVEN a polygon straddling the raster edge
- WHEN the ficha is requested
- THEN `cobertura` is `parcial` and percentages are computed over the covered part only

### Requirement: Actionable failures for missing reference data

Missing prerequisite data MUST surface as an explicit, actionable error rather than
zeros. An empty `suelos_catastro` MUST return HTTP 503 with a message identifying the
unpopulated dataset. An unknown parcel MUST return HTTP 404.

#### Scenario: Empty suelos table

- GIVEN `suelos_catastro` has zero rows
- WHEN any ficha is requested
- THEN the response is HTTP 503 stating that the soils dataset is not loaded
- AND the response does NOT contain a `suelos` breakdown of zeros

#### Scenario: Parcel not found

- GIVEN nomenclatura `ZZZ` does not exist in `parcelas_catastro`
- WHEN `{tipo: "parcela", nomenclatura: "ZZZ"}` is submitted
- THEN the response is HTTP 404 identifying the unknown nomenclatura

#### Scenario: Parcel with null nro_cuenta

> **Delta (post-JD)**: this scenario moves to `ficha-frontend`. With the client-side BPA join the
> backend has no membership section to report on, so the backend obligation is only that the ficha
> still returns 200 with every geometric dataset computed. Rationale: design [R1].

- GIVEN a parcel whose `nro_cuenta` is NULL
- WHEN the ficha is requested
- THEN the response is HTTP 200 with all geometric datasets computed
- AND the response contains no BPA/forestación field at all

### Requirement: Caps are enforced on server-derived geometries

> **Delta (post-JD)** — new requirement (JD-A-002, JDB-006).

Schema validation only sees caller-supplied polygons. Three of the four `tipo` values resolve a
geometry the caller does not send (a catastro parcel, an `ST_Buffer` result, a precomputed
catchment). The service MUST therefore re-check every resolved geometry against the area, envelope
and vertex caps **after resolution and before the first raster open**, and MUST reject with HTTP 422
naming the exceeded cap and its limit. `canal_buffer` MUST additionally enforce a maximum
`buffer_m` (`ficha_max_buffer_m`), and MUST be priced at the same rate-limit cost as `poligono`.

#### Scenario: Oversized parcel rejected

- GIVEN a `parcelas_catastro` parcel larger than the configured maximum hectares
- WHEN `{tipo: "parcela", nomenclatura}` is submitted
- THEN the response is HTTP 422 naming the area cap
- AND no raster file is opened

#### Scenario: Buffer distance cap

- GIVEN `buffer_m` exceeds `ficha_max_buffer_m`
- WHEN `{tipo: "canal_buffer", …}` is submitted
- THEN the response is HTTP 422 naming the buffer cap and its limit

### Requirement: Explicit error contract

> **Delta (post-JD)** — new requirement (JD-A-006, JDB-007, JDB-008).

Every failure MUST return a stable machine-readable `codigo` alongside the human `detail`, per this
table, and each row MUST have an integration test:

| Status | `codigo` | Trigger |
|---|---|---|
| 404 | `parcela_no_encontrada` / `canal_no_encontrado` | unknown nomenclatura / canal id |
| 409 | `variante_no_disponible` | requested catchment variant absent (lists `variantes_disponibles`) |
| 413 | `cuerpo_excedido` | request body over the configured maximum, rejected before parsing |
| 422 | `tipo_desconocido` / `geometria_invalida` / `cap_excedido` | union violation / unrepairable geometry / any cap |
| 429 | `limite_de_tasa` | rate limiter exhausted (with `Retry-After`) |
| 503 | `dataset_no_cargado` / `raster_ilegible` / `sobrecarga` | prerequisite data missing / unreadable raster / in-flight limit reached |

Drawn polygons MUST be normalized with `ST_MakeValid` followed by `ST_CollectionExtract(…, 3)`
before any intersection or masking; a geometry that reduces to empty or non-polygonal MUST be
rejected with 422 `geometria_invalida` rather than silently producing wrong areas.

#### Scenario: Oversized body rejected before parsing

- GIVEN a request body larger than the configured maximum
- WHEN it is submitted
- THEN the response is HTTP 413 and the body is never parsed

#### Scenario: Self-intersecting drawn polygon

- GIVEN a hand-drawn bow-tie polygon that `ST_MakeValid` reduces to a non-polygonal geometry
- WHEN it is submitted as `tipo: "poligono"`
- THEN the response is HTTP 422 `geometria_invalida`
- AND no raster file is opened

### Requirement: Rate limiting is scoped to this endpoint only

> **Delta (post-JD)** — new requirement (JDB-003).

The ficha rate limiter MUST be attached to a dedicated router that contains only this endpoint. It
MUST NOT be attached to the shared analysis router, so existing authenticated geo endpoints are
never throttled by public ficha traffic. Because this route is public while its siblings are
operator-only, a test MUST assert that every other route under `/api/v2/geo` still carries an
operator dependency.

#### Scenario: Existing geo endpoints unaffected

- GIVEN the ficha limiter is exhausted for an IP
- WHEN that IP calls an authenticated geo endpoint such as `/geo/zonal-stats`
- THEN the request is not rate limited by the ficha limiter

#### Scenario: No auth regression on sibling routes

- GIVEN the change is applied
- WHEN the route table is inspected
- THEN `analisis-zona` is the only `/api/v2/geo` route without an operator dependency

### Requirement: Raster reads use the nodata-correct primitive

All raster statistics MUST be derived from the composites zonal primitive that reads
nodata from the raster itself. The `nodata=-32768` path MUST NOT be used for
`flood_risk`, `drainage_need` or precipitation rasters (their nodata is `-9999.0`).

#### Scenario: Composite nodata honored

- GIVEN a flood-risk raster with nodata `-9999.0`
- WHEN statistics are computed for a zone containing nodata pixels
- THEN no `-9999.0` value appears in any class bin or in the mean

## Reconciliation note: orphaned `Afectados*` schemas

Verified during this phase: `ParcelaImportResult`, `AfectadoItem`, `AfectadosResponse`
and `EventoAfectadosResponse` (`gee-backend/app/domains/geo/schemas.py:316-346`) have NO
implementing router anywhere under `gee-backend/app/`, and `consorcio-web/src` contains
no `/admin/afectados` route or page (the only `afectados` hit is an unrelated
`caminos_afectados` field in `types/index.ts:215`). `consorcio-web/tests/e2e/afectados.spec.ts`
therefore exercises a UI that does not exist.

Verdict: **dead code, no overlap to reconcile.** `Afectados*` is a per-zone roster of
named consorcistas (PII: `consorcista_id`, `nombre`) — the opposite of this change, which
publishes only aggregate percentages with no personal data. This change MUST NOT revive,
extend, or reuse those schemas, and MUST NOT introduce any `/afectados` route. Removing
the dead schemas and the stale e2e spec is a separate backlog ticket (fix-between-SDDs).

#### Scenario: No afectados surface introduced

- GIVEN this change is fully applied
- WHEN the OpenAPI schema is inspected
- THEN no path matching `/afectados` exists
- AND no ficha response field exposes `consorcista_id` or a person's name
