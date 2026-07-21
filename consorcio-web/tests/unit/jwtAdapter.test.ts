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

function response(status: number, body: unknown = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response;
}

function expectLocalSessionCleared(): void {
  expect(window.sessionStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
  expect(window.sessionStorage.getItem(AUTH_USER_KEY)).toBeNull();
}

function expectLocalSessionRetained(): void {
  expect(window.sessionStorage.getItem(AUTH_TOKEN_KEY)).toBe('current-access-token');
  expect(window.sessionStorage.getItem(AUTH_USER_KEY)).not.toBeNull();
}

describe('JWTAuthAdapter.logout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    persistAuthSession(SESSION);
  });

  it('revokes every refresh session before clearing local auth state', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(204));
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

  it('refreshes a stale access token and retries logout-all once', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(401, { detail: 'expired' }))
      .mockResolvedValueOnce(response(200, { access_token: 'fresh-access-token' }))
      .mockResolvedValueOnce(response(204));
    vi.stubGlobal('fetch', fetchMock);
    const adapter = new JWTAuthAdapter();

    await adapter.logout();

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toBe('http://localhost:8000/api/v2/auth/jwt/refresh');
    expect(fetchMock.mock.calls[1][1]).toEqual({
      method: 'POST',
      credentials: 'include',
    });
    expect(fetchMock.mock.calls[2][1]).toEqual({
      method: 'POST',
      credentials: 'include',
      headers: { Authorization: 'Bearer fresh-access-token' },
    });
    expectLocalSessionCleared();
  });

  it('keeps local auth state when refreshed logout revocation still fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(401, { detail: 'expired' }))
      .mockResolvedValueOnce(response(200, { access_token: 'fresh-access-token' }))
      .mockResolvedValueOnce(response(503, { detail: 'unavailable' }));
    vi.stubGlobal('fetch', fetchMock);
    const adapter = new JWTAuthAdapter();

    await expect(adapter.logout()).rejects.toThrow(/cerrar la sesión/i);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expectLocalSessionRetained();
  });

  it('rejects a server revocation failure and keeps local auth state', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(503, { detail: 'unavailable' }));
    vi.stubGlobal('fetch', fetchMock);
    const listener = vi.fn();
    const adapter = new JWTAuthAdapter();
    adapter.onAuthStateChange(listener);

    await expect(adapter.logout()).rejects.toThrow(/cerrar la sesión/i);

    expectLocalSessionRetained();
    expect(listener).not.toHaveBeenCalled();
  });

  it('rejects a network failure and keeps local auth state', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('network unavailable'));
    vi.stubGlobal('fetch', fetchMock);
    const listener = vi.fn();
    const adapter = new JWTAuthAdapter();
    adapter.onAuthStateChange(listener);

    await expect(adapter.logout()).rejects.toThrow('network unavailable');

    expectLocalSessionRetained();
    expect(listener).not.toHaveBeenCalled();
  });
});
