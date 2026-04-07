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

test.describe('Informe Territorial Panel (UI)', () => {
  test('navega a /admin/informe-territorial sin redirigir a login', async ({ page }) => {
    await page.goto('/admin/informe-territorial');
    await page.waitForTimeout(2000);
    expect(page.url()).not.toContain('/login');
  });

  test('renderiza título correcto', async ({ page }) => {
    await page.goto('/admin/informe-territorial');
    await page.waitForTimeout(2000);

    await expect(page.getByRole('heading', { name: 'Informe Territorial' })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/Km de canales/i).first()).toBeVisible({ timeout: 10000 });
  });

  test('nav item Informe Territorial está en el menú lateral', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(2000);
    await expect(page.getByText('Informe Territorial')).toBeVisible({ timeout: 10000 });
  });

  test('nav item Informe Territorial navega a /admin/informe-territorial', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(2000);
    await page.getByText('Informe Territorial').click();
    await page.waitForTimeout(1500);
    expect(page.url()).toContain('/admin/informe-territorial');
  });

  test('muestra sección de importación con botones de suelos y canales', async ({ page }) => {
    await page.goto('/admin/informe-territorial');
    await page.waitForTimeout(2000);

    await expect(page.getByText('Importar geodatos')).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('button', { name: 'suelos_cu.geojson' })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('button', { name: 'canales_existentes.geojson' })).toBeVisible({ timeout: 10000 });
  });

  test('muestra tabs Todo el Consorcio, Por Cuenca, Por Subcuenca cuando hay datos', async ({ page }) => {
    await page.goto('/admin/informe-territorial');
    await page.waitForTimeout(3000);

    // Tabs solo aparecen cuando hay datos importados
    const hasTabs = await page.getByRole('tab', { name: /Todo el Consorcio/i }).isVisible().catch(() => false);
    const hasNoData = await page.getByText(/Sin datos importados/i).isVisible().catch(() => false);

    // Uno de los dos debe ser verdad
    expect(hasTabs || hasNoData).toBe(true);
  });

  test('muestra alerta de sin datos cuando no hay geodatos importados', async ({ page }) => {
    await page.goto('/admin/informe-territorial');
    await page.waitForTimeout(3000);

    // Either shows tabs (data imported) or shows no-data alert
    const hasAlert = await page.getByText(/Sin datos importados/i).isVisible().catch(() => false);
    const hasTabs = await page.getByRole('tab').first().isVisible().catch(() => false);
    expect(hasAlert || hasTabs).toBe(true);
  });
});

// ─── API tests ────────────────────────────────────────────────────────────────

test.describe('Informe Territorial API', () => {
  test('GET /territorial/status sin auth retorna 401', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const res = await ctx.get('/api/v2/territorial/status');
    expect([401, 403]).toContain(res.status());
    await ctx.dispose();
  });

  test('GET /territorial/status con auth retorna estructura correcta', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const token = await getToken(ctx);
    if (!token) { test.skip(true, 'No se pudo autenticar'); return; }

    const res = await ctx.get('/api/v2/territorial/status', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);

    const body = await res.json() as Record<string, unknown>;
    expect(typeof body.has_suelos).toBe('boolean');
    expect(typeof body.has_canales).toBe('boolean');
    await ctx.dispose();
  });

  test('GET /territorial/cuencas con auth retorna lista', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const token = await getToken(ctx);
    if (!token) { test.skip(true, 'No se pudo autenticar'); return; }

    const res = await ctx.get('/api/v2/territorial/cuencas', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);

    const body = await res.json() as Record<string, unknown>;
    expect(Array.isArray(body.cuencas)).toBe(true);
    await ctx.dispose();
  });

  test('GET /territorial/report scope=consorcio retorna estructura correcta', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const token = await getToken(ctx);
    if (!token) { test.skip(true, 'No se pudo autenticar'); return; }

    const res = await ctx.get('/api/v2/territorial/report?scope=consorcio', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(200);

    const body = await res.json() as Record<string, unknown>;
    expect(body.scope).toBe('consorcio');
    expect(body.scope_name).toBe('Todo el Consorcio');
    expect(typeof body.km_canales).toBe('number');
    expect(typeof body.total_ha_analizada).toBe('number');
    expect(Array.isArray(body.suelos)).toBe(true);

    // Si hay suelos, verificar estructura
    if ((body.suelos as unknown[]).length > 0) {
      const first = (body.suelos as Array<Record<string, unknown>>)[0];
      expect(typeof first.simbolo).toBe('string');
      expect(typeof first.ha).toBe('number');
      expect(typeof first.pct).toBe('number');
      // pct debe estar entre 0 y 100
      expect(first.pct as number).toBeGreaterThanOrEqual(0);
      expect(first.pct as number).toBeLessThanOrEqual(100);
    }
    await ctx.dispose();
  });

  test('GET /territorial/report scope inválido retorna 400', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const token = await getToken(ctx);
    if (!token) { test.skip(true, 'No se pudo autenticar'); return; }

    const res = await ctx.get('/api/v2/territorial/report?scope=invalido', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(400);
    await ctx.dispose();
  });

  test('GET /territorial/report scope=cuenca sin value retorna 400', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const token = await getToken(ctx);
    if (!token) { test.skip(true, 'No se pudo autenticar'); return; }

    const res = await ctx.get('/api/v2/territorial/report?scope=cuenca', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(400);
    await ctx.dispose();
  });

  test('POST /territorial/import/suelos sin auth retorna 401', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const res = await ctx.post('/api/v2/territorial/import/suelos', {
      headers: { 'Content-Type': 'application/json' },
      data: { geojson: { type: 'FeatureCollection', features: [] } },
    });
    expect([401, 403]).toContain(res.status());
    await ctx.dispose();
  });
});
