"""ETL — Canales Relevados y Propuestas (Pilar Azul).

Unzips two KMZ files containing per-canal LineString Placemarks (relevados +
propuestas), parses the metadata that lives inside each ``<name>`` string
(codigo, longitud declarada, prioridad, ★ featured flag), computes the true
geodesic longitud from each geometry via ``pyproj.Geod(ellps='WGS84')``,
generates a deterministic slug per canal (with folder-based collision
resolution), and emits three static assets consumed by the React frontend:

- ``public/capas/canales/relevados.geojson``
- ``public/capas/canales/propuestas.geojson``
- ``public/capas/canales/index.json``

Run entry point: ``python scripts/etl_canales.py`` (which imports and calls
``scripts.etl_canales.main.main``).
"""

__all__: list[str] = []
