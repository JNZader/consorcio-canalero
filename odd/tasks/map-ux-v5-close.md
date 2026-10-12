# map-ux-v5-close

Close remaining *implementable* v5 leftovers after #470. One PR onto `origin/main`.

## In

- [x] UX-07: stop remounting Accordion on search clear; controlled value; keepMounted display-none
- [x] API-01: public map GET layers/basins do not spend the 100/60 budget
- [x] PERF-04: OSM raster via CARTO (not tile.openstreetmap.org); full Esri World Imagery attribution
- [x] Tests locally before push (386 files pass; patchesApplied is worktree Stryker)
- [x] Canary 38290159991: scroll Territorio/checkbox into the Drawer before `visible`

## Out (not this PR)

- CODE-02 layer reconciler
- UX-25 public denuncias layer (product)
- PERF-01 Lighthouse 49 rewrite
- HAND publish pipeline (backend)
- Live km while measuring
