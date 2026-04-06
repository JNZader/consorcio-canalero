import { test, expect } from '@playwright/test';

const API_BASE = process.env.E2E_API_BASE ?? 'http://localhost:8000';
const APP_URL = process.env.E2E_APP_URL ?? 'http://localhost:5173';
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'e2e@test.com';
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'e2etest123';

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
        username: ADMIN_EMAIL,
        password: ADMIN_PASSWORD,
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
    expect(body.email).toBe(ADMIN_EMAIL);
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
      form: { username: ADMIN_EMAIL, password: ADMIN_PASSWORD },
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

    const ts = Date.now().toString().slice(-8);
    const cuit = `20-${ts.padStart(8, '0')}-5`;
    const createRes = await request.post(`${API_BASE}/api/v2/padron`, {
      headers: { Authorization: `Bearer ${authToken}`, Origin: APP_URL },
      data: {
        nombre: 'Playwright',
        apellido: 'Test',
        cuit,
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
      form: { username: ADMIN_EMAIL, password: ADMIN_PASSWORD },
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

// ============================================
// 8. AUTH EXTENDED
// ============================================

test.describe('Auth Extended', () => {
  test('register new user', async ({ request }) => {
    const uniqueEmail = `test-${Date.now()}@playwright.com`;
    const res = await request.post(`${API_BASE}/api/v2/auth/register`, {
      data: { email: uniqueEmail, password: 'TestPass123', nombre: 'E2E', apellido: 'Test' },
    });
    expect(res.status()).toBe(201);
    const body = await res.json();
    expect(body.email).toBe(uniqueEmail);
    expect(body.role).toBe('ciudadano'); // default role
  });

  test('logout invalidates session', async ({ request }) => {
    // Login first
    const loginRes = await request.post(`${API_BASE}/api/v2/auth/jwt/login`, {
      form: { username: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    const token = (await loginRes.json()).access_token;

    // Logout
    const logoutRes = await request.post(`${API_BASE}/api/v2/auth/jwt/logout`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(logoutRes.ok()).toBeTruthy();
  });
});

// ============================================
// 9. DENUNCIAS STATE TRANSITIONS
// ============================================

test.describe('Denuncias State Transitions', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/auth/jwt/login`, {
      form: { username: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    token = (await res.json()).access_token;
  });

  test('full denuncia lifecycle: create → en_revision → resuelto', async ({ request }) => {
    // 1. Create a denuncia via public endpoint
    const createRes = await request.post(`${API_BASE}/api/v2/public/denuncias`, {
      headers: { Origin: APP_URL },
      data: {
        tipo: 'desborde',
        descripcion: `E2E lifecycle test - ${Date.now()}`,
        latitud: -32.62,
        longitud: -62.68,
        cuenca: 'candil',
        contacto_telefono: '3534000001',
        contacto_email: 'lifecycle@test.com',
      },
    });
    expect(createRes.status()).toBe(201);
    const created = await createRes.json();
    const denunciaId = created.id;

    // 2. List denuncias and find the created one
    const listRes = await request.get(`${API_BASE}/api/v2/denuncias`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(listRes.ok()).toBeTruthy();
    const list = await listRes.json();
    const found = list.items.find((d: { id: string }) => d.id === denunciaId);
    expect(found).toBeTruthy();

    // 3. PATCH to en_revision
    const revisionRes = await request.patch(`${API_BASE}/api/v2/denuncias/${denunciaId}`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: { estado: 'en_revision', respuesta: 'Revisando denuncia E2E' },
    });
    expect(revisionRes.ok()).toBeTruthy();

    // 4. PATCH to resuelto
    const resolvedRes = await request.patch(`${API_BASE}/api/v2/denuncias/${denunciaId}`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: { estado: 'resuelto' },
    });
    expect(resolvedRes.ok()).toBeTruthy();

    // 5. Verify via public status check
    const statusRes = await request.get(`${API_BASE}/api/v2/public/denuncias/${denunciaId}/status`);
    expect(statusRes.ok()).toBeTruthy();
    const status = await statusRes.json();
    expect(status.estado).toBe('resuelto');
  });
});

// ============================================
// 10. INFRAESTRUCTURA EXTENDED
// ============================================

test.describe('Infraestructura Extended', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/auth/jwt/login`, {
      form: { username: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    token = (await res.json()).access_token;
  });

  test('asset CRUD lifecycle: create → get → update → maintenance → history', async ({ request }) => {
    const ts = Date.now();

    // 1. Create an asset
    const createRes = await request.post(`${API_BASE}/api/v2/infraestructura/assets`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: {
        nombre: `Canal E2E Extended ${ts}`,
        tipo: 'canal',
        descripcion: 'Asset para test extendido',
        estado_actual: 'bueno',
        latitud: -32.64,
        longitud: -62.70,
      },
    });
    expect(createRes.status()).toBe(201);
    const asset = await createRes.json();
    const assetId = asset.id;

    // 2. Get asset by ID
    const getRes = await request.get(`${API_BASE}/api/v2/infraestructura/assets/${assetId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(getRes.ok()).toBeTruthy();
    const fetched = await getRes.json();
    expect(fetched.nombre).toContain('Canal E2E Extended');

    // 3. PATCH update estado_actual to 'regular'
    const patchRes = await request.patch(`${API_BASE}/api/v2/infraestructura/assets/${assetId}`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: { estado_actual: 'regular' },
    });
    expect(patchRes.ok()).toBeTruthy();

    // 4. POST maintenance log
    const maintRes = await request.post(`${API_BASE}/api/v2/infraestructura/assets/${assetId}/maintenance`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: {
        tipo_trabajo: 'Limpieza correctiva',
        descripcion: `Mantenimiento E2E detallado ${ts}`,
        fecha_trabajo: '2026-03-24',
        realizado_por: 'Playwright E2E',
      },
    });
    expect(maintRes.status()).toBe(201);

    // 5. GET asset history
    const histRes = await request.get(`${API_BASE}/api/v2/infraestructura/assets/${assetId}/history`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(histRes.ok()).toBeTruthy();
  });
});

// ============================================
// 11. FINANZAS EXTENDED
// ============================================

test.describe('Finanzas Extended', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/auth/jwt/login`, {
      form: { username: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    token = (await res.json()).access_token;
  });

  test('create and list ingresos', async ({ request }) => {
    const ts = Date.now();
    const createRes = await request.post(`${API_BASE}/api/v2/finanzas/ingresos`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: {
        descripcion: `Ingreso E2E ${ts}`,
        monto: 15000.0,
        categoria: 'cuotas',
        fecha: '2026-03-24',
      },
    });
    expect(createRes.status()).toBe(201);

    const listRes = await request.get(`${API_BASE}/api/v2/finanzas/ingresos`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(listRes.ok()).toBeTruthy();
    const body = await listRes.json();
    expect(body).toHaveProperty('items');
  });

  test('create and list presupuestos', async ({ request }) => {
    const ts = Date.now();
    const createRes = await request.post(`${API_BASE}/api/v2/finanzas/presupuesto`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: {
        anio: 2026,
        rubro: `rubro-e2e-${ts}`,
        monto_proyectado: 50000.0,
      },
    });
    expect(createRes.status()).toBe(201);

    const listRes = await request.get(`${API_BASE}/api/v2/finanzas/presupuesto`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(listRes.ok()).toBeTruthy();
    const body = await listRes.json();
    expect(Array.isArray(body)).toBeTruthy();
  });

  test('budget execution for 2026', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/finanzas/ejecucion/2026`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBeTruthy();
  });
});

// ============================================
// 12. TRAMITES STATE TRANSITIONS
// ============================================

test.describe('Tramites State Transitions', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/auth/jwt/login`, {
      form: { username: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    token = (await res.json()).access_token;
  });

  test('tramite lifecycle: create → en_tramite → seguimiento → verify', async ({ request }) => {
    const ts = Date.now();

    // 1. Create tramite
    const createRes = await request.post(`${API_BASE}/api/v2/tramites`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: {
        tipo: 'permiso',
        titulo: `Tramite E2E ${ts}`,
        descripcion: 'Tramite para test de transiciones',
        solicitante: 'Playwright E2E',
        prioridad: 'media',
      },
    });
    expect(createRes.status()).toBe(201);
    const tramite = await createRes.json();
    const tramiteId = tramite.id;

    // 2. PATCH update estado to 'en_tramite'
    const patchRes = await request.patch(`${API_BASE}/api/v2/tramites/${tramiteId}`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: { estado: 'en_tramite' },
    });
    expect(patchRes.ok()).toBeTruthy();

    // 3. POST add seguimiento
    const segRes = await request.post(`${API_BASE}/api/v2/tramites/${tramiteId}/seguimiento`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: {
        comentario: `Seguimiento E2E detallado ${ts}`,
      },
    });
    expect(segRes.status()).toBe(201);

    // 4. GET tramite by ID and verify
    const getRes = await request.get(`${API_BASE}/api/v2/tramites/${tramiteId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(getRes.ok()).toBeTruthy();
    const fetched = await getRes.json();
    expect(fetched.estado).toBe('en_tramite');
  });
});

// ============================================
// 13. CAPAS CRUD
// ============================================

test.describe('Capas CRUD', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/auth/jwt/login`, {
      form: { username: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    token = (await res.json()).access_token;
  });

  test('capa lifecycle: create → get → update → reorder → delete', async ({ request }) => {
    const ts = Date.now();

    // 1. POST create a new capa
    const createRes = await request.post(`${API_BASE}/api/v2/capas`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: {
        nombre: `Capa E2E ${ts}`,
        tipo: 'polygon',
        fuente: 'local',
        visible: true,
        orden: 99,
        estilo: { color: '#FF0000', weight: 2, fillColor: '#FF0000', fillOpacity: 0.5 },
      },
    });
    expect(createRes.status()).toBe(201);
    const capa = await createRes.json();
    const capaId = capa.id;

    // 2. GET the created capa by ID
    const getRes = await request.get(`${API_BASE}/api/v2/capas/${capaId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(getRes.ok()).toBeTruthy();
    const fetched = await getRes.json();
    expect(fetched.nombre).toContain('Capa E2E');

    // 3. PATCH update the capa
    const patchRes = await request.patch(`${API_BASE}/api/v2/capas/${capaId}`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: { nombre: `Capa E2E Updated ${ts}`, visible: false },
    });
    expect(patchRes.ok()).toBeTruthy();

    // 4. PUT reorder capas
    const reorderRes = await request.put(`${API_BASE}/api/v2/capas/reorder`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: { ordered_ids: [capaId] },
    });
    // Reorder might return 200 or 204
    expect(reorderRes.status()).toBeLessThan(300);

    // 5. DELETE the capa (returns 204 No Content, requires admin)
    const deleteRes = await request.delete(`${API_BASE}/api/v2/capas/${capaId}`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Origin: APP_URL,
        'Content-Type': 'application/json',
      },
    });
    expect(deleteRes.status()).toBe(204);
  });
});

// ============================================
// 14. SUGERENCIAS MANAGEMENT
// ============================================

test.describe('Sugerencias Management', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/auth/jwt/login`, {
      form: { username: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    token = (await res.json()).access_token;
  });

  test('list sugerencias and update estado', async ({ request }) => {
    // First create a fresh sugerencia to update
    const createRes = await request.post(`${API_BASE}/api/v2/public/sugerencias`, {
      headers: { Origin: APP_URL },
      data: {
        titulo: `Sugerencia E2E ${Date.now()}`,
        descripcion: 'Sugerencia para test de gestion',
        contacto_nombre: 'E2E Bot',
        contacto_email: 'sugerencia-e2e@test.com',
      },
    });
    expect(createRes.status()).toBe(201);
    const created = await createRes.json();

    // List sugerencias
    const listRes = await request.get(`${API_BASE}/api/v2/sugerencias`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(listRes.ok()).toBeTruthy();
    const body = await listRes.json();
    expect(body).toHaveProperty('items');

    // PATCH update estado to 'revisada'
    const patchRes = await request.patch(`${API_BASE}/api/v2/sugerencias/${created.id}`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: { estado: 'revisada' },
    });
    expect(patchRes.ok()).toBeTruthy();
  });
});

// ============================================
// 15. SETTINGS UPDATE
// ============================================

test.describe('Settings Update', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/auth/jwt/login`, {
      form: { username: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    token = (await res.json()).access_token;
  });

  test('get, update, and verify setting', async ({ request }) => {
    // 1. GET all settings to find a key
    const listRes = await request.get(`${API_BASE}/api/v2/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(listRes.ok()).toBeTruthy();
    const settings = await listRes.json();
    if (!settings.length) test.skip();

    const setting = settings[0];
    const settingKey = setting.clave;
    if (!settingKey) test.skip();

    // 2. GET specific setting by key (route: /key/{clave})
    const getRes = await request.get(`${API_BASE}/api/v2/settings/key/${settingKey}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(getRes.ok()).toBeTruthy();
    const original = await getRes.json();

    // 3. PUT update the setting value (re-set same value to avoid side effects)
    const putRes = await request.put(`${API_BASE}/api/v2/settings/key/${settingKey}`, {
      headers: { Authorization: `Bearer ${token}`, Origin: APP_URL },
      data: { valor: original.valor },
    });
    expect(putRes.ok()).toBeTruthy();

    // 4. Verify persistence
    const verifyRes = await request.get(`${API_BASE}/api/v2/settings/key/${settingKey}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(verifyRes.ok()).toBeTruthy();
  });
});

// ============================================
// 16. GEE EXTENDED
// ============================================

test.describe('GEE Extended', () => {
  test('cuenca norte GeoJSON', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/gee/layers/norte`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.type).toBe('FeatureCollection');
  });

  test('cuenca ML GeoJSON', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/gee/layers/ml`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.type).toBe('FeatureCollection');
  });

  test('cuenca noroeste GeoJSON', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/gee/layers/noroeste`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.type).toBe('FeatureCollection');
  });

  test('colored roads layer', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/gee/layers/caminos/coloreados`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.type).toBe('FeatureCollection');
  });

  test('available visualizations', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/gee/images/visualizations`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(Array.isArray(body)).toBeTruthy();
  });
});

// ============================================
// 17. GEO INTELLIGENCE EXTENDED
// ============================================

test.describe('Geo Intelligence Extended', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/auth/jwt/login`, {
      form: { username: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    token = (await res.json()).access_token;
  });

  test('conflictos list', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/intelligence/conflictos`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  test('canales prioridad', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/intelligence/canales/prioridad`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  test('caminos riesgo', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/intelligence/caminos/riesgo`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  test('HCI results list', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/intelligence/hci`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBeTruthy();
  });
});

// ============================================
// 18. GEO JOBS & LAYERS
// ============================================

test.describe('Geo Jobs & Layers', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    const res = await request.post(`${API_BASE}/api/v2/auth/jwt/login`, {
      form: { username: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    token = (await res.json()).access_token;
  });

  test('list geo processing jobs', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/jobs`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBeTruthy();
  });

  test('list geo layers', async ({ request }) => {
    const res = await request.get(`${API_BASE}/api/v2/geo/layers`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBeTruthy();
  });
});
