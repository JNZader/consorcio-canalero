import { test, expect, request } from '@playwright/test';

// storageState inyectado via global-setup + playwright.local.config.ts

const API_BASE = process.env.E2E_API_BASE ?? 'http://localhost:8000';

test.describe('Flood Flow Panel (UI)', () => {
  test('admin puede navegar a /admin/flood-flow', async ({ page }) => {
    await page.goto('/admin/flood-flow');
    await page.waitForTimeout(3000);

    const url = page.url();
    expect(url).not.toContain('/login');
  });

  test('panel renderiza con titulo correcto', async ({ page }) => {
    await page.goto('/admin/flood-flow');
    await page.waitForTimeout(3000);

    const heading = page.getByText('Estimación de Caudal (Método Racional)');
    await expect(heading).toBeVisible({ timeout: 10000 });
  });

  test('boton Calcular Caudal esta visible', async ({ page }) => {
    await page.goto('/admin/flood-flow');
    await page.waitForTimeout(3000);

    const btn = page.getByRole('button', { name: /calcular caudal/i });
    await expect(btn).toBeVisible({ timeout: 10000 });
  });

  test('boton Calcular Caudal empieza deshabilitado (sin zonas ni fecha)', async ({ page }) => {
    await page.goto('/admin/flood-flow');
    await page.waitForTimeout(3000);

    // El botón está disabled hasta que el usuario seleccione zonas
    const btn = page.getByRole('button', { name: /calcular caudal/i });
    await expect(btn).toBeDisabled({ timeout: 10000 });
  });

  test('MultiSelect de zonas esta visible', async ({ page }) => {
    await page.goto('/admin/flood-flow');
    await page.waitForTimeout(3000);

    // El MultiSelect de Mantine renderiza un input con placeholder
    const select = page.getByPlaceholder(/seleccioná una o más zonas/i)
      .or(page.getByText(/zonas operativas/i).first());
    await expect(select.first()).toBeVisible({ timeout: 10000 });
  });

  test('DatePickerInput esta visible con fecha por defecto', async ({ page }) => {
    await page.goto('/admin/flood-flow');
    await page.waitForTimeout(3000);

    // Label del DatePickerInput
    const label = page.getByText(/fecha del evento de lluvia/i);
    await expect(label).toBeVisible({ timeout: 10000 });
  });

  test('nav item Caudal Estimado esta en el menu lateral', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(3000);

    const navItem = page.getByText('Caudal Estimado');
    await expect(navItem).toBeVisible({ timeout: 10000 });
  });

  test('nav item Caudal Estimado navega a /admin/flood-flow', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(3000);

    await page.getByText('Caudal Estimado').click();
    await page.waitForTimeout(2000);

    expect(page.url()).toContain('/admin/flood-flow');
  });

  test.skip('calcular caudal con zonas reales requiere GEE activo', async ({ page }) => {
    // El endpoint POST /api/v2/geo/hydrology/flood-flow llama GEE (SRTM + Sentinel-2).
    // Se skipea en CI/CD sin credenciales GEE activas.
    void page;
  });
});

test.describe('Flood Flow API', () => {
  test('GET /geo/hydrology/flood-flow/{zona_id} retorna 422 con UUID invalido', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });

    const res = await ctx.get('/api/v2/geo/hydrology/flood-flow/not-a-uuid', {
      headers: { Authorization: `Bearer ${process.env.E2E_ADMIN_TOKEN ?? ''}` },
    });

    // UUID invalido → 422 Unprocessable Entity
    expect([422, 404]).toContain(res.status());
    await ctx.dispose();
  });

  test('POST /geo/hydrology/flood-flow con body vacio retorna 422', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });

    const adminEmail = process.env.E2E_ADMIN_EMAIL ?? 'e2e@test.com';
    const adminPassword = process.env.E2E_ADMIN_PASSWORD ?? 'e2etest123';

    // Login para obtener token
    const loginRes = await ctx.post('/api/v2/auth/jwt/login', {
      form: { username: adminEmail, password: adminPassword },
    });

    if (!loginRes.ok()) {
      test.skip(true, 'No se pudo autenticar — saltear test de API');
      return;
    }

    const loginData = await loginRes.json() as { access_token: string };
    const token = loginData.access_token;

    const res = await ctx.post('/api/v2/geo/hydrology/flood-flow', {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      data: {},
    });

    expect(res.status()).toBe(422);
    await ctx.dispose();
  });

  test('POST /geo/hydrology/flood-flow con zona_ids vacio retorna 422', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });

    const adminEmail = process.env.E2E_ADMIN_EMAIL ?? 'e2e@test.com';
    const adminPassword = process.env.E2E_ADMIN_PASSWORD ?? 'e2etest123';

    const loginRes = await ctx.post('/api/v2/auth/jwt/login', {
      form: { username: adminEmail, password: adminPassword },
    });

    if (!loginRes.ok()) {
      test.skip(true, 'No se pudo autenticar — saltear test de API');
      return;
    }

    const loginData = await loginRes.json() as { access_token: string };
    const token = loginData.access_token;

    const res = await ctx.post('/api/v2/geo/hydrology/flood-flow', {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      data: { zona_ids: [], fecha_lluvia: '2024-01-01' },
    });

    // zona_ids con min_length=1 → 422
    expect(res.status()).toBe(422);
    await ctx.dispose();
  });

  test.skip('POST /geo/hydrology/flood-flow con zona valida retorna FloodFlowResponse', async () => {
    // Requiere GEE activo + zonas en la base de datos.
    // Correr manualmente con: npx playwright test flood-flow --grep "zona valida"
  });
});
