import { test, expect, request } from '@playwright/test';

const API_BASE = process.env.E2E_API_BASE ?? 'http://localhost:8000';

async function getToken(ctx: Awaited<ReturnType<typeof request.newContext>>) {
  const res = await ctx.post('/api/v2/auth/jwt/login', {
    form: {
      username: process.env.E2E_ADMIN_EMAIL ?? 'e2e@test.com',
      password: process.env.E2E_ADMIN_PASSWORD ?? 'e2etest123',
    },
  });
  if (!res.ok()) return null;
  const data = await res.json() as { access_token: string };
  return data.access_token;
}

// ─── UI tests ────────────────────────────────────────────────────────────────

test.describe('Return Periods Panel (UI)', () => {
  test('navega a /admin/return-periods sin redirigir a login', async ({ page }) => {
    await page.goto('/admin/return-periods');
    await page.waitForTimeout(2000);
    expect(page.url()).not.toContain('/login');
  });

  test('renderiza título y subtítulo correctos', async ({ page }) => {
    await page.goto('/admin/return-periods');
    await page.waitForTimeout(2000);

    await expect(page.getByRole('heading', { name: 'Períodos de Retorno' })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/Gumbel EV-I/i).first()).toBeVisible({ timeout: 10000 });
  });

  test('nav item Períodos de Retorno está en el menú lateral', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(2000);
    await expect(page.getByText('Períodos de Retorno')).toBeVisible({ timeout: 10000 });
  });

  test('nav item Períodos de Retorno navega a /admin/return-periods', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(2000);
    await page.getByText('Períodos de Retorno').click();
    await page.waitForTimeout(1500);
    expect(page.url()).toContain('/admin/return-periods');
  });

  test('selector de zona operativa está presente', async ({ page }) => {
    await page.goto('/admin/return-periods');
    await page.waitForTimeout(2000);

    await expect(page.getByText('Zona operativa', { exact: true })).toBeVisible({ timeout: 10000 });
  });

  test('muestra estado vacío cuando no hay zona seleccionada', async ({ page }) => {
    await page.goto('/admin/return-periods');
    await page.waitForTimeout(2000);

    await expect(
      page.getByText(/Seleccioná una zona operativa/i)
    ).toBeVisible({ timeout: 10000 });
  });

  test('muestra alerta con descripción del método estadístico', async ({ page }) => {
    await page.goto('/admin/return-periods');
    await page.waitForTimeout(2000);

    await expect(page.getByText(/método estadístico/i)).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/5 años/i)).toBeVisible({ timeout: 10000 });
  });

  test('carga zonas en el selector tras abrir la página', async ({ page }) => {
    await page.goto('/admin/return-periods');
    await page.waitForTimeout(3000);

    // Abre el dropdown del Select
    const selector = page.getByPlaceholder(/buscar zona/i).or(
      page.getByText('Zona operativa').locator('..').locator('input')
    ).first();
    await selector.click();
    await page.waitForTimeout(1500);

    // Debe haber al menos una opción
    const options = page.locator('[role="option"]');
    const count = await options.count();
    expect(count).toBeGreaterThan(0);
  });
});

// ─── API tests ────────────────────────────────────────────────────────────────

test.describe('Return Periods API', () => {
  test('GET /hydrology/return-periods sin auth retorna 401', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const res = await ctx.get('/api/v2/geo/hydrology/return-periods/00000000-0000-0000-0000-000000000001');
    expect([401, 403]).toContain(res.status());
    await ctx.dispose();
  });

  test('GET /hydrology/return-periods con UUID inválido retorna 422', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const token = await getToken(ctx);
    if (!token) { test.skip(true, 'No se pudo autenticar'); return; }

    const res = await ctx.get('/api/v2/geo/hydrology/return-periods/not-a-uuid', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect([422, 404]).toContain(res.status());
    await ctx.dispose();
  });

  test('GET /hydrology/return-periods con UUID inexistente retorna ReturnPeriodsResponse vacío', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const token = await getToken(ctx);
    if (!token) { test.skip(true, 'No se pudo autenticar'); return; }

    const res = await ctx.get(
      '/api/v2/geo/hydrology/return-periods/00000000-0000-0000-0000-000000000001',
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(res.status()).toBe(200);

    const body = await res.json() as Record<string, unknown>;
    // No data → return_periods vacío, years_of_data = 0
    expect(body.years_of_data).toBe(0);
    expect(Array.isArray(body.return_periods)).toBe(true);
    expect((body.return_periods as unknown[]).length).toBe(0);
    await ctx.dispose();
  });

  test('GET /hydrology/return-periods con zona real retorna estructura correcta', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const token = await getToken(ctx);
    if (!token) { test.skip(true, 'No se pudo autenticar'); return; }

    // Primero obtenemos una zona real
    const zonasRes = await ctx.get('/api/v2/geo/intelligence/zonas?limit=1', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!zonasRes.ok()) { test.skip(true, 'No hay zonas disponibles'); return; }

    const zonasData = await zonasRes.json() as { items: Array<{ id: string }> };
    if (!zonasData.items?.length) { test.skip(true, 'No hay zonas disponibles'); return; }

    const zonaId = zonasData.items[0].id;
    const res = await ctx.get(`/api/v2/geo/hydrology/return-periods/${zonaId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);

    const body = await res.json() as Record<string, unknown>;
    // Campos requeridos del schema
    expect(typeof body.zona_id).toBe('string');
    expect(typeof body.years_of_data).toBe('number');
    expect(typeof body.annual_maxima_count).toBe('number');
    expect(typeof body.mean_annual_max_mm).toBe('number');
    expect(typeof body.std_annual_max_mm).toBe('number');
    expect(Array.isArray(body.return_periods)).toBe(true);

    // Si hay datos suficientes, los períodos deben estar ordenados T5→T100
    if ((body.return_periods as unknown[]).length > 0) {
      const periods = body.return_periods as Array<{ return_period_years: number; precipitation_mm: number }>;
      const years = periods.map(p => p.return_period_years);
      expect(years).toContain(5);
      expect(years).toContain(100);
      // Precipitación debe aumentar con el período de retorno
      const t5 = periods.find(p => p.return_period_years === 5)!;
      const t100 = periods.find(p => p.return_period_years === 100)!;
      expect(t100.precipitation_mm).toBeGreaterThan(t5.precipitation_mm);
    }
    await ctx.dispose();
  });

  test('GET /hydrology/latest retorna lista de ZonaRiskSummary', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const token = await getToken(ctx);
    if (!token) { test.skip(true, 'No se pudo autenticar'); return; }

    const res = await ctx.get('/api/v2/geo/hydrology/flood-flow/latest', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);

    const body = await res.json() as unknown[];
    expect(Array.isArray(body)).toBe(true);
    await ctx.dispose();
  });
});
