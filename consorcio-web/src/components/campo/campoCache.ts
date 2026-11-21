/**
 * Campo (PR 6, S5) — package loader with Cache Storage fallback.
 *
 * "Primer uso con señal → funciona sin red": the FIRST successful fetch is
 * written to Cache Storage by the PAGE (not only by the service worker) so
 * the offline guarantee holds even while the SW is still installing, in
 * dev (no SW), or on browsers with flaky SW timing. The production SW adds
 * its own CacheFirst rule for the same URL and cache name
 * (`pwaPrecachePolicy.ts` → `campo-packages`), so both layers agree.
 *
 * On a network failure the cache answers; if both fail the caller renders
 * the honest error state — never a fabricated empty map.
 */

import type { PaqueteCampo } from './tiposCampo';

export const CAMPO_CACHE = 'campo-packages';

/** Raised when the public endpoint explicitly reports 404/410 (expired/revoked link). */
export class CampoRevocadoError extends Error {
  readonly status: number;
  constructor(status: number) {
    super(`campo_http_${status}`);
    this.name = 'CampoRevocadoError';
    this.status = status;
  }
}

export interface RespuestaCache {
  paquete: PaqueteCampo;
  desdeCache: boolean;
  avisoCache: string | null;
}

function esQuotaExceeded(error: unknown): boolean {
  if (error instanceof Error && error.name === 'QuotaExceededError') return true;
  if (
    typeof DOMException !== 'undefined' &&
    error instanceof DOMException &&
    (error.name === 'QuotaExceededError' || error.code === 22)
  ) {
    return true;
  }
  return false;
}

async function eliminarDeCache(url: string): Promise<void> {
  try {
    if (typeof caches === 'undefined') return;
    const cache = await caches.open(CAMPO_CACHE);
    await cache.delete(url);
  } catch {
    // Ignore Cache Storage deletion failures; rejection still propagates.
  }
}

async function guardarEnCache(
  url: string,
  bytes: ArrayBuffer
): Promise<{ guardado: boolean; motivo?: 'quota' | 'no_disponible' }> {
  try {
    if (typeof caches === 'undefined') return { guardado: false, motivo: 'no_disponible' };
    const cache = await caches.open(CAMPO_CACHE);
    const crearRespuesta = () =>
      new Response(bytes.slice(0), {
        headers: { 'content-type': 'application/json' },
      });

    try {
      await cache.put(url, crearRespuesta());
      return { guardado: true };
    } catch (error) {
      if (!esQuotaExceeded(error)) {
        return { guardado: false, motivo: 'no_disponible' };
      }
      // Evict older cached packages before retrying once on tight mobile storage.
      if (typeof cache.keys === 'function') {
        const entradas = await cache.keys();
        for (const entrada of entradas) {
          if (entrada.url !== url) {
            await cache.delete(entrada);
          }
        }
      }
      try {
        await cache.put(url, crearRespuesta());
        return { guardado: true };
      } catch (retryError) {
        return esQuotaExceeded(retryError)
          ? { guardado: false, motivo: 'quota' }
          : { guardado: false, motivo: 'no_disponible' };
      }
    }
  } catch {
    return { guardado: false, motivo: 'no_disponible' };
  }
}

async function leerDeCache(url: string): Promise<PaqueteCampo | null> {
  try {
    if (typeof caches === 'undefined') return null;
    const cache = await caches.open(CAMPO_CACHE);
    const respuesta = await cache.match(url);
    if (!respuesta?.ok) return null;
    return (await respuesta.json()) as PaqueteCampo;
  } catch {
    return null;
  }
}

/**
 * Fetch the package, cache it, and fall back to the cache when the network
 * is gone or returns a transient error. Revoked/expired tokens (404/410) purge
 * any cached copy and fail closed.
 */
export async function cargarPaqueteCampo(url: string): Promise<RespuestaCache> {
  try {
    const respuesta = await fetch(url, { cache: 'no-cache' });
    if (respuesta.status === 404 || respuesta.status === 410) {
      await eliminarDeCache(url);
      throw new CampoRevocadoError(respuesta.status);
    }
    if (!respuesta.ok) {
      const cacheado = await leerDeCache(url);
      if (cacheado) return { paquete: cacheado, desdeCache: true, avisoCache: null };
      throw new Error(`campo_http_${respuesta.status}`);
    }
    const bytes = await respuesta.arrayBuffer();
    const paquete = JSON.parse(new TextDecoder().decode(bytes)) as PaqueteCampo;
    const resCache = await guardarEnCache(url, bytes.slice(0));
    const avisoCache =
      resCache.motivo === 'quota'
        ? 'No hay espacio suficiente para guardar el mapa sin señal. Liberá espacio en el dispositivo.'
        : null;
    return { paquete, desdeCache: false, avisoCache };
  } catch (error) {
    if (error instanceof CampoRevocadoError) throw error;
    const cacheado = await leerDeCache(url);
    if (cacheado) return { paquete: cacheado, desdeCache: true, avisoCache: null };
    throw error instanceof Error ? error : new Error('campo_fallo_carga');
  }
}

/**
 * The public package URL for a token (no auth, nothing personal, S5).
 * ``apiBase`` is the bare origin (``API_URL``); the versioned prefix is
 * added HERE so callers cannot double it.
 */
export function urlPaqueteCampo(token: string, apiBase: string): string {
  return `${apiBase}/api/v2/public/campo/${encodeURIComponent(token)}`;
}
