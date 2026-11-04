import { expect, type Page, test } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers/overflow';
import { type ColorSchemeName, dynamicMasks, openStableRoute } from './helpers/page';

const VIEWPORTS = [
  { name: '360', width: 360, height: 800 },
  { name: '768', width: 768, height: 1024 },
  { name: '1280', width: 1280, height: 800 },
] as const;

const THEMES = ['light', 'dark'] as const satisfies readonly ColorSchemeName[];

const ROUTES = [
  { slug: 'home', path: '/' },
  { slug: 'mapa', path: '/mapa' },
  { slug: 'participacion-reportes', path: '/participacion' },
  { slug: 'participacion-sugerencias', path: '/participacion?tab=sugerencias' },
  { slug: 'privacidad', path: '/privacidad' },
  { slug: 'not-found', path: '/no-existe-visual-regression' },
  { slug: 'login', path: '/login' },
] as const;

async function waitForRoute(page: Page, slug: (typeof ROUTES)[number]['slug']) {
  if (slug === 'home') {
    await expect(
      page.getByRole('heading', { name: 'Consorcio Canalero 10 de Mayo' })
    ).toBeVisible();
    await expect(
      page.locator('[class*="statCard"]').filter({ hasText: 'Área total del consorcio' })
    ).toContainText('88.484');
    await expect(
      page.locator('[class*="statCard"]').filter({ hasText: 'Red de caminos rurales' })
    ).toContainText('1.280');
    await expect(
      page.locator('[class*="statCard"]').filter({ hasText: 'Canales existentes relevados' })
    ).toContainText('2');
    return;
  }

  if (slug === 'mapa') {
    await expect(page.getByRole('heading', { name: 'Mapa Interactivo' })).toBeVisible();
    await expect(page.getByText('No hay imagen satelital seleccionada')).toBeVisible();
    await expect(page.locator('.maplibregl-canvas').first()).toBeVisible();
    return;
  }

  if (slug === 'participacion-reportes') {
    await expect(page.getByRole('heading', { name: 'Participación' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Nuevo Reporte' })).toBeVisible();
    await expect(
      page
        .getByRole('application', { name: 'Mapa interactivo para seleccionar ubicación' })
        .locator('canvas')
    ).toBeVisible();
    return;
  }

  if (slug === 'participacion-sugerencias') {
    await expect(page.getByRole('heading', { name: 'Enviar Sugerencia' })).toBeVisible();
    await expect(page.locator('.maplibregl-canvas').first()).toBeVisible();
    return;
  }

  if (slug === 'privacidad') {
    await expect(page.getByRole('heading', { name: 'Política de Privacidad' })).toBeVisible();
    return;
  }

  if (slug === 'not-found') {
    await expect(page.getByRole('heading', { name: 'Página no encontrada' })).toBeVisible();
    return;
  }

  await expect(page.getByRole('heading', { name: 'Iniciar Sesión' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Email' })).toBeVisible();
}

test.describe('regresión visual de rutas públicas', () => {
  for (const viewport of VIEWPORTS) {
    for (const theme of THEMES) {
      for (const route of ROUTES) {
        test(`${route.slug} ${viewport.name} ${theme}`, async ({ page }) => {
          await openStableRoute(page, route.path, theme, viewport);
          await waitForRoute(page, route.slug);

          if (viewport.width === 360) {
            await expectNoHorizontalOverflow(page);
          }

          await expect(page).toHaveScreenshot(`${route.slug}-${viewport.name}-${theme}.png`, {
            fullPage: true,
            animations: 'disabled',
            caret: 'hide',
            mask: dynamicMasks(page),
          });
        });
      }
    }
  }
});
