# ETL Canales — Pilar Azul

Extract-Transform-Load pipeline for **Canales Relevados y Propuestas** (Pilar Azul). Reads
two KMZ files exported by the infrastructure team, parses canal metadata embedded in
Placemark names, computes geodesic lengths with `pyproj`, and emits three static JSON/GeoJSON
files that the `consorcio-web` map layer consumes at runtime.

This ETL is **offline** — not wired to the FastAPI backend. The user re-runs it manually each
time a new KMZ version is dropped into `~/Descargas/`. Outputs are committed to the repo as
static assets under `consorcio-web/public/capas/canales/`.

## Module Structure

```
scripts/etl_canales/
├── __init__.py       # package marker
├── main.py           # orchestrator: unzip -> parse -> build -> write, exit codes 0..4
├── kmz.py            # stdlib zipfile + xml.etree extractor, RawPlacemark dataclass
├── parse_name.py     # strict-then-fallback name decoder, PRIORIDAD_CANONICAL
├── slugify.py        # NFKD accent stripping + slugify_with_suffix collision rule
├── longitud.py       # pyproj.Geod(WGS84) per-segment geodesic sum
└── writers.py        # CanalFeature/IndexMeta dataclasses, JSON writers
scripts/etl_canales.py  # CLI shim: `python scripts/etl_canales.py`
```

### Responsibilities

| Module | Responsibility |
|--------|----------------|
| `kmz.py` | Walk the KMZ's `doc.kml` folder tree, extract LineString/Polygon/Point Placemarks with their folder path + style_url. Stdlib only — no `pykml` dependency. |
| `parse_name.py` | Decode Placemark names with the strict pattern `{codigo} · {descripcion} · {N.NNN m} · {PRIORIDAD}`. Falls back to partial recovery when any segment is missing. Normalizes priorities to the canonical set (`Alta`, `Media-Alta`, `Media`, `Opcional`, `Largo plazo`). Handles Spanish thousands-separator (`1.355 m` -> `1355`). |
| `slugify.py` | Produce stable, URL-safe ids from canal names. NFKD normalization, accent stripping, `slugify_with_suffix(base, folder, idx)` for deterministic collision resolution. |
| `longitud.py` | `compute_longitud_m(coords)` -> geodesic distance in meters using `pyproj.Geod(ellps="WGS84")`, summed per segment. |
| `writers.py` | `write_geojson_canales(features, path)` emits FeatureCollection with schema_version 1.0. `write_index_json(relevados, propuestas, path)` emits the toggle-registry metadata file. `ETL_GENERATED_AT` env var overrides `generated_at` for deterministic testing. |
| `main.py` | Orchestrator — wires everything together, enforces the all-or-nothing write gate, resolves slug collisions per-folder, filters out Polygon placemarks, returns an exit code. |

## How to Run

From repo root:

```bash
# Ensure venv is active (pyproj lives in the backend venv)
source gee-backend/venv/bin/activate

# Run the ETL
python scripts/etl_canales.py
```

The entry point is the CLI shim `scripts/etl_canales.py`, which ensures the repo root is on
`sys.path` and delegates to `scripts.etl_canales.main:main()`.

### Environment / Prerequisites

- Python 3.11+
- `pyproj >= 3.7.0` (installed in `gee-backend/venv/` — no separate venv needed)
- No other third-party deps; the KMZ reader is stdlib-only (`zipfile`, `xml.etree.ElementTree`)

## Input Paths (hardcoded v1)

| KMZ | Absolute path |
|-----|---------------|
| Relevados | `/home/javier/Descargas/Canales_existentes_v3.kmz` |
| Propuestas | `/home/javier/Descargas/Propuestas_v3.kmz` |

These paths are **hardcoded constants** in `main.py` (v1 scope — user-locked per proposal
`sdd/canales-relevados-y-propuestas/proposal`). When the user uploads a new KMZ version,
overwrite the file at the same path and re-run the ETL. Extracting paths to a config / env
is tracked under **Backlog** below.

## Output Paths

Always written to `<repo-root>/consorcio-web/public/capas/canales/`:

| File | Size (typical) | Purpose |
|------|----------------|---------|
| `relevados.geojson` | ~22 KB | FeatureCollection of 23 existing canals (LineString) |
| `propuestas.geojson` | ~14 KB | FeatureCollection of 20 proposed canals (LineString, dashed in UI) |
| `index.json` | ~11 KB | Schema-versioned metadata for the layer control dynamic-registration hook |

Writes are **all-or-nothing**: if any input is missing or the parse-failure gate trips, NO
files are written (the existing ones stay untouched).

## Exit Codes

| Code | Constant | Meaning |
|------|----------|---------|
| `0` | `EXIT_OK` | Three files written successfully |
| `1` | `EXIT_DATA_QUALITY` | Reserved — future zero-feature gates |
| `2` | `EXIT_PARSE_FAILED` | More than 10% of placemarks with structured intent (name contains `·`) failed to recover any metadata — abort without writing |
| `3` | `EXIT_INPUT_MISSING` | One or both hardcoded KMZ paths do not exist on disk |
| `4` | `EXIT_UNEXPECTED` | Uncaught exception during parse or write |

