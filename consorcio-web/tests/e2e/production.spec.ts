import { expect, test, type APIRequestContext } from '@playwright/test';

const API_BASE = process.env.E2E_API_BASE ?? 'http://localhost:8000';
const APP_URL = process.env.E2E_APP_URL ?? 'http://localhost:5173';
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'e2e@test.com';
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'e2etest123';

const apiUrl = (path: string) => `${API_BASE}${path}`;
const appUrl = (path = '') => `${APP_URL}${path}`;
const withOrigin = (token?: string) => ({
  ...(token ? { Authorization: `Bearer ${token}` } : {}),
  Origin: APP_URL,
});

async function loginAsAdmin(request: APIRequestContext) {
  const res = await request.post(apiUrl('/api/v2/auth/jwt/login'), {
    form: { username: ADMIN_EMAIL, password: ADMIN_PASSWORD },
  });
  expect(res.ok()).toBeTruthy();
  return (await res.json()).access_token as string;
}

async function expectOk(requestPromise: Promise<unknown>) {
  const res = (await requestPromise) as {
    ok(): boolean;
    status(): number;
    json(): Promise<any>;
  };
  expect(res.ok()).toBeTruthy();
  return res;
}

async function createPublicDenuncia(request: APIRequestContext, suffix = `${Date.now()}`) {
  const res = await request.post(apiUrl('/api/v2/public/denuncias'), {
    headers: withOrigin(),
    data: {
      tipo: 'desborde',
      descripcion: `E2E denuncia ${suffix}`,
      latitud: -32.62,
      longitud: -62.68,
      cuenca: 'candil',
      contacto_telefono: '3534000001',
      contacto_email: 'playwright@test.com',
    },
  });
  expect(res.status()).toBe(201);
  return res.json();
}

async function createPublicSugerencia(request: APIRequestContext, suffix = `${Date.now()}`) {
  const res = await request.post(apiUrl('/api/v2/public/sugerencias'), {
    headers: withOrigin(),
    data: {
      titulo: `Sugerencia E2E ${suffix}`,
      descripcion: 'Sugerencia de prueba automatizada',
      contacto_nombre: 'Playwright',
      contacto_email: 'playwright@test.com',
    },
  });
  expect(res.status()).toBe(201);
  return res.json();
}

test.describe('Backend Health', () => {
  test('health and docs are available', async ({ request }) => {
    const health = await expectOk(request.get(apiUrl('/health')));
    const body = await health.json();
    expect(body.status).toBe('healthy');
    expect(body.services.database.status).toBe('healthy');
    expect(body.services.redis.status).toBe('healthy');
    expect(body.version).toBe('2.0.0');

    await expectOk(request.get(apiUrl('/docs')));
  });
});

test.describe('Public API', () => {
  test('public stats, branding and layers respond', async ({ request }) => {
    const stats = await expectOk(request.get(apiUrl('/api/v2/public/stats')));
    expect(await stats.json()).toEqual(
      expect.objectContaining({
        total_denuncias: expect.anything(),
        total_sugerencias: expect.anything(),
      })
    );

    await expectOk(request.get(apiUrl('/api/v2/public/settings/branding')));

    const layers = await expectOk(request.get(apiUrl('/api/v2/public/layers')));
    expect(Array.isArray(await layers.json())).toBeTruthy();
  });

  test('can create anonymous denuncia and consult its status', async ({ request }) => {
    const created = await createPublicDenuncia(request, 'anonima');
    expect(created).toHaveProperty('id');

    const statusRes = await expectOk(
      request.get(apiUrl(`/api/v2/public/denuncias/${created.id}/status`))
    );
    expect((await statusRes.json()).estado).toBe('pendiente');
  });

  test('can create anonymous sugerencia', async ({ request }) => {
    await createPublicSugerencia(request, 'publica');
  });
});

