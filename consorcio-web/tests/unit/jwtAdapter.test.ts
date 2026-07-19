import { beforeEach, describe, expect, it, vi } from 'vitest';

import { JWTAuthAdapter } from '../../src/lib/auth/jwt-adapter';
import { AUTH_TOKEN_KEY, AUTH_USER_KEY, persistAuthSession } from '../../src/lib/auth/storage';
import type { AuthSession } from '../../src/lib/auth/types';

const SESSION: AuthSession = {
  access_token: 'current-access-token',
  user: {
    id: 'user-1',
    email: 'admin@example.com',
    nombre: 'Admin',
    apellido: 'Canalero',
    telefono: '',
    role: 'admin',
  },
};

function expectLocalSessionCleared(): void {
  expect(window.sessionStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
  expect(window.sessionStorage.getItem(AUTH_USER_KEY)).toBeNull();
}

describe('JWTAuthAdapter.logout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    persistAuthSession(SESSION);
  });

  it('revokes every refresh session before clearing local auth state', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);
    const listener = vi.fn();
    const adapter = new JWTAuthAdapter();
    adapter.onAuthStateChange(listener);

    await adapter.logout();

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/v2/auth/jwt/logout-all', {
      method: 'POST',
      credentials: 'include',
      headers: {
        Authorization: 'Bearer current-access-token',
      },
    });
    expectLocalSessionCleared();
    expect(listener).toHaveBeenCalledWith('SIGNED_OUT', null);
  });

  it('still clears local auth state when server revocation fails', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('network unavailable'));
    vi.stubGlobal('fetch', fetchMock);
    const listener = vi.fn();
    const adapter = new JWTAuthAdapter();
    adapter.onAuthStateChange(listener);

    await expect(adapter.logout()).resolves.toBeUndefined();

    expect(fetchMock).toHaveBeenCalledOnce();
    expectLocalSessionCleared();
    expect(listener).toHaveBeenCalledWith('SIGNED_OUT', null);
  });
});
