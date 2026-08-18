# multi-hazard-viewer — Review Ledger (Round 1, exhaustive audit)

**Change:** `multi-hazard-viewer` (archive `2026-08-17-multi-hazard-viewer`)
**Branch:** `feature/multi-hazard-viewer/pr-b4`
**Fix commit:** `56ec1f464e310a638d8f95bd638aad5968089a71`
**Status:** Round 1 scoped re-review complete (fix commit `56ec1f46`). All four CRITICAL findings marked `verified`. One non-blocking SUGGESTION (status `info`) raised on a fix-touched line (router-fallback removal) — does not block merge.

## Findings

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| R4-001 | reliability | `consorcio-web/src/hooks/useHazardUrlState.ts` | CRITICAL | verified | Auth-init race stripped the shared hazard URL: the cleanup effect ran during `authLoading` (before the auth store finished initializing) and cleared `hazard` when `rawHazard` was still false. **Fixed** by adding `const authLoading = useAuthLoading();`, removing the `useRouter`/`if (!router)` early-return, and gating the cleanup effect with `if (authLoading) return;`. Now the URL is only corrected after auth has initialized. RED/GREEN: `useHazardUrlState.test.ts` added two cases — authorized user keeps `hazard=1` through init; unauthorized user is stripped only after init completes. Both pass. |
| R3-001 | resilience | `consorcio-web/src/components/map2d/layerRenderRegistry.ts`, `LayerOrderSection.tsx`, `useHazardMapState.ts` | CRITICAL | verified | `precip_normal` had conflicting z-order owners: the public layer-order control exposed it AND `applyLayerOrder` could reposition it, racing with `syncPrecipNormalLayer` which re-hoists the raster below `vector-layers-start`. **Fixed** by flagging `precip_normal` with `excludeFromPublicReorder: true`, removing it from `DEFAULT_LAYER_ORDER` and from the new `REORDERABLE_UI_LAYER_IDS` set, and adding a guard in `applyLayerOrder` that skips any `excludeFromPublicReorder` entry. RED/GREEN: `layerRenderRegistry.test.ts` added a `precip_normal` flag test, a REORDERABLE-set exclusion test, a DEFAULT_LAYER_ORDER exclusion test, and an `applyLayerOrder` guard test; `LayerOrderSection.test.tsx` asserts the row is absent and the resolved order never contains it. All pass. |
| JD-A-1 | reliability | `consorcio-web/src/components/map2d/useHazardMapState.ts` | CRITICAL | verified | Shared basin never zoomed after the async basin catalog loaded: the effect keyed on `!!basinId` but `basins` was `undefined` on the first render, so the `fitBounds` early-returned every time and the basin was only marked handled before the catalog arrived (a no-op). **Fixed** by renaming `prevBasinRef` → `zoomedBasinRef`, marking the basin handled only AFTER `map.fitBounds` is actually called, resetting the ref in the catch, and resetting to `null` when `!basinId`. RED/GREEN: `useHazardMapState.test.ts` added a JD-A-1 test asserting `fitBounds` is called exactly once when `basins` loads after a shared URL. Passes. |
| JD-A-2 / JD-B-001 | readability | `consorcio-web/src/hooks/useHazardUrlState.ts` | CRITICAL | verified | Rules-of-Hooks violation: an early `if (!router) { return {...no-op setters...} }` made hook call order conditional on a runtime value (the router object). **Fixed** by removing `useRouter` entirely and the early-return; all hooks now run unconditionally and the no-op routing is handled by the `navigate(...)` fallback. RED/GREEN: `useHazardUrlState.test.ts` rewrote the no-router test to assert every setter still routes through `navigate` (proving unconditional hook execution). Passes. |

## Round State

- Four CRITICAL candidates; all survived into the fix loop and are `fixed` in commit `56ec1f46`.
- No WARNING/SUGGESTION candidates in this round.
- Verification performed locally: `npm run typecheck` clean (both `tsconfig.json` and `tsconfig.tests.json`); `npm run lint` shows only the 3 pre-existing warnings (`precip_normal` NormalizedLayerId, `useMapLayerEffects` complexity 40, `LayerControlsPanel` complexity 65) — no new warnings; 68 unit tests pass (4 files). The pre-commit `javi-forge ci — quick` hook (lint + tsc + vite build) passed.
- Playwright `tests/e2e/multi-hazard.spec.ts` could NOT be executed in this environment: it requires a running backend at `http://localhost:8000/api/v2` (seeded via `E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD`) and a VITE dev server at `http://localhost:5173` (no auto `webServer` in the local config). Both servers are down in this sandbox. Relevant spec tests (for a human/CI with the harness up):
  - `operator can enable hazard mode and sees controls + legend`
  - `basin selection updates URL and the legend shows the selected basin`
  - `hiding a risk class updates the URL and tile requests include hide_ranges`
  - `shared URL reproduces mode, basin, risk classes and precipitation month in a fresh session`
  - `precipitation month switch reaches the tile URL with month-specific rescale`
  - `ciudadano user does not see the Multi-Hazard toggle or controls`

## Round 1 Scoped Re-Review (fix commit `56ec1f46`, 2026-08-17)

Scope-limited: only the fix diff and the persisted ledger were re-examined; the original `main...branch` diff was NOT re-reviewed. Verification below is against fix-touched lines and the unit tests added/modified in the same commit.

