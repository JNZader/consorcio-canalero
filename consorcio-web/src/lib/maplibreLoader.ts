import type maplibregl from 'maplibre-gl';

/**
 * The `maplibre-gl` default export, typed WITHOUT pulling the runtime module
 * into the importing chunk: `import type` is erased by the compiler.
 */
export type MapLibreModule = typeof maplibregl;

/**
 * PERF-005 — `maplibre-gl` is ~800 KB raw (~215 KB gzipped) and its stylesheet
 * another ~65 KB. Any STATIC import of it welds the whole engine into the
 * importing route's chunk, so pages that only MIGHT show a map (the
 * `/participacion` forms: report location picker, suggestion geometry) paid for
 * it up front, even for users who never scrolled that far.
 *
 * Call this from the map's init effect instead. Rollup keeps the engine in the
 * shared `vendor-maplibre` chunk and fetches it on demand; the CSS rides along
 * in the same lazy request.
 */
export async function loadMapLibre(): Promise<MapLibreModule> {
  const [module] = await Promise.all([
    import('maplibre-gl'),
    import('maplibre-gl/dist/maplibre-gl.css'),
  ]);
  return module.default;
}
