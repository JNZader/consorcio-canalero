import { expect, type Page, test } from '@playwright/test';
import { VISUAL_DEV_PORT } from './helpers/network';
import { expectNoHorizontalOverflow } from './helpers/overflow';
import { installDeterminism } from './helpers/page';

/**
 * Sesión de admin sintética, el mismo mecanismo que
 * `tests/accessibility/a11y.spec.ts` (`authenticateAdminSession`):
 * el adapter JWT lee `sessionStorage` sin red y sin credenciales.
 */
const MOCK_ADMIN = {
  id: 'admin-smoke-1',
  email: 'admin@example.com',
  nombre: 'Admin',
  apellido: 'Smoke',
  telefono: '',
  role: 'admin',
} as const;

const MOBILE = { width: 360, height: 800 } as const;

const EMPTY_PAGE = { items: [], total: 0, page: 1, limit: 10 };

const EMPTY_STATS = {
  pendiente: 0,
  en_revision: 0,
  en_agenda: 0,
  tratado: 0,
  descartado: 0,
  resuelto: 0,
  total: 0,
  ciudadanas: 0,
  internas: 0,
};

function corsHeaders(): Record<string, string> {
  return {
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
    'access-control-allow-headers': '*',
  };
}

async function seedMockAdmin(page: Page): Promise<void> {
  await page.addInitScript((user) => {
    try {
      window.localStorage.removeItem('consorcio_auth_logout_tombstone');
    } catch {
      // Storage bloqueado: la sesión de esta pestaña igual vive en sessionStorage.
    }
    window.sessionStorage.setItem('consorcio_auth_token', 'mock-admin-smoke-token');
    window.sessionStorage.setItem('consorcio_auth_user', JSON.stringify(user));
    window.localStorage.setItem(
      'cc-auth-storage',
      JSON.stringify({
        state: {
          user: { id: user.id, email: user.email },
          profile: {
            id: user.id,
            email: user.email,
            nombre: `${user.nombre} ${user.apellido}`,
            telefono: user.telefono,
            rol: user.role,
          },
        },
        version: 0,
      })
    );
  }, MOCK_ADMIN);
}

/**
 * Listados vacíos. No hay datos de personas ni de denuncias: el smoke
 * solo comprueba que el shell llega a cada bandeja.
 */
function isBackendApi(url: URL): boolean {
  const devServer =
    (url.hostname === 'localhost' || url.hostname === '127.0.0.1') && url.port === VISUAL_DEV_PORT;
  // `/src/lib/api/*.ts` vive en el dev server. Solo se stubbea el API.
  return !devServer && url.pathname.startsWith('/api/');
}

async function stubAdminApi(page: Page): Promise<void> {
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (!isBackendApi(url)) {
      await route.fallback();
      return;
    }
    if (route.request().method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: corsHeaders(), body: '' });
      return;
    }

    const path = url.pathname;
    let body: unknown = EMPTY_PAGE;
    if (path.includes('/proxima-reunion') || path.includes('/padron')) {
      body = [];
    } else if (path.includes('/stats')) {
      body = EMPTY_STATS;
    } else if (path.includes('/monitoring/dashboard')) {
      body = { ranking_cuencas: [], alertas: [], total_alertas: 0 };
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: corsHeaders(),
      body: JSON.stringify(body),
    });
  });
}

async function openAdmin(page: Page): Promise<void> {
  await page.setViewportSize(MOBILE);
  await installDeterminism(page, 'light');
  await seedMockAdmin(page);
  await stubAdminApi(page);
  await page.goto('/admin', { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
  await page.locator('#main-content').waitFor({ state: 'attached' });
}

test.describe('admin mobile 360', () => {
  test.use({
    viewport: { width: MOBILE.width, height: MOBILE.height },
    hasTouch: true,
    isMobile: true,
  });

  test('el shell navega a reportes, sugerencias y padrón sin desborde horizontal', async ({
    page,
  }) => {
    await openAdmin(page);

    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByRole('heading', { name: 'Panel de Gestión Integral' })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    await page.getByRole('button', { name: 'Abrir menú de navegación' }).click();
    await page.getByRole('link', { name: 'Participación' }).click();
    await expect(page).toHaveURL(/\/admin\/participacion/);
    await expect(page.getByRole('heading', { name: 'Participación Ciudadana' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Reportes' })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    await expect(page.getByText('No hay denuncias')).toBeVisible();
    await expectNoHorizontalOverflow(page);

    await page.getByRole('tab', { name: 'Sugerencias' }).click();
    await expect(page.getByRole('tab', { name: 'Sugerencias' })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    await expect(page.getByText('No hay sugerencias')).toBeVisible();
    await expectNoHorizontalOverflow(page);

    await page.getByRole('button', { name: 'Abrir menú de navegación' }).click();
    await page.getByRole('link', { name: 'Padrón', exact: true }).click();
    await expect(page).toHaveURL(/\/admin\/padron/);
    await expect(page.getByRole('heading', { name: 'Padrón de Consorcistas' })).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Buscar consorcistas' })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });
});
