/**
 * Core API module - Base fetch function, auth token handling, API configuration.
 */

import { authAdapter } from '../auth/index';
import { hasLocalLogoutTombstone } from '../auth/storage';
import { logger } from '../logger';

// Backend URL (configure in .env)
// Supports VITE_ and PUBLIC_ prefixes for backwards compatibility
export const API_URL =
  import.meta.env.VITE_API_URL || import.meta.env.PUBLIC_API_URL || 'http://localhost:8000';
export const API_PREFIX = '/api/v2';

// Timeouts en milisegundos
export const DEFAULT_TIMEOUT = 30000; // 30 segundos
export const LONG_TIMEOUT = 60000; // 60 segundos para operaciones largas
export const GEE_TIMEOUT = 300000; // 5 minutos para operaciones GEE (clasificacion supervisada)
export const HEALTH_TIMEOUT = 5000; // 5 segundos para health check

// Token cache configuration
const TOKEN_CACHE_TTL = 5 * 60 * 1000; // 5 minutes cache TTL
let cachedToken: { token: string; expiresAt: number } | null = null;

// Guard: prevent multiple simultaneous 401s from each triggering a separate logout flow
let _handlingAuthExpiry = false;

/**
 * Get the current authentication token from JWT adapter.
 * Caches the token respecting the cache TTL.
 */
export async function getAuthToken(): Promise<string | null> {
  try {
    if (cachedToken && Date.now() < cachedToken.expiresAt) {
      return cachedToken.token;
    }

    const token = await authAdapter.getAccessToken();

    if (token) {
      cachedToken = { token, expiresAt: Date.now() + TOKEN_CACHE_TTL };
    } else {
      cachedToken = null;
    }

    return token;
  } catch {
    cachedToken = null;
    return null;
  }
}

/**
 * Clear the cached auth token. Call this on logout or auth state change.
 */
export function clearAuthTokenCache(): void {
  cachedToken = null;
}

/**
 * Options for the apiFetch function.
 */
export interface ApiFetchOptions extends RequestInit {
  timeout?: number;
  skipAuth?: boolean;
  /**
   * Internal flag: marked when this call is a retry after a refresh-
   * token attempt. Prevents an infinite refresh→retry loop when the
   * new token also gets a 401.
   */
  __alreadyRetried?: boolean;
}

/**
 * Try to refresh the access token via the HttpOnly cookie set on
 * login (Phase 2 / F2-K). Returns ``true`` when a fresh token is now
 * in storage and the caller can retry the original request.
 *
 * Multiple concurrent 401s share a single in-flight refresh promise
 * to avoid hammering the backend.
 */
let _refreshInFlight: Promise<boolean> | null = null;

async function attemptTokenRefresh(signal: AbortSignal): Promise<boolean> {
  if (hasLocalLogoutTombstone()) return false;

  if (_refreshInFlight) {
    const refreshed = await _refreshInFlight;
    return !hasLocalLogoutTombstone() && refreshed;
  }
  _refreshInFlight = (async () => {
    try {
      const response = await fetch(`${API_URL}${API_PREFIX}/auth/jwt/refresh`, {
        method: 'POST',
        credentials: 'include', // sends the HttpOnly refresh_token cookie
        signal,
      });
      if (!response.ok) {
        return false;
      }
      const body = await response.json();
      const token = body?.access_token as string | undefined;
      if (!token || hasLocalLogoutTombstone()) {
        return false;
      }
      // Persist the new access token via the auth adapter so the next
      // ``getAuthToken()`` returns it.
      await authAdapter.replaceAccessToken(token);
      if (hasLocalLogoutTombstone()) return false;
      clearAuthTokenCache();
      return true;
    } catch {
      return false;
    } finally {
      _refreshInFlight = null;
    }
  })();
  return _refreshInFlight;
}

interface RequestAbortScope {
  signal: AbortSignal;
  cleanup: () => void;
}

function createRequestAbortScope(
  timeout: number,
  callerSignal?: AbortSignal | null
): RequestAbortScope {
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort(callerSignal?.reason);

  if (callerSignal?.aborted) {
    abortFromCaller();
  } else {
    callerSignal?.addEventListener('abort', abortFromCaller, { once: true });
  }

  const timeoutId = setTimeout(() => controller.abort(), timeout);
  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timeoutId);
      callerSignal?.removeEventListener('abort', abortFromCaller);
    },
  };
}

function waitForWithSignal<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  if (signal.aborted) {
    return Promise.reject(new DOMException('The operation was aborted', 'AbortError'));
  }

  return new Promise<T>((resolve, reject) => {
    const abort = () => reject(new DOMException('The operation was aborted', 'AbortError'));
    signal.addEventListener('abort', abort, { once: true });
    promise.then(
      (value) => {
        signal.removeEventListener('abort', abort);
        resolve(value);
      },
      (error: unknown) => {
        signal.removeEventListener('abort', abort);
        reject(error);
      }
    );
  });
}

function hasItemsArray<T>(data: unknown): data is { items: T[] } {
  return (
    typeof data === 'object' &&
    data !== null &&
    'items' in data &&
    Array.isArray((data as { items?: unknown }).items)
  );
}

