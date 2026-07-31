# precip-normals-pipeline Specification

## Purpose

Generate CHIRPS monthly precipitation normals for the consorcio zone as rasters, so the
ficha reads precipitation through the same zonal-stats path as flood risk and drainage
need — no second implementation, no per-request GEE call.

## Requirements

### Requirement: Twelve monthly normals plus an annual raster

The pipeline MUST produce 12 monthly normal rasters (January-December) plus 1 annual
total raster, clipped to the consorcio extent, from CHIRPS via the existing GEE service
pattern. Pixel values are mean millimetres for that month across the normals period.

#### Scenario: Full set generated

- GIVEN valid GEE credentials and a configured consorcio extent
- WHEN the normals export runs
- THEN 13 rasters exist on disk (12 monthly + 1 annual)
- AND each covers the full consorcio extent

#### Scenario: Missing credentials fail loudly

- GIVEN GEE credentials are absent or invalid
- WHEN the export runs
- THEN it fails with an explicit credentials error
- AND no partial raster is registered as a layer

### Requirement: Registration as geo_layers

Each generated raster MUST be registered as a `geo_layers` row via the existing raster
registration path, with a layer type identifying it as a precipitation normal and a month
index. `metadata_extra` MUST record the CHIRPS normals period and a generation version so
regenerations are distinguishable.

> **Delta (post-JD)** — concrete registration and lookup contract (JD-A-008, JDB-011, JDB-018):
> all 13 rasters share `tipo = precip_normal`; `metadata_extra` is
> `{"mes": 1..12 | "anual", "normal_period": "1991-2020", "fuente": "CHIRPS", "version": <UTC
> ISO8601 of the export run>, "resolucion_m": 5000}`. Rasters MUST be warped to EPSG:32720 at
> **5 000 m** with nearest-neighbour resampling — CHIRPS native resolution is 0.05° (~5.5 km) and
> upsampling to the 30 m composite grid would fabricate detail the ficha then reports as measured.
> Nodata MUST be `-9999.0` to match the composites convention.
>
> The ficha MUST resolve inputs by selecting `tipo = precip_normal AND area_id = :area`, grouping by
> `metadata_extra->>'mes'` and taking the newest `version` **within each month**. The geo domain's
> usual "most recent layer of tipo X" idiom returns a single row and MUST NOT be used here — it
> would return the same raster for all twelve months.

#### Scenario: Layers discoverable by the ficha

- GIVEN the export completed and registered its layers
- WHEN the ficha service resolves precipitation inputs
- THEN it finds 12 monthly layers ordered by month index

#### Scenario: Regeneration versions the metadata

- GIVEN normals were generated previously
- WHEN they are regenerated
- THEN `metadata_extra` carries a new version identifier and the normals period

### Requirement: Read through the shared zonal-stats path

Precipitation values for a zone MUST be computed by the same composites zonal primitive
used for the other rasters, honouring the raster's own nodata value. No bespoke
precipitation statistics code path is permitted.

#### Scenario: Monthly series for a zone

> **Delta (post-JD)**: the monthly values are returned as a typed `serie` of `{mes, mm}` plus
> `anual_mm`, NOT as `{clase, ha, pct}` rows — see the delta on `geo-analysis-endpoint`
> "Uniform ficha response schema". `low_confidence` for this dataset is not driven by the pixel
> ratio (the field is a smooth interpolated normal). Rationale: design §1.3, §4.

- GIVEN registered monthly normals and a valid zone geometry
- WHEN the ficha is requested
- THEN the response contains 12 monthly mm values in calendar order

#### Scenario: Zone outside precipitation coverage

- GIVEN a zone entirely outside the normals extent
- WHEN the ficha is requested
- THEN `precipitacion_mensual.cobertura` is `sin_cobertura` with no fabricated zeros

### Requirement: Documented refresh cadence

The normals are static reference data. The pipeline MUST be runnable on demand and its
cadence MUST be documented (regenerate only when the CHIRPS normals period changes or the
extent changes). No scheduled job is required.

#### Scenario: On-demand regeneration documented

- GIVEN an operator needs to extend the normals period
- WHEN they consult the pipeline documentation
- THEN the manual regeneration command and its expected outputs are stated