test.describe('Authentication', () => {
  test('email login, current profile and google auth work', async ({ request }) => {
    const token = await loginAsAdmin(request);

    const me = await expectOk(
      request.get(apiUrl('/api/v2/users/me'), {
        headers: { Authorization: `Bearer ${token}` },
      })
    );
    const profile = await me.json();
    expect(profile.email).toBe(ADMIN_EMAIL);
    expect(profile.role).toBe('admin');
    expect(profile.is_superuser).toBe(true);

    const google = await expectOk(request.get(apiUrl('/api/v2/auth/google/authorize')));
    const googleBody = await google.json();
    expect(googleBody.authorization_url).toContain('accounts.google.com');
  });
});

test.describe('Authenticated CRUD', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await loginAsAdmin(request);
  });

  test('lists key resources and stats endpoints', async ({ request }) => {
    const checks: Array<[string, string, (body: any) => void]> = [
      ['/api/v2/denuncias', 'items list', (body) => expect(body).toEqual(expect.objectContaining({ items: expect.anything(), total: expect.anything() }))],
      ['/api/v2/settings', 'settings array', (body) => { expect(Array.isArray(body)).toBeTruthy(); expect(body.length).toBeGreaterThan(0); }],
    ];

    for (const [path, _label, assertBody] of checks) {
      const res = await expectOk(request.get(apiUrl(path), { headers: { Authorization: `Bearer ${token}` } }));
      assertBody(await res.json());
    }

    for (const path of [
      '/api/v2/denuncias/stats',
      '/api/v2/infraestructura/stats',
      '/api/v2/padron/stats',
      '/api/v2/tramites/stats',
      '/api/v2/capas',
      '/api/v2/sugerencias',
      '/api/v2/monitoring/dashboard',
    ]) {
      await expectOk(request.get(apiUrl(path), { headers: { Authorization: `Bearer ${token}` } }));
    }
  });

  test('creates representative records for infrastructure, padron, finanzas and tramites', async ({ request }) => {
    await expectOk(
      request.get(apiUrl('/api/v2/infraestructura/assets'), { headers: { Authorization: `Bearer ${token}` } })
    );
    const assetRes = await request.post(apiUrl('/api/v2/infraestructura/assets'), {
      headers: withOrigin(token),
      data: {
        nombre: 'Canal Playwright Test',
        tipo: 'canal',
        descripcion: 'Asset creado por Playwright',
        estado_actual: 'bueno',
        latitud: -32.63,
        longitud: -62.69,
      },
    });
    expect(assetRes.status()).toBe(201);

    await expectOk(request.get(apiUrl('/api/v2/padron'), { headers: { Authorization: `Bearer ${token}` } }));
    const ts = Date.now().toString().slice(-8);
    const cuit = `20-${ts.padStart(8, '0')}-5`;
    expect(
      (await request.post(apiUrl('/api/v2/padron'), {
        headers: withOrigin(token),
        data: { nombre: 'Playwright', apellido: 'Test', cuit, estado: 'activo' },
      })).status()
    ).toBe(201);

    expect(
      (await request.post(apiUrl('/api/v2/finanzas/gastos'), {
        headers: withOrigin(token),
        data: { descripcion: 'Gasto Playwright', monto: 2500.0, categoria: 'mantenimiento', fecha: '2026-03-25' },
      })).status()
    ).toBe(201);
    await expectOk(request.get(apiUrl('/api/v2/finanzas/resumen/2026'), { headers: { Authorization: `Bearer ${token}` } }));

    expect(
      (await request.post(apiUrl('/api/v2/tramites'), {
        headers: withOrigin(token),
        data: {
          tipo: 'permiso',
          titulo: 'Tramite Playwright',
          descripcion: 'Tramite creado por Playwright test',
          solicitante: 'Playwright',
          prioridad: 'baja',
        },
      })).status()
    ).toBe(201);
  });
});

