/**
 * seedAuth.ts — deterministic, network-free auth seeding for E2E specs.
 *
 * Mirrors the pattern used in `rainfall-v2-detail.spec.ts` but extracted so
 * future hazard/analytics specs can reuse the same mock session instead of
 * copying the helper inline.
 *
 * The session is written to `sessionStorage` before the app boots, so the auth
 * store hydrates a logged-in user without any `/auth/jwt/login` POST. Use this
 * when the test only cares about role-gated UI, not the login form itself.
 */

import type { Page } from '@playwright/test';

/** Storage key written by `jwt-adapter.ts` on a successful login. */
export const TOKEN_KEY = 'consorcio_auth_token';

/** Storage key for the serialized user object. */
export const USER_KEY = 'consorcio_auth_user';

/** A dummy bearer token; no request actually reaches the backend. */
export const MOCK_TOKEN = 'e2e-mock-token-mhv';

/** AuthUser shape read by the jwt adapter (src/lib/auth/types.ts). */
export interface MockAuthUser {
  id: string;
  email: string;
  nombre: string;
  apellido: string;
  telefono: string;
  role: 'ciudadano' | 'operador' | 'admin';
}

export function makeUser(role: MockAuthUser['role'], email: string): MockAuthUser {
  return { id: `u-${role}-mhv`, email, nombre: role, apellido: 'Test', telefono: '', role };
}

/**
 * Seed a session in sessionStorage BEFORE the app boots. `getSession()` reads
 * storage offline (no network), so the store hydrates an authenticated user
 * without any backend call. Call it BEFORE `page.goto`.
 */
export async function seedAuth(page: Page, user: MockAuthUser): Promise<void> {
  await page.addInitScript(
    ({ tokenKey, userKey, token, user }) => {
      try {
        window.localStorage.removeItem('consorcio_auth_logout_tombstone');
      } catch {
        /* storage unavailable — nothing to clean */
      }
      window.sessionStorage.setItem(tokenKey, token);
      window.sessionStorage.setItem(userKey, JSON.stringify(user));
    },
    { tokenKey: TOKEN_KEY, userKey: USER_KEY, token: MOCK_TOKEN, user }
  );
}
