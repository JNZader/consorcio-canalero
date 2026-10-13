# audit-v6-wave-d

Wave D from `auditoria-v6.pdf`: MAP-01/MAP-01b + BE-01. Stacked on `feat/map-ux-maplibre-6` (`541e33ce`).

## In

- [x] MAP-01: 2D soils PMTiles load as one ArrayBuffer (no HTTP Range). Register via existing `Protocol.add`. Source URL `pmtiles://<archiveKey>`, not `pmtiles://https://…`.
- [x] MAP-01b: keep 3D GeoJSON soil path unchanged.
- [x] Test: `soilPmtilesUrl` / source `url` is the in-memory key; fetch of `/data/suelos_cu.pmtiles` is a single GET.
- [x] BE-01: skip generic 100/60 only for exact public `/mapa` GETs (not `/geo/gee/layers`). Include `/geo/basins` and `/geo/basins/*`.
- [x] Cache-Control `public, max-age=300, stale-while-revalidate=60` on those skipped GET responses.
- [x] Query retry: never retry 429; 4xx < 500 false; else n < 3.

## Out

- Waterway pmtiles, R2/Caddy, ETag, MAP-02 dedupe, MAP-05, CODE-02, DB-04, CI-05, Terra Draw.
