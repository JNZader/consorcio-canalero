/**
 * Phase 4 / F4-C — End-to-end auth flow test.
 *
 * The existing ``login-flow.spec.ts`` covers the login form alone:
 * empty form renders, valid creds redirect, wrong creds keep you on
 * /login, Google OAuth button is present. It does NOT cover the
 * full session lifecycle — once logged in, can the user actually
 * reach a protected route? Does logout actually invalidate the
 * session? F4-D's auth-gate tests cover the BACKEND side (every
 * sensitive endpoint refuses unauthenticated callers); this spec
 * covers the FRONTEND side (the ``ProtectedRoute`` component
 * actually redirects, and the logout button actually clears state).
 *
 * Together with the backend gate they prove: an unauthenticated
 * caller is rejected by EITHER layer alone, so a regression in
 * one doesn't open a window.
 *
 * Runs against the live Cloudflare Pages deploy + the live Hetzner
 * backend, same as login-flow.spec.ts. The E2E admin seed credentials
 * are provided via E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD env vars
 * (same convention as helpers/auth.ts) — never committed to git.
 */

import { test, expect, type Page } from '@playwright/test';

import { loginAsAdmin } from './helpers/auth';

const APP_URL = 'https://consorcio-canalero.pages.dev';

// E2E admin credentials come from the environment — NEVER hardcode
// them here (this file is committed; the previous plaintext creds
// were rotated after being found in git history). Tests that need
// the admin seed self-skip when the vars are absent.
//
// Document these vars in consorcio-web/.env.example:
//   E2E_ADMIN_EMAIL=<seeded admin email>
//   E2E_ADMIN_PASSWORD=<seeded admin password>
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL;
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD;

// Generous per-condition timeout to absorb (a) Cloudflare Pages cold
// edge cache and (b) Hetzner backend cold-start + GEE auth on first
// hit. Applied to condition-based waits (waitForURL / toHaveURL),
// NOT as fixed sleeps.
const NAV_TIMEOUT_MS = 20_000;

/** Skip the current test unless the admin seed creds are configured. */
function requireAdminCreds(): void {
  test.skip(!ADMIN_EMAIL || !ADMIN_PASSWORD, 'set E2E_ADMIN_* env');
}

async function loginViaForm(page: Page): Promise<void> {
  // Diagnostic hook — only surfaces console errors so a flaky run
  // leaves breadcrumbs in the report. Cheap; never throws.
  page.on('console', (msg) => {
    if (msg.type() === 'error') console.log('[browser-console-error]', msg.text());
  });

  // B4c/T1: the form-filling + settle-wait it used to open-code now lives in
  // ``helpers/auth`` (shared with ``login-flow.spec.ts`` and the /mapa admin
  // tests). ``requireAdminCreds`` already skipped when the vars are missing, so
  // a ``false`` here would mean the two gates disagree.
  const login = await loginAsAdmin(page, { baseUrl: APP_URL });
  // This spec's SUBJECT is the session lifecycle, so an environment that cannot
  // log in is a failure here (unlike the /mapa admin tests, which skip): the
  // reason string names it — missing creds, unreachable app — and a rejected
  // password throws from the helper with the on-screen error.
  expect(login.ok, login.skipReason ?? '').toBe(true);
}

