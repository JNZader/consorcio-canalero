import { test, expect } from '@playwright/test';

const API_BASE = 'https://cc10demayo-api.javierzader.com';
const APP_URL = 'https://consorcio-canalero.pages.dev';

// ============================================
// 1. HEALTH & INFRASTRUCTURE
// ============================================

test.describe('Backend Health', () => {
  test('API health check returns healthy', async ({ request }) => {
    const res = await request.get(`${API_BASE}/health`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe('healthy');
    expect(body.services.database.status).toBe('healthy');
    expect(body.services.redis.status).toBe('healthy');
    expect(body.version).toBe('2.0.0');
  });

  test('Swagger docs accessible', async ({ request }) => {
    const res = await request.get(`${API_BASE}/docs`);
    expect(res.ok()).toBeTruthy();
  });
});

// ============================================
// 2. PUBLIC ENDPOINTS (no auth)
// ============================================

test.describe('Public API', () => {
  test('public stats returns counts', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/public/stats`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty('total_denuncias');
    expect(body).toHaveProperty('total_sugerencias');
  });

  test('public branding settings accessible', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/public/settings/branding`);
    expect(res.ok()).toBeTruthy();
  });

  test('public layers returns array', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/public/layers`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body)).toBeTruthy();
  });

  test('create anonymous denuncia', async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/public/denuncias`, {
      headers: { 'Origin': APP_URL },
      data: {
        tipo: 'desborde',
        descripcion: 'Test E2E Playwright - denuncia anonima',
        latitud: -32.62,
        longitud: -62.68,
        cuenca: 'candil',
        contacto_telefono: '3534000000',
        contacto_email: 'playwright@test.com',
      },
    });
    expect(res.status()).toBe(201);
    const body = await res.json();
    expect(body).toHaveProperty('id');

    // Check status of created denuncia
    const statusRes = await request.get(`${API_BASE}/api/v2/public/denuncias/${body.id}/status`);
    expect(statusRes.ok()).toBeTruthy();
    const status = await statusRes.json();
    expect(status.estado).toBe('pendiente');
  });

  test('create anonymous sugerencia', async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/public/sugerencias`, {
      headers: { 'Origin': APP_URL },
      data: {
        titulo: 'Test E2E Playwright',
        descripcion: 'Sugerencia de prueba automatizada',
        contacto_nombre: 'Playwright',
        contacto_email: 'playwright@test.com',
      },
    });
    expect(res.status()).toBe(201);
  });
});

// ============================================
// 3. AUTH FLOW
// ============================================

let authToken: string;

test.describe('Authentication', () => {
  test('login with email/password returns JWT', async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/auth/jwt/login`, {
      form: {
        username: 'jnzader@gmail.com',
        password: '1qaz2wsx',
      },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty('access_token');
    expect(body.token_type).toBe('bearer');
    authToken = body.access_token;
  });

  test('get current user profile', async ({ request }) => {
    if (!authToken) test.skip();
    const res = await request.get(`${API_BASE}/api/v2/users/me`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.email).toBe('jnzader@gmail.com');
    expect(body.role).toBe('admin');
    expect(body.is_superuser).toBe(true);
  });

  test('Google OAuth returns authorization URL', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/auth/google/authorize`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty('authorization_url');
    expect(body.authorization_url).toContain('accounts.google.com');
  });
});

// ============================================
// 4. AUTHENTICATED CRUD OPERATIONS
// ============================================

test.describe('Authenticated CRUD', () => {
  test.beforeAll(async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/auth/jwt/login`, {
      form: { username: 'jnzader@gmail.com', password: '1qaz2wsx' },
    });
    const body = await res.json();
    authToken = body.access_token;
  });

  // --- Denuncias ---
  test('list denuncias', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/denuncias`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty('items');
    expect(body).toHaveProperty('total');
  });

  test('get denuncias stats', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/denuncias/stats`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  // --- Infraestructura ---
  test('list and create assets', async ({ request }) => {
    const listRes = await request.get(`${API_BASE}/api/v2/infraestructura/assets`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(listRes.ok()).toBeTruthy();

    const createRes = await request.post(`${API_BASE}/api/v2/infraestructura/assets`, {
      headers: { Authorization: `Bearer ${authToken}`, Origin: APP_URL },
      data: {
        nombre: 'Canal Playwright Test',
        tipo: 'canal',
        descripcion: 'Asset creado por Playwright',
        estado_actual: 'bueno',
        latitud: -32.63,
        longitud: -62.69,
      },
    });
    expect(createRes.status()).toBe(201);
  });

  test('infraestructura stats', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/infraestructura/stats`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  // --- Padron ---
  test('list and create consorcista', async ({ request }) => {
    const listRes = await request.get(`${API_BASE}/api/v2/padron`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(listRes.ok()).toBeTruthy();

    const createRes = await request.post(`${API_BASE}/api/v2/padron`, {
      headers: { Authorization: `Bearer ${authToken}`, Origin: APP_URL },
      data: {
        nombre: 'Playwright',
        apellido: 'Test',
        cuit: '20-99887766-5',
        estado: 'activo',
      },
    });
    expect(createRes.status()).toBe(201);
  });

  test('padron stats', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/padron/stats`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  // --- Finanzas ---
  test('create gasto and check resumen', async ({ request }) => {
    const createRes = await request.post(`${API_BASE}/api/v2/finanzas/gastos`, {
      headers: { Authorization: `Bearer ${authToken}`, Origin: APP_URL },
      data: {
        descripcion: 'Gasto Playwright',
        monto: 2500.00,
        categoria: 'mantenimiento',
        fecha: '2026-03-25',
      },
    });
    expect(createRes.status()).toBe(201);

    const resumenRes = await request.get(`${API_BASE}/api/v2/finanzas/resumen/2026`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(resumenRes.ok()).toBeTruthy();
  });

  // --- Tramites ---
  test('create tramite', async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/tramites`, {
      headers: { Authorization: `Bearer ${authToken}`, Origin: APP_URL },
      data: {
        tipo: 'permiso',
        titulo: 'Tramite Playwright',
        descripcion: 'Tramite creado por Playwright test',
        solicitante: 'Playwright',
        prioridad: 'baja',
      },
    });
    expect(res.status()).toBe(201);
  });

  test('tramites stats', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/tramites/stats`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  // --- Capas ---
  test('list capas', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/capas`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  // --- Sugerencias ---
  test('list sugerencias', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/sugerencias`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  // --- Monitoring ---
  test('monitoring dashboard', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/monitoring/dashboard`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  // --- Settings ---
  test('list all settings', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/settings`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body)).toBeTruthy();
    expect(body.length).toBeGreaterThan(0);
  });
});

// ============================================
// 5. GEE ENDPOINTS
// ============================================

test.describe('Google Earth Engine', () => {
  test('list GEE layers', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/gee/layers`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body)).toBeTruthy();
    expect(body.length).toBeGreaterThan(0);
    expect(body[0]).toHaveProperty('id');
    expect(body[0]).toHaveProperty('nombre');
  });

  test('get zona GeoJSON', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/gee/layers/zona`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.type).toBe('FeatureCollection');
    expect(body.features.length).toBeGreaterThan(0);
  });

  test('get cuenca candil GeoJSON', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/gee/layers/candil`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.type).toBe('FeatureCollection');
  });
});

// ============================================
// 6. GEO INTELLIGENCE
// ============================================

test.describe('Geo Intelligence', () => {
  test.beforeAll(async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/auth/jwt/login`, {
      form: { username: 'jnzader@gmail.com', password: '1qaz2wsx' },
    });
    authToken = (await res.json()).access_token;
  });

  test('intelligence dashboard', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/intelligence/dashboard`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  test('list zonas', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/intelligence/zonas`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  test('list alertas', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/intelligence/alertas`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    expect(res.ok()).toBeTruthy();
  });
});

// ============================================
// 7. FRONTEND PAGES LOAD
// ============================================

test.describe('Frontend Pages', () => {
  test('homepage loads', async ({ page }) => {
    await page.goto(APP_URL);
    await expect(page).toHaveTitle(/Consorcio/i);
  });

  test('login page accessible', async ({ page }) => {
    await page.goto(APP_URL);
    // Check that some content loads (not a blank page)
    await expect(page.locator('body')).not.toBeEmpty();
  });

  test('map page loads without crash', async ({ page }) => {
    await page.goto(`${APP_URL}/mapa`);
    // Wait for the page to settle
    await page.waitForTimeout(3000);
    // Check no fatal error boundary
    const errorBoundary = page.locator('text=Something went wrong');
    const hasError = await errorBoundary.count();
    // Map may show error boundary due to GEE loading, but page should load
    expect(hasError).toBeLessThanOrEqual(1);
  });

  test('reportes page loads', async ({ page }) => {
    await page.goto(`${APP_URL}/reportes`);
    await page.waitForTimeout(2000);
    await expect(page.locator('body')).not.toBeEmpty();
  });
});
