# Verify Report: Multi-Hazard Viewer E2E

## status

PASSED — 6/6 Playwright E2E tests green after targeted fixes.

## executive_summary

The `multi-hazard.spec.ts` E2E suite was executed against a local frontend
instance started with `VITE_FEATURE_MULTI_HAZARD_VIEWER=true` on port 15174,
using the existing Consorcio Canalero backend container on port 18000.

| Test ID | Description | Initial | Final |
|---------|-------------|---------|-------|
| MHV-E2E-001 | Operator enables hazard mode and sees controls + legend | FAIL | PASS |
| MHV-E2E-002 | Basin selection updates URL and legend | PASS | PASS |
| MHV-E2E-003 | Hiding a risk class updates URL and tile `hide_ranges` | PASS | PASS |
| MHV-E2E-004 | Shared URL reproduces state in a fresh session | FAIL | PASS |
| MHV-E2E-005 | Precip month switch reaches tile URL with rescale | FAIL | PASS |
| MHV-E2E-006 | Ciudadano role gate hides toggle and cleans URL | FAIL | PASS |

Three implementation defects and one test assertion mismatch were found and
fixed. No backend changes were required because the spec mocks the geo/tile
endpoints at the network boundary.

## artifacts

All logs and captured failure artifacts are under `/tmp/opencode/mhv-e2e/`:

- `frontend.log` — first local Vite startup log.
- `frontend-restart.log` — second Vite startup log (after first code fixes).
- `frontend-restart-2.log` — third Vite startup log (after final fixes).
- `playwright-run-1.log` — first test run (3 failures).
- `playwright-run-2.log` — second run (2 failures: basin assertion + role gate).
- `playwright-run-3.log` — final run (6 passed).
- `multi-hazard-Multi-Hazard--11e65-de-and-sees-controls-legend-chromium-—-multi-hazard/` — MHV-E2E-001 initial failure (screenshot + error-context).
- `multi-hazard-Multi-Hazard--d1b48-on-month-in-a-fresh-session-chromium-—-multi-hazard/` — MHV-E2E-004 initial failure (screenshots, error-context, trace).
- `multi-hazard-Multi-Hazard--d84b3-with-month-specific-rescale-chromium-—-multi-hazard/` — MHV-E2E-005 initial failure (screenshots, error-context, trace).
- `multi-hazard-Multi-Hazard--0056e-i-Hazard-toggle-or-controls-chromium-—-multi-hazard/` — MHV-E2E-006 failure from run 2 (screenshots, error-context, trace).

## failures (initial)

### 1. MHV-E2E-001 — URL serialized `hazard=true` instead of `hazard=1`

- **Evidence**: `Received string: "http://localhost:15174/mapa?hazard=true&..."`
- **Root cause**: TanStack Router's default `stringifySearch` serializes boolean
  values as `true`/`false` and arrays as JSON strings. The implementation had
  no custom serializer.
- **Fix**: Added a router-level `stringifySearch` in `src/main.tsx` that emits
  `hazard=1`, repeated `riskClasses`/`layers` params, and omits the default
  `precipMonth=anual`.

### 2. MHV-E2E-004 — URL basin was cleared before the basin catalog loaded

- **Evidence**: `hazard-basin-select` showed "Mostrar todo" despite
  `basin=candil` in the URL.
- **Root cause**: `useHazardMapState` had an effect that dropped unknown basin
  IDs; it fired on the first render while `basins` was still `null`.
- **Fix**: Guarded the cleanup effect so it only runs after `basins` has loaded.

### 3. MHV-E2E-005 — Switching precipitation month did not request the monthly layer

- **Evidence**: No tile request matched `geo-precip-normal-01` +
  `rescale_max=200`.
- **Root cause**: `useGeoLayers` deduplicated layers by `(variante, tipo,
  area_id)`, which collapsed all `precip_normal` layers into one (annual,
  because it was returned first).
- **Fix**: Included `metadata_extra` in the deduplication key so monthly
  precipitation normals survive alongside the annual layer.

### 4. MHV-E2E-006 — Ciudadano with `hazard=1` kept the param in the URL

- **Evidence**: `not.toHaveURL(/[?&]hazard=1/)` failed; URL stayed
  `?hazard=1`.
- **Root cause**: `useHazardUrlState` removed `hazard` only when `setHazard`
  was called interactively; there was no mount-time cleanup for gated-out
  users.
- **Fix**: Added a `useEffect` in `useHazardUrlState` that drops `hazard`
  from the URL whenever `hazard` is true but the role/flag gate is closed.

### 5. MHV-E2E-004 — Mantine Select input value assertions

- **Evidence**: `hazard-basin-select` value was "Cuenca Candil" (label)
  instead of "candil" (option value); `hazard-precip-month-select` would
  similarly show "Marzo" instead of "03".
- **Root cause**: The spec asserted the raw option value on a Mantine
  `Select`, whose visible input holds the selected label.
- **Fix**: Updated `multi-hazard.spec.ts` to assert the rendered labels
  ("Cuenca Candil", "Marzo"), which is the observable user-facing state.

## fixes_applied

