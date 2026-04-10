import { test, expect } from '@playwright/test';

// storageState ya inyectado via global-setup + playwright.local.config.ts

test.describe('Canal Suggestions Panel', () => {

  test('admin puede navegar a /admin/canal-suggestions', async ({ page }) => {
    await page.goto('/admin/canal-suggestions');
    await page.waitForTimeout(4000);

    const url = page.url();
    expect(url).not.toContain('/login');
  });

  test('panel renderiza con titulo correcto', async ({ page }) => {
    await page.goto('/admin/canal-suggestions');
    await page.waitForTimeout(4000);

    // Titulo real del componente
    const heading = page.getByText('Sugerencias de Red de Canales');
    await expect(heading).toBeVisible({ timeout: 10000 });
  });

  test('boton "Analizar Red" esta visible y habilitado', async ({ page }) => {
    await page.goto('/admin/canal-suggestions');
    await page.waitForTimeout(4000);

    const analyzeBtn = page.getByRole('button', { name: /analizar red/i });
    await expect(analyzeBtn).toBeVisible({ timeout: 10000 });
    await expect(analyzeBtn).toBeEnabled();
  });

  test('select de filtro por tipo esta visible', async ({ page }) => {
    await page.goto('/admin/canal-suggestions');
    await page.waitForTimeout(4000);

    // Mantine Select renderiza un combobox — buscar por role o por texto visible
    const filterSelect = page.getByRole('combobox').filter({ hasText: /tipo|todos/i })
      .or(page.locator('input[placeholder*="tipo"]'))
      .or(page.locator('[aria-label*="tipo"]'));
    await expect(filterSelect.first()).toBeVisible({ timeout: 10000 });
  });

  test('mapa Leaflet carga correctamente', async ({ page }) => {
    await page.goto('/admin/canal-suggestions');
    await page.waitForTimeout(5000);

    // Leaflet siempre renderiza con esta clase
    const leafletMap = page.locator('.leaflet-container');
    await expect(leafletMap).toBeVisible({ timeout: 15000 });
  });

  test.skip('trigger de analisis completo requiere GEE activo', async ({ page }) => {
    // El boton "Analizar Red" dispara un job Celery que necesita
    // Google Earth Engine + pgRouting. Se skipea en CI/CD sin GEE.
  });

  test.skip('filtrar por tipo muestra solo sugerencias del tipo seleccionado', async ({ page }) => {
    // Requiere que haya datos de sugerencias previos en la base de datos.
    // Sin un run previo de analisis, la tabla esta vacia.
  });

  test('flujo completo de corridor routing: calcular, guardar, aprobar y exportar', async ({ page }) => {
    let saved = false;
    let approved = false;
    let favorite = false;
    let geojsonExported = false;
    let pdfExported = false;

    const scenarioResponse = () => ({
      id: 'scenario-1',
      name: 'Escenario corredor test',
      profile: 'hidraulico',
      notes: 'Escenario generado por Playwright',
      approval_note: approved ? 'Validado en comité' : favorite ? 'Ajuste pendiente' : null,
      is_approved: approved,
      is_favorite: favorite,
      approved_at: approved ? '2026-04-10T12:00:00Z' : null,
      request_payload: {
        from_lon: -63.0,
        from_lat: -32.0,
        to_lon: -63.1,
        to_lat: -32.1,
        mode: 'raster',
        profile: 'hidraulico',
        corridor_width_m: 80,
        alternative_count: 1,
      },
      result_payload: {
        source: { id: 'raster-source' },
        target: { id: 'raster-target' },
        summary: {
          mode: 'raster',
          profile: 'hidraulico',
          total_distance_m: 1820,
          edges: 1,
          corridor_width_m: 80,
          penalty_factor: 2,
          cost_breakdown: {
            profile: 'hidraulico',
            avg_profile_factor: 0.86,
            edge_count_with_profile_factor: 1,
            max_profile_factor: 0.86,
            min_profile_factor: 0.86,
            avg_hydric_index: 72.4,
            hydric_features: 3,
            property_features: 2,
            weights: { slope: 0.35, hydric: 0.55, property: 0.1 },
          },
        },
        centerline: {
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              geometry: { type: 'LineString', coordinates: [[-63.0, -32.0], [-63.1, -32.1]] },
              properties: {},
            },
          ],
        },
        corridor: {
          type: 'Feature',
          geometry: {
            type: 'Polygon',
            coordinates: [[[-63.0, -32.0], [-63.1, -32.0], [-63.1, -32.1], [-63.0, -32.1], [-63.0, -32.0]]],
          },
          properties: { corridor_width_m: 80 },
        },
        alternatives: [],
      },
      created_at: '2026-04-10T10:00:00Z',
      updated_at: '2026-04-10T10:00:00Z',
    });

    await page.route('**/api/v2/geo/intelligence/suggestions/results**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, page: 1, limit: 100, batch_id: null }),
      });
    });

    await page.route('**/api/v2/geo/routing/corridor', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(scenarioResponse().result_payload),
      });
    });

    await page.route('**/api/v2/geo/routing/corridor/scenarios', async (route) => {
      const method = route.request().method();
      if (method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: saved ? [{
              id: 'scenario-1',
              name: 'Escenario corredor test',
              profile: 'hidraulico',
              notes: 'Escenario generado por Playwright',
              approval_note: approved ? 'Validado en comité' : favorite ? 'Ajuste pendiente' : null,
              is_approved: approved,
              is_favorite: favorite,
              version: 2,
              approved_at: approved ? '2026-04-10T12:00:00Z' : null,
              created_at: '2026-04-10T10:00:00Z',
            }] : [],
            total: saved ? 1 : 0,
            page: 1,
            limit: 20,
          }),
        });
        return;
      }
      saved = true;
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(scenarioResponse()),
      });
    });

    await page.route('**/api/v2/geo/routing/corridor/scenarios/scenario-1', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(scenarioResponse()),
      });
    });

    await page.route('**/api/v2/geo/routing/corridor/scenarios/scenario-1/approve', async (route) => {
      approved = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(scenarioResponse()),
      });
    });

    await page.route('**/api/v2/geo/routing/corridor/scenarios/scenario-1/unapprove', async (route) => {
      approved = false;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(scenarioResponse()),
      });
    });

    await page.route('**/api/v2/geo/routing/corridor/scenarios/scenario-1/favorite', async (route) => {
      const body = route.request().postDataJSON() as { is_favorite: boolean };
      favorite = body.is_favorite;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(scenarioResponse()),
      });
    });

    await page.route('**/api/v2/geo/routing/corridor/scenarios/scenario-1/geojson', async (route) => {
      geojsonExported = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ type: 'FeatureCollection', features: [] }),
      });
    });

    await page.route('**/api/v2/geo/routing/corridor/scenarios/scenario-1/pdf', async (route) => {
      pdfExported = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/pdf',
        body: 'fake-pdf',
      });
    });

    await page.goto('/admin/canal-suggestions');
    await expect(page.getByText('Corridor Routing')).toBeVisible({ timeout: 15000 });

    await page.getByRole('textbox', { name: 'Modo de cálculo' }).click();
    await page.getByRole('option', { name: /raster multi-criterio/i, hidden: true }).click();

    await page.getByLabel('Origen lon').fill('-63.0');
    await page.getByLabel('Origen lat').fill('-32.0');
    await page.getByLabel('Destino lon').fill('-63.1');
    await page.getByLabel('Destino lat').fill('-32.1');
    await page.getByLabel('Peso pendiente').fill('0.30');
    await page.getByLabel('Peso hidrología').fill('0.55');
    await page.getByLabel('Peso propiedad').fill('0.15');

    await page.getByRole('button', { name: /calcular corredor/i }).click();

    await expect(page.getByText('Raster multi-criterio').first()).toBeVisible();
    await expect(page.getByText('1.82 km')).toBeVisible();

    await page.getByLabel('Nombre del escenario').fill('Escenario corredor test');
    await page.getByRole('button', { name: /guardar escenario/i }).click();

    await expect(page.getByText('Escenario corredor test')).toBeVisible();
    await expect(page.getByText('v2')).toBeVisible();

    page.once('dialog', async (dialog) => dialog.accept('Validado en comité'));
    await page.getByRole('button', { name: /marcar aprobado/i }).click();
    await expect(page.getByText('Aprobado', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: /marcar favorito/i }).click();
    await expect(page.getByText('Favorito', { exact: true })).toBeVisible();

    page.once('dialog', async (dialog) => dialog.accept('Ajuste pendiente'));
    await page.getByRole('button', { name: /volver a borrador/i }).click();
    await expect(page.getByText('Borrador', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: /exportar geojson/i }).click();
    await page.getByRole('button', { name: /exportar pdf/i }).click();

    expect(favorite).toBeTruthy();
    expect(geojsonExported).toBeTruthy();
    expect(pdfExported).toBeTruthy();
  });
});
