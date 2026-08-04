/**
 * mapWorkspace.ts — shared navigation helper for the /mapa e2e suites.
 *
 * Extracted from `mapa-maplibre.spec.ts` when `mapa-viewport-movil.spec.ts`
 * needed the same "go to /mapa and tell me whether the shell mounted" step. Two
 * copies would have drifted the moment the workspace testid changed.
 */

import type { Page } from '@playwright/test';

export const APP_URL = process.env.E2E_APP_URL ?? 'http://localhost:5173';

/** Navigate to /mapa and report whether the responsive workspace shell mounted. */
export async function gotoMapWorkspace(page: Page): Promise<boolean> {
  // goto is inside the try: with no dev server listening it throws
  // ERR_CONNECTION_REFUSED, and an unguarded throw turns every blind local run
  // into an error instead of the skip that `requireCondition` promises.
  try {
    await page.goto(`${APP_URL}/mapa`);
    // waitFor, NOT isVisible: `isVisible()` returns IMMEDIATELY and ignores
    // its timeout option (Playwright API contract). With the old call the
    // helper asked "is it visible right now?" one tick after goto — against
    // production-sized chunks the answer was always "no", so every spec that
    // gated on this helper skipped forever and nobody noticed until the
    // strict gate turned those skips into failures.
    await page.getByTestId('map-workspace-root').waitFor({ state: 'visible', timeout: 30000 });
    return true;
  } catch {
    return false;
  }
}
