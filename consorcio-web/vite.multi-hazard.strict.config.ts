/**
 * vite.multi-hazard.strict.config.ts
 * ────────────────────────────────────
 * Dedicated Vite DEV-server config for the Multi-Hazard STRICT Playwright harness
 * (`tests/e2e/playwright.multi-hazard.strict.config.ts`).
 *
 * WHY A SEPARATE CONFIG (not CLI flags)
 *   Passing `--host`/`--port`/`--strictPort` on the `vite` CLI makes Vite treat
 *   the resolved config as "changed" and RE-OPTIMIZE the whole dependency tree on
 *   every run. For this large app (maplibre, mantine, react) that optimization
 *   holds the first request until it finishes — longer than any reasonable
 *   webServer timeout — so Playwright's health-check times out. A committed,
 *   STABLE config file keeps Vite's dep-optimization cache valid run-to-run.
 *
 *   The feature flag is passed as a SHELL ENV VAR in the Playwright webServer
 *   command (`VITE_FEATURE_MULTI_HAZARD_VIEWER=true`). Env vars do not change
 *   Vite's resolved config, so they do not trigger re-optimization either.
 *
 * Binds 127.0.0.1 (IPv4 loopback) on 5188 so Playwright's health-check (which
 * resolves the url to 127.0.0.1) and the dev server agree on the same stack.
 */

import { defineConfig } from 'vite';
import baseConfig from './vite.config';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  ...baseConfig,
  // The Playwright webServer launches this command from `tests/e2e/` (its
  // config rootDir), so Vite's DEFAULT `root` (= process.cwd()) resolves to
  // `tests/e2e/` — which has no `index.html`, so the dev server answers 404
  // on `/` and Playwright's health-check never passes (run times out). A
  // RELATIVE `root: '.'` would ALSO be resolved against cwd (= `tests/e2e/`)
  // and fail the same way. Pin `root` to this config file's OWN directory as
  // an ABSOLUTE path so the app entry is always served regardless of the cwd
  // Playwright spawns the server from.
  root: fileURLToPath(new URL('.', import.meta.url)),
  server: {
    // Keep the base proxy (so non-mocked /api calls still route like prod),
    // but pin host/port/strictPort here instead of via CLI flags.
    ...(baseConfig.server ?? {}),
    host: '127.0.0.1',
    port: 5188,
    strictPort: true,
  },
});
