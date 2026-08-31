/**
 * Citizen / anonymous multi-hazard journeys on /mapa.
 *
 * READ-ONLY: no writes, no `E2E_ADMIN_*`. Safe for the production canary.
 * A shared `?hazard=&basin=&riskClasses=&precipMonth=` URL must still load
 * the map; operator-only hazard controls must stay hidden.
 */

import { expect, test } from '@playwright/test';

import { gotoMapWorkspace } from './helpers/mapWorkspace';
import { requireCondition } from './helpers/strictGate';

const SHARED_HAZARD_SEARCH = '?hazard=1&basin=shared-basin&riskClasses=Alto&precipMonth=03';

function operatorHazardUi(page: import('@playwright/test').Page) {
  return {
    toggle: page.getByRole('checkbox', { name: 'Visor de riesgos' }),
    desktop: page.getByTestId('hazard-controls-desktop'),
    desktopCollapsed: page.getByTestId('hazard-controls-desktop-collapsed'),
    mobileChip: page.getByTestId('hazard-controls-mobile-chip'),
    mobileSheet: page.getByTestId('hazard-controls-mobile-sheet'),
    badge: page.getByText('Visor de riesgos disponible'),
  };
}

async function expectNoOperatorHazardUi(page: import('@playwright/test').Page): Promise<void> {
  const ui = operatorHazardUi(page);
  await expect(ui.toggle).toHaveCount(0);
  await expect(ui.desktop).toHaveCount(0);
  await expect(ui.desktopCollapsed).toHaveCount(0);
  await expect(ui.mobileChip).toHaveCount(0);
  await expect(ui.mobileSheet).toHaveCount(0);
  await expect(ui.badge).toHaveCount(0);
}

test.describe('Multi-hazard — citizen /mapa', () => {
  test(
    'citizen /mapa has no operator hazard controls',
    { tag: ['@e2e', '@mapa', '@hazard', '@MHV-E2E-003'] },
    async ({ page }) => {
      // The helper waits 30s for the shell; keep headroom so a miss becomes
      // requireCondition skip instead of colliding with the default timeout.
      test.setTimeout(60_000);
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'Map workspace shell did not mount (dev server unavailable)');
      await expectNoOperatorHazardUi(page);
    }
  );

  test(
    'shared hazard URL still loads the map without operator controls',
    { tag: ['@e2e', '@mapa', '@hazard', '@MHV-E2E-004'] },
    async ({ page }) => {
      test.setTimeout(60_000);
      const ready = await gotoMapWorkspace(page, SHARED_HAZARD_SEARCH);
      requireCondition(ready, 'Map workspace shell did not mount for the shared URL');
      await expect(page.getByTestId('map-workspace-root')).toBeVisible();
      await expectNoOperatorHazardUi(page);
    }
  );
});
