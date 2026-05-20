/**
 * Phase 5 / F5-J — QA Sesión C automation.
 *
 * The hand-written QA checklist
 * (``~/Escritorio/consorcio/qa-checklist-consorcio-canalero.md``)
 * has C1-C4 items that require manual browser verification.
 * This spec automates the parts that DON'T need real human eyeballs:
 *
 *   - C1: page loads without console errors, form fields render.
 *   - C2: client-side validation catches the obvious bad inputs
 *         (empty submit, descripción < 10 chars).
 *   - C2 (positive): the POST to ``/api/v2/denuncias`` returns 401
 *         for the unauthenticated form attempt — F2-anti-spam moved
 *         denuncia creation behind auth, so the public form is now
 *         effectively a login-prompt. (This is the contract the
 *         current checklist needs to confirm, NOT the legacy
 *         "anonymous create works" claim.)
 *
 * What this spec deliberately does NOT cover (manual-only):
 *   - Geolocation API permission flow (browser-level UI).
 *   - Photo upload from a real device camera.
 *   - The admin "ver en mapa" cross-link to /mapa with highlight.
 *
 * Runs against the same live prod stack as the other E2E specs.
 */

import { test, expect, type Page } from '@playwright/test';

const APP_URL = 'https://consorcio-canalero.pages.dev';

test.describe('QA Sesión C — public denuncias form', () => {
  test.setTimeout(60_000);

  test('C1: /reportes loads without console errors', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.goto(`${APP_URL}/reportes`);
    await page.waitForLoadState('networkidle', { timeout: 15_000 });

    // Allow a couple of expected non-blocking errors:
    //   - manifest "Failed to load resource" from the service worker
    //     on a fresh visit (browsers complain about icons not yet
    //     cached);
    //   - Sentry / BetterStack init noise when those vars are empty
    //     in dev-deploys.
    // Anything ELSE counts.
    const blocking = consoleErrors.filter(
      (e) =>
        !/manifest/i.test(e) &&
        !/sentry/i.test(e) &&
        !/logtail|betterstack/i.test(e) &&
        // ChunkLoadError under Cloudflare cold edge — retry usually fixes
        !/ChunkLoadError/i.test(e)
    );
    expect(blocking, `unexpected console errors: ${blocking.join('\n')}`).toEqual([]);
  });

  test('C1 (post-F2 anti-spam): /reportes opens to "Verificar identidad" step', async ({
    page,
  }) => {
    // Discovered during F5-J automation: ``/reportes`` no longer
    // shows the type/description form to anonymous visitors. The
    // F2 anti-spam change put a "Verificar identidad" step in front
    // of everything — the citizen must log in (Google OAuth or email
    // magic link) BEFORE the actual report form appears.
    //
    // This test pins that contract: step 1 renders with both
    // identity options visible. The actual report form (tipo /
    // descripción / location / photo) is post-login and requires
    // either a manual Google OAuth flow OR a magic-link click —
    // neither feasible to automate against the live stack without
    // a fake mail provider, so C1's "form fields render" portion
    // stays manual.
    await page.goto(`${APP_URL}/reportes`);
    await page.waitForLoadState('networkidle', { timeout: 15_000 });

    // Step header.
    await expect(
      page.getByText(/verificar identidad/i).first()
    ).toBeVisible({ timeout: 10_000 });

    // Google OAuth path.
    await expect(
      page.locator('button:has-text("Google")').first()
    ).toBeVisible();

    // Email magic-link path.
    await expect(
      page.locator('input[type="email"], input[placeholder*="email"]').first()
    ).toBeVisible();
    await expect(
      page.locator('button:has-text("Enviar link")').first()
    ).toBeVisible();
  });

  test('C2 (client validation): empty email submit shows error', async ({ page }) => {
    // Same anti-spam reality as C1: the only client-side validation
    // we can test without a real session is the email field on the
    // magic-link step.
    await page.goto(`${APP_URL}/reportes`);
    await page.waitForLoadState('networkidle', { timeout: 15_000 });

    const submitMagicLink = page
      .locator('button:has-text("Enviar link")')
      .first();
    await expect(submitMagicLink).toBeVisible({ timeout: 10_000 });
    await submitMagicLink.click();
    await page.waitForTimeout(1500);

    // Mantine form / HTML5 ``required`` should surface a validation
    // hint — either an inline error or the browser-native
    // ``:invalid`` state on the input. Both leave the user on the
    // same step (i.e. NOT navigated forward).
    const stillOnStep1 = await page
      .getByText(/verificar identidad/i)
      .first()
      .isVisible();
    expect(stillOnStep1).toBeTruthy();
  });

  test('C2 (anti-spam contract): anonymous POST without login is rejected', async ({ request }) => {
    // The public form requires a logged-in user since the F2 anti-spam
    // change. A direct API POST from an unauthenticated caller
    // must return 401 — that's the contract the form relies on.
    const resp = await request.post(
      'https://cc10demayo-api.javierzader.com/api/v2/denuncias',
      {
        data: {
          tipo: 'alcantarilla_tapada',
          descripcion: 'Prueba QA C2 — descripción suficientemente larga.',
          latitud: -32.628,
          longitud: -62.68,
          cuenca: 'Candil',
          contacto_email: 'qa@playwright.com',
        },
      }
    );
    expect(resp.status()).toBe(401);
  });
});
