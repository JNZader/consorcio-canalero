import { test, expect } from '@playwright/test';

// storageState ya inyectado via global-setup + playwright.local.config.ts

test.describe('Flood Calibration Panel', () => {

  test('admin puede navegar a /admin/flood-calibration', async ({ page }) => {
    await page.goto('/admin/flood-calibration');
    await page.waitForTimeout(4000);

    const url = page.url();
    // Should NOT be redirected to login
    expect(url).not.toContain('/login');
  });

  test('panel de calibracion renderiza con titulo y calendario', async ({ page }) => {
    await page.goto('/admin/flood-calibration');
    await page.waitForTimeout(4000);

    // Titulo real del componente
    const heading = page.getByText('Calibracion de Modelo de Inundacion');
    await expect(heading).toBeVisible({ timeout: 10000 });
  });

  test('calendario muestra nombres de dias y navegacion de mes', async ({ page }) => {
    await page.goto('/admin/flood-calibration');
    await page.waitForTimeout(4000);

    // Navegacion del calendario (aria-labels del componente)
    const prevMonth = page.getByRole('button', { name: 'Mes anterior' });
    const nextMonth = page.getByRole('button', { name: 'Mes siguiente' });

    await expect(prevMonth).toBeVisible({ timeout: 10000 });
    await expect(nextMonth).toBeVisible({ timeout: 10000 });

    // Nombres de dias de la semana: Lu, Ma, Mi, Ju, Vi, Sa, Do
    await expect(page.getByText('Lu').first()).toBeVisible();
    await expect(page.getByText('Vi').first()).toBeVisible();
  });

  test('boton de entrenar modelo existe', async ({ page }) => {
    await page.goto('/admin/flood-calibration');
    await page.waitForTimeout(4000);

    // Texto del boton de entrenar (IconPlayerPlay)
    const trainBtn = page.getByRole('button', { name: /entrenar|train/i });
    await expect(trainBtn).toBeVisible({ timeout: 10000 });
  });

  test.skip('listar eventos flood requiere datos GEE reales precargados', async ({ page }) => {
    // El timeline de flood events solo aparece si hay datos en el backend
    // que dependan de Google Earth Engine. Se skipea en CI/CD sin GEE.
  });
});
