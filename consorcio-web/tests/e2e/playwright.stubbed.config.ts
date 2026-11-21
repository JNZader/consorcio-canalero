import { defineConfig, devices } from '@playwright/test';

/**
 * Dedicated Playwright configuration for 100% network-stubbed local browser
 * flows (informe de area + campo offline). Never targets production URLs and
 * always starts a local Vite dev server on localhost so Geolocation + Cache API
 * run in a Chromium secure context without touching any live API.
 */
export default defineConfig({
  testDir: '.',
  testMatch: ['informe-area.spec.ts', 'campo-offline.spec.ts'],
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { outputFolder: '../../stubbed-e2e-report', open: 'never' }]],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5173 --strictPort',
    url: 'http://localhost:5173',
    reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: [{ name: 'chromium' }],
});
