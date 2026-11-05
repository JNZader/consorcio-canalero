import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';
import { describe, expect, it } from 'vitest';

import {
  GEE_IMAGE_NETWORK_ONLY,
  GLYPH_SPRITE_NETWORK_ONLY,
  MAP_ENGINE_NETWORK_ONLY,
  MARTIN_TILE_NETWORK_ONLY,
  PRECACHE_GLOB_IGNORES,
  PRECACHE_GLOB_PATTERNS,
  TERRAIN_TILE_NETWORK_ONLY,
  excludeMapFromPrecacheManifest,
  isExcludedFromInstallPrecache,
} from '../../pwaPrecachePolicy';

const PRECACHED = [
  'index.html',
  'assets/index-CiwMulPR.js',
  'assets/index-I28dGLLK.css',
  'assets/ParticipacionPage-DL3JWKCW.js',
  'assets/ParticipacionPage-DjJA8fpi.css',
  'assets/vendor-mantine-dropzone-DyOHsrxY.js',
  'assets/vendor-mantine-dropzone-aPCBPjDN.css',
  'assets/vendor-mantine-B5HaKcPQ.js',
  'assets/inter-latin-400-normal-C38fXH4l.woff2',
  'assets/dm-serif-display-latin-400-normal-C5_t9oOD.woff2',
  'assets/maplibreLoader-4syBL0eF.js',
  'assets/mapLibreLocale-HvMyceod.js',
  'assets/mapColorTokens-DoLFZUSw.js',
  'icons/icon-192.png',
];

const EXCLUDED = [
  'assets/maplibre-gl-worker-Br3j0JGE.js',
  'assets/vendor-maplibre-OhB1yxs2.js',
  'assets/vendor-maplibre-qvkd0SPb.css',
  'assets/useMapInitialization-IzoP9j7O.js',
  'assets/MapaMapLibre-DAm0Mv_n.js',
  'assets/MapaMapLibre-BfFAvBcj.css',
  'assets/MapaPage-DvhaKh9P.js',
  'assets/MapaPage-x4SHztia.css',
  'assets/TerrainViewer3D-BnvAkU4w.js',
  'assets/vendor-map-draw-DFtao4bR.js',
  'assets/vendor-pmtiles-CHPQy3sf.js',
  'assets/vendor-charts-q80CQEk6.js',
  'assets/vendor-mantine-dates-CX0f9IBc.js',
  'assets/vendor-mantine-dates-CrbPQ12V.css',
  'version.json',
  '_worker.js',
  'icons/icon-512.png',
  'data/pilar-verde/bpa_enriched.json',
  'capas/zona.geojson',
];

function precacheNames(files: readonly string[]): string[] {
  const root = mkdtempSync(join(tmpdir(), 'pwa-precache-'));
  for (const file of files) {
    const full = join(root, file);
    mkdirSync(join(full, '..'), { recursive: true });
    writeFileSync(full, '');
  }
  const matched = PRECACHE_GLOB_PATTERNS.flatMap((pattern) =>
    globSync(pattern, {
      cwd: root,
      ignore: [...PRECACHE_GLOB_IGNORES],
      nodir: true,
    })
  );
  return excludeMapFromPrecacheManifest(matched.map((url) => ({ url }))).manifest.map(
    (entry) => entry.url
  );
}

describe('install precache', () => {
  const manifest = precacheNames([...PRECACHED, ...EXCLUDED]);

  it('keeps the shell, the denuncia form and the self-hosted fonts', () => {
    for (const url of PRECACHED) {
      expect(manifest, url).toContain(url);
      expect(isExcludedFromInstallPrecache(url), url).toBe(false);
    }
  });

  it('leaves MapLibre, its worker, terrain and Martin-side chunks out', () => {
    for (const url of EXCLUDED) {
      expect(manifest, url).not.toContain(url);
      expect(isExcludedFromInstallPrecache(url), url).toBe(true);
    }
  });
});

describe('map runtime stays on the network', () => {
  it('does not cache the MapLibre worker or vendor chunk', () => {
    expect(MAP_ENGINE_NETWORK_ONLY.test('/assets/maplibre-gl-worker-Br3j0JGE.js')).toBe(true);
    expect(MAP_ENGINE_NETWORK_ONLY.test('/assets/vendor-maplibre-OhB1yxs2.js')).toBe(true);
    expect(MAP_ENGINE_NETWORK_ONLY.test('/assets/vendor-maplibre-qvkd0SPb.css')).toBe(true);
    expect(MAP_ENGINE_NETWORK_ONLY.test('/assets/useMapInitialization-IzoP9j7O.js')).toBe(true);
    expect(MAP_ENGINE_NETWORK_ONLY.test('/assets/ParticipacionPage-DL3JWKCW.js')).toBe(false);
    expect(MAP_ENGINE_NETWORK_ONLY.test('/assets/maplibreLoader-4syBL0eF.js')).toBe(false);
    expect(MAP_ENGINE_NETWORK_ONLY.test('/assets/vendor-mantine-dropzone-DyOHsrxY.js')).toBe(false);
  });

  it('does not cache GEE pixels, glyphs or Martin tiles', () => {
    expect(
      GEE_IMAGE_NETWORK_ONLY.test(
        'https://earthengine.googleapis.com/v1/projects/earthengine-legacy/maps/abc/tiles/1/2/3'
      )
    ).toBe(true);
    expect(
      GLYPH_SPRITE_NETWORK_ONLY.test(
        'https://tiles.openfreemap.org/fonts/Noto%20Sans%20Regular/0-255.pbf'
      )
    ).toBe(true);
    expect(
      GLYPH_SPRITE_NETWORK_ONLY.test('https://tiles.openfreemap.org/sprites/liberty/sprite.json')
    ).toBe(true);
    expect(
      MARTIN_TILE_NETWORK_ONLY.test('https://tiles.consorcio.example.com/vt_canal_network/12/100/200')
    ).toBe(true);
    expect(
      MARTIN_TILE_NETWORK_ONLY.test('http://localhost:3000/parcelas_catastro/14/1/2')
    ).toBe(true);
    expect(
      MARTIN_TILE_NETWORK_ONLY.test(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/12/1/2'
      )
    ).toBe(false);
  });

  it('keeps terrain-rgb off the geo raster cache and leaves colored tiles alone', () => {
    expect(
      TERRAIN_TILE_NETWORK_ONLY.test(
        '/api/v2/geo/layers/dem-1/tiles/12/1/2.png?encoding=terrain-rgb&v=3'
      )
    ).toBe(true);
    expect(
      TERRAIN_TILE_NETWORK_ONLY.test('/api/v2/geo/layers/dem-1/tiles/12/1/2.png?colormap=viridis')
    ).toBe(false);
  });
});

describe('frontend image', () => {
  it('copies the precache policy next to vite.config.ts in both stages', () => {
    const dockerfile = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '../../Dockerfile'),
      'utf8'
    );
    const copies = dockerfile.split('\n').filter((line) => line.includes('vite.config.ts'));
    expect(copies).toHaveLength(2);
    for (const line of copies) {
      expect(line).toContain('pwaPrecachePolicy.ts');
      expect(line).toContain('vite.modulePreload.ts');
    }
  });
});
