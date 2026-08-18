/**
 * playwright.multi-hazard.strict.config.ts
 * ─────────────────────────────────────────
 * Committed, DETERMINISTIC, NON-SKIPPING harness for `multi-hazard.spec.ts`.
 *
 * THE DEFECT THIS FIXES
 *   The generic canary (`test:e2e:canary`, `tests/e2e/playwright.config.ts`)
 *   sets `E2E_APP_URL`, which flips `tests/e2e/helpers/strictGate.ts` into
 *   strict mode for *structural* gates (app shell, WebGL canvas). But the five
 *   operator Multi-Hazard tests still call `skipForMissingData`, which ALWAYS
 *   `test.skip`'s when the toggle is absent — so CI stays green with zero
 *   feature coverage whenever `VITE_FEATURE_MULTI_HAZARD_VIEWER` is not
 *   explicitly on (it defaults to `false` in `.env.example`). A temporary
 *   strict local config previously reached 6/6 but was removed, leaving the
 *   regression uncovered.
 *
 * THIS HARNESS
 *   - starts its OWN Vite dev server with `VITE_FEATURE_MULTI_HAZARD_VIEWER`
 *     forced on (committed default `true`; override `MULTI_HAZARD_VITE_FLAG`
 *     only to PROVE the gate — see the verification in the H3 report);
 *   - sets `MULTI_HAZARD_E2E_STRICT=1`, which makes `skipForMissingData` HARD
 *     FAIL instead of skipping. A missing toggle/control is a regression, never
 *     a silent green;
 *   - sets `E2E_APP_URL` so the structural `requireCondition` gate also fails
 *     rather than skips (mirrors the canary's strict mode);
 *   - runs ONLY `multi-hazard.spec.ts` — it never touches the unrelated e2e
 *     suite.
 *
 * PORT — 5188, dedicated to this harness, distinct from 5173 (local config) and
 * 5174 (accessibility config). `--strictPort` makes Vite fail if the port is
 * taken, so we never silently reuse a server started WITHOUT the feature flag.
 */

import { defineConfig, devices } from '@playwright/test';

// Declare the environment BEFORE Playwright spawns workers, so the spec and its
// helpers read it at module load: mapWorkspace reads E2E_APP_URL for APP_URL,
// and strictGate reads MULTI_HAZARD_E2E_STRICT to disable the soft-skip branch.
//
// NOTE: bind to 127.0.0.1 (IPv4 loopback), NOT `localhost`. Vite resolves
// `localhost` to `::1` (IPv6) on this host, while Playwright's webServer
// health-check resolves it to 127.0.0.1 (IPv4) — the mismatch makes the check
// time out. Pinning 127.0.0.1 on BOTH the url and the vite `--host` keeps them
// on the same stack (mirrors tests/accessibility/playwright.config.ts).
const STRICT_APP_URL = 'http://127.0.0.1:5188';
process.env.E2E_APP_URL = STRICT_APP_URL;
process.env.MULTI_HAZARD_E2E_STRICT = '1';

// Guard: this config EXISTS to disable soft-skips. If a future edit dropped the
// env assignment, fail loudly at load instead of silently regressing to a
// green-but-empty run.
if (process.env.MULTI_HAZARD_E2E_STRICT !== '1') {
  throw new Error(
    'multi-hazard strict config: MULTI_HAZARD_E2E_STRICT is not set — the soft-skip guard would be disabled'
  );
}

export default defineConfig({
  testDir: '.',
  testMatch: /multi-hazard\.spec\.ts/,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  // The strict harness must never be "green by skipping".
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: STRICT_APP_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: {
    // Committed default flag value is `true`. The `MULTI_HAZARD_VITE_FLAG`
    // override exists ONLY so verification can prove the soft-skip branch is
    // disabled: run with `MULTI_HAZARD_VITE_FLAG=false` and the operator tests
    // MUST fail, never skip. POSIX `${VAR:-default}` keeps the default on.
    //
    // The dev server uses a dedicated, STABLE vite config (`vite.multi-hazard.
    // strict.config.ts`) that pins host/port there (no CLI --host/--port). CLI
    // flags would make Vite re-optimize the whole dep tree every run and hold
    // this health-check request until it finishes. The feature flag is a SHELL
    // env var, which does NOT change Vite's resolved config and so never
    // triggers re-optimization either.
    command:
      'VITE_FEATURE_MULTI_HAZARD_VIEWER=${MULTI_HAZARD_VITE_FLAG:-true} npx vite --config ../../vite.multi-hazard.strict.config.ts',
    url: STRICT_APP_URL,
    // Cold dependency optimization of this large app (maplibre, mantine, react)
    // can exceed the default 120s on a fresh `.vite/deps` cache; a stable vite
    // config (see vite.multi-hazard.strict.config.ts) keeps the cache valid
    // run-to-run so this is only ever the first cold start.
    timeout: 300_000,
    reuseExistingServer: false,
    stdout: 'pipe',
    stderr: 'pipe',
  },
  projects: [
    {
      name: 'chromium — multi-hazard strict',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