test.describe('E2E auth flow — login → protected → logout', () => {
  // Each test runs the login form again (fresh browser context per
  // Playwright default). Cloudflare cold edge + Hetzner cold-start
  // on first hit can blow past the 30s default per-test budget; bump
  // to 60s so the cold path still passes deterministically.
  test.setTimeout(60_000);

  test('login lands on a screen that proves authentication', async ({ page }) => {
    requireAdminCreds();
    await loginViaForm(page);
    const url = page.url();
    const body = (await page.textContent('body')) ?? '';

    // The app redirects logged-in admins to /admin (or directly to the
    // dashboard tab). The login screen redirects to landing on logout.
    // Either of these signals "authenticated" is enough for this test;
    // we don't pin the exact URL because the redirect target has
    // changed once already in the project's history and we don't want
    // a future copy/UX tweak to break this gate.
    const authenticatedSignals =
      url.includes('/admin') ||
      url.includes('/perfil') ||
      body.includes('Panel') ||
      body.includes('Dashboard') ||
      body.includes('Bienvenido') ||
      body.includes('Cerrar sesión') ||
      body.includes('Cerrar sesion');

    expect(authenticatedSignals).toBeTruthy();
  });

  test('protected /admin route is reachable after login', async ({ page }) => {
    requireAdminCreds();
    await loginViaForm(page);
    await page.goto(`${APP_URL}/admin`);

    // ProtectedRoute redirects to /login when the session is missing.
    // ``toHaveURL`` auto-retries: it passes as soon as the SPA settles
    // on /admin, and fails with a clear diff if we got bounced.
    await expect(page).toHaveURL(/\/admin/, { timeout: NAV_TIMEOUT_MS });
    expect(page.url()).not.toContain('/login');
  });

  // 3vr Opus-alt HIGH: the original "logout clears session" test had
  // a fallback that ran ``sessionStorage.clear()`` when the button
  // wasn't found, masking a future regression where the logout UI
  // disappears. Split into TWO tests so a missing button now fails
  // a dedicated assertion AND we still cover the protected-route
  // guard against cleared-storage independently.
  //
  // Implementation note: the admin UI hides the logout action inside
  // the user-avatar dropdown (the ``A Admin`` button in the topbar).
  // The two-step click — open dropdown → find logout item — pins
  // the UX, not just the underlying ``signOut`` call.
  test('logout BUTTON exists and clicking it leaves /admin', async ({ page }) => {
    requireAdminCreds();
    await loginViaForm(page);

    // Step 1: open the user menu. Match the avatar by its visible
    // text "Admin" since that's the role name; a future i18n swap
    // would need to update this and the assertions below in lockstep.
    const userMenuTrigger = page
      .locator('button:has-text("Admin"), [role="button"]:has-text("Admin")')
      .first();
    await expect(userMenuTrigger).toBeVisible({ timeout: 10_000 });
    await userMenuTrigger.click();

    // Step 2: the dropdown should now expose a logout entry. Accept
    // either "Cerrar sesión" (with accent) or "Salir" (alternative
    // wording the project has used at different points). Use a
    // generic menuitem locator since Mantine renders the dropdown
    // as a role=menu.
    const logoutItem = page
      .locator(
        '[role="menuitem"]:has-text("Cerrar"), button:has-text("Cerrar"), [role="menuitem"]:has-text("Salir"), button:has-text("Salir")'
      )
      .first();
    await expect(logoutItem).toBeVisible({ timeout: 5_000 });
    await logoutItem.click();

    // After clicking, the app should redirect away from /admin
    // (typically to / or /login). Condition-based wait instead of a
    // fixed sleep — resolves as soon as the redirect lands.
    await page.waitForURL((url) => !/\/admin/.test(url.pathname), {
      timeout: NAV_TIMEOUT_MS,
    });
    expect(page.url()).not.toMatch(/\/admin/);
  });

  test('protected route guard fires when session storage is gone', async ({ page }) => {
    // Independent of the logout button UI — this test only proves
    // the ProtectedRoute component itself re-redirects to /login when
    // the stored session vanishes, however that happens (logout,
    // session expiry, manual ``sessionStorage.clear()`` from devtools).
    requireAdminCreds();
    await loginViaForm(page);

    // Wait for the post-login navigation to finish before touching
    // storage — ``waitForLoadState('networkidle')`` ensures the JS
    // execution context for the destination page is stable, so
    // ``evaluate`` below doesn't race against an in-flight nav.
    await page.waitForLoadState('networkidle', { timeout: 15_000 });

    await page.evaluate(() => {
      window.sessionStorage.clear();
      window.localStorage.clear();
    });

    await page.goto(`${APP_URL}/admin`);

    // Wait for the guard's redirect by condition, not by clock.
    await expect(page).toHaveURL(/\/login/, { timeout: NAV_TIMEOUT_MS });
  });

  // F5-C gap closer: cross-tab session semantics. F4-E moved tokens to
  // sessionStorage which is per-tab — a new tab opened after login has
  // NO token. ProtectedRoute must redirect that tab to /login even
  // though Zustand's ``cc-auth-storage`` persists ``user`` / ``profile``
  // to localStorage (which IS shared across tabs). The bug we want to
  // catch is "frontend trusts localStorage user and lets the new tab
  // through despite the missing token".
  test('new tab opened after login is unauthenticated', async ({ context, page }) => {
    requireAdminCreds();
    await loginViaForm(page);
    await page.waitForLoadState('networkidle', { timeout: 15_000 });

    const newTab = await context.newPage();
    await newTab.goto(`${APP_URL}/admin`);

    // Token is per-tab; the new tab never received one, so the
    // guard must bounce it. Condition-based wait for the redirect.
    await expect(newTab).toHaveURL(/\/login/, { timeout: NAV_TIMEOUT_MS });
    await newTab.close();
  });

  // F5-C gap closer: ciudadano-role bounce. ProtectedRoute defaults to
  // ``allowedRoles=['admin', 'operador']``. A logged-in ciudadano hitting
  // /admin should see the ``UnauthorizedState`` ("Acceso Denegado"),
  // NOT be redirected to /login (the session IS valid; just the role
  // doesn't have access).
  test('ciudadano logged in cannot reach /admin', async ({ page, request }) => {
    // Register a fresh ciudadano on-the-fly. The /auth/register endpoint
    // auto-assigns role=ciudadano per production.spec.ts:281. Using a
    // throwaway email keeps this test independent of any seeded fixture
    // and self-cleaning at the DB layer (account is unused after).
    // ``@playwright.com`` (not ``.test``): Pydantic's email-validator
    // rejects reserved RFC 6761 TLDs like ``.test``. The existing
    // ``production.spec.ts`` uses the same domain for registration.
    const uniqueEmail = `f5c-citizen-${Date.now()}@playwright.com`;
    const password = 'TestCitizen123';
    const reg = await request.post('https://cc10demayo-api.javierzader.com/api/v2/auth/register', {
      data: {
        email: uniqueEmail,
        password,
        nombre: 'F5C',
        apellido: 'Citizen',
      },
    });
    expect(reg.status()).toBe(201);

    // Log in through the form (not the API) so the frontend session
    // hydration runs exactly as a real user. The ``waitFor`` on the
    // email input below already absorbs the Cloudflare cold-edge
    // first paint — no fixed settle sleep needed.
    await page.goto(`${APP_URL}/login`);
    const emailInput = page
      .locator(
        'input[type="email"], input[name="email"], input[placeholder*="mail"], input[placeholder*="correo"]'
      )
      .first();
    await emailInput.waitFor({ state: 'visible', timeout: 20_000 });
    await emailInput.fill(uniqueEmail);
    await page.locator('input[type="password"]').first().fill(password);
    await page.locator('button[type="submit"]').first().click();

    // Wait for the token to land (same trick as ``loginViaForm``).
    await page.waitForFunction(() => !!window.sessionStorage.getItem('consorcio_auth_token'), {
      timeout: 20_000,
    });

    await page.goto(`${APP_URL}/admin`);

    // Wait by condition: the role gate redirects AWAY from /admin.
    await page.waitForURL((url) => !/^\/admin($|\/)/.test(url.pathname), {
      timeout: NAV_TIMEOUT_MS,
    });

    // The contract: a ciudadano with a valid session reaching /admin
    // ends up SOMEWHERE OTHER than /admin (the project chose to
    // redirect to the public home instead of rendering the
    // ``UnauthorizedState`` inline — both are valid implementations,
    // but the redirect is what's live). Two asserts together pin it:
    //   - session stayed alive (no bounce to /login, that would mean
    //     "you have no session", not "you can't access this");
    //   - the URL is no longer /admin (the guard fired).
    const url = page.url();
    expect(url).not.toContain('/login');
    expect(url).not.toMatch(/\/admin($|\/)/);

    // Belt-and-suspenders: the token is still in sessionStorage, i.e.
    // the session itself survived — only the role gate kicked in.
    const tokenStillPresent = await page.evaluate(
      () => !!window.sessionStorage.getItem('consorcio_auth_token')
    );
    expect(tokenStillPresent).toBeTruthy();
  });
});

