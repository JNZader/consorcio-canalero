# map-ux-a11y-cart-leftovers

Grow PR #469 (`feat/map-ux-a11y-cart-leftovers`) to a real leftover pack. Do not pad. Do not open another PR.

## Already on the branch

- [x] CART-08 labels minzoom 10 vs MAP_DEFAULT_ZOOM 11
- [x] Canary: do not collapse Territorio when already open
- [x] mapLabelSize tests follow zoom 10 / 13px

## Remaining in this pack

- [x] CART-08 copy: user-facing "Red Vial" → "Red vial rural"; legend "Red vial rural del consorcio" (rural roads, not city plant)
- [x] CART-06: catastro + soils layer minzoom 12; panel hint "Acercate para ver esta capa" when map zoom < layer minzoom
- [x] PERF-02: lazy-load `PrecipChart` and `RainfallAccumulationChart` (Suspense) so `/mapa` does not pay @mantine/charts up front
- [ ] Tests + work-unit commit (writer spawn blocked; parent implements + commits)

## Constraints

- One theme: leftover public `/mapa` cartography + panel honesty + chart chunk.
- No vaul, no new map libs, no font binaries, no PERF-01 Lighthouse rewrite, no UX-07 accordion keepMounted, no API-01, no UX-25 denuncias layer.
- English artifacts. Do not invent cuenca centroids.
- Keep 75% mutation floor. No `--no-verify`.
