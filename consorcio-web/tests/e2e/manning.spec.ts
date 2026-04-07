import { test, expect, request } from '@playwright/test';

const API_BASE = process.env.E2E_API_BASE ?? 'http://localhost:8000';

// ─── helpers ─────────────────────────────────────────────────────────────────

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

test.describe('Manning Panel (UI)', () => {
  test('navega a /admin/manning sin redirigir a login', async ({ page }) => {
    await page.goto('/admin/manning');
    await page.waitForTimeout(2000);
    expect(page.url()).not.toContain('/login');
  });

  test('renderiza titulo y subtitulo de Manning', async ({ page }) => {
    await page.goto('/admin/manning');
    await page.waitForTimeout(2000);

    await expect(page.getByText('Capacidad Hidráulica — Manning')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/Sección trapezoidal/i).first()).toBeVisible({ timeout: 10000 });
  });

  test('nav item Manning (Capacidad) está en el menú lateral', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(2000);
    await expect(page.getByText('Manning (Capacidad)')).toBeVisible({ timeout: 10000 });
  });

  test('nav item Manning navega a /admin/manning', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(2000);
    await page.getByText('Manning (Capacidad)').click();
    await page.waitForTimeout(1500);
    expect(page.url()).toContain('/admin/manning');
  });

  test('formulario renderiza los campos de geometría', async ({ page }) => {
    await page.goto('/admin/manning');
    await page.waitForTimeout(2000);

    await expect(page.getByText('Ancho de base (m)')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Profundidad normal (m)')).toBeVisible();
    await expect(page.getByText(/Pendiente/i)).toBeVisible();
    await expect(page.getByText(/Talud/i)).toBeVisible();
  });

  test('selector de material está presente', async ({ page }) => {
    await page.goto('/admin/manning');
    await page.waitForTimeout(2000);

    await expect(page.getByText('Material del canal')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Rugosidad Manning')).toBeVisible();
  });

  test('botón Calcular está visible', async ({ page }) => {
    await page.goto('/admin/manning');
    await page.waitForTimeout(2000);

    const btn = page.getByRole('button', { name: /calcular/i });
    await expect(btn).toBeVisible({ timeout: 10000 });
  });

  test('calcula y muestra resultados con valores típicos', async ({ page }) => {
    await page.goto('/admin/manning');
    await page.waitForTimeout(2000);

    // Limpia y rellena ancho
    const anchoInput = page.getByLabel(/Ancho de base/i).or(
      page.locator('input').nth(0)
    );
    await anchoInput.fill('3');

    // Profundidad
    const profInput = page.getByLabel(/Profundidad normal/i).or(
      page.locator('input').nth(1)
    );
    await profInput.fill('1.5');

    // Pendiente
    const slopeInput = page.getByLabel(/Pendiente/i).first().or(
      page.locator('input').nth(2)
    );
    await slopeInput.fill('0.001');

    await page.getByRole('button', { name: /calcular/i }).click();
    await page.waitForTimeout(3000);

    // Debe aparecer sección de resultados con Q capacidad
    await expect(page.getByText(/Q capacidad/i)).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/m³\/s/i).first()).toBeVisible();
  });

  test('muestra panel de parámetros de sección confirmados tras calcular', async ({ page }) => {
    await page.goto('/admin/manning');
    await page.waitForTimeout(2000);

    await page.getByRole('button', { name: /calcular/i }).click();
    await page.waitForTimeout(3000);

    await expect(page.getByText(/Parámetros de entrada confirmados/i)).toBeVisible({ timeout: 10000 });
  });
});

// ─── API tests ────────────────────────────────────────────────────────────────

test.describe('Manning API', () => {
  test('POST /hydrology/manning sin auth retorna 401', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const res = await ctx.post('/api/v2/geo/hydrology/manning', {
      headers: { 'Content-Type': 'application/json' },
      data: { ancho_m: 3, profundidad_m: 1.5, slope: 0.001, talud: 1.0 },
    });
    expect([401, 403]).toContain(res.status());
    await ctx.dispose();
  });

  test('POST /hydrology/manning con body vacío retorna 422', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const token = await getToken(ctx);
    if (!token) { test.skip(true, 'No se pudo autenticar'); return; }

    const res = await ctx.post('/api/v2/geo/hydrology/manning', {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: {},
    });
    expect(res.status()).toBe(422);
    await ctx.dispose();
  });

  test('POST /hydrology/manning con valores válidos retorna ManningResponse', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const token = await getToken(ctx);
    if (!token) { test.skip(true, 'No se pudo autenticar'); return; }

    const res = await ctx.post('/api/v2/geo/hydrology/manning', {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: {
        ancho_m: 3.0,
        profundidad_m: 1.5,
        slope: 0.001,
        talud: 1.0,
        material: 'tierra',
      },
    });
    expect(res.status()).toBe(200);

    const body = await res.json() as Record<string, unknown>;
    expect(typeof body.q_capacity_m3s).toBe('number');
    expect(typeof body.velocidad_ms).toBe('number');
    expect(typeof body.area_m2).toBe('number');
    expect(typeof body.n).toBe('number');
    // tierra tiene n=0.025 por defecto
    expect(body.n).toBeCloseTo(0.025, 3);
    // Q debe ser positivo
    expect(body.q_capacity_m3s as number).toBeGreaterThan(0);
    await ctx.dispose();
  });

  test('POST /hydrology/manning con override de n respeta el valor', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const token = await getToken(ctx);
    if (!token) { test.skip(true, 'No se pudo autenticar'); return; }

    const res = await ctx.post('/api/v2/geo/hydrology/manning', {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: {
        ancho_m: 3.0,
        profundidad_m: 1.5,
        slope: 0.001,
        talud: 0.0,
        coef_manning: 0.014,
      },
    });
    expect(res.status()).toBe(200);
    const body = await res.json() as Record<string, unknown>;
    expect(body.n).toBeCloseTo(0.014, 3);
    // Sección rectangular: A = b * y = 3 * 1.5 = 4.5 m²
    expect(body.area_m2 as number).toBeCloseTo(4.5, 2);
    await ctx.dispose();
  });

  test('POST /hydrology/manning con hormigon usa n=0.014', async () => {
    const ctx = await request.newContext({ baseURL: API_BASE });
    const token = await getToken(ctx);
    if (!token) { test.skip(true, 'No se pudo autenticar'); return; }

    const res = await ctx.post('/api/v2/geo/hydrology/manning', {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { ancho_m: 2, profundidad_m: 1, slope: 0.005, talud: 0, material: 'hormigon' },
    });
    expect(res.status()).toBe(200);
    const body = await res.json() as Record<string, unknown>;
    expect(body.n).toBeCloseTo(0.014, 3);
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
});
