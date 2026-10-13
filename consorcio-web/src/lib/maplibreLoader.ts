import { setWorkerUrl } from 'maplibre-gl';
import type * as maplibregl from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

/**
 * The `maplibre-gl` module namespace. v6 is ESM-only: there is no default export.
 */
export type MapLibreModule = typeof maplibregl;

let workerUrlSet = false;

/**
 * Vite cannot see `import.meta.url` inside the MapLibre package, so the
 * worker URL must be set once before `new Map()`.
 */
export function bootMapLibreWorker(): void {
  if (workerUrlSet) return;
  workerUrlSet = true;
  setWorkerUrl(workerUrl);
}

/**
 * PERF-005 — `maplibre-gl` is ~800 KB raw. Call this from a map init effect
 * instead of a static import on routes that only might show a map.
 */
export async function loadMapLibre(): Promise<MapLibreModule> {
  const [module] = await Promise.all([
    import('maplibre-gl'),
    import('maplibre-gl/dist/maplibre-gl.css'),
  ]);
  bootMapLibreWorker();
  return module;
}
