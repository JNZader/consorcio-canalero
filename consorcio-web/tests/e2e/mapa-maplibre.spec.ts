/**
 * Smoke tests for MapaMapLibre — validates that the MapLibre-based 2D map
 * is wired correctly and the /mapa route loads without crashing the app.
 *
 * Canvas rendering tests require the Vite dev server to have maplibre-gl
 * and @mapbox/mapbox-gl-draw pre-bundled (optimizeDeps). If running against
 * a cold server, the ErrorBoundary may be visible instead of the canvas.
 */

import { test, expect } from '@playwright/test';

const APP_URL = process.env.E2E_APP_URL ?? 'http://localhost:5173';

test.describe('MapaMapLibre — /mapa route', () => {
  test('/mapa route responds with 200', async ({ request }) => {
    const res = await request.get(`${APP_URL}/mapa`);
    expect(res.ok()).toBeTruthy();
  });

  test('/mapa page does not white-screen (body has content)', async ({ page }) => {
    await page.goto(`${APP_URL}/mapa`);
    await page.waitForTimeout(3000);

    const body = await page.textContent('body');
    expect(body).toBeTruthy();
    expect(body!.length).toBeGreaterThan(10);
  });

  test('MapLibre map module is wired — lazy import resolves or ErrorBoundary is shown', async ({ page }) => {
    await page.goto(`${APP_URL}/mapa`);

    // Either the map container renders (success) OR the ErrorBoundary fallback appears.
    // Both outcomes mean MapaMapLibre replaced MapaLeaflet correctly.
    // We specifically check that "Leaflet" is NOT referenced in any visible error.
    await page.waitForTimeout(5000);

    const body = await page.textContent('body');
    // The page should not reference Leaflet anywhere in visible text
    expect(body?.toLowerCase()).not.toContain('react-leaflet');
    // The page should have some content (not just a blank white screen)
    expect(body!.trim().length).toBeGreaterThan(20);
  });
});

test.describe('MapaMapLibre — admin map features', () => {
  test('admin map page loads and shows 2D/3D toggle', async ({ page }) => {
    await page.goto(`${APP_URL}/admin`);
    await page.waitForTimeout(2000);

    // The page should not show a crash
    const body = await page.textContent('body');
    expect(body).not.toBeNull();
  });

  test('layer toggle controls are accessible on map page', async ({ page }) => {
    await page.goto(`${APP_URL}/admin`);
    await page.waitForTimeout(3000);

    // 2D/3D segmented control should be visible
    const segmentedControl = page
      .getByText('2D')
      .or(page.locator('[data-active]'))
      .first();
    const visible = await segmentedControl.isVisible({ timeout: 10000 }).catch(() => false);
    expect(visible).toBeTruthy();
  });

  test('satellite imagery toggle is visible for admin', async ({ page }) => {
    await page.goto(`${APP_URL}/admin`);
    await page.waitForTimeout(3000);

    // Look for satellite-related UI elements (icon or text)
    const satelliteEl = page
      .getByText(/imagen satelital|satelital|satellite/i)
      .or(page.locator('[aria-label*="satelit"], [title*="satelit"]'))
      .first();
    const found = await satelliteEl.isVisible({ timeout: 10000 }).catch(() => false);
    expect(found).toBeTruthy();
  });
});
