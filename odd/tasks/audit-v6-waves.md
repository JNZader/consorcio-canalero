# audit-v6-waves

Campaign from `auditoria-v6.pdf` (12/10/2026, base `6f76b97`). One theme per PR. MapLibre 6 is a separate worktree; do not share `MapaMapLibre.tsx` with MAP-07 until the bump lands or MAP-07 merges first.

## Wave A (parallel, no MapLibre API)

- [ ] FE-01 — `/assets/*` 404 before SPA fallback + `vite:preloadError` (same reload guard as chunk errors)
- [ ] UI-07 — finite `longitud_m` on landing; SQL `COALESCE` + `ST_Length` on public canales
- [ ] MAP-06 — drop CARTO Voyager watermark; Esri World Street Map raster (same host as satellite)

## Wave B (after A, or MAP-07 before MapLibre)

- [ ] MAP-07 — pass live `mapZoom` into every `LayerControlsPanel`
- [ ] MAP-13 — do not POST elevation-profile for anonymous visitors
- [ ] MapLibre 6 — pin ≥6.4.1, namespace imports, Vite `setWorkerUrl`, keep mapbox-gl-draw

## Wave C

- [ ] MAP-01 — PMTiles without Range (full buffer or R2)
- [ ] BE-01 — exact public GET allowlist + no 429 retry

## Out

CODE-02, UX-25, Terra Draw unless draw breaks on v6, skills/MCP install.