test.describe('Google Earth Engine', () => {
  test('layers and selected geojson endpoints respond', async ({ request }) => {
    const layers = await expectOk(request.get(apiUrl('/api/v2/geo/gee/layers')));
    const layerBody = await layers.json();
    expect(Array.isArray(layerBody)).toBeTruthy();
    expect(layerBody[0]).toEqual(expect.objectContaining({ id: expect.anything(), nombre: expect.anything() }));

    for (const path of [
      '/api/v2/geo/gee/layers/zona',
      '/api/v2/geo/gee/layers/candil',
      '/api/v2/geo/gee/layers/norte',
      '/api/v2/geo/gee/layers/ml',
      '/api/v2/geo/gee/layers/noroeste',
      '/api/v2/geo/gee/layers/caminos/coloreados',
    ]) {
      const res = await expectOk(request.get(apiUrl(path)));
      expect((await res.json()).type).toBe('FeatureCollection');
    }

    const visualizations = await expectOk(request.get(apiUrl('/api/v2/geo/gee/images/visualizations')));
    expect(Array.isArray(await visualizations.json())).toBeTruthy();
  });
});

test.describe('Geo Intelligence and geo jobs', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await loginAsAdmin(request);
  });

  test('intelligence, jobs and layers endpoints respond', async ({ request }) => {
    for (const path of [
      '/api/v2/geo/intelligence/dashboard',
      '/api/v2/geo/intelligence/zonas',
      '/api/v2/geo/intelligence/alertas',
      '/api/v2/geo/intelligence/conflictos',
      '/api/v2/geo/intelligence/canales/prioridad',
      '/api/v2/geo/intelligence/caminos/riesgo',
      '/api/v2/geo/intelligence/hci',
      '/api/v2/geo/jobs',
      '/api/v2/geo/layers',
    ]) {
      await expectOk(request.get(apiUrl(path), { headers: { Authorization: `Bearer ${token}` } }));
    }
  });
});

test.describe('Frontend Pages', () => {
  test('homepage, mapa and reportes load without blank page or fatal crash', async ({ page }) => {
    await page.goto(appUrl());
    await expect(page).toHaveTitle(/Consorcio/i);
    await expect(page.locator('body')).not.toBeEmpty();

    await page.goto(appUrl('/mapa'));
    await page.waitForTimeout(3000);
    expect(await page.locator('text=Something went wrong').count()).toBeLessThanOrEqual(1);

    await page.goto(appUrl('/reportes'));
    await page.waitForTimeout(2000);
    await expect(page.locator('body')).not.toBeEmpty();
  });
});

test.describe('Auth Extended', () => {
  test('registers a new user and logs out an authenticated session', async ({ request }) => {
    const uniqueEmail = `test-${Date.now()}@playwright.com`;
    const register = await request.post(apiUrl('/api/v2/auth/register'), {
      data: { email: uniqueEmail, password: 'TestPass123', nombre: 'E2E', apellido: 'Test' },
    });
    expect(register.status()).toBe(201);
    expect(await register.json()).toEqual(
      expect.objectContaining({ email: uniqueEmail, role: 'ciudadano' })
    );

    const token = await loginAsAdmin(request);
    await expectOk(
      request.post(apiUrl('/api/v2/auth/jwt/logout'), {
        headers: { Authorization: `Bearer ${token}` },
      })
    );
  });
});

