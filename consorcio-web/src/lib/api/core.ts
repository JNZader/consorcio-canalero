/**
 * Core API module - Base fetch function, auth token handling, API configuration.
 */

import { authAdapter } from '../auth/index';
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
export async function apiFetch<T>(endpoint: string, options: ApiFetchOptions = {}): Promise<T> {
  const url = `${API_URL}${API_PREFIX}${endpoint}`;
  const { timeout = DEFAULT_TIMEOUT, skipAuth = false, ...fetchOptions } = options;

  // Crear AbortController para timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    // Get auth token if not skipped
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
      signal: controller.signal,
      headers: {
        ...defaultHeaders,
        ...authHeaders,
        ...fetchOptions.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));

      // Handle expired/invalid token — auto-logout + redirect
      // Guard prevents multiple parallel 401s from each triggering a separate logout
      if (response.status === 401 && !skipAuth) {
        if (!_handlingAuthExpiry) {
          _handlingAuthExpiry = true;
          logger.warn('Sesion expirada — redirigiendo a login');
          clearAuthTokenCache();
          authAdapter.clearTokens();
          window.dispatchEvent(new CustomEvent('auth:expired'));
          // Reset flag after redirect completes (fallback: 10s)
          setTimeout(() => {
            _handlingAuthExpiry = false;
          }, 10_000);
        }
        throw new Error('Tu sesion ha expirado. Por favor inicia sesion nuevamente.');
      }

      throw new Error(getApiErrorMessage(error, response.status));
    }

    return response.json();
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error(`La solicitud excedio el tiempo limite (${timeout / 1000}s)`);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
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
