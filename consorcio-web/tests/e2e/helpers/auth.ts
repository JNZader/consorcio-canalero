import type { Page } from '@playwright/test';
import { expect } from '@playwright/test';

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'e2e@test.com';
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'e2etest123';
const API_BASE = 'http://localhost:8000/api/v2';

// Keys from jwt-adapter.ts
const TOKEN_KEY = 'consorcio_auth_token';
const USER_KEY = 'consorcio_auth_user';

export async function loginAsAdmin(page: Page): Promise<void> {
  // 1. Obtener JWT via API
  const formData = new URLSearchParams();
  formData.append('username', ADMIN_EMAIL);
  formData.append('password', ADMIN_PASSWORD);

  const loginRes = await page.request.post(`${API_BASE}/auth/jwt/login`, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    data: formData.toString(),
  });

  if (!loginRes.ok()) {
    throw new Error(`Login failed: ${loginRes.status()} ${await loginRes.text()}`);
  }

  const { access_token: token } = await loginRes.json() as { access_token: string };

  // 2. Obtener datos del usuario
  const userRes = await page.request.get(`${API_BASE}/users/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!userRes.ok()) {
    throw new Error(`Could not fetch user: ${userRes.status()}`);
  }

  const user = await userRes.json();

  // 3. Navegar para que localStorage esté disponible en el dominio
  await page.goto('/');
  await page.waitForTimeout(500);

  // 4. Inyectar token y user en localStorage — exactamente como lo hace jwt-adapter.ts
  await page.evaluate(
    ({ tokenKey, userKey, token, user }) => {
      window.localStorage.setItem(tokenKey, token);
      window.localStorage.setItem(userKey, JSON.stringify(user));
    },
    { tokenKey: TOKEN_KEY, userKey: USER_KEY, token, user }
  );
}

export async function expectAdminRedirect(page: Page): Promise<void> {
  const url = page.url();
  const body = await page.textContent('body');
  const isAdmin =
    url.includes('/admin') ||
    body?.includes('Panel') ||
    body?.includes('Dashboard') ||
    body?.includes('Bienvenido');
  expect(isAdmin).toBeTruthy();
}
