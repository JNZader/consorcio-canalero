# audit-2026-10-zona-boundary

Fix audit finding **C4** (CRITICAL, adversarially confirmed): the red consorcio
boundary (`/geo/gee/layers/zona`) never rendered on `/admin/images`, and GEE
rasters lost their `beforeId` z-order slot under the boundary line.

Root cause: commit `84c0a9c4` (2026-10-14) moved `new maplibregl.Map()` behind
`await bootMapLibreWorker()` inside an async IIFE, so `mapInstanceRef.current`
is assigned only in a later microtask. The zona effect (deps `[]`) ran
synchronously in the same passive-effects flush, read the ref as `null`,
early-returned, and nothing ever re-ran it — no state/timeout retrigger,
cleanup nulls the ref, and re-running init on config change does not re-run a
`[]`-deps effect.

## In

- [x] Moved the zona fetch/add INTO the map-init IIFE (`useImageExplorerMap.tsx`),
      after map creation and BEFORE the pending-raster block, mirroring the
      `pendingTileUrlRef` wiring. Zona add keeps the old `isStyleLoaded()` /
      `once('load')` gate; fetch keeps its `AbortController` + `logger.warn`
      failure path; a stale-application guard (`cancelled || live !== map`)
      mirrors the pending-idle handler. In-code comment references the
      84c0a9c4 regression.
- [x] Cleanup (init effect): aborts the zona fetch, drops a still-pending
      `once('load', fetchZona)` listener, and nulls `zonaLayerIdRef` so
      `applyGeeRaster`/`updateWaterMask` never pass a `beforeId` that no
      longer exists on the next map instance (MapLibre throws on that).
      Explicit layer/source removal is unnecessary — `map.remove()` destroys
      them — noted in a comment.
- [x] Deleted the dead zona effect (its whole body was unreachable work).
      `fitZona` untouched: it uses static `ZONA_FIT_BOUNDS`, no zona-data
      dependency, so no refit change was needed.
- [x] Regression tests `tests/hooks/useImageExplorerMapZona.test.tsx` (new
      harness mirroring the tiles harness, with `apiFetch` RESOLVING for
      `/geo/gee/layers/zona`): (1) zona source+line appear after map creation,
      (2) a subsequent `updateTileLayer` inserts `gee-image-layer` with
      `beforeId: 'zona-boundary-line'`. Red-checked: both failed on the
      pre-fix code (`2 failed`), both pass after.
- [x] Updated one stale comment in `useImageExplorerMapTiles.test.tsx` that
      pointed at the zona "effect" (now the init IIFE).
- [x] Biome formatter fix on `useImageExplorerMap.tsx` line 47 (trailing
      comma) — pre-existing failure at HEAD, confirmed via stash, mechanical
      `biome check --write` output.

## Out

- No new maplibre-boot harness built: `tests/hooks/useImageExplorerMapTiles.test.tsx`
  already provides a full maplibre-gl mock harness (`bootMapLibreWorker`
  short-circuits in MODE `test`); the new test file reuses that pattern.
- `tileLayerIdRef` remains write-only (dead state) — pre-existing, out of
  scope for a regression fix.
- No parallelization of the zona fetch with worker boot (latency optimization,
  not the regression); fetch keeps the old timing (after style load).
- No e2e additions; no behavior change outside the explorer map.

## Validation

`npm run typecheck` (tsc + tsconfig.tests) clean; `npx biome check` on touched
files clean (note: `tests/**/*.tsx` are outside biome `files.includes` by repo
config, so only the src file is checked); `npx vitest run` over the 7
image-explorer test files (incl. both harnesses, controller, panel components,
admin-pages): **7 files / 84 tests passed**.
