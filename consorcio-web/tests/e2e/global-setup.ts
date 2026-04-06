/**
 * Global setup para tests E2E locales.
 * Hace login una vez, guarda el storageState (localStorage + cookies).
 * Cada test reutiliza ese estado sin re-autenticar.
 */

import { chromium, type FullConfig } from '@playwright/test';

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'e2e@test.com';
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'e2etest123';
const API_BASE = 'http://localhost:8000/api/v2';
const TOKEN_KEY = 'consorcio_auth_token';
const USER_KEY = 'consorcio_auth_user';

export default async function globalSetup(_config: FullConfig) {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // 1. Login via API
  const formData = new URLSearchParams();
  formData.append('username', ADMIN_EMAIL);
  formData.append('password', ADMIN_PASSWORD);

  const loginRes = await page.request.post(`${API_BASE}/auth/jwt/login`, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    data: formData.toString(),
  });

  if (!loginRes.ok()) {
    throw new Error(`Global setup login failed: ${loginRes.status()} ${await loginRes.text()}`);
  }

  const { access_token: token } = await loginRes.json() as { access_token: string };

  // 2. Fetch user data
  const userRes = await page.request.get(`${API_BASE}/users/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!userRes.ok()) {
    throw new Error(`Global setup fetch user failed: ${userRes.status()}`);
  }

  const user = await userRes.json();

  // 3. Navegar al sitio e inyectar localStorage
  await page.goto('http://localhost:5173/');
  await page.waitForTimeout(1000);

  await page.evaluate(
    ({ tokenKey, userKey, authToken, userData }) => {
      window.localStorage.setItem(tokenKey, authToken);
      window.localStorage.setItem(userKey, JSON.stringify(userData));
    },
    { tokenKey: TOKEN_KEY, userKey: USER_KEY, authToken: token, userData: user }
  );

  // 4. Guardar storage state para que todos los tests lo usen
  await page.context().storageState({ path: 'tests/e2e/.auth/admin.json' });

  await browser.close();
}