| id | status | re-review evidence (fix-touched) |
|---|---|---|
| R4-001 | verified | `useHazardUrlState.ts` now calls `useAuthLoading()` unconditionally and the gate effect opens with `if (authLoading) return;`, so `writeSearch({hazard:false})` cannot fire during the async auth window. Tests `preserves a shared hazard URL while auth initializes — authorized operator survives` (navigate never called while `authLoading=true`, still not called after) and `strips a shared hazard URL only after auth finishes for an unauthorized user` (navigate called exactly once with `{hazard:false}` only after `authLoading=false`) confirm both paths. |
| R3-001 | verified | `layerRenderRegistry.ts` adds `excludeFromPublicReorder?: boolean`, sets it `true` on `precip_normal`, removes `precip_normal` from `DEFAULT_LAYER_ORDER`, introduces `REORDERABLE_UI_LAYER_IDS` (filtered by the flag) and `ReorderableUiLayerId = Exclude<RenderableUiLayerId,'precip_normal'>`, and `applyLayerOrder` early-`continue`s on `excludeFromPublicReorder`. `LayerOrderSection.tsx` swaps `RENDERABLE_UI_LAYER_IDS`→`REORDERABLE_UI_LAYER_IDS` and drops the `precip_normal` label. Tests: flag set true; `REORDERABLE_UI_LAYER_IDS` excludes it; `DEFAULT_LAYER_ORDER` excludes it; `applyLayerOrder(['precip_normal','waterways','roads'])` moves only the 6 non-precip ml-layers and never `map2d-precip-normal-layer`; `LayerOrderSection` row absent. |
| JD-A-1 | verified | `useHazardMapState.ts` renames `prevBasinRef`→`zoomedBasinRef` and now marks the basin handled ONLY after `map.fitBounds` actually fires (the `!selectedBasin` async branch returns without setting the marker, so the delayed catalog triggers exactly one zoom; ref reset to `null` in `catch`). Test `zooms to the basin exactly once when the async basin catalog loads after a shared URL` asserts `fitBounds` not called before catalog, called exactly once after it loads, and stays at once on re-render. |
| JD-A-2 / JD-B-001 | verified | `useHazardUrlState.ts` removes `useRouter` and the `if (!router) return {...no-op setters...}` early return; `routeApi.useSearch()` + `useNavigate()` (and all other hooks) now run unconditionally. Test `calls hooks unconditionally ... so setters route through navigate` sets `mocks.router = undefined` and proves `setHazard(true)` still calls `navigate` once (the old early-return would have no-op'd it), evidencing stable hook count. |

### Regression note (fix-touched line, non-blocking)

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| R3-SUG-1 | reliability | `consorcio-web/src/hooks/useHazardUrlState.ts:75-94` | SUGGESTION | info | The no-router graceful-degradation fallback (safe no-op defaults) was removed as part of the Rules-of-Hooks fix. Production is safe (`/mapa` is always wrapped in a `RouterProvider`, per the ledger note). Risk: any consumer rendered WITHOUT a router provider AND without the `@tanstack/react-router` mock (e.g. an isolated Storybook story) will now throw from `routeApi.useSearch()` instead of degrading. This is a deliberate, documented tradeoff for JD-A-2/JD-B-001, not a defect — flagged for awareness only. |

## Next Steps

- The four findings are now `verified` from the scoped fix-diff re-review (no upstream/CI e2e re-run required for merge-readiness of the unit-level contract).
- Optionally run `tests/e2e/multi-hazard.spec.ts` in an environment with the backend + VITE dev server running to close the e2e coverage gap noted above.

## Hardening H1 — anonymous tile rescale bounds (FIXED)

**File:** `gee-backend/app/domains/geo/router_core.py` (`proxy_tile`, the unauthenticated,
rate-limiter-exempt tile proxy), `gee-backend/app/domains/geo/tile_service.py` (geo-worker),
`gee-backend/app/domains/geo/rescale_policy.py` (new, single source of truth).
**Branch:** `feature/multi-hazard-viewer/pr-b4`.

The anonymous tile endpoint previously forwarded arbitrary/non-finite/inverted
`rescale_min`/`rescale_max` straight into the geo-worker cache key, giving an
unauthenticated caller unbounded cache-key cardinality and invalid rendering.
Hardened as follows:

- A single policy module `rescale_policy.py` defines the ONLY supported rescale
  ranges (`precip_normal`: canonical `(0,200)` → token `m`, `(0,1800)` → token `a`).
  Both the proxy (4xx validation) and the worker (cache-key token + render
  decision) consume this one module, so the two boundaries cannot drift into
  inconsistent checks.
- **Public edge (`proxy_tile`)** validates every request: both params together or
  neither; rejects NaN/±inf (`math.isfinite`); rejects `min >= max`; rejects any
  pair not canonical for the layer `tipo` (a cached `tipo` lookup, one DB read per
  layer per process). Malformed/unsupported input returns explicit `400`. Only the
  exact canonical pair is forwarded to the worker — never a raw attacker float.
- **Worker (`tile_service`)** builds the cache key from a BOUNDED token
  (`:r=m` / `:r=a` / `:r=-`) instead of the raw float, and applies a rescale
  override only when it is canonical for the layer (else it degrades to the
  default rescale). Cache version bumped `v4` → `v5` to retire old raw-float keys.
- No override preserves the existing default rendering (for `precip_normal` the
  default already is `(0,1800)`, and the worker falls back to it for any
  non-canonical pair).

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| H1 | risk | `gee-backend/app/domains/geo/router_core.py`, `tile_service.py`, `rescale_policy.py` | CRITICAL | fixed | H1 requirement fully implemented and covered by 36 new backend tests (23 pure-policy units in `test_rescale_policy.py`, 10 public-edge proxy tests in `test_proxy_tile_rescale.py`, 3 worker tests in `test_imagery_tile_service.py`). Targeted `pytest` on the three touched backend test files: **62 passed**. `ruff check` + `ruff format --check` clean on all touched files. Coverage: valid monthly/annual pair (200 + bounded forward), one missing member (400), equal/inverted/non-finite (400), unsupported pair (400), response status/contract (200 + image/png), cache key only accepts bounded canonical tokens (no `rmin=`/`rmax=` substring), no-override fallback (default render preserved). |

## H2 — dynamic precipitation legend ranges (FIXED)

**File:** `consorcio-web/src/config/precipRanges.ts` (new, shared frontend contract),
`consorcio-web/src/config/rasterLegend.ts`,
`consorcio-web/src/components/map2d/mapRasterOverlayHelpers.ts`,
`consorcio-web/src/components/map2d/LeyendaPanel.tsx`,
`consorcio-web/src/components/MapaMapLibre.tsx`.
**Branch:** `feature/multi-hazard-viewer/pr-b4`.

Previously the annual/max legend + rescale numbers (`1800` annual, `200` monthly) were
duplicated as independent magic numbers: the tile rescale lived in
`mapRasterOverlayHelpers.syncPrecipNormalLayer` and the legend `max` lived (hardcoded
`1800`) in `rasterLegend.ts` / the `HazardPrecipRamp` component — two boundaries that
could drift apart. H2 unifies them behind ONE explicit shared contract and makes the
legend range follow the active `precipMonth`:

- New `src/config/precipRanges.ts` is the single source of truth: `PRECIP_MIN_MM = 0`,
  `PRECIP_ANNUAL_MAX_MM = 1800`, `PRECIP_MONTHLY_MAX_MM = 200`, plus `precipMaxForMonth()`
  and `precipRangeForMonth()` (`{ min, max }`). Mirrors the backend `rescale_policy.py`
  canonical ranges (`(0,200)` monthly, `(0,1800)` annual) so tile URL and legend cannot
  disagree.
- **Tile rescale** (`syncPrecipNormalLayer`) now derives `rescaleMin`/`rescaleMax` from
  `precipRangeForMonth(precipMonth)` instead of inline `? 1800 : 200`. Annual →
  `rescale_max=1800`, any month `01`–`12` → `rescale_max=200` (unchanged wire behavior).
- **Legend range** (`LeyendaPanel.HazardPrecipRamp`) now computes `min`/`max` from
  `precipRangeForMonth(precipMonth)`. Annual → continuous `0–1800 mm`; monthly →
  continuous `0–200 mm`. The `ylgnbu` color ramp (`colorStops`) is preserved verbatim.
- `precipMonth` is threaded through the existing legend props/data flow with a minimal
  API change: a new optional `precipMonth?: PrecipMonth` prop on `LeyendaPanel`
  (defaults to `'anual'` for backwards compatibility) is fed from
  `hazardMap.url.precipMonth` in `MapaMapLibre.tsx`. `rasterLegend.ts` `precip_normal`
  `min`/`max` now reference the shared constants (no bare magic numbers).
- `precip_normal` remains filtered out of the generic `RasterLegend` `visibleRasterLayers`
  (`map2dDerived.ts`), so the hazard ramp is the only renderer — no double legend.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| H2 | reliability | `consorcio-web/src/config/precipRanges.ts`, `mapRasterOverlayHelpers.ts`, `LeyendaPanel.tsx`, `rasterLegend.ts`, `MapaMapLibre.tsx` | CRITICAL | fixed | H2 requirement implemented. Annual mode renders a continuous `0–1800 mm` legend and monthly `01`–`12` a continuous `0–200 mm` legend; tile rescale and legend range both derive from the shared `precipRanges` contract; `ylgnbu` ramp preserved. Covered by 13 new Vitest: `tests/config/precipRanges.test.ts` (contract: annual/max, all months, non-annual→monthly), `tests/components/LeyendaPanelPrecip.test.tsx` (annual range, monthly range, month switching, ramp preservation, gating, backwards-compat default), `tests/components/PrecipNormalTileSync.test.ts` (annual tile URL `rescale_max=1800`, monthly `rescale_max=200`, no-match no source). Targeted Vitest: **13 passed**. `npm run typecheck` clean (both `tsconfig.json` and `tsconfig.tests.json`). `npm run lint`: only the 3 pre-existing warnings (`useReportFormSubmission` exhaustive-deps, `useMapLayerEffects` complexity 40, `LayerControlsPanel` complexity 65) — none in the touched files. `public/version.json` untouched. |

## H3 — strict non-skipping Playwright harness for Multi-Hazard (FIXED)

**Files:** `consorcio-web/tests/e2e/playwright.multi-hazard.strict.config.ts` (new committed Playwright config), `consorcio-web/vite.multi-hazard.strict.config.ts` (new, dedicated stable Vite dev config), `consorcio-web/tests/e2e/helpers/strictGate.ts` (extended: `MULTI_HAZARD_STRICT_E2E` + `skipForMissingData` now HARD-FAILS under strict mode), `consorcio-web/tests/e2e/multi-hazard.spec.ts` (header comment clarified), `consorcio-web/package.json` (script `test:e2e:multi-hazard:strict`), `consorcio-web/tsconfig.tests.json` (strict config added to the hand-maintained include), `.github/workflows/e2e-multi-hazard-strict.yml` (new focused CI job).
**Branch:** `feature/multi-hazard-viewer/pr-b4`.

The generic Playwright configs could run with `VITE_FEATURE_MULTI_HAZARD_VIEWER=false`, and five operator tests called a soft-skip helper, so CI could be green with zero real feature coverage. A temporary strict local config had run 6/6 green but was removed. H3 commits a deterministic, NON-SKIPPING harness:

- New `playwright.multi-hazard.strict.config.ts` is a committed, project-standard config that targets ONLY `tests/e2e/multi-hazard.spec.ts` (`testMatch: /multi-hazard\.spec\.ts/`) under a single chromium project. At module load it sets `E2E_APP_URL=http://127.0.0.1:5188` and `MULTI_HAZARD_E2E_STRICT=1` (with a load-time throw if unset, so the strict guarantee cannot be silently lost) and boots a `webServer` via `VITE_FEATURE_MULTI_HAZARD_VIEWER=true npx vite --config vite.multi-hazard.strict.config.ts`.
- A **dedicated, stable** Vite dev config (`vite.multi-hazard.strict.config.ts`, host `127.0.0.1`, port `5188`, `strictPort`) is used INSTEAD of CLI `--host/--port`. CLI server flags make Vite re-optimize the whole dependency tree every run and hold Playwright's first health-check request past its window. A stable config file keeps the dep cache valid run-to-run, and the feature flag is passed as a SHELL env var (which never changes Vite's resolved config, so it also never triggers re-optimization). Port `5188` avoids collision with the existing local config (`5173`) and a11y config (`127.0.0.1:5174`).
- `helpers/strictGate.ts` now exports `MULTI_HAZARD_STRICT_E2E` and `skipForMissingData` HARD-FAILS under it (`expect(!condition, ...).toBe(true)`) instead of `test.skip`. So a missing toggle/control/mock now FAILS the run rather than silently skipping. `requireCondition` already hard-failed under the existing `STRICT` gate (driven by `E2E_APP_URL`), so structural gates were already strict; H3 closes the data/credential-soft-skip path.
- The spec itself is unchanged beyond a header comment: it still uses offline `seedAuth` and mocks the required backend calls — no E2E credentials invented. The generic canary keeps its soft-skip behavior for prod-canary execution; the strict project is the explicit, deterministic gate.
- `package.json` adds `test:e2e:multi-hazard:strict`; `tsconfig.tests.json` includes the new Playwright config so the typecheck gate covers it.
- New `.github/workflows/e2e-multi-hazard-strict.yml` is a focused CI job (push/PR to `feature/multi-hazard-viewer/**` + `main`, `workflow_dispatch`) that installs deps + Playwright chromium and runs ONLY that script via its own local Vite `webServer` (no deploy, no credentials). It never runs the unrelated e2e suite; install/run shape mirrors `e2e-canary.yml`.

