# audit-v6-wave-e

Wave E: MAP-05 2D hillshade visible on pampa. Stacked on `feat/audit-v6-wave-d` (#485).

## In

- [x] 2D hillshade paint: exaggeration 1, method `multidirectional`, stronger shadow/highlight.
- [x] 2D tile URL `z_factor=15` (not 3D terrain-rgb).
- [x] Tile service + public proxy forward `z_factor`; cache key includes it only when set.
- [x] Panel note when Relieve sombreado is on: exagerado para terreno llano.

## Out

3D mesh z_factor, precomputed gdaldem raster, CODE-02, MAP-08.
