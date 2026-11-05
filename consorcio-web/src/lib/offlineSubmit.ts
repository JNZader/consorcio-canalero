import { QueryError } from './queryError';

/**
 * El service worker responde 503 (NetworkOnly) cuando el POST sale sin red.
 * Un `fetch` que el worker rechaza llega como TypeError "Failed to fetch".
 * Los dos son el mismo estado para denuncia y sugerencia.
 */
export function isOfflineSubmitError(error: unknown): boolean {
  if (error instanceof QueryError && error.statusCode === 503) return true;
  if (!(error instanceof Error)) return false;
  if (/\b503\b/.test(error.message) || /service unavailable/i.test(error.message)) return true;
  return /failed to fetch|networkerror|network request failed|load failed/i.test(error.message);
}
