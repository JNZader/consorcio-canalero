# catchment-analysis Specification

## Purpose

`tipo=canal_cuenca`: derive the real drainage catchment contributing to a selected canal
using a D8 flow-direction raster and the WhiteboxTools `watershed` tool, then run the
standard ficha datasets over that catchment.

> **BLOCKED**: this capability MUST NOT be implemented until the backlog fix for the D8
> pointer bug (`intelligence/tasks.py:353` passes a DEM where `watershed` expects a D8
> pointer, via `calculations_hydrology_support.py:255`) has landed. The contract below is
> specified now so downstream phases can plan against it.

> **Delta (post-JD) — catchments are PRECOMPUTED, and the request path stays synchronous.**
> `canal_network` is a finite set whose geometry changes only when the topology is reloaded, so the
> watershed derivation runs **offline** as a batch step after each DEM pipeline run: for every canal
> × every available variant, the canal LINESTRING is rasterized onto that variant's `flow_dir` grid
> as int16 seed cells, `watershed(d8_pntr=flow_dir, pour_pts, output)` runs, and the polygonized
> result is stored in a `canal_catchment` table (`canal_id`, `variante`, `geometria`, `area_ha`,
> `oversized`, `flow_dir_layer_id`, `version`) with the raster registered as an artifact.
>
> At request time `tipo=canal_cuenca` is a lookup by `(canal_id, variante)` followed by the same
> synchronous zonal statistics as every other `tipo`. There is no Celery job and no poll envelope,
> so the uniform response schema this spec requires is preserved literally. Missing rows for the
> requested canal in *any* variant → HTTP 503 `dataset_no_cargado` (catchments not precomputed for
> this deployment).
>
> **The area cap is applied at precompute time**: an oversized catchment is stored with
> `oversized = true`, and the endpoint returns HTTP 422 naming the cap without opening a raster —
> which is exactly the "oversized catchment rejected" scenario below.
>
> **`JensenSnapPourPoints` is NOT used.** Jensen snapping relocates *point* pour locations to the
> nearest high-accumulation cell; applying it to an entire rasterized line trace collapses every
> seed cell onto one drainage cell and yields a plausible-but-wrong basin. The rasterized trace is
> the seed set, matching how the existing code already builds a pour-points raster
> (`calculations_hydrology_support.py:249-254`). Rationale: design §5 (JD-A-003, JD-A-015).

## Requirements

### Requirement: Watershed derived from a D8 pointer raster

The catchment MUST be computed by passing a **D8 flow-direction (`flow_dir`) raster** to
`watershed`, with the canal geometry supplying the pour points. Passing a DEM as the
pointer argument is prohibited; the existing miscall MUST NOT be copied.

#### Scenario: Catchment computed from flow_dir

- GIVEN a `flow_dir` raster and a selected canal
- WHEN `{tipo: "canal_cuenca", canal_id, variante}` is requested
- THEN the pour points are derived from the canal geometry
- AND the D8 pointer raster (not the DEM) is passed to `watershed`

#### Scenario: DEM passed as pointer is rejected

- GIVEN a caller/config supplies a DEM path where the pointer is expected
- WHEN the catchment routine validates its inputs
- THEN it raises an explicit input-type error rather than producing a plausible-but-wrong
  basin

### Requirement: Caller chooses the DEM variant

The request MUST carry `variante` ∈ `natural|relevado`. `relevado` uses the stream-burned
derivatives; `natural` uses the unburned ones. The response MUST echo which variant
produced the catchment. When the requested variant's derivatives do not exist, the
endpoint MUST return an explicit error naming the missing variant — it MUST NOT silently
fall back to the other one.

#### Scenario: Natural variant requested and available

- GIVEN `natural_flow_dir` derivatives exist for the area
- WHEN `variante: "natural"` is requested
- THEN the catchment is computed from the unburned derivatives
- AND the response reports `variante: "natural"`

#### Scenario: Requested variant missing

- GIVEN only burned (`relevado`) derivatives exist
- WHEN `variante: "natural"` is requested
- THEN the response is an explicit error stating the natural variant is unavailable
- AND no result is returned from the burned derivatives

### Requirement: Catchment feeds the standard ficha datasets

Once derived, the catchment polygon MUST be analysed by the same pipeline as every other
`tipo`, producing the identical response schema including `cobertura`, `pixel_count` and
`low_confidence`. The catchment area cap MUST be enforced after derivation: a catchment
exceeding the configured maximum hectares MUST be rejected before raster statistics run.

#### Scenario: Uniform response shape

- GIVEN a successfully derived catchment
- WHEN the ficha is produced
- THEN the response schema is byte-compatible with `tipo=parcela`
- AND `area_ha` is the catchment area in EPSG:32720

#### Scenario: Oversized catchment rejected

- GIVEN a canal whose derived catchment exceeds the configured area cap
- WHEN the request is processed
- THEN the response is HTTP 422 naming the exceeded cap
- AND no zonal statistics are computed over the catchment

#### Scenario: Degenerate catchment

- GIVEN pour points that yield an empty or single-pixel basin
- WHEN the ficha is produced
- THEN the response reports the tiny `pixel_count` with `low_confidence: true`
- AND it does NOT report percentages as if they were reliable
