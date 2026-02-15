/**
 * Core API module - Base fetch function, auth token handling, API configuration.
 */

import { getSupabaseClient } from '../supabase';

// Backend URL (configure in .env)
// Supports VITE_ and PUBLIC_ prefixes for backwards compatibility
export const API_URL = import.meta.env.VITE_API_URL || import.meta.env.PUBLIC_API_URL || 'http://localhost:8000';
export const API_PREFIX = '/api/v1';

// Timeouts en milisegundos
export const DEFAULT_TIMEOUT = 30000; // 30 segundos
export const LONG_TIMEOUT = 60000; // 60 segundos para operaciones largas
export const GEE_TIMEOUT = 300000; // 5 minutos para operaciones GEE (clasificacion supervisada)
export const HEALTH_TIMEOUT = 5000; // 5 segundos para health check

// Token cache configuration
const TOKEN_CACHE_TTL = 5 * 60 * 1000; // 5 minutes cache TTL
let cachedToken: { token: string; expiresAt: number } | null = null;

/**
 * Get the current authentication token from Supabase session.
 * Caches the token respecting both the cache TTL and the actual JWT expiry.
 */
export async function getAuthToken(): Promise<string | null> {
  try {
    // Check cache first
    if (cachedToken && Date.now() < cachedToken.expiresAt) {
      return cachedToken.token;
    }

    const { data: { session } } = await getSupabaseClient().auth.getSession();
    const token = session?.access_token || null;

    // Cache the token if valid, respecting JWT expiry
    if (token && session?.expires_at) {
      const expiresAt = Math.min(
        Date.now() + TOKEN_CACHE_TTL,
        session.expires_at * 1000 - 30_000
      );
      cachedToken = { token, expiresAt };
    } else if (token) {
      cachedToken = {
        token,
        expiresAt: Date.now() + TOKEN_CACHE_TTL,
      };
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

/**
 * Fetch wrapper con manejo de errores, timeout y autenticacion automatica.
 */
export async function apiFetch<T>(
  endpoint: string,
  options: ApiFetchOptions = {}
): Promise<T> {
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

    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders,
        ...fetchOptions.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `API Error: ${response.status}`);
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
 * Helper function to get Accept header for export format.
 * Avoids nested ternary operators (SonarQube S3358).
 */
export function getExportAcceptHeader(format: string): string {
  if (format === 'csv') return 'text/csv';
  if (format === 'json') return 'application/json';
  return 'application/pdf';
}
