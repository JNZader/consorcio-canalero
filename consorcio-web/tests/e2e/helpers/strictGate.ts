/**
 * strictGate.ts — "skip" must never be a synonym for "green".
 *
 * The /mapa e2e specs guard every step with `test.skip(...)`, which is honest
 * when the suite runs blind (no environment declared) and DISHONEST when it does
 * not: a run where the app shell never mounts reported all-skipped, i.e. a green
 * suite that proved nothing.
 *
 * `E2E_APP_URL` is the declaration: whoever set it asserted that an environment
 * is up. In that mode a structural gate (shell mounted, WebGL canvas alive) FAILS
 * instead of skipping. Gates that depend on DATA or CREDENTIALS (a seeded
 * catastro, an admin login, a feature flag) keep skipping in both modes with a
 * message that names what was missing — those are legitimately environmental.
 *
 * Extracted from `mapa-viewport-movil.spec.ts`, which pioneered the pattern.
 */

import { expect, test } from '@playwright/test';

/** True when the caller declared a live environment via `E2E_APP_URL`. */
export const STRICT = !!process.env.E2E_APP_URL;

/**
 * Structural gate: fails in a declared environment, skips when running blind.
 * Use for anything whose failure means the APP is broken (shell, canvas).
 */
export function requireCondition(condition: boolean, reason: string): void {
  if (STRICT) {
    expect(condition, `${reason} (E2E_APP_URL set -> this MUST work)`).toBe(true);
    return;
  }
  test.skip(!condition, reason);
}

/**
 * Data/credential gate: always skips, in both modes, but says so out loud.
 * Use for seeded datasets, feature flags and admin credentials — their absence
 * is an environment fact, not a regression.
 */
export function skipForMissingData(condition: boolean, reason: string): void {
  test.skip(condition, `[datos/credenciales] ${reason}`);
}