A non-zero exit leaves the output directory untouched.

## Re-Run Cadence

Re-run the ETL **every time the infrastructure team ships a new KMZ version**. Typical flow:

1. Drop the new KMZs at `~/Descargas/Canales_existentes_v3.kmz` and `~/Descargas/Propuestas_v3.kmz`
   (or update the constants in `main.py` if the filenames change).
2. `source gee-backend/venv/bin/activate && python scripts/etl_canales.py`
3. `git diff consorcio-web/public/capas/canales/` — visual review.
4. Commit the regenerated files (they're part of the web bundle).

The pipeline is deterministic: identical inputs + `ETL_GENERATED_AT` env override = byte-identical outputs.

## Name Parsing Rules

The Placemark names follow the **strict pattern**:

```
{codigo} · {descripcion} · {N.NNN m} · {PRIORIDAD}
```

Example: `S5 · Desagüe Sur · 1.355 m · MEDIA-ALTA`

When the strict pattern matches, all four fields are populated in the resulting `ParsedName`.
When it doesn't match (partial metadata, malformed separator, informational label), the
**fallback path** runs — each chunk is classified heuristically (codigo-like tokens, meter
expressions, priority words) and whatever is recognized is recovered.

### Priority Normalization

Input priorities are case-insensitive and accent-agnostic. Canonical values:

| Canonical | Accepted inputs |
|-----------|-----------------|
| `Alta` | `alta`, `ALTA`, `Alta` |
| `Media-Alta` | `media-alta`, `media alta`, `MEDIA-ALTA` |
| `Media` | `media`, `MEDIA` |
| `Opcional` | `opcional`, `OPCIONAL`, `opc` (if present) |
| `Largo plazo` | `largo plazo`, `LARGO PLAZO`, `largo-plazo` |

Anything outside this set is stored as `None` with an INFO log.

### Featured Star

A leading `★` (U+2605) in the name marks the canal as `featured=true` (UI highlights it).
The star is stripped before name parsing.

### Parse-Failure Threshold

A placemark counts toward the **parse-failure** metric **only** if:

1. Its name contains a `·` separator (author intent to pack metadata), AND
2. The parser recovered NOTHING (codigo, longitud_declarada_m, and prioridad all `None`).

Informational labels like `Canal NE (sin intervención)` are **not failures** — they're
legitimate relevado entries with no structured metadata.

If more than 10% of linestring placemarks trip that rule, the ETL aborts with exit 2.

## Slug Collision Resolution

Multiple canals can share the same base slug (e.g. `canal-ne-sin-intervencion` appears in 7
distinct folders). Collision rule:

1. First occurrence keeps the base slug.
2. Each subsequent occurrence gets a deterministic suffix: `-{folder-slug}-{idx}` where `idx`
   is a per-base-slug 0-indexed counter that follows KML document order.

This keeps ids stable across re-runs as long as the KMZ folder tree order is stable.

## Test Command

From the `scripts/` directory:

```bash
cd scripts && source ../gee-backend/venv/bin/activate && python -m pytest tests/canales/
```

Expected: **75 passed** in ~0.2 seconds. The suite covers:

- `test_parse_name.py` (29) — strict pattern, normalization, fallback, featured, edge cases
- `test_slugify.py` (16) — basic + collision rule
- `test_longitud.py` (7) — multi-segment + degenerate + cross-check against `pyproj.Geod.inv`
- `test_kmz.py` (10) — LineString/Polygon extraction, folder walking, missing styleUrl
- `test_writers.py` (6) — FeatureCollection shape, schema_version, timestamp override
- `test_main_orchestrator.py` (7) — happy path, input missing, parse threshold, polygon skip

Fixtures are under `scripts/tests/canales/fixtures/` as both `.kml` source + pre-built `.kmz`.

## Backlog / Futuras Mejoras

Out of scope for v1; revisit when painful:

- **KMZ auto-discovery** — glob `/home/javier/Descargas/*_v*.kmz`, pick the highest version. Removes the manual filename update when a v4 arrives.
- **Config-driven input paths** — read from `.env` or `openspec/config.yaml`. Required if this ETL ever ships to CI.
- **Shapely integration** — currently only `pyproj.Geod` is used for length. If polygon support comes back (currently the lone polygon `Las Tres del Norte` is dropped), `shapely` would clean up centroid/area math.
- **Parse-failure CSV log** — emit a per-placemark reason-for-failure CSV alongside the geojsons when the threshold is approached (below 10% but above 5%). Helps the infra team fix names.
- **`longitud_declarada_m` vs `longitud_m` agreement check** — spec allows 0.1%; real data currently agrees within ~1m. A hard-fail gate at 1% disagreement is an option.
- **Backend endpoint wrapper** — if other frontends need the same data, wrap the ETL behind a `/api/v2/public/capas/canales/*` route that serves the same files.
