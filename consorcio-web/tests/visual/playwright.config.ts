import { defineConfig, devices } from '@playwright/test';

/**
 * Regresión visual y e2e mobile de las rutas públicas.
 *
 * Las baselines se generan y se comparan en la imagen
 * `mcr.microsoft.com/playwright:v1.64.1-noble` (la misma que usa el job
 * `visual` de `.github/workflows/frontend.yml`). Tiene que coincidir con
 * `@playwright/test` en package-lock.json. Ver docs/visual-regression.md.
 */
const PORT = 5175;

export default defineConfig({
  testDir: '.',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  timeout: 90_000,
  expect: {
    timeout: 20_000,
    toHaveScreenshot: {
      animations: 'disabled',
      caret: 'hide',
      scale: 'css',
      maxDiffPixelRatio: 0,
    },
  },
  snapshotPathTemplate: '{testDir}/__screenshots__/{arg}-{platform}{ext}',
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  outputDir: 'test-results',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `http://127.0.0.1:${PORT}`,
    locale: 'es-AR',
    timezoneId: 'America/Argentina/Cordoba',
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      // Puerto de descarte: el browser no tiene un API real. Los stubs de
      // tests/visual/helpers/network.ts responden antes de que salga nada.
      VITE_API_URL: 'http://127.0.0.1:9',
      VITE_MARTIN_URL: 'http://127.0.0.1:9',
      VITE_SENTRY_DSN: '',
      VITE_LOGTAIL_TOKEN: '',
    },
  },
});
