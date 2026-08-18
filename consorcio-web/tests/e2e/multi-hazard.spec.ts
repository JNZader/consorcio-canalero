/**
 * multi-hazard.spec.ts — PR-B4 end-to-end journey for the Multi-Hazard viewer.
 *
 * Validates the full operator flow: enable hazard mode, select a basin, hide a
 * risk class, switch the precipitation month, and restore the same state from a
 * shared URL in a fresh session. Also confirms citizens never see the toggle.
 *
 * DETERMINISM
 * ───────────
 * The backend surface is mocked at the network boundary (`page.route`):
 *   · `/api/v2/geo/basins` → a single deterministic basin (`candil`) with a
 *     known bounding box, so the basin selector is always populated.
 *   · `/api/v2/geo/layers?fuente=dem_pipeline` → deterministic
 *     `flood_risk`, `drainage_need` and `precip_normal` layers, so the tile URLs
 *     the map builds are predictable.
 *   · `/api/v2/geo/layers/{id}/tiles/{z}/{x}/{y}.png` → a transparent 1×1 PNG, while
 *     the test records the request URLs to assert `hide_ranges` and rescale
 *     params are sent.
 *
 * AUTH gate is seeded offline via `seedAuth` (sessionStorage seam read by the
 * jwt adapter). No `E2E_ADMIN_*` credentials and no login POST are required.
 *
 * FEATURE-FLAG gate: against the generic prod/canary config the toggle-absent
 * case is a soft skip (the flag may legitimately be off there). BUT the committed
 * strict harness — `playwright.multi-hazard.strict.config.ts` /
 * `npm run test:e2e:multi-hazard:strict` — starts Vite with
 * `VITE_FEATURE_MULTI_HAZARD_VIEWER=true` and sets `MULTI_HAZARD_E2E_STRICT=1`,
 * which turns `skipForMissingData` into a HARD FAILURE. So under the strict
 * harness a missing toggle/control FAILS CI instead of soft-skipping green.
 */

import { type Page, expect, test } from '@playwright/test';

import { APP_URL } from './helpers/mapWorkspace';
import { makeUser, seedAuth } from './helpers/seedAuth';
import { requireCondition, skipForMissingData } from './helpers/strictGate';

/** Transparent 1×1 PNG served for every intercepted raster tile request. */
const TRANSPARENT_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==',
  'base64'
);

interface HazardMockRegistration {
  readonly tileRequests: Array<{ url: string; method: string }>;
}

function mockBasinsEndpoint(page: Page): void {
  page.route(/\/api\/v2\/geo\/basins\?/, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            id: 'candil',
            properties: { id: 'candil', nombre: 'Cuenca Candil' },
            geometry: {
              type: 'Polygon',
              coordinates: [
                [
                  [-62.6, -32.6],
                  [-62.4, -32.6],
                  [-62.4, -32.4],
                  [-62.6, -32.4],
                  [-62.6, -32.6],
                ],
              ],
            },
            bbox: [-62.6, -32.6, -62.4, -32.4],
          },
        ],
      }),
    });
  });
}

function mockGeoLayersEndpoint(page: Page): void {
  page.route(/\/api\/v2\/geo\/layers\?.*fuente=dem_pipeline/, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            id: 'geo-flood-risk',
            nombre: 'Riesgo de Inundacion',
            tipo: 'flood_risk',
            fuente: 'dem_pipeline',
            formato: 'tif',
            area_id: null,
            created_at: '2026-01-01T00:00:00Z',
            metadata_extra: {},
          },
          {
            id: 'geo-drainage-need',
            nombre: 'Necesidad de Drenaje',
            tipo: 'drainage_need',
            fuente: 'dem_pipeline',
            formato: 'tif',
            area_id: null,
            created_at: '2026-01-01T00:00:00Z',
            metadata_extra: {},
          },
          {
            id: 'geo-precip-normal-anual',
            nombre: 'Precipitacion normal anual',
            tipo: 'precip_normal',
            fuente: 'dem_pipeline',
            formato: 'tif',
            area_id: null,
            created_at: '2026-01-01T00:00:00Z',
            metadata_extra: { mes: 'anual' },
          },
          {
            id: 'geo-precip-normal-01',
            nombre: 'Precipitacion normal enero',
            tipo: 'precip_normal',
            fuente: 'dem_pipeline',
            formato: 'tif',
            area_id: null,
            created_at: '2026-01-01T00:00:00Z',
            metadata_extra: { mes: '01' },
          },
        ],
      }),
    });
  });
}

function mockTileProxy(page: Page, registration: HazardMockRegistration): void {
  page.route(/\/api\/v2\/geo\/layers\/[^/]+\/tiles\/\d+\/\d+\/\d+\.png/, async (route) => {
    registration.tileRequests.push({
      url: route.request().url(),
      method: route.request().method(),
    });

    await route.fulfill({
      status: 200,
      contentType: 'image/png',
      body: TRANSPARENT_PNG,
    });
  });
}

