/**
 * Install-time precache for the PWA shell.
 *
 * Vite names the MapLibre worker `maplibre-gl-worker-<hash>.js`, not
 * `vendor-maplibre-<hash>.js`. A glob that only lists the vendor chunk lets
 * the ~519 KB worker, the MapLibre CSS and `useMapInitialization` into the
 * precache manifest. `manifestTransforms` applies the same stems again so a
 * renamed asset cannot slip past `globIgnores`.
 *
 * `maplibreLoader` and `mapLibreLocale` stay in the precache: the denuncia
 * form imports them statically and they are not the GL library or the worker.
 * Dropzone stays too: `PhotoSection` imports it statically, so `/participacion`
 * cannot render offline without that chunk.
 */

/** Chunks that must not be installed into every visitor's precache. */
export const MAP_PRECACHE_EXCLUDED_STEMS = [
  'maplibre-gl-worker',
  'vendor-maplibre',
  'useMapInitialization',
  'MapaMapLibre',
  'MapaPage',
  'TerrainViewer3D',
  'vendor-map-draw',
  'vendor-pmtiles',
  'vendor-charts',
  'vendor-mantine-charts',
  'vendor-mantine-dates',
] as const;

export const PRECACHE_GLOB_PATTERNS = ['**/*.{js,css,html,png,svg,json,woff2}'] as const;

export const PRECACHE_GLOB_IGNORES = [
  // ``data/pilar-verde/*.json`` is panel data, fetched on demand.
  'data/**/*.json',
  // The OS reads the 512 px icons from the web manifest, not the precache.
  '**/icon-512*.png',
  '**/*.geojson',
  // Freshness probe. A precached copy would hide new deploys from the banner.
  'version.json',
  // Pages executes ``dist/_worker.js``. Clients must not cache that source.
  '_worker.js',
  ...MAP_PRECACHE_EXCLUDED_STEMS.flatMap((stem) => [`**/${stem}*.js`, `**/${stem}*.css`]),
] as const;

export function isExcludedFromInstallPrecache(url: string): boolean {
  const path = url.split(/[?#]/, 1)[0]?.replaceAll('\\', '/') ?? '';
  const base = path.split('/').pop() ?? path;
  if (MAP_PRECACHE_EXCLUDED_STEMS.some((stem) => base.startsWith(stem))) return true;
  if (base.endsWith('.geojson')) return true;
  if (base === 'version.json' || base === '_worker.js') return true;
  if (base.startsWith('icon-512')) return true;
  if (/(?:^|\/)data\/.+\.json$/i.test(path)) return true;
  return false;
}

export function excludeMapFromPrecacheManifest<T extends { url: string }>(
  entries: readonly T[]
): { manifest: T[]; warnings: string[] } {
  return {
    manifest: entries.filter((entry) => !isExcludedFromInstallPrecache(entry.url)),
    warnings: [],
  };
}

/** MapLibre chunks, worker, page CSS. Fetched when a map opens; never stored. */
export const MAP_ENGINE_NETWORK_ONLY =
  /\/assets\/(?:maplibre-gl-worker|vendor-maplibre|vendor-map-draw|vendor-pmtiles|useMapInitialization|MapaMapLibre|MapaPage|TerrainViewer3D)-[^/]+\.(?:js|css)$/i;

/** Satellite / thumb pixels. The API JSON that points here is a different route. */
export const GEE_IMAGE_NETWORK_ONLY = /^https:\/\/earthengine\.googleapis\.com\//i;

/** Style glyphs and sprites. OpenFreeMap is the production glyph host. */
export const GLYPH_SPRITE_NETWORK_ONLY = /^https:\/\/tiles\.openfreemap\.org\//i;

/**
 * Martin MVT: ``{host}/{table}/{z}/{x}/{y}`` with no file extension.
 * Same-origin ``/api/...`` and Esri paths have more segments, so they miss.
 */
export const MARTIN_TILE_NETWORK_ONLY =
  /^https?:\/\/[^/]+\/[a-z0-9_]+\/\d+\/\d+\/\d+(?:\?.*)?$/i;

/** 3D terrain-rgb tiles. Colored geo overlays keep their own runtime cache. */
export const TERRAIN_TILE_NETWORK_ONLY =
  /\/api\/v2\/geo\/layers\/[^/]+\/tiles\/.*encoding=terrain-rgb/i;
