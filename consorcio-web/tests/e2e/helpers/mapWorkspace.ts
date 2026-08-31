/**
 * mapWorkspace.ts — shared navigation helper for the /mapa e2e suites.
 *
 * Extracted from `mapa-maplibre.spec.ts` when `mapa-viewport-movil.spec.ts`
 * needed the same "go to /mapa and tell me whether the shell mounted" step. Two
 * copies would have drifted the moment the workspace testid changed.
 */

import type { Page } from '@playwright/test';

export const APP_URL = process.env.E2E_APP_URL ?? 'http://localhost:5173';

export interface HazardSearchParams {
  readonly hazard: string | null;
  readonly basin: string | null;
  readonly riskClasses: string | null;
  readonly precipMonth: string | null;
}

/** Decode the /mapa hazard query keys written by `toHazardSearch`. */
export function readHazardSearch(page: Page): HazardSearchParams {
  const url = new URL(page.url());
  return {
    hazard: url.searchParams.get('hazard'),
    basin: url.searchParams.get('basin'),
    riskClasses: url.searchParams.get('riskClasses'),
    precipMonth: url.searchParams.get('precipMonth'),
  };
}

/**
 * Navigate to /mapa (optional `?hazard=&basin=&riskClasses=&precipMonth=`)
 * and report whether the responsive workspace shell mounted.
 */
export async function gotoMapWorkspace(page: Page, search = ''): Promise<boolean> {
  // goto is inside the try: with no dev server listening it throws
  // ERR_CONNECTION_REFUSED, and an unguarded throw turns every blind local run
  // into an error instead of the skip that `requireCondition` promises.
  const query = search === '' ? '' : search.startsWith('?') ? search : `?${search}`;
  try {
    await page.goto(`${APP_URL}/mapa${query}`);
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
