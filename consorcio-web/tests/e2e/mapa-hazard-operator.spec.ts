/**
 * Operator multi-hazard journeys on /mapa.
 *
 * NOT in the production canary: these log in through `loginAsAdmin`, and
 * `test_e2e_canary_stays_read_only_against_production` forbids `E2E_ADMIN_*`.
 * Credentials and the feature-flag toggle stay `skipForMissingData`. The
 * workspace shell is a structural `requireCondition` gate.
 */

import { expect, test } from '@playwright/test';

import { loginAsAdmin, NO_ADMIN_CREDENTIALS_REASON } from './helpers/auth';
import { gotoMapWorkspace, readHazardSearch } from './helpers/mapWorkspace';
import { requireCondition, skipForMissingData } from './helpers/strictGate';

const SHARED_RISK_CLASSES = 'Alto,Crítico';
const SHARED_PRECIP_MONTH = '03';

async function loginToMap(page: import('@playwright/test').Page): Promise<void> {
  test.setTimeout(60_000);
  const login = await loginAsAdmin(page);
  skipForMissingData(!login.ok, login.skipReason ?? NO_ADMIN_CREDENTIALS_REASON);
}

async function requireVisorToggle(page: import('@playwright/test').Page) {
  const toggle = page.getByRole('checkbox', { name: 'Visor de riesgos' });
  const visible = await toggle
    .waitFor({ state: 'visible', timeout: 10_000 })
    .then(() => true)
    .catch(() => false);
  skipForMissingData(
    !visible,
    'Visor de riesgos no visible (VITE_FEATURE_MULTI_HAZARD_VIEWER off or role gate closed)'
  );
  return toggle;
}

async function expandDesktopHazardControls(page: import('@playwright/test').Page): Promise<void> {
  const expanded = page.getByTestId('hazard-controls-desktop');
  const collapsed = page.getByTestId('hazard-controls-desktop-collapsed');
  const mounted = await expanded
    .or(collapsed)
    .waitFor({ state: 'visible', timeout: 10_000 })
    .then(() => true)
    .catch(() => false);
  requireCondition(mounted, 'Hazard controls did not mount after enabling the visor');
  if (await collapsed.isVisible()) {
    await page.getByRole('button', { name: 'Expandir controles de riesgos' }).click();
  }
  await expect(expanded).toBeVisible();
}

test.describe('Multi-hazard — operator /mapa', () => {
  test(
    'operator sees hazard controls on /mapa after enabling the visor',
    { tag: ['@e2e', '@mapa', '@hazard', '@MHV-E2E-001'] },
    async ({ page }) => {
      await loginToMap(page);
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'Map workspace shell did not mount (dev server/auth unavailable)');

      const toggle = await requireVisorToggle(page);
      if (!(await toggle.isChecked())) {
        await toggle.check();
      }

      await expandDesktopHazardControls(page);
      const controls = page.getByTestId('hazard-controls-desktop');
      await expect(controls.getByLabel('Seleccionar cuenca')).toBeVisible();
      await expect(controls.getByText('Clases de riesgo')).toBeVisible();
      await expect(controls.getByLabel('Periodo de precipitación')).toBeVisible();
      await expect(controls.getByRole('button', { name: 'Restablecer' })).toBeVisible();
    }
  );

  test(
    'shared /mapa URL keeps hazard, basin, riskClasses and precipMonth after load',
    { tag: ['@e2e', '@mapa', '@hazard', '@MHV-E2E-002'] },
    async ({ page }) => {
      await loginToMap(page);
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'Map workspace shell did not mount (dev server/auth unavailable)');

      const toggle = await requireVisorToggle(page);
      if (!(await toggle.isChecked())) {
        await toggle.check();
      }
      await expandDesktopHazardControls(page);

      await page.getByLabel('Seleccionar cuenca').click();
      const basinOption = page.getByRole('option').filter({ hasNotText: /^Mostrar todo$/ }).first();
      const hasBasin = await basinOption
        .waitFor({ state: 'visible', timeout: 10_000 })
        .then(() => true)
        .catch(() => false);
      skipForMissingData(!hasBasin, 'Basin catalog not seeded');
      await basinOption.click();

      await expect.poll(() => readHazardSearch(page).basin, { timeout: 15_000 }).not.toBeNull();
      const basin = readHazardSearch(page).basin;
      expect(basin).toBeTruthy();

      const shared = new URLSearchParams({
        hazard: '1',
        basin: basin as string,
        riskClasses: SHARED_RISK_CLASSES,
        precipMonth: SHARED_PRECIP_MONTH,
      });
      const reloaded = await gotoMapWorkspace(page, `?${shared.toString()}`);
      requireCondition(reloaded, 'Map workspace shell did not remount for the shared URL');

      await expect.poll(() => readHazardSearch(page).hazard, { timeout: 15_000 }).toBe('1');
      await expect.poll(() => readHazardSearch(page).basin).toBe(basin);
      await expect.poll(() => readHazardSearch(page).precipMonth).toBe(SHARED_PRECIP_MONTH);
      await expect.poll(() => readHazardSearch(page).riskClasses).toBe(SHARED_RISK_CLASSES);
    }
  );
});
