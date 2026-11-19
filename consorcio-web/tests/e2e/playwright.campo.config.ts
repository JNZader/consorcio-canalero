import { defineConfig, devices } from '@playwright/test';

/**
 * Campo (PR 6, S8) — the offline field-map suite.
 *
 * Its OWN config because the campo journey is deliberately UNauthenticated
 * (the local e2e harness's global-setup logs in an admin and the storage
 * state would drag cookies into what must be a public, anonymous surface),
 * and because it starts the dev server itself when none is running.
 */
export default defineConfig({
  testDir: '.',
  testMatch: /campo-offline\.spec\.ts/,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    ...devices['Desktop Chrome'],
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [{ name: 'chromium' }],
});
