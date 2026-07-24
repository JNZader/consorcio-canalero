import type { AuthSession, AuthUser } from './types';

export const AUTH_TOKEN_KEY = 'consorcio_auth_token';
export const AUTH_USER_KEY = 'consorcio_auth_user';

const LOCAL_LOGOUT_STATE = {
  TOMBSTONE_KEY: 'consorcio_auth_logout_tombstone',
  TOMBSTONE_VALUE: 'logged-out',
  WARNING_KEY: 'consorcio_auth_logout_warning',
  WARNING_VALUE: 'remote-revocation-unconfirmed',
} as const;

const REMOTE_LOGOUT_WARNING =
  'La sesión local se cerró, pero no pudimos confirmar el cierre de todas las sesiones en el servidor.';

let logoutTombstonedInMemory = false;
let logoutWarningInMemory = false;

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

export function markLocalLogout(): void {
  logoutTombstonedInMemory = true;
  try {
    getLegacyLocalStorage()?.setItem(
      LOCAL_LOGOUT_STATE.TOMBSTONE_KEY,
      LOCAL_LOGOUT_STATE.TOMBSTONE_VALUE
    );
  } catch {
    // The in-memory tombstone still protects the current page when storage is unavailable.
  }
}

export function hasLocalLogoutTombstone(): boolean {
  if (logoutTombstonedInMemory) return true;
  try {
    return (
      getLegacyLocalStorage()?.getItem(LOCAL_LOGOUT_STATE.TOMBSTONE_KEY) ===
      LOCAL_LOGOUT_STATE.TOMBSTONE_VALUE
    );
  } catch {
    return logoutTombstonedInMemory;
  }
}

export function clearLocalLogoutTombstone(): void {
  logoutTombstonedInMemory = false;
  try {
    getLegacyLocalStorage()?.removeItem(LOCAL_LOGOUT_STATE.TOMBSTONE_KEY);
  } catch {
    // Explicit login can still clear the in-memory guard in restricted environments.
  }
}

export function storeLocalLogoutWarning(): void {
  logoutWarningInMemory = true;
  try {
    getLegacyLocalStorage()?.setItem(
      LOCAL_LOGOUT_STATE.WARNING_KEY,
      LOCAL_LOGOUT_STATE.WARNING_VALUE
    );
  } catch {
    // Keep a one-shot warning for the current page when durable storage is unavailable.
  }
}

export function consumeLocalLogoutWarning(): string | null {
  let hasWarning = logoutWarningInMemory;
  logoutWarningInMemory = false;

  try {
    const storage = getLegacyLocalStorage();
    hasWarning ||=
      storage?.getItem(LOCAL_LOGOUT_STATE.WARNING_KEY) === LOCAL_LOGOUT_STATE.WARNING_VALUE;
    storage?.removeItem(LOCAL_LOGOUT_STATE.WARNING_KEY);
  } catch {
    // The in-memory marker was already consumed above.
  }

  return hasWarning ? REMOTE_LOGOUT_WARNING : null;
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
  if (hasLocalLogoutTombstone()) {
    clearAuthStorage();
    return null;
  }

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
  if (hasLocalLogoutTombstone()) return;

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

/**
 * Best-effort purge of every service-worker cache holding API responses.
 *
 * Called on logout so the next user of a shared device can't pop
 * cached padron / denuncias / finanzas bodies out of the SW caches.
 * Safe in environments without service workers (silent no-op).
 *
 * Currently we drop every cache whose name starts with ``api-``
 * (matches both ``api-public`` and any future named cache). The
 * ``app-shell`` precache is left intact — its contents are public
 * static assets, no PII risk.
 */
export async function clearApiServiceWorkerCaches(): Promise<void> {
  if (typeof window === 'undefined' || !('caches' in window)) {
    return;
  }
  try {
    const names = await window.caches.keys();
    await Promise.all(
      names.filter((name) => name.startsWith('api-')).map((name) => window.caches.delete(name))
    );
  } catch {
    // SW disabled or storage quota error — best-effort, no fallback needed.
  }
}
