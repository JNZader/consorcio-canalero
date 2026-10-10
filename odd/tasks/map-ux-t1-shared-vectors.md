# map-ux-t1-shared-vectors

UX PDF T1 remainder, slice 1 of 2. Branch `feat/map-t1-shared-vectors` → `main`.

## Tasks

- [x] T1b-1: 3D vector visibility reads/writes `map2d.visibleVectors` (canonical). Raster types stay split.
- [x] T1b-2: 3D panel lists 2D-only layers disabled with tooltip `no disponible en 3D`. Drop “se mantienen por separado”.
- [x] T1b-3: Tests + work-unit commit. Not in this slice: mount `LayerControlsPanel` in 3D (T1c), exaggeration presets (T2), daltonismo.

Evidence: `b37278d1`. Vitest 25 passed (unsupported panel + canales/PV 3D sync + default visibility).

Canonical defaults: 2D `visibleVectors` (primary map). Catastro may appear in 3D if 2D had it on.
