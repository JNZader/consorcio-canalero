# ETL — Escuelas Rurales

Static pipeline that turns `Escuelas_rurales_CC10mayo.kmz` into a PII-free
GeoJSON consumed by the 2D map layer in `consorcio-web`.

## Purpose

- **Input**: one KMZ with 7 Point placemarks authored in Google Earth Pro.
  The CDATA description inside each placemark carries a mix of operational
  metadata (Localidad, Ámbito, Nivel) and personally-identifiable data
  (Directivo, Teléfono, Email) alongside bureaucratic codes (CUE,
  Departamento, Sector).
- **Output**:
  - `consorcio-web/public/capas/escuelas/escuelas_rurales.geojson` —
    FeatureCollection with **exactly 4 property keys per feature**. No PII,
    by construction (see PII Policy below).
- Zero backend. Zero per-run HTTP. Zero DB migration. The geojson is a
  committed artefact — the ETL is only invoked when the source KMZ
  changes.

> **Frontend rendering note.** The 7 school points are rendered on the
> map as a native MapLibre `circle` layer (plus a companion text-only
> `symbol` layer for the label). No icon asset is required. The
> `export_icon.py` script and the `escuela-icon.png` asset that previous
> iterations produced were removed — see
> `consorcio-web/src/components/map2d/escuelasLayers.ts` for the current
> rendering contract.

## Re-run instructions

### 0) Pick the Python interpreter

Any `python>=3.11` works. The project's existing venv at `gee-backend/venv/`
is fine:

```bash
export PY="$PWD/gee-backend/venv/bin/python"
```

(all commands below assume you are in the repo root —
`/home/javier/programacion/consorcio-canalero`).

### 1) Regenerate the GeoJSON

```bash
ETL_GENERATED_AT=2026-04-21T00:00:00Z \
  $PY -c "
from pathlib import Path
from scripts.etl_escuelas.build import build_geojson, serialize_feature_collection
fc = build_geojson('/home/javier/Descargas/vault_1/vault/kmz/Escuelas_rurales_CC10mayo.kmz')
serialize_feature_collection(fc, Path('consorcio-web/public/capas/escuelas/escuelas_rurales.geojson'))
print('features:', len(fc['features']))
"
```

Pinning `ETL_GENERATED_AT` is required for **byte-idempotent** re-runs (git
shows no diff when the KMZ is unchanged). Use the same timestamp the
previous commit used if you are not refreshing the data.

Commit the resulting `.geojson`.

### 2) Run the tests

```bash
$PY -m pytest scripts/etl_escuelas/tests/ -v
```

All 40 tests must pass (11 parse, 13 slug, 16 build) with zero regressions
against the 86 canales tests under `scripts/tests/canales/`.

## PII Policy

The KMZ CDATA contains **9** labelled fields per placemark. The public
static asset is allowed to expose **exactly 4 of them**, and no others.

### The 4-key public schema

Every feature's `properties` object has **exactly** these keys, in this
order, for every feature:

```json
{
  "nombre":    "string (the <name> element verbatim)",
  "localidad": "string (labelled 'Localidad' in CDATA)",
  "ambito":    "string ('Rural Aglomerado' | 'Rural Disperso')",
  "nivel":     "string (e.g. 'Inicial · Primario')"
}
```

Plus one top-level `id` (the deterministic slug — e.g.
`esc-joaquin-victor-gonzalez`) and the `geometry` with `[lon, lat]`.

### The 6 dropped fields (and why)

| Label         | Why dropped                                                              |
|---------------|--------------------------------------------------------------------------|
| `CUE`         | Bureaucratic identifier — not needed by the map viewer, leaks the school's Argentine education registry code. |
| `Departamento`| Redundant with `Localidad`; adds noise without value.                    |
| `Sector`      | "Estatal"/"Privado" — out of scope for v1; can be inferred by consumers. |
| `Directivo`   | **PII** — the principal's full name. Hard no.                            |
| `Teléfono`    | **PII** — personal/school phone number. Hard no.                         |
| `Email`       | **PII** — personal/institutional email. Hard no.                         |

### How the policy is enforced (defence in depth)

1. **Parser whitelist** — `parse_description` matches **only** the three
   allowed labels via a single compiled regex
   (`<b>\s*(Localidad|[ÁA]mbito|Nivel)\s*:\s*</b>...`). Any other label
   (including labels added to the KMZ in the future) is invisible to the
   parser.
2. **Writer whitelist** — `build.py::_build_properties` composes a dict
   from exactly `("nombre", "localidad", "ambito", "nivel")`. Any stray
   key the parser might return is dropped before the feature reaches
   disk.
3. **Test gate** — `scripts/etl_escuelas/tests/test_parse.py` and
   `test_build.py` include assertions that PII substrings (`cue`,
   `teléfono`, `email`, `directivo`, `sector`, `departamento`) NEVER
   appear in parser outputs or build outputs.
4. **Verify gate** — Phase 6 of the SDD change runs
   `rg -iE 'cue|tel[eé]fono|email|directivo|sector|departamento' consorcio-web/public/capas/escuelas/escuelas_rurales.geojson`
   — must return 0 matches. Runs locally before push.

If a future KMZ author renames a label or adds a new one, the parser
silently drops it. Adding a new approved field requires an explicit code
change AND a new spec REQ — the default posture is closed.

## Reproducibility notes

- **Deterministic ids**: each feature's `id` is `slug(nombre)` with a
  `-2`, `-3`, … collision counter in KML document order. Two runs over
  the same KMZ produce byte-identical ids.
- **Deterministic JSON**: `serialize_feature_collection` uses
  `ensure_ascii=False`, `separators=(",", ":")`, and a trailing newline
  — byte-stable across Python versions.
- **Pinnable timestamp**: `metadata.generated_at` honours
  `ETL_GENERATED_AT`. Leave it pinned across re-runs of the same KMZ so
  the geojson diff stays empty.
- **Tests for the KMZ extractor**: we REUSE
  `scripts.etl_canales.kmz.extract_placemarks` unchanged. Do not fork it.

## Source-of-truth trail

- Engram design: `sdd/escuelas-rurales/design` (#2059)
- Engram tasks: `sdd/escuelas-rurales/tasks` (#2060)
- Engram apply progress: `sdd/escuelas-rurales/apply-progress` (latest)
