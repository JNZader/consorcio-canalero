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

interface RespuestaCache {
  paquete: PaqueteCampo;
  desdeCache: boolean;
}

async function guardarEnCache(url: string, bytes: ArrayBuffer): Promise<void> {
  try {
    if (typeof caches === 'undefined') return;
    const cache = await caches.open(CAMPO_CACHE);
    await cache.put(
      url,
      new Response(bytes, {
        headers: { 'content-type': 'application/json' },
      })
    );
  } catch {
    // Cache Storage unavailable (private mode…): the map still works this
    // session; the NEXT offline open simply won't have the package.
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
 * is gone. `desdeCache: true` is what drives the "Sin señal" chip (S6).
 */
export async function cargarPaqueteCampo(url: string): Promise<RespuestaCache> {
  try {
    const respuesta = await fetch(url, { cache: 'no-store' });
    if (!respuesta.ok) {
      // 404/410 from the public route: a dead token is NOT a network
      // failure — fall through to the cache (a previously saved package
      // keeps the phone working even after the informe expired).
      const cacheado = await leerDeCache(url);
      if (cacheado) return { paquete: cacheado, desdeCache: true };
      throw new Error(`campo_http_${respuesta.status}`);
    }
    const bytes = await respuesta.arrayBuffer();
    const paquete = JSON.parse(new TextDecoder().decode(bytes)) as PaqueteCampo;
    await guardarEnCache(url, bytes.slice(0));
    return { paquete, desdeCache: false };
  } catch (error) {
    const cacheado = await leerDeCache(url);
    if (cacheado) return { paquete: cacheado, desdeCache: true };
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
