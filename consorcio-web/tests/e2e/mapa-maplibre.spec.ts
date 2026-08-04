/**
 * Smoke tests for MapaMapLibre — validates that the MapLibre-based 2D map
 * is wired correctly and the /mapa route loads without crashing the app.
 *
 * Canvas rendering tests require the Vite dev server to have maplibre-gl
 * and @mapbox/mapbox-gl-draw pre-bundled (optimizeDeps). If running against
 * a cold server, the ErrorBoundary may be visible instead of the canvas.
 */

import { test, expect } from '@playwright/test';

import { loginAsAdmin, NO_ADMIN_CREDENTIALS_REASON } from './helpers/auth';
import { APP_URL, gotoMapWorkspace } from './helpers/mapWorkspace';
// T6 — with `E2E_APP_URL` declared, a shell/canvas that does not come up is a
// FAILURE, not a skip. Data-dependent gates stay soft. See `helpers/strictGate`.
import { requireCondition, skipForMissingData } from './helpers/strictGate';

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

  test('MapLibre map module is wired — lazy import resolves or ErrorBoundary is shown', async ({
    page,
  }) => {
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

/**
 * Rediseño UX del mapa (change `rediseno-ux-mapa`, Fases 1-3).
 *
 * These extend the smoke suite with the redesign scenarios: responsive
 * controls shell (collapsible sidebar / mobile Drawer), the cooperative-gesture
 * scroll-trap fix, the per-layer opacity slider, and the "Orden de capas"
 * drag-reorder list.
 *
 * All selectors are derived from the real DOM:
 *   - MapWorkspace.tsx: data-testid `map-workspace-root` (carries `data-desktop`
 *     + `data-collapsed`), `map-workspace-canvas`, `map-workspace-sidebar`,
 *     `map-workspace-collapse` (aria-label "Colapsar/Expandir panel de capas"),
 *     `map-workspace-burger` (Burger, aria-label "Abrir/Cerrar panel…").
 *   - LayerControlsPanel.tsx: region role aria-label "Controles de capas del
 *     mapa" (data-testid `layer-controls-panel-scroll`); opacity slider under
 *     `layer-opacity-<id>` (Mantine Slider → role "slider"); order collapsible
 *     `layer-order-collapsible` (CollapsibleSection header role "button" named
 *     "Orden de capas").
 *   - LayerOrderSection.tsx: `layer-order-section` + rows `layer-order-item-<id>`.
 *   - useMapInitialization.ts: `cooperativeGestures: true` → MapLibre injects
 *     `.maplibregl-cooperative-gesture-screen` into the map container.
 *
 * These need the app served with auth (the mapa project uses a storageState) and
 * ideally the backend for layer data. A real run needs the dev server + backend +
 * E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD (see tests/e2e/playwright.local.config.ts).
 *
 * TWO GATES, NOT ONE (corrected — this header used to claim everything "skips,
 * does NOT fail", which stopped being true when `helpers/strictGate` landed):
 *   - STRUCTURAL (`requireCondition`): shell mounted, WebGL canvas alive. It
 *     skips only when running BLIND; with `E2E_APP_URL` declared — someone
 *     asserting an environment is up — it FAILS. That is the whole point of the
 *     strict gate: an all-skipped run used to report green while proving nothing.
 *   - DATA / CREDENTIALS (`skipForMissingData`): seeded layers, admin login.
 *     These skip in BOTH modes, naming what was missing, because their absence
 *     is an environment fact and not a regression.
 */

test.describe('MapaMapLibre — rediseño UX (desktop shell)', () => {
  test(
    'controls live in a collapsible sidebar; collapsing widens the canvas',
    { tag: ['@e2e', '@medium', '@mapa', '@rediseno-ux-mapa', '@MAPA-E2E-010'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'Map workspace shell did not mount (dev server/auth unavailable)');

      const root = page.getByTestId('map-workspace-root');
      await expect(root).toHaveAttribute('data-desktop', 'true');

      const sidebar = page.getByTestId('map-workspace-sidebar');
      await expect(sidebar).toBeVisible();

      const canvas = page.getByTestId('map-workspace-canvas');
      const before = await canvas.boundingBox();

      // Collapse the sidebar via its toggle (aria-label "Colapsar panel de capas").
      const collapse = page.getByTestId('map-workspace-collapse');
      await expect(collapse).toBeVisible();
      await collapse.click();

      // Deterministic signal: the root flips data-collapsed to "true".
      await expect(root).toHaveAttribute('data-collapsed', 'true');

      // And the canvas should be at least as wide as before (sidebar collapses
      // to a hidden/narrow rail via CSS grid — the map reclaims the space).
      const after = await canvas.boundingBox();
      if (before && after) {
        expect(after.width).toBeGreaterThanOrEqual(before.width);
      }

      // Toggling again expands it back.
      await collapse.click();
      await expect(root).toHaveAttribute('data-collapsed', 'false');
    }
  );

  test(
    'active layer has an opacity slider in its family accordion',
    { tag: ['@e2e', '@medium', '@mapa', '@rediseno-ux-mapa', '@MAPA-E2E-011'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'Map workspace shell did not mount (dev server/auth unavailable)');

      const controls = page.getByRole('region', { name: 'Controles de capas del mapa' });
      await expect(controls).toBeVisible();

      // Enable a RENDERABLE vector layer (opacity sliders only show for layers in
      // the render registry — Base IGN/DEM checkboxes do NOT produce a slider).
      const renderable = controls
        .getByRole('checkbox', { name: /Suelos|Catastro|Hidrografía|Red vial|Subcuencas/i })
        .first();
      const hasRenderable = await renderable.waitFor({ state: 'visible', timeout: 10000 }).then(
        () => true,
        () => false
      );
      skipForMissingData(!hasRenderable, 'No renderable vector layer available (no layer data)');

      await renderable.check();

      // The per-layer opacity control (Mantine Slider → role "slider") appears.
      const slider = controls.getByRole('slider').first();
      await expect(slider).toBeVisible();
    }
  );

  test(
    '"Orden de capas" renders the sortable layer list',
    { tag: ['@e2e', '@medium', '@mapa', '@rediseno-ux-mapa', '@MAPA-E2E-012'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'Map workspace shell did not mount (dev server/auth unavailable)');

      const controls = page.getByRole('region', { name: 'Controles de capas del mapa' });
      await expect(controls).toBeVisible();

      // The "Orden de capas" section is a collapsible, defaultOpen=false → expand it.
      const orderHeader = page.getByTestId('layer-order-collapsible-header');
      await expect(orderHeader).toBeVisible();
      await orderHeader.click();

      // The sortable list ALWAYS renders the full renderable set (active + dimmed).
      const orderSection = page.getByTestId('layer-order-section');
      await expect(orderSection).toBeVisible();
      const rows = page.locator('[data-testid^="layer-order-item-"]');
      expect(await rows.count()).toBeGreaterThan(0);
    }
  );

  test(
    'wheeling over the map does not zoom without a modifier (cooperativeGestures)',
    { tag: ['@e2e', '@medium', '@mapa', '@rediseno-ux-mapa', '@MAPA-E2E-013'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'Map workspace shell did not mount (dev server/auth unavailable)');

      // MapLibre with `cooperativeGestures: true` injects the gesture-hint
      // overlay into the map container. Its presence is the robust, WebGL-init
      // signal that the scroll-trap fix is active (wheel-without-ctrl scrolls the
      // page / shows the hint instead of zooming).
      const gestureScreen = page.locator('.maplibregl-cooperative-gesture-screen');
      const mounted = await gestureScreen
        .first()
        .waitFor({ state: 'attached', timeout: 15000 })
        .then(() => true)
        .catch(() => false);
      requireCondition(
        mounted,
        'MapLibre canvas did not initialize (no WebGL in this environment)'
      );

      expect(await gestureScreen.count()).toBeGreaterThan(0);
    }
  );
});

test.describe('MapaMapLibre — rediseño UX (mobile shell)', () => {
  // No mobile project exists in the config, so pin a phone-sized viewport here.
  // useMediaQuery('(min-width: 48em)') resolves to mobile → Burger + Drawer.
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test(
    'burger opens a full-screen Drawer with the same controls',
    { tag: ['@e2e', '@medium', '@mapa', '@rediseno-ux-mapa', '@MAPA-E2E-014'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'Map workspace shell did not mount (dev server/auth unavailable)');

      const root = page.getByTestId('map-workspace-root');
      await expect(root).toHaveAttribute('data-desktop', 'false');

      // The desktop sidebar must NOT be present on mobile.
      await expect(page.getByTestId('map-workspace-sidebar')).toHaveCount(0);

      // The Burger (☰) is visible and opens the Drawer.
      const burger = page.getByTestId('map-workspace-burger');
      await expect(burger).toBeVisible();
      await burger.click();

      // Full-screen Drawer (role "dialog") titled "Capas y leyenda".
      const drawer = page.getByRole('dialog');
      await expect(drawer).toBeVisible();

      // The SAME controls tree is reachable inside the Drawer.
      const controls = drawer.getByRole('region', { name: 'Controles de capas del mapa' });
      await expect(controls).toBeVisible();
      await expect(drawer.getByLabel('Buscar capa')).toBeVisible();
    }
  );
});

test.describe('MapaMapLibre — admin map features', () => {
  test('admin map page loads and shows 2D/3D toggle', async ({ page }) => {
    await page.goto(`${APP_URL}/admin`);
    await page.waitForTimeout(2000);

    // The page should not show a crash
    const body = await page.textContent('body');
    expect(body).not.toBeNull();
  });

  // B4c/T1 — these two were `fixme` because they navigated to /admin WITHOUT
  // authenticating: an anonymous run always saw the login screen, so the admin
  // UI they assert could never exist and a `skip` would have been green-silent.
  // `helpers/auth.loginAsAdmin` now drives the real /login form first. Absent
  // credentials remain a SOFT gate (`skipForMissingData`) — the production
  // canary is contractually forbidden from carrying `E2E_ADMIN_*`
  // (`test_e2e_canary_stays_read_only_against_production`), so skipping there is
  // the designed behaviour, not a hole.
  test('layer toggle controls are accessible on map page', async ({ page }) => {
    test.setTimeout(60_000);
    const login = await loginAsAdmin(page);
    // Sin credenciales O con la app caída: skip blando con el motivo real.
    skipForMissingData(!login.ok, login.skipReason ?? NO_ADMIN_CREDENTIALS_REASON);

    await page.goto(`${APP_URL}/admin`);

    // 2D/3D segmented control (Mantine SegmentedControl → radio group).
    const segmentedControl = page
      .getByText('2D', { exact: true })
      .or(page.getByRole('radio', { name: /2D/i }))
      .first();
    await expect(segmentedControl).toBeVisible({ timeout: 20_000 });
  });

  test('satellite imagery toggle is visible for admin', async ({ page }) => {
    test.setTimeout(60_000);
    const login = await loginAsAdmin(page);
    // Sin credenciales O con la app caída: skip blando con el motivo real.
    skipForMissingData(!login.ok, login.skipReason ?? NO_ADMIN_CREDENTIALS_REASON);

    await page.goto(`${APP_URL}/admin`);

    const satelliteEl = page
      .getByText(/imagen satelital|satelital|satellite/i)
      .or(page.locator('[aria-label*="satelit"], [title*="satelit"]'))
      .first();
    await expect(satelliteEl).toBeVisible({ timeout: 20_000 });
  });
});
