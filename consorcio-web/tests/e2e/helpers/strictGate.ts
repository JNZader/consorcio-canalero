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
 * True when the dedicated Multi-Hazard strict harness is active
 * (`MULTI_HAZARD_E2E_STRICT=1`, set by
 * `playwright.multi-hazard.strict.config.ts`). In that mode a feature/data gate
 * HARD-FAILS instead of skipping, because the harness starts the frontend with
 * the feature flag forced on and an absent toggle/control is a real regression,
 * never an environment fact.
 */
export const MULTI_HAZARD_STRICT_E2E = process.env.MULTI_HAZARD_E2E_STRICT === '1';

/**
 * Data/credential gate.
 *
 * Generic / canary runs: always skips (the feature flag, a seeded dataset or
 * admin credentials are environment facts, not regressions) with a message that
 * names what was missing — honest green when the env is simply not configured.
 *
 * Multi-Hazard strict harness (`MULTI_HAZARD_E2E_STRICT=1`): the soft-skip
 * branch is DISABLED. `condition === true` means "missing → skip"; here it means
 * "missing → FAIL", so a missing toggle/control can never mask a regression.
 */
export function skipForMissingData(condition: boolean, reason: string): void {
  if (MULTI_HAZARD_STRICT_E2E) {
    expect(
      !condition,
      `[strict multi-hazard] ${reason} — under the strict harness this MUST be present, not skipped`
    ).toBe(true);
    return;
  }
  test.skip(condition, `[datos/credenciales] ${reason}`);
}