1. `consorcio-web/src/main.tsx`
   - Imported `defaultStringifySearch`.
   - Added `stringifySearch` to `createRouter` with custom hazard-mode
      serialization.

2. `consorcio-web/src/routeTree.gen.tsx`
   - Improved `parseRiskClasses` to handle legacy JSON-array strings and
      empty `[]` for backward compatibility.

3. `consorcio-web/src/hooks/useHazardUrlState.ts`
   - Added mount-time effect to strip `hazard` from the URL when the gate is
      closed.

4. `consorcio-web/src/components/map2d/useHazardMapState.ts`
   - Guarded the unknown-basin cleanup so it does not fire while basin data is
      still loading.

5. `consorcio-web/src/hooks/useGeoLayers.ts`
   - Included deterministic `metadata_extra` in the layer deduplication key,
      fixing monthly `precip_normal` discovery.

6. `consorcio-web/tests/e2e/multi-hazard.spec.ts`
   - Corrected basin and precipitation-month select assertions to check
      rendered labels instead of raw option values.

## next_recommended

- Run the full `test:e2e:local` canary/prod suite to confirm the route
  serializer change does not regress other routes' search params.
- Run `npm run typecheck` and the Vitest unit suite before merging.
- Add a dedicated Playwright project for the Multi-Hazard spec to
  `playwright.local.config.ts` (with `globalSetup` skipped or made conditional)
  so future runs do not need a temporary config file.
- Consider adding a backend integration test for the `precip_normal` dedup
  key change to prevent regression in the geo-layers catalog.

---

# Final Verification Pass

## status

PASS WITH WARNINGS

## executive_summary

After the E2E fixes, the final verification pass ran the backend geo
tile/catalog tests, the frontend TypeScript typecheck, the full Vitest unit
suite, and the Biome linter. All functional checks passed. The only issue is one
new Biome warning introduced by the `stringifyHazardSearch` helper in
`main.tsx`, which exceeds the project's cognitive-complexity threshold.

## results

### 1. Backend geo tests

| Check | Command | Result |
|---|---|---|
| Geo public layers + imagery tile service | `pytest tests/new/test_geo_public_layers.py tests/new/test_imagery_tile_service.py` | **PASS** — 34/34 tests passed in 2.89s |

### 2. Frontend typecheck

| Check | Command | Result |
|---|---|---|
| TypeScript (src + tests) | `npm run typecheck` | **PASS** — no errors |

### 3. Frontend unit tests

| Check | Command | Result |
|---|---|---|
| Vitest unit suite | `npm run test:run` | **PASS** — 282 test files, 3719 tests passed in 30.21s |

### 4. Frontend lint

| Check | Command | Result |
|---|---|---|
| Biome lint | `npm run lint` | **PASS WITH 4 WARNINGS** — 3 pre-existing, 1 new |

## failures

No functional failures. The single new warning is a code-quality finding:

| Severity | File | Rule | Message |
|---|---|---|---|
| WARNING | `src/main.tsx:61:10` | `lint/complexity/noExcessiveCognitiveComplexity` | `stringifyHazardSearch` has cognitive complexity 42 (max 30) |

### Suggested fix

Refactor `stringifyHazardSearch` in `src/main.tsx` to reduce the function's
cognitive complexity below 30. Practical approaches:

- Extract the per-parameter serialization logic into smaller helpers, e.g.
  `appendHazardParam`, `appendArrayParams`, `appendBasinParam`,
  `appendPrecipMonthParam`.
- Use an array of serializer functions and iterate over it instead of a
  sequence of `if` blocks.
- Move the default-value filtering (e.g. skipping `precipMonth === 'anual'`)
  into the helper that handles precipitation months.

Example outline:

```ts
function appendHazardParam(params: URLSearchParams, search: Record<string, unknown>) {
  if (search.hazard === true || search.hazard === 1 || search.hazard === '1') {
    params.set('hazard', '1');
  }
}

function appendArrayParam(
  params: URLSearchParams,
  key: string,
  value: unknown,
) {
  if (!Array.isArray(value)) return;
  for (const item of value) {
    params.append(key, String(item));
  }
}

function appendStringParam(
  params: URLSearchParams,
  key: string,
  value: unknown,
  defaultValue?: string,
) {
  if (typeof value !== 'string') return;
  if (value !== '' && value !== defaultValue) {
    params.set(key, value);
  }
}

export function stringifyHazardSearch(search: Record<string, unknown>): string {
  const params = new URLSearchParams();
  appendHazardParam(params, search);
  appendArrayParam(params, 'riskClasses', search.riskClasses);
  appendArrayParam(params, 'layers', search.layers);
  appendStringParam(params, 'basin', search.basin);
  appendStringParam(params, 'precipMonth', search.precipMonth, 'anual');
  return params.toString();
}
```

This keeps the serialization behavior identical while satisfying the project's
complexity rule.

## final_verdict

- **Backend geo tests**: PASS
- **Frontend typecheck**: PASS
- **Frontend unit tests**: PASS
- **Frontend lint**: PASS WITH WARNINGS (1 new warning)

Overall: **PASS WITH WARNINGS**. The multi-hazard viewer changes are
functionally verified and safe to merge once the new lint warning is addressed
or explicitly accepted.