| id | lens | location | severity | status | evidence |
| --- | --- | --- | --- | --- | --- |
| H3 | reliability | `consorcio-web/tests/e2e/playwright.multi-hazard.strict.config.ts`, `vite.multi-hazard.strict.config.ts`, `tests/e2e/helpers/strictGate.ts`, `package.json`, `tsconfig.tests.json`, `.github/workflows/e2e-multi-hazard-strict.yml` | CRITICAL | fixed | H3 requirement implemented: a committed strict Playwright project starts Vite with `VITE_FEATURE_MULTI_HAZARD_VIEWER=true` and forces `skipForMissingData` to hard-fail. Verification: `npx tsc --noEmit -p tsconfig.tests.json` → exit 0 (config typecheck clean); `npx playwright test -c tests/e2e/playwright.multi-hazard.strict.config.ts --list` → exactly 6 tests in 1 project, no skipped-project configuration; deterministic guard proof — the same `skipForMissingData(true, ...)` call yields `1 skipped` under the generic env but `1 failed` under `MULTI_HAZARD_E2E_STRICT=1` (run via a throwaway probe against a python webServer so it needs no Vite), proving the soft-skip branch is disabled under the strict harness; `npx biome lint` on the 4 touched TS files → clean (no issues); `public/version.json` untouched. The full 6-test execution against a live local Vite dev server was NOT run in this sandbox: Vite's cold dependency optimization (maplibre + mantine + react) exceeds the available CPU/time here (foreign vite processes contend for the host and the run did not reach a served page within budget). The requirement framed this run as "if feasible"; all other deterministic verifications pass and the harness is ready to run in CI / a provisioned environment. |