function getApiErrorMessage(error: unknown, status: number): string {
  if (typeof error !== 'object' || error === null) {
    return `API Error: ${status}`;
  }

  const payload = error as {
    detail?: unknown;
    message?: unknown;
    error?: { message?: unknown };
  };

  if (typeof payload.detail === 'string') return payload.detail;
  if (typeof payload.message === 'string') return payload.message;
  if (typeof payload.error?.message === 'string') return payload.error.message;

  return `API Error: ${status}`;
}

/**
 * Fetch wrapper con manejo de errores, timeout y autenticacion automatica.
 */
async function authenticatedFetchResponse<T>(
  url: string,
  options: ApiFetchOptions,
  consumeResponse: (response: Response) => Promise<T>,
  sharedAbortScope?: RequestAbortScope
): Promise<T> {
  const {
    timeout = DEFAULT_TIMEOUT,
    skipAuth = false,
    __alreadyRetried = false,
    signal: callerSignal,
    ...fetchOptions
  } = options;
  const ownsAbortScope = sharedAbortScope === undefined;
  const abortScope = sharedAbortScope ?? createRequestAbortScope(timeout, callerSignal);

  try {
    const authHeaders: Record<string, string> = {};
    if (!skipAuth) {
      const token = await getAuthToken();
      if (token) {
        authHeaders.Authorization = `Bearer ${token}`;
      }
    }

    const isFormData = fetchOptions.body instanceof FormData;
    const defaultHeaders: Record<string, string> = isFormData
      ? {}
      : { 'Content-Type': 'application/json' };

    const response = await fetch(url, {
      ...fetchOptions,
      signal: abortScope.signal,
      headers: {
        ...defaultHeaders,
        ...authHeaders,
        ...fetchOptions.headers,
      },
    });

    if (!response.ok) {
      const error = await waitForWithSignal(
        response.json().catch(() => ({})),
        abortScope.signal
      );

      if (response.status === 401 && !skipAuth && !__alreadyRetried) {
        const refreshed = await waitForWithSignal(
          attemptTokenRefresh(abortScope.signal),
          abortScope.signal
        );
        if (refreshed) {
          return await authenticatedFetchResponse(
            url,
            { ...options, __alreadyRetried: true },
            consumeResponse,
            abortScope
          );
        }

        if (!_handlingAuthExpiry) {
          _handlingAuthExpiry = true;
          logger.warn('Sesion expirada — redirigiendo a login');
          clearAuthTokenCache();
          authAdapter.clearTokens();
          window.dispatchEvent(new CustomEvent('auth:expired'));
          setTimeout(() => {
            _handlingAuthExpiry = false;
          }, 10_000);
        }
        throw new Error('Tu sesion ha expirado. Por favor inicia sesion nuevamente.');
      }

      throw new Error(getApiErrorMessage(error, response.status));
    }

    return await waitForWithSignal(consumeResponse(response), abortScope.signal);
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      if (callerSignal?.aborted) {
        throw error;
      }
      throw new Error(`La solicitud excedio el tiempo limite (${timeout / 1000}s)`);
    }
    throw error;
  } finally {
    if (ownsAbortScope) {
      abortScope.cleanup();
    }
  }
}

export async function apiFetch<T>(endpoint: string, options: ApiFetchOptions = {}): Promise<T> {
  return authenticatedFetchResponse(
    `${API_URL}${API_PREFIX}${endpoint}`,
    options,
    async (response) => {
      if (response.status === 204 || response.headers.get('content-length') === '0') {
        return undefined as T;
      }
      return response.json() as Promise<T>;
    }
  );
}

function resolveProtectedPhotoUrl(resource: string): string {
  const apiBase = new URL(API_URL);
  const resolved = new URL(resource, `${apiBase.origin}/`);

  if (
    resolved.origin !== apiBase.origin ||
    !resolved.pathname.startsWith('/uploads/denuncias/') ||
    resolved.username ||
    resolved.password ||
    resolved.searchParams.has('access_token')
  ) {
    throw new Error('La URL de la imagen protegida no pertenece al servidor autorizado.');
  }

  return resolved.toString();
}

/**
 * Load a protected denuncia photo without putting bearer credentials in its URL.
 * Uses the same one-shot refresh/retry and auth-expiry behavior as apiFetch.
 */
export async function fetchAuthenticatedBlob(
  resource: string,
  options: ApiFetchOptions = {}
): Promise<Blob> {
  return authenticatedFetchResponse(
    resolveProtectedPhotoUrl(resource),
    options,
    (response) => response.blob()
  );
}

/**
 * Health check for the API backend.
 */
export const healthCheck = async (): Promise<boolean> => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), HEALTH_TIMEOUT);

  try {
    const response = await fetch(`${API_URL}/health`, {
      signal: controller.signal,
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutId);
  }
};

/**
 * Unwrap a potentially paginated response to get the items array.
 * Handles both plain arrays and {items: T[]} responses.
 */
export function unwrapItems<T>(data: T[] | { items: T[] } | unknown): T[] {
  if (Array.isArray(data)) return data;
  if (hasItemsArray<T>(data)) return data.items;
  return [];
}

/**
 * Helper function to get Accept header for export format.
 * Avoids nested ternary operators (SonarQube S3358).
 */
export function getExportAcceptHeader(format: string): string {
  if (format === 'csv') return 'text/csv';
  if (format === 'json') return 'application/json';
  return 'application/pdf';
}
