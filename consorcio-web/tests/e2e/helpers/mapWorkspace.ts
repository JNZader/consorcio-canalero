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
    const root = page.getByTestId('map-workspace-root');
    return await root.isVisible({ timeout: 15000 });
  } catch {
    return false;
  }
}
