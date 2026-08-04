import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  timeout: 30000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  // 2 retries under CI only: the canary hits production cold with parallel
  // workers, and a first paint can legitimately exceed the shell timeout under
  // load. Locally keep 0 so flakes stay visible while developing.
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  use: {
    baseURL: 'https://consorcio-canalero.pages.dev',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