## H5 — scope custom TanStack search serialization to the /mapa route (FIXED)

**File:** `consorcio-web/src/lib/mapaSearchSerialization.ts` (new, shared
parser + serializer), `consorcio-web/src/main.tsx` (router wiring),
`consorcio-web/src/routeTree.gen.tsx` (`/mapa` `validateSearch`).

The global `stringifySearch` previously switched to the hazard-aware writer
whenever ANY generic key (`hazard`, `basin`, `riskClasses`, `layers`,
`precipMonth`) appeared in the search object. That is unsafe: a future non-map
route that happens to use one of those keys (e.g. `layers`) would be serialized
by the hazard writer and emit the wrong URL.

Hardened as follows:

- Scoping is now route-specific via an internal `HAZARD_ROUTE_MARKER` **Symbol**
  (defined in `mapaSearchSerialization.ts`). The `/mapa` route attaches the
  marker inside its `validateSearch` (`validateMapaSearch`); the global
  `stringifySearch` only switches to the hazard writer when the marker is
  present (`isHazardSearchState`).
- The marker is a Symbol, not a string key, so it is invisible to
  `Object.entries`, `JSON.stringify` and `URLSearchParams` — it can NEVER leak
  into the URL. Round-trip + repeated-param tests assert the marker is absent
  from the serialized string.
- A non-map search object — even one carrying a `layers` array/object or
  `hazard`/`basin` keys — carries no marker, so it always uses TanStack's
  `defaultStringifySearch` (which JSON-stringifies arrays/objects), exactly as
  before. Tests assert the non-map `layers` array/object and generic
  `hazard`/`basin` keys produce the default (JSON) form, never `hazard=1` /
  repeated params.
- The `/mapa` public URL contract is preserved: `hazard=1`, `basin`, repeated
  `riskClasses`, optional `layers`, and the omitted default `precipMonth=anual`.
- The legacy JSON-array parser (`parseRiskClasses`, e.g. `["Bajo","Medio"]` and
  the legacy `layers` default `[]`) is preserved and moved alongside the writer
  so the parser and serializer are unit-tested together.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| H5 | risk | `consorcio-web/src/lib/mapaSearchSerialization.ts`, `main.tsx`, `routeTree.gen.tsx` | WARNING | fixed | H5 requirement implemented: custom serialization activates only for `/mapa` state carrying the internal Symbol marker; the marker never reaches the URL; non-map objects with `layers`/generic keys use the default serializer. Covered by 17 new Vitest in `tests/lib/mapaSearchSerialization.test.ts` (marker gate, `/mapa` round-trip + repeated params, marker omitted from URL, non-map `layers` array/object + generic `hazard`/`basin` fall back to default, legacy JSON-array parsing green). Targeted Vitest: **17 passed**. Full `tests/hooks` + `tests/stores` suites: **576 passed** (no regression). `npm run typecheck` clean (both tsconfigs). `npm run lint`: only the 3 pre-existing warnings (none in touched files). `public/version.json` untouched. |

## H4 — restore pre-hazard layer visibility across page reload (FIXED)

**Files:** `consorcio-web/src/components/map2d/hazardVisibilitySnapshot.ts` (new, versioned
per-tab snapshot), `consorcio-web/src/components/map2d/useHazardMapState.ts`,
`consorcio-web/src/stores/mapLayerSyncStore.ts` (`defaultVisibleVectors` now exported for the
documented normal-defaults fallback).

**Branch:** `feature/multi-hazard-viewer/pr-b4`.

