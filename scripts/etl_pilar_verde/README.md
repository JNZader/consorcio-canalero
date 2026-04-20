# ETL — Pilar Verde (BPA + Plan Provincial Agroforestal)

Python ETL que construye los **9 activos estáticos** del subsistema "Pilar Verde" a partir de IDECor WFS (Gobierno de Córdoba) y del KML de la zona CC 10 de Mayo AMPLIADA. Salida: 6 GeoJSON en `consorcio-web/public/capas/pilar-verde/` y 3 JSON planos en `consorcio-web/public/data/pilar-verde/`.

Todos los outputs viajan en el bundle del frontend — **no hay backend Pilar Verde** (static-first, matching el patrón de `catastro_rural_cu.geojson` / memoria #733).

---

## Estructura del paquete

```
scripts/
├── etl_pilar_verde.py          # entrypoint — invoca main.main()
└── etl_pilar_verde/
    ├── __init__.py
    ├── constants.py            # BPA_LAYERS (2019-2025), AGRO_*, FORESTACION, OUTPUT_FILES, EXIT_*, CRS, tolerancias
    ├── kml.py                  # kml_to_geojson() — xml.etree parser (sin fiona)
    ├── wfs.py                  # fetch_layer() — tenacity-free retry loop 2s/4s (3 intentos)
    ├── clip.py                 # clip_to_zona() — shapely.intersection preservando properties
    ├── join.py                 # normalize_cuenta(), join_bpa(), build_bpa_history()
    ├── aggregates.py           # compute_ley_forestal, compute_bpa_kpis, ranking, ejes, zonas_agro, grilla
    ├── writers.py              # simplify_features, thin_properties, write_geojson, write_json
    └── main.py                 # run_etl() orquestador + argparse + exit codes
```

Tests: `scripts/tests/` (71 casos, `pytest.ini` local, conftest para resolver `scripts.*` imports).

---

## Cómo correrlo

Desde la raíz del repo:

```bash
source gee-backend/venv/bin/activate        # reutiliza el venv del backend
python scripts/etl_pilar_verde.py           # run completo
python scripts/etl_pilar_verde.py --help    # lista flags
```

### Flags

| Flag | Efecto |
|------|--------|
| `--skip-historical-bpa` | No baja BPA 2019-2024. `bpa_history.json` queda con `history: {}`. |
| `--skip-zonas-agroforestales` | No baja `idecor:agricultura_agro_zonas`. `agro_zonas.geojson` queda vacío. |
| `--skip-forestacion` | No baja `idecor:agricultura_agro_porcentaje_forestacion`. Archivo vacío. |
| `-v` / `--verbose` | Log level DEBUG. |

Flags útiles para builds rápidos contra IDECor lento: `--skip-historical-bpa --skip-zonas-agroforestales`.

### Variables de entorno

Ninguna es obligatoria. Opcional:

| Var | Uso |
|-----|-----|
| `ETL_GENERATED_AT` | ISO-8601 UTC. Override del campo `generated_at` en todos los outputs. Necesario si querés builds **byte-identical** (idempotencia estricta) en CI. Si no se setea, cada corrida estampa `datetime.now(UTC)` y los outputs difieren byte-a-byte aunque el contenido de IDECor no haya cambiado. |

---

## Outputs (9 archivos)

Ruta base del frontend: `consorcio-web/public/`.

### GeoJSON (`capas/pilar-verde/`)

| Archivo | Layer IDECor (o fuente) | Notas |
|---------|-------------------------|-------|
| `zona_ampliada.geojson` | KML `gee/zona_cc_ampliada/CC 10 de mayo ampliado2.kml` | Polygon único (~642 vértices, ~88.307 ha). |
| `bpa_2025.geojson` | `idecor:bpa_2025` | Clip a zona. Sin simplificación. |
| `agro_aceptada.geojson` | `idecor:agricultura_v_agro_aceptada_cuentas` | Clip. |
| `agro_presentada.geojson` | `idecor:agricultura_v_agro_presentada_cuentas` | Clip. |
| `agro_zonas.geojson` | `idecor:agricultura_agro_zonas` | `shapely.simplify(tolerance=0.0001)` (~11 m). |
| `porcentaje_forestacion.geojson` | `idecor:agricultura_agro_porcentaje_forestacion` | Thinned a `{nro_cuenta, forest_obligatoria}`. |

### JSON planos (`data/pilar-verde/`)

| Archivo | Contenido |
|---------|-----------|
| `bpa_enriched.json` | JOIN catastro × bpa_2025 × aceptada × presentada (por `nro_cuenta`). Un objeto por parcela del catastro; `bpa_2025: null` si no hay match. |
| `bpa_history.json` | `{ "history": { "<nro_cuenta>": { "<year>": "<n_explotacion>" } } }`. **No incluye 2025** (ese dato vive en `bpa_enriched.json`). |
| `aggregates.json` | KPIs pre-computados para `PilarVerdeWidget` y sesiones AI: `zona`, `ley_forestal` (two-track), `bpa` (cobertura + top práctica ± adoptada + ranking + ejes), `grilla_aggregates`, `zonas_agroforestales`. |

**Todos los outputs** traen `schema_version: "1.0"` + `generated_at: <ISO-8601 UTC>` al top-level (los GeoJSON lo exponen bajo la key `metadata`).

---

## Exit codes

| Code | Significado | Acción sugerida |
|------|-------------|-----------------|
| `0` | OK — los 9 outputs quedaron escritos. | Commitear los 9 archivos como assets estáticos. |
| `1` | `EXIT_REQUIRED_LAYER_EMPTY` — alguna layer REQUERIDA (`bpa_2025` / `agro_aceptada` / `agro_presentada`) devolvió 0 features dentro de la zona. **No se escribió ningún archivo** (all-or-nothing). | Verificar en IDECor que la layer existe y tiene features. Puede indicar drift de naming (ver sección siguiente). |
| `2` | `EXIT_IDECOR_UNREACHABLE` — IDECor no respondió después de 3 intentos con backoff 2s/4s, **probando ambos hosts (`gn-idecor` + `idecor-ws`) dentro de cada intento**. | Reintentar más tarde. IDECor tiene downtime real en horario pico (verificado 2026-04-20 con `idecor-ws` caído; `gn-idecor` ya es primary). |
| `3` | `EXIT_KML_PARSE_FAILURE` — el KML de zona existe pero es inválido. | Revisar `gee/zona_cc_ampliada/CC 10 de mayo ampliado2.kml`. |
| `4` | `EXIT_ZONA_MISSING` — el KML o el catastro source file no existen. | Confirmar que el repo está completo (los dos archivos son tracked en git). |

## Drift de naming en BPA (IDECor)

IDECor publica BPA con **tres formas de naming distintas** según el año. Esto está encapsulado en `BPA_LAYERS` (en `constants.py`) y es la **fuente de verdad** — no hardcodear años en f-strings.

| Año | Nombre IDECor | Forma |
|-----|---------------|-------|
| 2025 | `idecor:bpa_2025` | `bpa_YYYY` |
| 2024 | `idecor:bpa_2024` | `bpa_YYYY` |
| 2023 | `idecor:bpa_2023` | `bpa_YYYY` |
| 2022 | `idecor:bpa_2022_v` | `bpa_YYYY_v` |
| 2021 | `idecor:bpa_2021_v` | `bpa_YYYY_v` |
| 2020 | `idecor:bpa2020` | `bpaYYYY` |
| 2019 | `idecor:bpa2019` | `bpaYYYY` |

Si IDECor introduce una nueva inconsistencia en el vintage 2026, se agrega la entrada acá y se re-corre el ETL.

## BPA 2025: 21 prácticas verificadas

El layer `idecor:bpa_2025` publica **21 prácticas** (no 22 — la prosa del spec dice "22" pero el listado enumerado termina en `riego_precision`). El código usa 21 en todos lados (`BPA_PRACTICAS` tuple en `constants.py`). La inconsistencia del spec se corrige al archivar el change.

4 ejes: `persona`, `planeta`, `prosperidad`, `alianza`. IDECor **no publica** un mapping canónico eje→práctica, por lo que InfoPanel renderiza las 21 prácticas en lista plana (no agrupadas por eje).

---

## Cadencia de re-ejecución

**Anual**, cuando IDECor publica el nuevo vintage de BPA — típicamente Q1 (enero-marzo). El ETL no corre en CI: se lanza manualmente, se inspeccionan los 9 outputs, y se commitea el delta en una PR dedicada.

Si IDECor introduce una layer nueva (ej. `bpa_2026`), actualizar `BPA_LAYERS` en `constants.py` antes de correr.

## Testing

```bash
cd scripts
source ../gee-backend/venv/bin/activate
python -m pytest                  # 71 tests, ~0.5s
python -m pytest -v               # verbose
python -m pytest tests/test_join_bpa.py    # un archivo
```

Tests cubren:
- `normalize_cuenta` (10 casos — None, whitespace, float, int, "None" sentinel)
- `kml_to_geojson` (7 — real KML ampliada, tiny fixture)
- `fetch_layer` retry (5 — 503 transitorio, timeout, backoff determinístico) + dual-host fallback (9 — primary success, primary 504 → fallback 200, both-fail budget, exhaustion, host catalog)
- `clip_to_zona` (6)
- `join_bpa` (12 — no-match → null, aceptada wins, overlap, keys con whitespace)
- `compute_ley_forestal` (6 — two-track, zero-division WARN)
- `compute_aggregates` (19 — ranking, ejes dist, zonas intersect, grilla)
- `required_layer_empty` (6 — integration: happy path + 3 exit-1 + exit-4 + schema_version)

---

## Estilo de logs

Structured `logging` stdlib (no structlog). Una línea por fetch con `{layer, features_count, elapsed_ms}`. Final del run imprime a stdout un resumen tipo:

```
=== Pilar Verde ETL summary ===
  zona_ampliada                99.7 KB  consorcio-web/public/capas/pilar-verde/zona_ampliada.geojson
  bpa_2025                    186.4 KB  …
  …
wall_time: 47.3s schema_version: 1.0
```
