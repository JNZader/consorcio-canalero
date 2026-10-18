# Weld one tramo per road

Objective: one LineString per ruta when the pieces meet or their endpoints fall within 8 m; a real gap or a branch stays another part, ordered so the elevation cursor does not jump. Branch: `fix/weld-ordered-caminos`. Delivery: ask-on-risk. Tests: pytest in `gee-backend`.

## Specs

S1. "dale, hacé esa migración"

S2. "y si no anda hay que buscar otro enfoque"

S3. "pero tenemos que solucionar los saltos"

S4. "la idea era no usar los tramos sueltos que teniamos antes y crear un solo tramo por camino(siempre que se pueda obvio)"

Assumption, agreed before this implementation: snap tolerance is 8 m (`8.0/111320.0` degrees), pairwise and mutual, not a transitive cluster. Do not draw a straight segment across a real gap or through a branch. `red_vial` rows stay. Legend kilometres stay the padrón sum. `longitud_geodesica_km` becomes the welded geography length. The walk starts at the westernmost free end (minimum x, then minimum y) and then takes the nearest unused end, flipping the part when the far end is closer. The same walk lives in SQL (stored geometry) and in Python (request + cache key).

## Tasks

- T1 (S1, S4) inline — Alembic `0030_weld_order_caminos` replaces `mv_caminos_unificados`. PostGIS tests use their own schema. Status: done. `tests/new/test_caminos_soldados_migration.py` and `tests/new/test_caminos_unificados_migration.py` passed.
- T2 (S3) inline — `geometria_ordenada` runs before the profile cache key and the sampler. Two storage orders of the same parts share a cache key; a different trace does not. Status: done. `tests/unit/test_elevation_profile_order.py` and `tests/new/test_elevation_profile_cache.py` passed.

## Log

L1. dale, hacé esa migración...y si no anda hay que buscar otro enfoque....pero tenemos que solucionar los saltos....

L2. 2026-10-18. `./venv/bin/pytest tests/unit/test_elevation_profile_order.py tests/new/test_caminos_soldados_migration.py tests/new/test_caminos_unificados_migration.py tests/new/test_elevation_profile_cache.py --tb=short -q` → 34 passed. A 3 m gap and a chain of 3 m gaps become one LineString (chain length stays about 24 m, so the snap is not transitive). A gap of about 0.2 degrees stays two parts with the western part first even when the eastern part is stored first. Overlapping copies count once. Downgrade restores 0029's MultiLineString wrapper. Not applied on Hetzner. Not committed.