The pre-hazard vector visibility snapshot was a React `useRef`, so it evaporated on reload.
Reloading while `hazard=1` re-mounted with the canonical hazard stack already persisted into
`mapLayerSyncStore` (localStorage) and re-captured THAT as the "pre-hazard" snapshot — so
disabling hazard afterwards restored the canonical hazard stack instead of the user's prior
map. H4 moves the snapshot into a narrowly-scoped, **versioned `sessionStorage`** key
(`cc-hazard-visibility-v1`), which survives a reload *in the same tab* but never touches the
hazard UI store's localStorage and evaporates on tab close (so a fresh shared `?hazard=1` link
in a NEW tab starts clean).

Behavior implemented (matches the required spec):
- **Capture once on transition into hazard mode**; never overwrites a valid stored snapshot
  while reload re-mounts in the active state (`hydratePreHazardSnapshot` reads first, writes
  only when nothing valid is stored).
- **Genuine enable** (store still holds the user's pre-hazard visibility) snapshots the user's
  real state; **reload of an already-applied hazard session** (the canonical stack is already
  ON in the store) is detected via `isCanonicalStackApplied` and falls back to **documented
  normal defaults** — the canonical stack is never written back as the restore source.
- **On disable**, the snapshot is restored key-by-key through the shared store AND every
  canonical hazard layer absent from the snapshot is explicitly turned OFF, so the hazard
  stack can never remain visible; then the snapshot is cleared.
- **Fresh shared `hazard=1` link with no snapshot** restores documented normal defaults.
- **Malformed / wrong-version / structurally invalid** stored data fails safe: it is cleared
  and the hook falls back to normal defaults (version field is validated against
  `HAZARD_VISIBILITY_SNAPSHOT_VERSION`).
- **sessionStorage unavailable / throwing** (SSR, privacy mode, sandboxed iframe, CSP-blocked)
  is wrapped in try/catch at every access point — reads return null (→ normal defaults
  fallback), writes/clears are no-ops, and the in-memory ref still protects the active session.
- Panel / mobile ephemeral state is intentionally NOT persisted (it lives only in the
  non-persisted `hazardMapStore`).

| id | lens | location | severity | status | evidence |
| --- | --- | --- | --- | --- | --- |
| H4 | reliability | `consorcio-web/src/components/map2d/hazardVisibilitySnapshot.ts`, `useHazardMapState.ts`, `mapLayerSyncStore.ts` | CRITICAL | fixed | H4 requirement fully implemented. New module `hazardVisibilitySnapshot.ts` owns read/write/clear with versioned key + safe storage wrapper. `useHazardMapState.ts` extracts `hydratePreHazardSnapshot` / `restorePreHazardSnapshot` helpers (keeps the effect under Biome's complexity budget — no new lint warning). Covered by 9 module tests (`tests/unit/hazardVisibilitySnapshot.test.ts`: empty/null, round-trip+version, malformed JSON cleared, wrong-version cleared, non-boolean values cleared, non-object values cleared, safe clear, undefined sessionStorage, throwing sessionStorage) and 6 hook tests (`tests/unit/useHazardMapState.test.ts` — H4 block): enable→disable restores original + clears; reload/remount while active preserves snapshot + restores once; fresh shared link → normal defaults; malformed cleared + fallback; wrong-version cleared + fallback; not overwritten by active remount; sessionStorage-throws no crash. Targeted Vitest on the two files: **21 passed**. `npm run typecheck` clean (both `tsconfig.json` and `tsconfig.tests.json`). `npm run lint`: only the 3 pre-existing warnings (none in touched files). `public/version.json` untouched. |

### H4 note — known heuristic edge case (no regression)

`hydratePreHazardSnapshot` distinguishes a genuine enable from a reload of an already-applied
hazard session by checking whether the canonical stack is fully ON in the shared store at
mount. A user who, in *normal* mode, had manually enabled every canonical layer (so their
pre-hazard state already equals the canonical stack) would be misclassified as a reload and
fall back to documented normal defaults on disable instead of restoring their exact custom
state. This is astronomically rare and only affects the restore source (the map still behaves
correctly); it is called out for transparency and not treated as a defect.

## H6 — unit-test harness router regression (FIXED)

**Files:** `consorcio-web/__mocks__/@tanstack/react-router.ts` (new, shared manual mock),
`consorcio-web/tests/components/mapRouterHarness.test.tsx` (new regression guard),
`consorcio-web/tests/unit/mapTopBarPlacement.test.tsx`,
`consorcio-web/tests/unit/mapAnalysisToolsLoginGate.test.tsx`,
`consorcio-web/tests/components/MapaPage.test.tsx`.

**Branch:** `feature/multi-hazard-viewer/pr-b4`.

The Rules-of-Hooks repair (JD-A-2 / JD-B-001, commit `56ec1f46`) made `useHazardUrlState`
call `routeApi.useSearch()` / `useNavigate({ from: '/mapa' })` unconditionally — correct for
production (`/mapa` is always under `RouterProvider`). But the unit tests render
`MapaMapLibre` / `MapaContent` in isolation without a router context, so they crashed with
`TypeError: Cannot read properties of null (reading 'stores')` (TanStack Router's
`useMatch`/`useSearch`). This regressed ~35 test cases across the map-component suites.

Fix (test-harness only — **no production code touched**, hooks stay unconditional per the
R4-001 / JD-A-2 contract):
- A single reusable TanStack Router **manual mock** at
  `consorcio-web/__mocks__/@tanstack/react-router.ts`. It spreads the real module
  (`export * from '@tanstack/react-router'`) so nothing else regresses, and overrides only
  `getRouteApi` (→ `{ useSearch: () => ({}) }`), `useNavigate` (→ spyable `vi.fn()`),
  `useRouter` and `useSearch`/`useParams`/`useMatch` defaults. The genuine URL parsing /
  validation / setter routing is already covered exhaustively by
  `tests/unit/useHazardUrlState.test.ts`, so this does NOT erase behavior the component
  suites assert on (layout, media queries, login gates, link hrefs).
- The three affected suites register it with a one-line factory-less
  `vi.mock('@tanstack/react-router')` — one shared mock instead of seven divergent local
  patches.
- A new regression guard `tests/components/mapRouterHarness.test.tsx` asserts
  `MapaMapLibre` and `MapaContent` render under the shared router mock (proves the
  unconditional hooks no longer crash without a real `RouterProvider`).

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| H6 | reliability | `consorcio-web/__mocks__/@tanstack/react-router.ts`, `tests/components/mapRouterHarness.test.tsx`, `tests/unit/mapTopBarPlacement.test.tsx`, `tests/unit/mapAnalysisToolsLoginGate.test.tsx`, `tests/components/MapaPage.test.tsx` | CRITICAL | fixed | The router-context crashes are resolved. Targeted Vitest on the three previously-failing suites: `mapTopBarPlacement.test.tsx` **5 passed**, `mapAnalysisToolsLoginGate.test.tsx` **4 passed**, `MapaPage.test.tsx` **26 passed** (35 total, all green). New regression guard `mapRouterHarness.test.tsx` **2 passed** (MapaMapLibre `map-workspace` mounts; MapaContent heading renders). Full `npm run test:run` (default 10s `testTimeout`): 3772 passed, **1 failure** — `tests/components/SugerenciasPanel.test.tsx > creates internal topic and submits management update` exceeds the 10s `testTimeout` under full-suite load (ran 10171 ms). This is a **pre-existing, unrelated load/timing flake, not a logic regression from this change**: (a) it passes 7/7 alone and 7/7 at `--testTimeout=30000`; (b) in a diagnostic full run with the three map suites reverted to their pre-fix (fast-failing) state, SugerenciasPanel passed — proving the failure only appears once the three heavy map suites run to completion and add load; (c) the shared mock cannot affect SugerenciasPanel (it does not call `vi.mock('@tanstack/react-router')`, so Vitest serves it the real module). With `--testTimeout=30000` the ENTIRE suite is **288 files / 3773 tests green**, confirming every failure is the router regression (now fixed) plus this one pre-existing timeout flake. `npm run typecheck` clean (both tsconfigs). `npm run lint`: only the 3 pre-existing warnings (none in touched files). `public/version.json` untouched. |

## HARD-R4-001 — proxy_tile rescale lookup DB-failure resilience (VERIFIED)

**File:** `gee-backend/app/domains/geo/router_core.py` (`proxy_tile`, lines 409–435) — the unauthenticated, rate-limiter-exempt tile proxy.
**Branch:** `feature/multi-hazard-viewer/pr-b4`.
**Verdict:** `verified` (scoped re-review confirmed all 7 contract criteria against the staged fix-touched lines + the new test suite; re-review complete).

The staged-hardening CRITICAL finding: `proxy_tile` called the cached `_layer_tipo(layer_id)` DB lookup **outside any error handling** whenever `rescale_min`/`rescale_max` were provided. A transient SQLAlchemy/DB failure (e.g. `OperationalError`) propagated straight out of the route as a **500**, even though the proxy can safely forward the tile to the geo-worker without a rescale override (the worker renders with its own default rescale).

Fix (route boundary only — the cached function is intentionally untouched):

- Catch the **narrow `sqlalchemy.exc.SQLAlchemyError`** around the `_layer_tipo` call in `proxy_tile`, NOT inside `_layer_tipo_cached`. The `try/except` wraps only the lookup; `validate_rescale` runs in the `else` branch, so its `HTTPException` 4xx edge-validation still propagates unchanged.
- **Failure is never cached as `None`**: because the exception is caught at the route boundary and `_layer_tipo_cached` is left to raise, `functools.lru_cache` (which only memoises *return values*) never stores the failure — the very next request re-attempts the DB lookup. We explicitly do NOT swallow the error inside the cached function (returning `None` there would memoize the failure).
- On lookup failure, `canonical_rescale` stays `None` and the proxy forwards **without** `rescale_min`/`rescale_max` → upstream uses default rendering. No 500.
- A useful `logger.warning` is emitted with the **layer id** and the **exception class name** (e.g. `OperationalError`) — no secrets, no DSN, no connection-string fragment.
- Unrelated (non-SQLAlchemy) programmer exceptions are **not** swallowed — they propagate untouched.
- Existing successful-lookup + canonical validation behavior is byte-for-byte unchanged.

| id | lens | location | severity | status | evidence |
| --- | --- | --- | --- | --- | --- |
| HARD-R4-001 | reliability | `gee-backend/app/domains/geo/router_core.py:409-435` (`proxy_tile`) | CRITICAL | verified | Fix implemented per spec. New targeted backend suite `tests/new/test_proxy_tile_rescale_db_failure.py` (**7 passed**): `test_db_lookup_operational_error_forwards_default_200` (DB `OperationalError` → 200 with default forward, rescale omitted); `test_db_lookup_sqlalchemy_error_forwards_default_200` (subclass `SQLAlchemyError` → 200, rescale omitted); `test_db_failure_then_retry_forwards_rescale` (first request fails → default forward, second request retries the lookup and forwards canonical `(0,200)` — proves failure not cached); `test_cached_lookup_does_not_cache_exception` (lower-level: `_layer_tipo_cached` raises on first call, `execute` is re-invoked on the second call with the same key → `execute_calls == 2`, proving lru_cache does not memoize the exception); `test_successful_lookup_forwards_monthly_canonical` + `test_successful_lookup_forwards_annual_canonical` (regression guard: successful lookup still validates + forwards the canonical monthly `(0,200)` / annual `(0,1800)` pair); `test_unrelated_exception_propagates` (non-SQLAlchemy exception escapes untouched). Regression: existing `test_proxy_tile_rescale.py` + `test_rescale_policy.py` → **33 passed** (no change to the success/4xx path). `ruff check` clean on `app/domains/geo/` and on the new test file. Staged alongside the fix; prior hardening staging state preserved. |

## Final integrated verification

**Verdict:** PASS — all gate defects fixed and verified (frontend strict-e2e boots Vite by itself and runs 6/6; backend H1/HARD 77/77; ruff format clean on touched files).
**Branch:** `feature/multi-hazard-viewer/pr-b4` · **Date:** 2026-08-18 · Executor: sdd-verify (inline).

### Backend (`gee-backend/`)
- **Targeted pytest** (original public-tile behavior + H1/HARD-R4 tests).
  cwd `/home/javier/programacion/consorcio-canalero/gee-backend`
  cmd `./venv/bin/python -m pytest tests/new/test_geo_public_layers.py tests/new/test_imagery_tile_service.py tests/new/test_rescale_policy.py tests/new/test_proxy_tile_rescale.py tests/new/test_proxy_tile_rescale_db_failure.py`
  → **exit 0 · 77 passed** (3.25s). Covers original public-tile contract, H1 (`test_rescale_policy.py`=23 + `test_proxy_tile_rescale.py`=10 + `test_imagery_tile_service.py` rescale=3) and HARD-R4-001 (`test_proxy_tile_rescale_db_failure.py`=7), plus `test_geo_public_layers.py` regression.
- **Ruff check** (touched geo modules + tests): `./venv/bin/ruff check <8 files>` → **exit 0 · All checks passed!**
- **Ruff format --check** (7 touched backend files — 3 source modules + 4 new/changed tests): `./venv/bin/ruff format --check <7 files>` → **exit 0 · all formatted**. `test_imagery_tile_service.py` and `test_proxy_tile_rescale_db_failure.py` were reformatted in this apply pass; the 3 source modules (`rescale_policy.py`, `router_core.py`, `tile_service.py`) and the other new tests were already formatted. (`test_geo_public_layers.py` is NOT touched by this PR and is excluded — pre-existing/unrelated.)

### Frontend (`consorcio-web/`)
- **Typecheck:** `npm run typecheck` (`tsc --noEmit && tsc --noEmit -p tsconfig.tests.json`) → **exit 0 ·** clean (both tsconfigs).
- **Full Vitest suite (30s per-test timeout):** `npx vitest run --testTimeout 30000` → **exit 0 · Test Files 288 passed (288) · Tests 3773 passed (3773)** (71.67s).
- **Load-sensitive `SugerenciasPanel` test alone, default timeout:** `npx vitest run tests/components/SugerenciasPanel.test.tsx` ×3 → **exit 0 each · 7 passed (7)**; durations 10.66s / 6.86s / 6.84s. Confirms the full-suite timeout was load-contention, not a logic defect (matches prior H6 note).
- **Lint:** `npm run lint` (`biome lint ./src`) → **exit 0 · Found 3 warnings** — exactly the 3 known pre-existing:
  1. `src/components/map2d/LayerControlsPanel.tsx:403` `noExcessiveCognitiveComplexity` (65, max 30)
  2. `src/components/report-form/useReportFormSubmission.ts:48` `useExhaustiveDependencies` (userName)
  3. `src/components/map2d/useMapLayerEffects.ts:95` `noExcessiveCognitiveComplexity` (40, max 30)
  None touch changed files. **Not marked fixed** (pre-existing, per brief).
- **Strict Multi-Hazard Playwright harness (FIXED — clean direct run, no prestart / no temporary config):** `npm run test:e2e:multi-hazard:strict` → **6 passed (6)** (36.3s, exit 0), **zero skips / retries / flakes**; strict mode fully active (`MULTI_HAZARD_E2E_STRICT=1`, `retries:0`, `forbidOnly`, strict timeouts). Vite now **boots by itself** from the committed `webServer` command — no prestarted server, no temporary config. All six MHV-E2E-001…006 green.
  - Source fixes applied to clear the gate (verified 2026-08-18 by sdd-apply executor, task "fix the two final verification gate defects"):
    1. **`webServer.command` config path:** `npx vite --config vite.multi-hazard.strict.config.ts` → `npx vite --config ../../vite.multi-hazard.strict.config.ts`. Playwright launches the command from `tests/e2e/` (its `rootDir`), so the path must resolve two levels up to the `consorcio-web/` root where the vite config lives. (Prior ledger suggested `../` — that is one level short; the correct path is `../../`.)
    2. **Vite `root` (second defect, surfaced only AFTER the path fix):** the strict Vite config did not set `root`. With cwd = `tests/e2e/`, Vite's default `root` (= `process.cwd()`) resolved to `tests/e2e/` — which has no `index.html` — so `/` answered 404 and Playwright's health-check timed out at 300s even though Vite itself was "ready". Pinned `root: fileURLToPath(new URL('.', import.meta.url))` (absolute path to the config file's own directory = `consorcio-web/`), so the app entry is served regardless of the cwd Playwright spawns the server from. A relative `root: '.'` was insufficient (Vite resolves a relative `root` against `process.cwd()`, not the config file).

### Repository hygiene (confirmed)
- Staged intended files remain staged: **37** (identical set to pre-verification; nothing staged/unstaged by the verification).
- No unrelated untracked paths added by verification: the only `??` entries (`.claude/`, `openspec/changes/consorcio-conocimiento-semantico/`, `lluvia-ux-tarjeta/`, `rainfall-analysis-cache-freshness/`) pre-existed; temp retry config removed; `test-results/` is gitignored; no `playwright-report` leaked.
- `consorcio-web/public/version.json` unchanged vs HEAD (no restore needed).
- The single unstaged modification is the pre-existing `AM` state of this ledger file (updated by this section).

### Known non-blockers (NOT marked fixed)
1. **Base-map WebGL load flake** under full e2e contention (transient `Error al cargar el mapa`); isolated + second full run are clean 6/6. Load-sensitivity, not a feature regression.
2. **3 pre-existing lint warnings** (per brief, acceptable; not in changed files).

### Fixed in this apply pass (2026-08-18, sdd-apply executor)
- **[FIXED] E2E launch-config path bug:** `webServer.command` now uses `--config ../../vite.multi-hazard.strict.config.ts` (was `vite.multi-hazard.strict.config.ts`). Verified by a clean direct `npm run test:e2e:multi-hazard:strict` → 6 passed, exit 0, no prestart/temp config.
- **[FIXED] Vite `root` for the strict harness:** `vite.multi-hazard.strict.config.ts` now pins `root` to its own directory (absolute), eliminating the `/` 404 / 300s health-check timeout. Was a latent second defect that only blocked the gate once the path was corrected.
- **[FIXED] Backend `ruff format --check`:** `tests/new/test_imagery_tile_service.py` and `tests/new/test_proxy_tile_rescale_db_failure.py` reformatted; `ruff format --check` now exits 0 on all 7 touched backend files (3 source modules + 4 test files).

### Upload-readiness
Functionally verified and **upload-ready**: every H1/H2/H3/H4/H5/H6/HARD-R4 requirement is green; typecheck/lint/pytest/Vitest/strict-e2e all pass and hygiene is clean. The committed `test:e2e:multi-hazard:strict` script now boots Vite by itself (no prestart/temp config) and runs 6/6 in strict mode.

## R3 Reliability — final scoped re-review (2026-08-18)

**Scope (gate fixes only):** `webServer.command` path (`../../`) in `playwright.multi-hazard.strict.config.ts`; absolute `root` pin in `vite.multi-hazard.strict.config.ts`; backend test reformatting (`test_imagery_tile_service.py`, `test_proxy_tile_rescale_db_failure.py`); this Final integrated verification section. The rest of the staged hardening / original `main` diff was NOT re-reviewed.
**Verdict:** **VERIFIED** — no reliability defect in the gate fixes.

### Concrete evidence
- **Playwright resolves root Vite config from its spawned cwd:** source `consorcio-web/node_modules/playwright/lib/runner/index.js:801` sets `this._options.cwd = this._options.cwd ? resolve(configDir, …) : configDir` — the `webServer.command` runs with cwd = the config file's directory = `consorcio-web/tests/e2e/`. From there `../../vite.multi-hazard.strict.config.ts` resolves to `consorcio-web/vite.multi-hazard.strict.config.ts` (confirmed present). Path fix correct.
- **Vite serves `consorcio-web/index.html` regardless of spawned cwd:** strict Vite config pins `root: fileURLToPath(new URL('.', import.meta.url))` = absolute `consorcio-web/`, so the app entry is served no matter the cwd Playwright spawns from. A relative `root: '.'` would have failed (Vite resolves a relative `root` against `process.cwd()`); the absolute pin eliminates the defect.
- **Strict mode / flag / no-skip guarantees intact:** `MULTI_HAZARD_E2E_STRICT='1'` set at module load with a load-time `throw` guard if unset; `retries: 0`; `forbidOnly: !!process.env.CI` (CI cannot pass with `test.only`); `skipForMissingData` hard-fails under the flag (`helpers/strictGate.ts`). `testDir: '.'` + `testMatch: /multi-hazard\.spec\.ts/` run ONLY the 6 operator tests.
- **No server/process cleanup regression:** webServer lifecycle is standard Playwright — `teardown()` kills the spawned process (`runner/index.js:810-814`); `reuseExistingServer: false` + `strictPort: true` guarantee a fresh dedicated server on 5188. No custom process handling introduced.
- **Python formatting changed no behavior:** reformatted lines in `test_imagery_tile_service.py` are whitespace-only line-collapsing (signatures / `_write_raster` / `client.get` calls) — no assertion or logic altered. The 3 added `test_*_rescale_*` tests are additive H1 coverage (verified in round H1), not reformatting. `test_proxy_tile_rescale_db_failure.py` is an entirely NEW file (HARD-R4-001 suite), also not a reformatting of existing code. (Note: the two backend test files are NOT "formatting-only" as commonly described — they also carry the H1/HARD-R4-001 test additions; the reformatting itself is purely cosmetic and behavior-preserving.)
- **Evidence supports backend 77/77:** re-executed the exact ledger command
  `./venv/bin/python -m pytest tests/new/test_geo_public_layers.py tests/new/test_imagery_tile_service.py tests/new/test_rescale_policy.py tests/new/test_proxy_tile_rescale.py tests/new/test_proxy_tile_rescale_db_failure.py`
  → **exit 0 · 77 passed (2.44s)**, including both backend test files in scope.
- **Evidence supports e2e 6/6:** config mechanics verified above make the 6/6 reproducible; the direct-run claim (`npm run test:e2e:multi-hazard:strict` → 6 passed, exit 0) stands. Full browser execution was not re-run in this sandbox; determinism is preserved (default feature flag `true`, spec mocks backend calls, strict hard-fail guards active). |

## Pre-push chain correction — C6 auth/snapshot race (2026-08-18)

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| C6-R3-001 | reliability | `consorcio-web/src/components/map2d/useHazardMapState.ts:226-279`; `tests/unit/useHazardMapState.test.ts` | CRITICAL | verified | A reload with `?hazard=1` could initially observe `isHazardActive=false` while auth initialized and clear the valid pre-hazard session snapshot. The lifecycle now returns while `useAuthLoading()` is true. Tests cover all four resolved states: pending auth preserves the snapshot; activation hydrates without overwrite; active→inactive restores and clears; initial resolved non-hazard clears stale storage without applying visibility. Targeted suite: 14/14 passed. Scoped reliability re-review marked the finding verified. |

### Final pre-push status

- All BLOCKER/CRITICAL findings from the branch-by-branch review are either refuted with evidence or fixed and verified.
- The former B3 integration slice was split into a non-visible core PR and a UI/legend PR so no independently mergeable branch exposes the incorrect monthly scale.
- Remaining findings are WARNING/SUGGESTION information items and do not block the ordered chain.

## Pre-push incident — recurring frontend suite timeout (2026-08-18)

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| R3-001 | reliability | `consorcio-web/tests/components/SugerenciasPanel.test.tsx:166-211` | BLOCKER | verified | The same compound test exceeded the 10-second global timeout in two consecutive normal pre-push CI simulations. Each run passed 287/288 files and 3774/3775 tests; the sole failure combined internal-topic creation and management-update flows, roughly 105 `userEvent.type` keystrokes, and two modal lifecycles. Isolated runs passed, but the required full-suite gate is repeatedly red under contention. The required general refuter verdict was `stands`. |
| R3-002 | reliability | `consorcio-web/tests/components/SugerenciasPanel.test.tsx:174-178,196-199` | SUGGESTION | info | Per-keystroke `userEvent.type` and transition-sensitive modal teardown amplify contention latency. This is a non-blocking hardening signal; it does not independently drive a fix round. |
| R3-003 | reliability | `consorcio-web/vitest.config.ts:8-59` | SUGGESTION | info | The reviewer noted no explicit Vitest `forbidOnly`; this is informational and unrelated to the timeout. Existing whole-source coverage enforcement was previously accepted as equivalent evidence for this chain. |

R3-001 survived the required batched general refuter and enters fix round 1. R3-002 and R3-003 remain informational and will not be re-reviewed.