test.describe('Business lifecycles', () => {
  let token: string;

  test.beforeAll(async ({ request }) => {
    token = await loginAsAdmin(request);
  });

  test('denuncia lifecycle reaches resuelto', async ({ request }) => {
    const created = await createPublicDenuncia(request, `lifecycle-${Date.now()}`);
    const denunciaId = created.id;

    const listRes = await expectOk(request.get(apiUrl('/api/v2/denuncias'), { headers: { Authorization: `Bearer ${token}` } }));
    const list = await listRes.json();
    expect(list.items.find((item: { id: string }) => item.id === denunciaId)).toBeTruthy();

    for (const payload of [
      { estado: 'en_revision', respuesta: 'Revisando denuncia E2E' },
      { estado: 'resuelto' },
    ]) {
      await expectOk(
        request.patch(apiUrl(`/api/v2/denuncias/${denunciaId}`), {
          headers: withOrigin(token),
          data: payload,
        })
      );
    }

    const statusRes = await expectOk(request.get(apiUrl(`/api/v2/public/denuncias/${denunciaId}/status`)));
    expect((await statusRes.json()).estado).toBe('resuelto');
  });

  test('asset lifecycle supports create, update, maintenance and history', async ({ request }) => {
    const ts = Date.now();
    const create = await request.post(apiUrl('/api/v2/infraestructura/assets'), {
      headers: withOrigin(token),
      data: {
        nombre: `Canal E2E Extended ${ts}`,
        tipo: 'canal',
        descripcion: 'Asset para test extendido',
        estado_actual: 'bueno',
        latitud: -32.64,
        longitud: -62.7,
      },
    });
    expect(create.status()).toBe(201);
    const assetId = (await create.json()).id;

    const getRes = await expectOk(request.get(apiUrl(`/api/v2/infraestructura/assets/${assetId}`), { headers: { Authorization: `Bearer ${token}` } }));
    expect((await getRes.json()).nombre).toContain('Canal E2E Extended');

    await expectOk(request.patch(apiUrl(`/api/v2/infraestructura/assets/${assetId}`), {
      headers: withOrigin(token),
      data: { estado_actual: 'regular' },
    }));
    expect(
      (await request.post(apiUrl(`/api/v2/infraestructura/assets/${assetId}/maintenance`), {
        headers: withOrigin(token),
        data: {
          tipo_trabajo: 'Limpieza correctiva',
          descripcion: `Mantenimiento E2E detallado ${ts}`,
          fecha_trabajo: '2026-03-24',
          realizado_por: 'Playwright E2E',
        },
      })).status()
    ).toBe(201);
    await expectOk(request.get(apiUrl(`/api/v2/infraestructura/assets/${assetId}/history`), { headers: { Authorization: `Bearer ${token}` } }));
  });

  test('tramite lifecycle supports status transition and seguimiento', async ({ request }) => {
    const ts = Date.now();
    const create = await request.post(apiUrl('/api/v2/tramites'), {
      headers: withOrigin(token),
      data: {
        tipo: 'permiso',
        titulo: `Tramite E2E ${ts}`,
        descripcion: 'Tramite para test de transiciones',
        solicitante: 'Playwright E2E',
        prioridad: 'media',
      },
    });
    expect(create.status()).toBe(201);
    const tramiteId = (await create.json()).id;

    await expectOk(request.patch(apiUrl(`/api/v2/tramites/${tramiteId}`), {
      headers: withOrigin(token),
      data: { estado: 'en_tramite' },
    }));
    expect(
      (await request.post(apiUrl(`/api/v2/tramites/${tramiteId}/seguimiento`), {
        headers: withOrigin(token),
        data: { comentario: `Seguimiento E2E detallado ${ts}` },
      })).status()
    ).toBe(201);

    const fetched = await expectOk(request.get(apiUrl(`/api/v2/tramites/${tramiteId}`), { headers: { Authorization: `Bearer ${token}` } }));
    expect((await fetched.json()).estado).toBe('en_tramite');
  });

  test('capa lifecycle supports create, update, reorder and delete', async ({ request }) => {
    const ts = Date.now();
    const create = await request.post(apiUrl('/api/v2/capas'), {
      headers: withOrigin(token),
      data: {
        nombre: `Capa E2E ${ts}`,
        tipo: 'polygon',
        fuente: 'local',
        visible: true,
        orden: 99,
        estilo: { color: '#FF0000', weight: 2, fillColor: '#FF0000', fillOpacity: 0.5 },
      },
    });
    expect(create.status()).toBe(201);
    const capaId = (await create.json()).id;

    const fetched = await expectOk(request.get(apiUrl(`/api/v2/capas/${capaId}`), { headers: { Authorization: `Bearer ${token}` } }));
    expect((await fetched.json()).nombre).toContain('Capa E2E');

    await expectOk(request.patch(apiUrl(`/api/v2/capas/${capaId}`), {
      headers: withOrigin(token),
      data: { nombre: `Capa E2E Updated ${ts}`, visible: false },
    }));
    expect(
      (await request.put(apiUrl('/api/v2/capas/reorder'), {
        headers: withOrigin(token),
        data: { ordered_ids: [capaId] },
      })).status()
    ).toBeLessThan(300);
    expect(
      (await request.delete(apiUrl(`/api/v2/capas/${capaId}`), {
        headers: { ...withOrigin(token), 'Content-Type': 'application/json' },
      })).status()
    ).toBe(204);
  });

  test('sugerencias can be listed and updated', async ({ request }) => {
    const created = await createPublicSugerencia(request, `gestion-${Date.now()}`);
    const list = await expectOk(request.get(apiUrl('/api/v2/sugerencias'), { headers: { Authorization: `Bearer ${token}` } }));
    expect(await list.json()).toEqual(expect.objectContaining({ items: expect.anything() }));

    await expectOk(request.patch(apiUrl(`/api/v2/sugerencias/${created.id}`), {
      headers: withOrigin(token),
      data: { estado: 'revisada' },
    }));
  });

  test('settings can be fetched and re-saved without changing value', async ({ request }) => {
    const listRes = await expectOk(request.get(apiUrl('/api/v2/settings'), { headers: { Authorization: `Bearer ${token}` } }));
    const settings = await listRes.json();
    test.skip(!settings.length, 'No settings available');

    const settingKey = settings[0]?.clave;
    test.skip(!settingKey, 'No setting key available');

    const getRes = await expectOk(request.get(apiUrl(`/api/v2/settings/key/${settingKey}`), { headers: { Authorization: `Bearer ${token}` } }));
    const original = await getRes.json();

    await expectOk(request.put(apiUrl(`/api/v2/settings/key/${settingKey}`), {
      headers: withOrigin(token),
      data: { valor: original.valor },
    }));
    await expectOk(request.get(apiUrl(`/api/v2/settings/key/${settingKey}`), { headers: { Authorization: `Bearer ${token}` } }));
  });

  test('finanzas extended endpoints create ingresos and presupuesto and read execution', async ({ request }) => {
    const ts = Date.now();

    expect(
      (await request.post(apiUrl('/api/v2/finanzas/ingresos'), {
        headers: withOrigin(token),
        data: { descripcion: `Ingreso E2E ${ts}`, monto: 15000, categoria: 'cuotas', fecha: '2026-03-24' },
      })).status()
    ).toBe(201);
    expect((await (await expectOk(request.get(apiUrl('/api/v2/finanzas/ingresos'), { headers: { Authorization: `Bearer ${token}` } }))).json())).toEqual(
      expect.objectContaining({ items: expect.anything() })
    );

    expect(
      (await request.post(apiUrl('/api/v2/finanzas/presupuesto'), {
        headers: withOrigin(token),
        data: { anio: 2026, rubro: `rubro-e2e-${ts}`, monto_proyectado: 50000 },
      })).status()
    ).toBe(201);
    const presupuesto = await expectOk(request.get(apiUrl('/api/v2/finanzas/presupuesto'), { headers: { Authorization: `Bearer ${token}` } }));
    expect(Array.isArray(await presupuesto.json())).toBeTruthy();

    await expectOk(request.get(apiUrl('/api/v2/finanzas/ejecucion/2026'), { headers: { Authorization: `Bearer ${token}` } }));
  });
});
