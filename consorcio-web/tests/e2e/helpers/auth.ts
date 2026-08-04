/**
 * auth.ts — the ONE admin login used by the e2e suites.
 *
 * Three rules, all learned the hard way:
 *
 * 1. CREDENTIALS ARE ALWAYS A SOFT GATE. `strictGate.STRICT` turns STRUCTURAL
 *    failures (shell, canvas) into errors, never credential ones: a run without
 *    `E2E_ADMIN_*` proves nothing about the admin UI and must say so out loud
 *    (`skipForMissingData`), not fail. That is also what keeps the production
 *    canary honest — its workflow is FORBIDDEN from carrying admin credentials
 *    (`gee-backend/tests/test_ci_workflow_contracts.py::
 *    test_e2e_canary_stays_read_only_against_production`), so every admin test
 *    skips there BY DESIGN. A `false` outcome is that design, not a failure.
 *
 * 2. LOG IN THROUGH THE UI. The previous version of this file POSTed to
 *    `/auth/jwt/login` and injected the token into `sessionStorage`. It was
 *    dead code (nothing imported it), it hardcoded `http://localhost:8000`, and
 *    it asserted nothing about the login screen a real admin actually uses.
 *    This one drives the real form — the same flow `login-flow.spec.ts` and
 *    `auth-protected-flow.spec.ts` exercise, which now delegate here instead of
 *    keeping a third copy.
 *
 * 3. A FAILING LOGIN MUST SAY WHY (B4c fix round, RES-002/003). Two different
 *    "it didn't work" cases used to look identical — a raw timeout:
 *      · the app is not reachable at all (no dev server, wrong `E2E_APP_URL`)
 *        → `skipReason`, a SOFT skip, exactly like `gotoMapWorkspace`;
 *      · the app is up and rejected the credentials (rotated password, seed not
 *        applied) → we scrape the error the screen is already showing and put it
 *        in the thrown message, so a rotated password costs one glance instead
 *        of a debugging cycle.
 */

import type { Page } from '@playwright/test';

import { APP_URL } from './mapWorkspace';

/** Storage key written by `jwt-adapter.ts` on a successful login. */
export const TOKEN_KEY = 'consorcio_auth_token';

/**
 * Seeded admin credentials. NEVER hardcode them here (this file is committed;
 * the previous plaintext pair was rotated after being found in git history).
 * Documented in `consorcio-web/.env.example`.
 */
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL;
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD;

/** True when both admin env vars are set. */
export function hasAdminCredentials(): boolean {
  return !!ADMIN_EMAIL && !!ADMIN_PASSWORD;
}

/** The reason string to hand `skipForMissingData` when credentials are absent. */
export const NO_ADMIN_CREDENTIALS_REASON =
  'sin E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD (el canary corre sin credenciales a propósito)';

const emailLocator = (page: Page) =>
  page
    .locator(
      'input[type="email"], input[name="email"], input[placeholder*="mail"], input[placeholder*="correo"]'
    )
    .first();

export interface LoginAsAdminOptions {
  /**
   * Origin to log in against. Defaults to the same `E2E_APP_URL` every /mapa
   * spec uses; `login-flow.spec.ts` / `auth-protected-flow.spec.ts` pass their
   * own (they target the Cloudflare Pages deploy explicitly).
   */
  readonly baseUrl?: string;
  /** Budget for each condition-based wait. Cold edge + cold backend need room. */
  readonly timeoutMs?: number;
}

export interface LoginResult {
  /** The session is live. */
  readonly ok: boolean;
  /**
   * Why not, phrased for a skip message — `null` when `ok`. Both reasons are
   * ENVIRONMENTAL (no credentials / no reachable app); bad credentials never
   * land here, they throw.
   */
  readonly skipReason: string | null;
}

const OK: LoginResult = { ok: true, skipReason: null };

/**
 * Best-effort read of whatever error the login screen is showing.
 *
 * `LoginForm` raises a Mantine notification titled "Error al iniciar sesión"
 * with the API detail (or "Verifica tus credenciales") as its body. Anything we
 * find beats "waiting for … timed out".
 */
async function readLoginError(page: Page): Promise<string | null> {
  const candidates = [
    page.getByText(/error al iniciar sesi/i).first(),
    page.locator('[role="alert"]').first(),
    page.locator('.mantine-Notification-root').first(),
  ];
  for (const locator of candidates) {
    const text = await locator.textContent({ timeout: 2_000 }).catch(() => null);
    if (text?.trim()) return text.trim().replace(/\s+/g, ' ');
  }
  return null;
}

/**
 * Log in as the seeded admin through the real `/login` form.
 *
 * @returns `{ ok: false, skipReason }` — having touched nothing — when the
 * credentials are not configured or the app is unreachable, so the caller can
 * `skipForMissingData(...)`. `{ ok: true }` once the session is live.
 * @throws when the app IS reachable, credentials ARE configured and the login
 * still does not settle: whoever set the env vars asserted that this account
 * works, and the thrown message carries the on-screen error.
 */
export async function loginAsAdmin(
  page: Page,
  options: LoginAsAdminOptions = {}
): Promise<LoginResult> {
  if (!hasAdminCredentials()) return { ok: false, skipReason: NO_ADMIN_CREDENTIALS_REASON };

  const baseUrl = options.baseUrl ?? APP_URL;
  const timeout = options.timeoutMs ?? 20_000;

  // Same guard as `gotoMapWorkspace`: an unguarded `goto` throws
  // ERR_CONNECTION_REFUSED and turns a blind local run into an error instead of
  // the skip the caller is prepared for.
  const reached = await page
    .goto(`${baseUrl}/login`)
    .then(() => true)
    .catch(() => false);
  if (!reached) {
    return { ok: false, skipReason: `la app no responde en ${baseUrl}/login` };
  }

  const emailInput = emailLocator(page);
  const passwordInput = page.locator('input[type="password"]').first();
  const formVisible = await emailInput
    .waitFor({ state: 'visible', timeout })
    .then(() => true)
    .catch(() => false);
  if (!formVisible) {
    return { ok: false, skipReason: `la pantalla de login no montó en ${baseUrl}/login` };
  }

  await emailInput.fill(ADMIN_EMAIL!);
  await passwordInput.fill(ADMIN_PASSWORD!);

  await page.locator('button[type="submit"]').first().click();

  // Two valid completion signals, raced: the SPA navigated away from /login, or
  // the token landed in sessionStorage. Whichever lands first is enough — a
  // future change to either the redirect target or the storage key breaks ONE
  // branch instead of the whole helper.
  const settled = await Promise.any([
    page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout }),
    page.waitForFunction((key) => !!window.sessionStorage.getItem(key), TOKEN_KEY, {
      timeout,
    }),
  ])
    .then(() => true)
    .catch(() => false);

  if (!settled) {
    const onScreen = await readLoginError(page);
    throw new Error(
      `El login con E2E_ADMIN_EMAIL=${ADMIN_EMAIL} no prosperó en ${baseUrl}. ` +
        (onScreen
          ? `La pantalla dice: "${onScreen}" (¿contraseña rotada o seed sin aplicar?)`
          : 'La pantalla no mostró ningún error: el submit no llegó al backend o quedó colgado.')
    );
  }

  return OK;
}
