import { beforeEach, describe, expect, it, vi } from 'vitest';

import { JWTAuthAdapter } from '../../src/lib/auth/jwt-adapter';
import {
  AUTH_TOKEN_KEY,
  AUTH_USER_KEY,
  clearLocalLogoutTombstone,
  hasLocalLogoutTombstone,
  markLocalLogout,
  persistAuthSession,
} from '../../src/lib/auth/storage';
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

describe('JWTAuthAdapter.logout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    clearLocalLogoutTombstone();
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
    expect(hasLocalLogoutTombstone()).toBe(true);
    expect(listener).toHaveBeenCalledWith('SIGNED_OUT', null);

    await adapter.replaceAccessToken('resurrection-token');
    expect(fetchMock).toHaveBeenCalledOnce();
    expectLocalSessionCleared();
  });

  it('does not clear the tombstone when explicit login fails', async () => {
    markLocalLogout();
    const fetchMock = vi.fn().mockResolvedValue(response(401, { detail: 'bad credentials' }));
    vi.stubGlobal('fetch', fetchMock);
    const adapter = new JWTAuthAdapter();

    await expect(
      adapter.login({ email: 'admin@example.com', password: 'wrong-password' })
    ).rejects.toThrow();

    expect(hasLocalLogoutTombstone()).toBe(true);
    await expect(adapter.getSession()).resolves.toBeNull();
    expectLocalSessionCleared();
  });

  it('clears the tombstone only after explicit login succeeds', async () => {
    markLocalLogout();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(200, { access_token: 'new-explicit-token' }))
      .mockResolvedValueOnce(
        response(200, {
          id: SESSION.user.id,
          email: SESSION.user.email,
          nombre: SESSION.user.nombre,
          apellido: SESSION.user.apellido,
          role: SESSION.user.role,
        })
      )
      .mockResolvedValueOnce(response(204));
    vi.stubGlobal('fetch', fetchMock);
    const adapter = new JWTAuthAdapter();

    await adapter.login({ email: 'admin@example.com', password: 'correct-password' });

    expect(hasLocalLogoutTombstone()).toBe(false);
    expect(window.sessionStorage.getItem(AUTH_TOKEN_KEY)).toBe('new-explicit-token');
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

  it('clears local auth state when refreshed logout revocation still fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(401, { detail: 'expired' }))
      .mockResolvedValueOnce(response(200, { access_token: 'fresh-access-token' }))
      .mockResolvedValueOnce(response(503, { detail: 'unavailable' }));
    vi.stubGlobal('fetch', fetchMock);
    const listener = vi.fn();
    const adapter = new JWTAuthAdapter();
    adapter.onAuthStateChange(listener);

    await expect(adapter.logout()).rejects.toThrow(/cerrar la sesión/i);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expectLocalSessionCleared();
    expect(listener).toHaveBeenCalledWith('SIGNED_OUT', null);
  });

  it('rejects a server revocation failure after clearing local auth state', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(503, { detail: 'unavailable' }));
    vi.stubGlobal('fetch', fetchMock);
    const listener = vi.fn();
    const adapter = new JWTAuthAdapter();
    adapter.onAuthStateChange(listener);

    await expect(adapter.logout()).rejects.toThrow(/cerrar la sesión/i);

    expectLocalSessionCleared();
    expect(listener).toHaveBeenCalledWith('SIGNED_OUT', null);
  });

  it('rejects a network failure after clearing local auth state', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('network unavailable'));
    vi.stubGlobal('fetch', fetchMock);
    const listener = vi.fn();
    const adapter = new JWTAuthAdapter();
    adapter.onAuthStateChange(listener);

    await expect(adapter.logout()).rejects.toThrow('network unavailable');

    expectLocalSessionCleared();
    expect(listener).toHaveBeenCalledWith('SIGNED_OUT', null);
  });

  it('converges locally after an ambiguous revoke followed by refresh 401', async () => {
    const fetchMock = vi
      .fn()
      // The server may have processed logout-all before the response was lost.
      .mockRejectedValueOnce(new TypeError('connection lost after revoke'))
      // A second local logout has no access token and the revoked cookie now returns 401.
      .mockResolvedValueOnce(response(401, { detail: 'refresh token revoked' }));
    vi.stubGlobal('fetch', fetchMock);
    const listener = vi.fn();
    const adapter = new JWTAuthAdapter();
    adapter.onAuthStateChange(listener);

    await expect(adapter.logout()).rejects.toThrow('connection lost after revoke');
    expectLocalSessionCleared();

    await expect(adapter.logout()).rejects.toThrow(/renovar la sesión/i);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toBe('http://localhost:8000/api/v2/auth/jwt/refresh');
    expectLocalSessionCleared();
    expect(listener).toHaveBeenNthCalledWith(1, 'SIGNED_OUT', null);
    expect(listener).toHaveBeenNthCalledWith(2, 'SIGNED_OUT', null);
  });
});
