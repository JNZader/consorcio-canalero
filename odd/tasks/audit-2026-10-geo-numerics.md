# audit-2026-10-geo-numerics

Three verified audit WARNINGs in `gee-backend/app/domains/geo/`, fixed with the smallest honest diffs plus RED-check regression tests. All three were numeric/integrity lies the system told operators: a wrong length, wrong stats, and a disk that silently fills until every tile 404s.

## In

- **GEO-2 — runoff `longitud_m` was the step count** (`intelligence/calculations_hydrology_support.py`): `len(coords)` (one vertex per D8 step, ~one 30 m GLO-30 cell) made a 150 km trace report `longitud_m=5000`. Now `round(line.length, 2)` — the LineString's own length in the flow-direction raster's CRS; the DEM pipeline reprojects to UTM before deriving flow directions, so the units are metres (stated in the field comment). `pasos` is now the genuine D8 move count (`len(coords) - 1`; the first vertex is the start, not a step).
- **GEO-3 — zonal stats hardcoded `nodata=-32768` for every raster** (`zonal_stats.py`): terrain_class is uint8/255 and composites have no nodata, so the 255 fill counted as a legitimate max on `/zonal-stats` endpoints. Now `src.nodata` is passed through; `-32768` survives ONLY as a documented fallback for float16/float32 rasters with no embedded tag (historical float terrain products whose fill was never declared). Undeclared non-float rasters mask nothing — exactly what a fill-free composite means.
- **GEO-5 — orphaned `*.tmp.tif` DEM downloads were never swept** (`processing_wbt_support.py` + `tasks.py`): `download_dem_impl` unlinks its temp only on the success path; a worker OOM/SIGKILL mid-download orphans a full-size temp DEM and repeated crashes exhaust the geo-worker disk. `sweep_stale_dem_tmp_impl` now runs at full-DEM-pipeline start inside `_area_execution_lock` (race-free by construction); staleness = mtime age ≥ 1 h — the download is bounded by the 300 s GEE fetch, so 1 h covers clock skew/restarts with a 12x margin and never touches a live download. Only the exact `*.tmp.tif` pattern this code creates is eligible. Wired in `tasks.py` (not `tasks_dem_support.py`, which a chain-scoped untouched-proof in `test_cruces_camino_no_regression.py` keeps byte-identical to `origin/feat/flujo-caminos-s1-red-vial`).
- RED-check tests: `tests/new/test_escorrentia_longitud.py` (old code: `6 == 166.07`), `tests/new/test_zonal_stats_nodata.py` (old code: `max == 255`), `tests/new/test_dem_tmp_sweep.py` (old code: no sweep existed → ImportError; plus lock-order wiring tests).

## Out of scope

- Fixing the two pre-existing failures in `test_cruces_camino_no_regression.py::TestUntouchedFileProofs` (`martin/` config and `repository_metrics.py` differ between the chain base ref and committed `origin/main` — unrelated to this work unit).
- Vertex placement of the runoff LineString (vertices land on grid corners, so the first segment is a half-cell; length is consistent with the returned geometry, which is what GEO-2 demands).
- Any FE/consumer change for `longitud_m`/`pasos` — operator-only endpoint, no FE consumer.
- Sweeping in the standalone `download_dem_from_gee_task` (not serialized by the area lock; its orphans are picked up by the next pipeline run's sweep).
- Alembic / persistence changes.
