import { test, expect, type APIRequestContext } from '@playwright/test';

const API_BASE = 'http://localhost:8000/api/v2';
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'e2e@test.com';
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'e2etest123';

async function getAuthToken(request: APIRequestContext): Promise<string> {
  // fastapi-users usa OAuth2PasswordRequestForm (form-urlencoded)
  const formData = new URLSearchParams();
  formData.append('username', ADMIN_EMAIL);
  formData.append('password', ADMIN_PASSWORD);

  const res = await request.post(`${API_BASE}/auth/jwt/login`, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    data: formData.toString(),
  });

  expect(res.status()).toBe(200);
  const body = await res.json() as { access_token: string };
  return body.access_token;
}

test.describe('Rainfall API', () => {
  test('GET /geo/rainfall/summary responde 200 con estructura esperada', async ({ request }) => {
    const token = await getAuthToken(request);

    // El endpoint requiere start y end como query params (YYYY-MM-DD)
    const end = new Date().toISOString().split('T')[0];
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - 30);
    const start = startDate.toISOString().split('T')[0];

    const res = await request.get(`${API_BASE}/geo/rainfall/summary?start=${start}&end=${end}`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    expect(res.status()).toBe(200);
    const body = await res.json() as Record<string, unknown>;
    expect(typeof body).toBe('object');
  });

  test('GET /geo/rainfall/events responde 200 con estructura paginada', async ({ request }) => {
    const token = await getAuthToken(request);

    const res = await request.get(`${API_BASE}/geo/rainfall/events`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    expect(res.status()).toBe(200);
    // Retorna objeto con campo "events" (array) no array directo
    const body = await res.json() as { events: unknown[] };
    expect(Array.isArray(body.events)).toBeTruthy();
  });

  test('GET /geo/rainfall/zona/:id responde 200 o 404 con estructura correcta', async ({ request }) => {
    const token = await getAuthToken(request);

    // Zona ID de prueba — si no existe devuelve 404, que tambien es valido
    const res = await request.get(`${API_BASE}/geo/rainfall/zona/1`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    expect([200, 404]).toContain(res.status());

    if (res.status() === 200) {
      const body = await res.json() as Record<string, unknown>;
      expect(typeof body).toBe('object');
    }
  });

  test.skip('POST /geo/rainfall/backfill requiere GEE disponible', async ({ request }) => {
    // El backfill llama a Google Earth Engine para descargar datos CHIRPS.
    // No ejecutar en CI/CD sin credenciales GEE configuradas.
  });
});