function mockHazardApi(page: Page): HazardMockRegistration {
  const registration: HazardMockRegistration = { tileRequests: [] };
  mockBasinsEndpoint(page);
  mockGeoLayersEndpoint(page);
  mockTileProxy(page, registration);
  return registration;
}

function isRiskLayerTile(url: string): boolean {
  return /\/layers\/(geo-flood-risk|geo-drainage-need)\/tiles\//.test(url);
}

async function gotoMapWorkspace(page: Page, path = '/mapa'): Promise<boolean> {
  try {
    await page.goto(`${APP_URL}${path}`);
    await page.getByTestId('map-workspace-root').waitFor({ state: 'visible', timeout: 30_000 });
    return true;
  } catch {
    return false;
  }
}

async function expectHazardToggle(page: Page): Promise<boolean> {
  const toggle = page.getByTestId('hazard-mode-toggle');
  return toggle.waitFor({ state: 'visible', timeout: 5_000 }).then(
    () => true,
    () => false
  );
}

test.describe('Multi-Hazard — full operator flow', () => {
  test(
    'operator can enable hazard mode and sees controls + legend',
    { tag: ['@e2e', '@high', '@mapa', '@multi-hazard-viewer', '@MHV-E2E-001'] },
    async ({ page }) => {
      mockHazardApi(page);
      await seedAuth(page, makeUser('operador', 'operador@e2e.local'));

      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'Map workspace shell no montó (dev server/auth no disponible)');

      const toggleVisible = await expectHazardToggle(page);
      skipForMissingData(
        !toggleVisible,
        'Multi-Hazard toggle no disponible (VITE_FEATURE_MULTI_HAZARD_VIEWER puede estar desactivado)'
      );

      await page.getByTestId('hazard-mode-toggle').click();
      await expect(page).toHaveURL(/[?&]hazard=1/);

      await expect(page.getByTestId('hazard-controls-desktop')).toBeVisible();
      await expect(page.getByTestId('hazard-risk-classes-legend')).toContainText('Crítico');
      await expect(page.getByTestId('hazard-precip-legend')).toBeVisible();
    }
  );

  test(
    'basin selection updates URL and the legend shows the selected basin',
    { tag: ['@e2e', '@high', '@mapa', '@multi-hazard-viewer', '@MHV-E2E-002'] },
    async ({ page }) => {
      mockHazardApi(page);
      await seedAuth(page, makeUser('operador', 'operador@e2e.local'));

      const ready = await gotoMapWorkspace(page, '/mapa?hazard=1');
      requireCondition(ready, 'Map workspace shell no montó (dev server/auth no disponible)');

      const toggleVisible = await expectHazardToggle(page);
      skipForMissingData(
        !toggleVisible,
        'Multi-Hazard toggle no disponible (VITE_FEATURE_MULTI_HAZARD_VIEWER puede estar desactivado)'
      );

      await expect(page.getByTestId('hazard-controls-desktop')).toBeVisible();

      // Open the basin selector and pick the mocked basin.
      await page.getByTestId('hazard-basin-select').click();
      await page.getByRole('option', { name: 'Cuenca Candil' }).click();

      await expect(page).toHaveURL(/[?&]basin=candil/);
      await expect(page.getByTestId('hazard-basin-legend')).toContainText('Cuenca Candil');
    }
  );

  test(
    'hiding a risk class updates the URL and tile requests include hide_ranges',
    { tag: ['@e2e', '@high', '@mapa', '@multi-hazard-viewer', '@MHV-E2E-003'] },
    async ({ page }) => {
      const registration = mockHazardApi(page);
      await seedAuth(page, makeUser('operador', 'operador@e2e.local'));

      const ready = await gotoMapWorkspace(page, '/mapa?hazard=1');
      requireCondition(ready, 'Map workspace shell no montó (dev server/auth no disponible)');

      const toggleVisible = await expectHazardToggle(page);
      skipForMissingData(
        !toggleVisible,
        'Multi-Hazard toggle no disponible (VITE_FEATURE_MULTI_HAZARD_VIEWER puede estar desactivado)'
      );

      await expect(page.getByTestId('hazard-controls-desktop')).toBeVisible();

      // Wait until the map has requested at least one risk-layer tile with all
      // classes visible (no hide_ranges param).
      await expect
        .poll(() => registration.tileRequests.some((r) => isRiskLayerTile(r.url)))
        .toBe(true);
      const requestsBefore = registration.tileRequests.filter(
        (r) => isRiskLayerTile(r.url) && !r.url.includes('hide_ranges')
      );
      expect(requestsBefore.length).toBeGreaterThan(0);

      // Uncheck "Crítico" — RISK_CLASS_LABELS index 3.
      await page.getByTestId('hazard-risk-class-crítico').uncheck();
      await expect(page).toHaveURL(/[?&]riskClasses=/);

      // The next tile requests for flood_risk / drainage_need must carry hide_ranges=3.
      await expect
        .poll(() =>
          registration.tileRequests.some(
            (r) => isRiskLayerTile(r.url) && r.url.includes('hide_ranges=3')
          )
        )
        .toBe(true);

      // The panel shows the "some classes hidden" hint.
      await expect(page.getByTestId('hazard-risk-filter-hint')).toContainText(
        'Algunas clases ocultas'
      );
    }
  );

  test(
    'shared URL reproduces mode, basin, risk classes and precipitation month in a fresh session',
    { tag: ['@e2e', '@high', '@mapa', '@multi-hazard-viewer', '@MHV-E2E-004'] },
    async ({ page, context }) => {
      mockHazardApi(page);
      await seedAuth(page, makeUser('operador', 'operador@e2e.local'));

      const stateUrl =
        '/mapa?hazard=1&basin=candil&riskClasses=Bajo&riskClasses=Medio&riskClasses=Alto&precipMonth=03';
      const ready = await gotoMapWorkspace(page, stateUrl);
      requireCondition(ready, 'Map workspace shell no montó (dev server/auth no disponible)');

      const toggleVisible = await expectHazardToggle(page);
      skipForMissingData(
        !toggleVisible,
        'Multi-Hazard toggle no disponible (VITE_FEATURE_MULTI_HAZARD_VIEWER puede estar desactivado)'
      );

      await expect(page.getByTestId('hazard-controls-desktop')).toBeVisible();
      // Mantine Select renders the selected label in the input's `value`
      // attribute, not the raw option value.
      await expect(page.getByTestId('hazard-basin-select')).toHaveValue('Cuenca Candil');
      await expect(page.getByTestId('hazard-risk-class-crítico')).not.toBeChecked();
      await expect(page.getByTestId('hazard-risk-class-bajo')).toBeChecked();
      await expect(page.getByTestId('hazard-precip-month-select')).toHaveValue('Marzo');

      // Copy the absolute URL and open it in a brand-new page (same browser
      // context is enough to prove shareability; storage is clean on newPage).
      const url = page.url();
      const freshPage = await context.newPage();
      mockHazardApi(freshPage);
      await seedAuth(freshPage, makeUser('operador', 'operador2@e2e.local'));
      await freshPage.goto(url);

      await expect(freshPage.getByTestId('hazard-controls-desktop')).toBeVisible();
      await expect(freshPage.getByTestId('hazard-basin-select')).toHaveValue('Cuenca Candil');
      await expect(freshPage.getByTestId('hazard-risk-class-crítico')).not.toBeChecked();
      await expect(freshPage.getByTestId('hazard-precip-month-select')).toHaveValue('Marzo');
    }
  );

  test(
    'precipitation month switch reaches the tile URL with month-specific rescale',
    { tag: ['@e2e', '@high', '@mapa', '@multi-hazard-viewer', '@MHV-E2E-005'] },
    async ({ page }) => {
      const registration = mockHazardApi(page);
      await seedAuth(page, makeUser('operador', 'operador@e2e.local'));

      const ready = await gotoMapWorkspace(page, '/mapa?hazard=1');
      requireCondition(ready, 'Map workspace shell no montó (dev server/auth no disponible)');

      const toggleVisible = await expectHazardToggle(page);
      skipForMissingData(
        !toggleVisible,
        'Multi-Hazard toggle no disponible (VITE_FEATURE_MULTI_HAZARD_VIEWER puede estar desactivado)'
      );

      await expect(page.getByTestId('hazard-controls-desktop')).toBeVisible();

      // Default annual should use rescale_max=1800.
      await expect
        .poll(() =>
          registration.tileRequests.some(
            (r) => r.url.includes('geo-precip-normal-anual') && r.url.includes('rescale_max=1800')
          )
        )
        .toBe(true);

      // Switch to January.
      await page.getByTestId('hazard-precip-month-select').click();
      await page.getByRole('option', { name: 'Enero' }).click();
      await expect(page).toHaveURL(/[?&]precipMonth=01/);

      // January tiles should use rescale_max=200.
      await expect
        .poll(() =>
          registration.tileRequests.some(
            (r) => r.url.includes('geo-precip-normal-01') && r.url.includes('rescale_max=200')
          )
        )
        .toBe(true);
    }
  );
});

test.describe('Multi-Hazard — role gate', () => {
  test(
    'ciudadano user does not see the Multi-Hazard toggle or controls',
    { tag: ['@e2e', '@high', '@mapa', '@multi-hazard-viewer', '@MHV-E2E-006'] },
    async ({ page }) => {
      mockHazardApi(page);
      await seedAuth(page, makeUser('ciudadano', 'ciudadano@e2e.local'));

      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'Map workspace shell no montó (dev server/auth no disponible)');

      await expect(page.getByTestId('hazard-mode-toggle')).toHaveCount(0);
      await expect(page.getByTestId('hazard-controls-desktop')).toHaveCount(0);

      // Even with hazard=1 in the URL, the role gate must keep it off.
      await page.goto(`${APP_URL}/mapa?hazard=1`);
      await expect(page.getByTestId('hazard-mode-toggle')).toHaveCount(0);
      await expect(page).not.toHaveURL(/[?&]hazard=1/);
    }
  );
});
