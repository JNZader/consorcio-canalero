# map-ux-soil-pmtiles

PERF-01 remainder: 2D soil fill uses bundled `suelos_cu.pmtiles` (349k) instead of fetching `suelos_cu.geojson` (2.2MB) when the layer is on.

## In

- [ ] `syncSoilLayers` vector source `pmtiles://…/data/suelos_cu.pmtiles`, source-layer `suelos_cu`
- [ ] Fill color from `cap` (same I–VIII palette); no `__color` client paint
- [ ] Legend lists I–VIII when soil is on (no FeatureCollection scan)
- [ ] `useSoilMap` on `/mapa` only for KMZ (`exportIntent`), same idea as catastro
- [ ] Tests for source type + legend

## Out

- Catastro 2D (already Martin)
- 3D soil (still GeoJSON + `__color`)
- Waterway pmtiles
- CODE-02, UX-25
