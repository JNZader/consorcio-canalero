import type { AuthSession, AuthUser } from './types';

export const AUTH_TOKEN_KEY = 'consorcio_auth_token';
export const AUTH_USER_KEY = 'consorcio_auth_user';

type BrowserStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function getSessionStorage(): BrowserStorage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function getLegacyLocalStorage(): BrowserStorage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function readSessionFrom(storage: BrowserStorage): AuthSession | null {
  const token = storage.getItem(AUTH_TOKEN_KEY);
  const userJson = storage.getItem(AUTH_USER_KEY);

  if (!token || !userJson) return null;

  try {
    const user = JSON.parse(userJson) as AuthUser;
    return { access_token: token, user };
  } catch {
    storage.removeItem(AUTH_TOKEN_KEY);
    storage.removeItem(AUTH_USER_KEY);
    return null;
  }
}

function clearLegacyLocalAuth(): void {
  const legacy = getLegacyLocalStorage();
  legacy?.removeItem(AUTH_TOKEN_KEY);
  legacy?.removeItem(AUTH_USER_KEY);
}

export function getStoredAuthSession(): AuthSession | null {
  const sessionStorage = getSessionStorage();
  const session = sessionStorage ? readSessionFrom(sessionStorage) : null;
  if (session) return session;

  const legacyStorage = getLegacyLocalStorage();
  const legacySession = legacyStorage ? readSessionFrom(legacyStorage) : null;

  if (legacySession) {
    persistAuthSession(legacySession);
  }

  return legacySession;
}

export function getStoredAccessToken(): string | null {
  return getStoredAuthSession()?.access_token ?? null;
}

export function persistAuthSession(session: AuthSession): void {
  const storage = getSessionStorage();
  if (!storage) return;

  storage.setItem(AUTH_TOKEN_KEY, session.access_token);
  storage.setItem(AUTH_USER_KEY, JSON.stringify(session.user));
  clearLegacyLocalAuth();
}

export function clearAuthStorage(): void {
  const storage = getSessionStorage();
  storage?.removeItem(AUTH_TOKEN_KEY);
  storage?.removeItem(AUTH_USER_KEY);
  clearLegacyLocalAuth();
}
