import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  AUTH_TOKEN_KEY,
  AUTH_USER_KEY,
  clearAuthStorage,
  getStoredAccessToken,
  getStoredAuthSession,
  persistAuthSession,
} from '../../src/lib/auth/storage';
import type { AuthSession } from '../../src/lib/auth/types';

const user = {
  id: 'user-1',
  email: 'admin@example.com',
  nombre: 'Ada',
  apellido: 'Lovelace',
  telefono: '',
  role: 'admin' as const,
};

const session: AuthSession = {
  access_token: 'session-token',
  user,
};

describe('auth storage', () => {
  let localStore: Record<string, string>;

  beforeEach(() => {
    window.sessionStorage.clear();
    localStore = {};
    vi.mocked(window.localStorage.getItem).mockImplementation((key: string) => localStore[key] ?? null);
    vi.mocked(window.localStorage.setItem).mockImplementation((key: string, value: string) => {
      localStore[key] = value;
    });
    vi.mocked(window.localStorage.removeItem).mockImplementation((key: string) => {
      delete localStore[key];
    });
    vi.mocked(window.localStorage.clear).mockImplementation(() => {
      localStore = {};
    });
  });

  it('persists new sessions in sessionStorage instead of localStorage', () => {
    persistAuthSession(session);

    expect(window.sessionStorage.getItem(AUTH_TOKEN_KEY)).toBe('session-token');
    expect(window.sessionStorage.getItem(AUTH_USER_KEY)).toBe(JSON.stringify(user));
    expect(window.localStorage.getItem(AUTH_TOKEN_KEY) ?? null).toBeNull();
    expect(window.localStorage.getItem(AUTH_USER_KEY) ?? null).toBeNull();
    expect(getStoredAccessToken()).toBe('session-token');
  });

  it('migrates a legacy localStorage session into sessionStorage and clears localStorage', () => {
    window.localStorage.setItem(AUTH_TOKEN_KEY, 'legacy-token');
    window.localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));

    const migrated = getStoredAuthSession();

    expect(migrated).toEqual({ access_token: 'legacy-token', user });
    expect(window.sessionStorage.getItem(AUTH_TOKEN_KEY)).toBe('legacy-token');
    expect(window.localStorage.getItem(AUTH_TOKEN_KEY) ?? null).toBeNull();
    expect(window.localStorage.getItem(AUTH_USER_KEY) ?? null).toBeNull();
  });

  it('clears session and legacy auth storage', () => {
    window.sessionStorage.setItem(AUTH_TOKEN_KEY, 'session-token');
    window.sessionStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
    window.localStorage.setItem(AUTH_TOKEN_KEY, 'legacy-token');
    window.localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));

    clearAuthStorage();

    expect(getStoredAuthSession()).toBeNull();
    expect(window.sessionStorage.getItem(AUTH_TOKEN_KEY) ?? null).toBeNull();
    expect(window.localStorage.getItem(AUTH_TOKEN_KEY) ?? null).toBeNull();
  });
});