test.describe('F5-E reset-password code exchange', () => {
  // The backend's ``USE_ONE_TIME_CODES`` flag is OFF in prod today
  // (rollout sequenced — backend ships first, frontend follows in
  // this commit, then operations flips the flag). So we cannot test
  // the live exchange flow against a real email. Instead we test the
  // frontend contract from the SPA side:
  //   - ``?code=...`` triggers a loader state (the exchange call).
  //   - A bogus code is rejected by the backend with HTTP 400 →
  //     SPA degrades gracefully to the "invalid link" screen.
  test('reset-password with ?code= shows loader then "invalid link" on bad code', async ({
    page,
  }) => {
    await page.goto(`${APP_URL}/reset-password?code=NEVERWAS`);
    // The exchange call hits ``/auth/exchange-code`` which returns 400
    // for any bogus code. The SPA renders the loader for the
    // round-trip then falls through to the "invalid" Alert.
    await page.waitForLoadState('networkidle', { timeout: 15_000 });
    // Either the loader stayed visible (slow backend) or the
    // "invalid" alert is showing. Both are acceptable end states for
    // a bogus code. ``toContainText`` auto-retries, replacing the
    // previous fixed 2s sleep.
    await expect(page.locator('body')).toContainText(
      /verificando el enlace|enlace invalido|enlace invalid|expir/i,
      { timeout: 15_000 }
    );
    // What we DON'T want is the password form rendered (which would
    // mean the SPA proceeded with a missing token).
    const passwordInputVisible = await page
      .locator('input[type="password"]')
      .first()
      .isVisible()
      .catch(() => false);
    expect(passwordInputVisible).toBeFalsy();
  });

  test('reset-password with ?token= (legacy path) keeps working', async ({ page }) => {
    // Legacy fallback while ``USE_ONE_TIME_CODES=false``: the email
    // still embeds the long JWT in ``?token=``. The SPA must accept
    // it without hitting the exchange endpoint — same behaviour as
    // pre-F5-E. We use a junk JWT here; the API will reject it as
    // ``RESET_PASSWORD_BAD_TOKEN``, but only AFTER the password form
    // is rendered (proving the SPA didn't try to exchange).
    await page.goto(`${APP_URL}/reset-password?token=ey-invalid-but-renders-form`);
    await page.waitForLoadState('networkidle', { timeout: 15_000 });
    // The password input renders because the SPA treats ``?token=``
    // as already-valid for rendering purposes — actual validation
    // happens on submit.
    await expect(page.locator('input[type="password"]').first()).toBeVisible({ timeout: 10_000 });
  });
});

// Phase 5+ backlog (still deferred, harder to land):
//   - Token refresh cycle (silent JWT refresh after 15-min expiry) —
//     needs fake-clock or a real wait + retry; the spec already takes
//     ~50s, adding 16 min per test isn't viable. Worth wiring through
//     the API directly (POST /auth/jwt/refresh) in a separate spec
//     when the F2 refresh contract gets touched again.
//   - Mutating actions (POST/PATCH/DELETE) through UI — CSRF
//     middleware requires ``Content-Type: application/json``; a
//     frontend fetcher regression that drops the header would not
//     fail this spec because we only exercise reads. Wiring needs
//     a real mutating flow through a form component, which is more
//     test infrastructure than F5-C's scope.
