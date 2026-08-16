/**
 * playwright.rainfall-harness.config.ts (W4.3) — dedicated fail-closed config
 * for the rainfall multi-parcel E2E harness.
 *
 * The default `playwright.config.ts` is the SHARED project config (baseURL
 * pointing at production, CI retries, a single chromium project, list
 * reporter). This file is the HARNESS-only override the Python runner drives:
 *
 *   * Selects ONLY `rainfall-v2-detail.spec.ts` (testMatch). The existing 10
 *     tests + the ONE appended W7/W8 multi-context `test()` = exactly 11, the
 *     W9 collection gate. A `.only` anywhere is forbidden (`forbidOnly: true`
 *     unconditionally — a `.only` would drop discovery below 11 and turn the
 *     run into `HARNESS_ACCOUNTING_FAILURE`).
 *   * ONE worker, retries `0`: the W7/W8 state machine creates its own two
 *     contexts inside the single `test()`, so parallel workers would race on
 *     the disposable stack. Retries `0` is the design's hard accounting
 *     invariant (JD-DES-002 / RMEH-009-D) — a Playwright retry would hide a
 *     helper failure behind a second attempt.
 *   * JSON reporter to a runner-controlled path: `RMEH_PLAYWRIGHT_JSON` (the
 *     runner points it at `<evidence>/playwright-results.json`). The W9 result
 *     gate parses this file; `list` is kept for the human operator console.
 *   * Chromium only: RMEH-014-A bounds the browser scope. No trace/screenshots
 *     on success (`trace: 'retain-on-failure'`, `screenshot: 'only-on-failure'`)
 *     — passing traces are not retained; the JSON geometry/request evidence is
 *     sufficient and the handoff stays small.
 *
 * Invoked by the package.json `test:e2e:rainfall-harness` command (W4.4) and
 * by the Python runner's collection + execution gates (W9). The acceptance is
 * `playwright test -c <this file> --list` reporting the expected cardinality
 * (10 before W7; exactly 11 after).
 */
import { defineConfig } from '@playwright/test';

const harnessOutputJson =
  process.env.RMEH_PLAYWRIGHT_JSON ?? '.artifacts/rainfall-multi-parcel/playwright-results.json';

export default defineConfig({
  testDir: '.',
  testMatch: /rainfall-v2-detail\.spec\.ts$/,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: harnessOutputJson }]],
  use: {
    // The harness runner starts the frontend on a loopback origin and passes
    // the URL via baseURL (the spec internals use APP_URL from mapWorkspace).
    baseURL: process.env.RMEH_FRONTEND_URL ?? 'http://127.0.0.1:5174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'rainfall-harness',
      use: { browserName: 'chromium' },
    },
  ],
});