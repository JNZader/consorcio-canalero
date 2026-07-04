import { test, expect } from '@playwright/test';

const APP_URL = 'https://consorcio-canalero.pages.dev';

// E2E admin credentials come from the environment — NEVER hardcode
// them here (this file is committed; the previous plaintext creds
// were rotated after being found in git history).
//
// Document these vars in consorcio-web/.env.example:
//   E2E_ADMIN_EMAIL=<seeded admin email>
//   E2E_ADMIN_PASSWORD=<seeded admin password>
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL;
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD;

// Storage key set by jwt-adapter.ts on successful login — used as a
// login-completed signal (same trick as auth-protected-flow.spec.ts).
const TOKEN_KEY = 'consorcio_auth_token';

const emailLocator = (page: import('@playwright/test').Page) =>
  page
    .locator(
      'input[type="email"], input[name="email"], input[placeholder*="mail"], input[placeholder*="correo"]'
    )
    .first();

test.describe('Frontend Login Flow', () => {
  test('login page loads with form', async ({ page }) => {
    await page.goto(`${APP_URL}/login`);

    // No fixed sleep — the visibility expectation below already
    // retries until the SPA hydrates (cold Cloudflare edge included).
    const emailInput = emailLocator(page);
    const passwordInput = page.locator('input[type="password"]').first();

    await expect(emailInput).toBeVisible({ timeout: 15_000 });
    await expect(passwordInput).toBeVisible();
  });

  test('login with valid credentials redirects to admin', async ({ page }) => {
    test.skip(!ADMIN_EMAIL || !ADMIN_PASSWORD, 'set E2E_ADMIN_* env');

    await page.goto(`${APP_URL}/login`);

    const emailInput = emailLocator(page);
    const passwordInput = page.locator('input[type="password"]').first();
    await emailInput.waitFor({ state: 'visible', timeout: 15_000 });

    await emailInput.fill(ADMIN_EMAIL!);
    await passwordInput.fill(ADMIN_PASSWORD!);

    const submitBtn = page.locator('button[type="submit"]').first();
    await submitBtn.click();

    // Condition-based wait: login is complete when EITHER the SPA
    // navigated away from /login OR the auth token landed in
    // sessionStorage — whichever happens first.
    await Promise.any([
      page.waitForURL((url) => !url.pathname.endsWith('/login'), {
        timeout: 20_000,
      }),
      page.waitForFunction(
        (key) => !!window.sessionStorage.getItem(key),
        TOKEN_KEY,
        { timeout: 20_000 }
      ),
    ]);

    // Should redirect to /admin or show admin content
    const url = page.url();
    const pageContent = await page.textContent('body');
    const loggedIn =
      url.includes('/admin') ||
      pageContent?.includes('Panel') ||
      pageContent?.includes('Dashboard') ||
      pageContent?.includes('Bienvenido');

    expect(loggedIn).toBeTruthy();
  });

  test('login with wrong credentials shows error', async ({ page }) => {
    await page.goto(`${APP_URL}/login`);

    const emailInput = emailLocator(page);
    const passwordInput = page.locator('input[type="password"]').first();
    await emailInput.waitFor({ state: 'visible', timeout: 15_000 });

    await emailInput.fill('wrong@email.com');
    await passwordInput.fill('wrongpassword');

    const submitBtn = page.locator('button[type="submit"]').first();
    await submitBtn.click();

    // A visible error message MUST be shown to the user — LoginForm
    // fires a Mantine notification titled "Error al iniciar sesion"
    // with fallback body "Verifica tus credenciales". Waiting on it
    // (instead of a fixed sleep) also absorbs backend latency.
    await expect(
      page.getByText(/error al iniciar sesi|verifica tus credenciales/i).first()
    ).toBeVisible({ timeout: 15_000 });

    // And we must still be on the login page.
    expect(page.url()).toContain('/login');
  });

  test('Google OAuth button visible on login page', async ({ page }) => {
    await page.goto(`${APP_URL}/login`);

    const googleBtn = page
      .locator('text=Google')
      .or(page.locator('button:has-text("Google")'))
      .first();

    // Auto-retrying assertion instead of fixed sleep + isVisible().
    await expect(googleBtn).toBeVisible({ timeout: 15_000 });
  });
});
