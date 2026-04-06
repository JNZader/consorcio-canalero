import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  timeout: 60000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  retries: 1,
  reporter: 'list',
  globalSetup: './global-setup.ts',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    storageState: 'tests/e2e/.auth/admin.json',
  },
  projects: [
    {
      name: 'chromium — authenticated',
      testMatch: /flood-calibration|canal-suggestions|flood-flow/,
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'tests/e2e/.auth/admin.json',
      },
    },
    {
      name: 'chromium — api',
      testMatch: /rainfall-api/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'chromium — other',
      testIgnore: /flood-calibration|canal-suggestions|flood-flow|rainfall-api/,
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
