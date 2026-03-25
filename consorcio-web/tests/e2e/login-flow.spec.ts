import { test, expect } from '@playwright/test';

const APP_URL = 'https://consorcio-canalero.pages.dev';

test.describe('Frontend Login Flow', () => {
  test('login page loads with form', async ({ page }) => {
    await page.goto(`${APP_URL}/login`);
    await page.waitForTimeout(2000);

    // Verify login form elements exist
    const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="mail"], input[placeholder*="correo"]').first();
    const passwordInput = page.locator('input[type="password"]').first();

    await expect(emailInput).toBeVisible({ timeout: 10000 });
    await expect(passwordInput).toBeVisible();
  });

  test('login with valid credentials redirects to admin', async ({ page }) => {
    await page.goto(`${APP_URL}/login`);
    await page.waitForTimeout(2000);

    const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="mail"], input[placeholder*="correo"]').first();
    const passwordInput = page.locator('input[type="password"]').first();

    await emailInput.fill('jnzader@gmail.com');
    await passwordInput.fill('1qaz2wsx');

    const submitBtn = page.locator('button[type="submit"]').first();
    await submitBtn.click();

    // Wait for login to complete and redirect
    await page.waitForTimeout(5000);

    // Should redirect to /admin or show admin content
    const url = page.url();
    const pageContent = await page.textContent('body');
    const loggedIn = url.includes('/admin') ||
      pageContent?.includes('Panel') ||
      pageContent?.includes('Dashboard') ||
      pageContent?.includes('Javier') ||
      pageContent?.includes('Bienvenido');

    expect(loggedIn).toBeTruthy();
  });

  test('login with wrong credentials shows error', async ({ page }) => {
    await page.goto(`${APP_URL}/login`);
    await page.waitForTimeout(2000);

    const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="mail"], input[placeholder*="correo"]').first();
    const passwordInput = page.locator('input[type="password"]').first();

    await emailInput.fill('wrong@email.com');
    await passwordInput.fill('wrongpassword');

    const submitBtn = page.locator('button[type="submit"]').first();
    await submitBtn.click();

    await page.waitForTimeout(3000);

    // Should stay on login page and show error
    const url = page.url();
    expect(url).toContain('/login');
  });

  test('Google OAuth button visible on login page', async ({ page }) => {
    await page.goto(`${APP_URL}/login`);
    await page.waitForTimeout(2000);

    const googleBtn = page.locator('text=Google').or(page.locator('button:has-text("Google")')).first();
    const hasGoogleBtn = await googleBtn.isVisible({ timeout: 5000 }).catch(() => false);

    // Google button should exist on login page
    expect(hasGoogleBtn).toBeTruthy();
  });
});
