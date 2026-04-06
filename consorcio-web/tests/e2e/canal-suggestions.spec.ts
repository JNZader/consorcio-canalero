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
});
