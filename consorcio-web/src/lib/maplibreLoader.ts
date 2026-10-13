import type * as maplibregl from 'maplibre-gl';

/**
 * The `maplibre-gl` module namespace. v6 is ESM-only: there is no default export.
 */
export type MapLibreModule = typeof maplibregl;

let workerUrlSet = false;

function asModule(value: unknown): MapLibreModule | null {
  if (typeof value !== 'object' || value === null) return null;
  if (typeof (value as { Map?: unknown }).Map !== 'function') return null;
  return value as MapLibreModule;
}

/**
 * Vite cannot see `import.meta.url` inside the MapLibre package, so the
 * worker URL must be set once before `new Map()`. Tests skip this: they mock
 * `maplibre-gl` without `setWorkerUrl` and without the worker file.
 */
export function bootMapLibreWorker(): void {
  if (workerUrlSet) return;
  workerUrlSet = true;
  if (import.meta.env.MODE === 'test') return;
  void Promise.all([
    import('maplibre-gl'),
    import('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'),
  ]).then(([ml, worker]) => {
    if (typeof ml.setWorkerUrl === 'function') {
      ml.setWorkerUrl(worker.default);
    }
  });
}

/**
 * PERF-005 — `maplibre-gl` is ~800 KB raw. Call this from a map init effect
 * instead of a static import on routes that only might show a map.
 *
 * Vitest factories often still stub `{ default: { Map } }`. Prefer that when
 * present so lazy-load tests keep working; production v6 has no default.
 */
export async function loadMapLibre(): Promise<MapLibreModule> {
  const [module] = await Promise.all([
    import('maplibre-gl'),
    import('maplibre-gl/dist/maplibre-gl.css'),
  ]);
  bootMapLibreWorker();
  return asModule((module as { default?: unknown }).default) ?? asModule(module) ?? (module as MapLibreModule);
}
