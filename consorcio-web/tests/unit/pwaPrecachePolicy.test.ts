import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';
import { describe, expect, it } from 'vitest';

import {
  CAMPO_MAP_ENGINE_CACHE_FIRST,
  CAMPO_PACKAGE_NETWORK_ONLY,
  excludeMapFromPrecacheManifest,
  GEE_IMAGE_NETWORK_ONLY,
  GLYPH_SPRITE_NETWORK_ONLY,
  isExcludedFromInstallPrecache,
  MAP_ENGINE_NETWORK_ONLY,
  MARTIN_TILE_NETWORK_ONLY,
  matchCampoMapEngineAsset,
  PRECACHE_GLOB_IGNORES,
  PRECACHE_GLOB_PATTERNS,
  TERRAIN_TILE_NETWORK_ONLY,
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
  'assets/AdminLayout-A1b2C3d4.js',
  'assets/AdminDashboard-E5f6G7h8.js',
  'assets/ReportsPanel-I9j0K1l2.js',
  'assets/SugerenciasPanel-M3n4O5p6.js',
  'assets/ParticipacionPanel-Q7r8S9t0.js',
  'assets/PadronPanel-U1v2W3x4.js',
  'assets/TramitesPanel-Y5z6A7b8.js',
  'assets/ReunionesPanel-C9d0E1f2.js',
  'assets/FinanzasPanel-G3h4I5j6.js',
  'assets/DemPipelinePanel-K7l8M9n0.js',
  'assets/ImageExplorerPanel-O1p2Q3r4.js',
  'assets/ConocimientoPanel-S5t6U7v8.js',
  'assets/CanalesPublicacionPanel-W9x0Y1z2.js',
  'assets/ThemeLabPanel-A3b4C5d6.js',
  'assets/DashboardEstadisticas-E7f8G9h0.js',
  'assets/CampoPage-I1j2K3l4.js',
  'assets/InformeAreaDrawer-M5n6O7p8.js',
  'assets/ElevationProfileChart-Q9r0S1t2.js',
  'assets/jszip-U3v4W5x6.js',
  'assets/togeojson-Y7z8A9b0.js',
  'assets/qrcode-C1d2E3f4.js',
  'version.json',
  '_worker.js',
  '_headers',
  '_redirects',
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
      MARTIN_TILE_NETWORK_ONLY.test(
        'https://tiles.consorcio.example.com/vt_canal_network/12/100/200'
      )
    ).toBe(true);
    expect(MARTIN_TILE_NETWORK_ONLY.test('http://localhost:3000/parcelas_catastro/14/1/2')).toBe(
      true
    );
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

  it('caches both vendor-maplibre js and css (and maplibre-gl-worker js) on campo pages', () => {
    expect(CAMPO_MAP_ENGINE_CACHE_FIRST.test('/assets/vendor-maplibre-OhB1yxs2.js')).toBe(true);
    expect(CAMPO_MAP_ENGINE_CACHE_FIRST.test('/assets/vendor-maplibre-qvkd0SPb.css')).toBe(true);
    expect(CAMPO_MAP_ENGINE_CACHE_FIRST.test('/assets/maplibre-gl-worker-Br3j0JGE.js')).toBe(true);
    expect(CAMPO_MAP_ENGINE_CACHE_FIRST.test('/assets/vendor-mantine-B5HaKcPQ.js')).toBe(false);
    expect(CAMPO_MAP_ENGINE_CACHE_FIRST.test('/assets/MapaPage-DvhaKh9P.js')).toBe(false);

    expect(
      matchCampoMapEngineAsset({
        url: new URL('https://app.example/assets/vendor-maplibre-OhB1yxs2.js'),
        request: { referrer: 'https://app.example/campo/tok-1' } as Request,
      })
    ).toBe(true);
    expect(
      matchCampoMapEngineAsset({
        url: new URL('https://app.example/assets/vendor-maplibre-qvkd0SPb.css'),
        request: { referrer: 'https://app.example/campo/tok-1' } as Request,
      })
    ).toBe(true);
    expect(
      matchCampoMapEngineAsset({
        url: new URL('https://app.example/assets/maplibre-gl-worker-Br3j0JGE.js'),
        request: { referrer: 'https://app.example/campo/tok-1' } as Request,
      })
    ).toBe(true);
    expect(
      matchCampoMapEngineAsset({
        url: new URL('https://app.example/assets/vendor-maplibre-OhB1yxs2.js'),
        request: { referrer: 'https://app.example/mapa' } as Request,
      })
    ).toBe(false);
    expect(
      matchCampoMapEngineAsset({
        url: new URL('https://app.example/assets/vendor-maplibre-OhB1yxs2.js'),
        request: { referrer: '' } as Request,
      })
    ).toBe(false);
    expect(
      matchCampoMapEngineAsset({
        url: new URL('https://app.example/assets/vendor-mantine-B5HaKcPQ.js'),
        request: { referrer: 'https://app.example/campo/tok-1' } as Request,
      })
    ).toBe(false);
  });

  it('uses status 200 only on same-origin and CORS SW caches while keeping 0 for opaque Esri tiles', () => {
    const viteConfig = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '../../vite.config.ts'),
      'utf8'
    );
    expect(viteConfig).toContain('urlPattern: matchCampoMapEngineAsset');

    const sliceFor = (cacheName: string) => {
      const idx = viteConfig.indexOf(`cacheName: '${cacheName}'`);
      expect(idx).toBeGreaterThan(-1);
      return viteConfig.slice(idx, idx + 450);
    };

    expect(sliceFor('campo-map-engine')).toContain('statuses: [200]');
    expect(sliceFor('lazy-vendor-chunks')).toContain('statuses: [200]');
    expect(sliceFor('api-public')).toContain('statuses: [200]');
    expect(sliceFor('geo-public-vectors')).toContain('statuses: [200]');
    expect(sliceFor('arcgis-tiles')).toContain('statuses: [0, 200]');
  });

  it('keeps /api/v2/public/campo/* NetworkOnly in SW before generic public NetworkFirst', () => {
    expect(CAMPO_PACKAGE_NETWORK_ONLY.test('/api/v2/public/campo/abc-123')).toBe(true);
    expect(CAMPO_PACKAGE_NETWORK_ONLY.test('/api/v2/public/layers/catalog')).toBe(false);

    const viteConfig = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '../../vite.config.ts'),
      'utf8'
    );
    const campoIdx = viteConfig.indexOf('urlPattern: CAMPO_PACKAGE_NETWORK_ONLY');
    const genericPublicIdx = viteConfig.indexOf('/\\/api\\/v2\\/public\\/.*/i');
    expect(campoIdx).toBeGreaterThan(-1);
    expect(genericPublicIdx).toBeGreaterThan(campoIdx);
    const fragment = viteConfig.slice(campoIdx, campoIdx + 120);
    expect(fragment).toContain("handler: 'NetworkOnly'");
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

  it('prevents 1-year caching of SW files, preserves security headers in locations, and strips Cloudflare files', () => {
    const dockerfile = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '../../Dockerfile'),
      'utf8'
    );

    const staticAssetIdx = dockerfile.indexOf('location ~* \\.(js|css');
    expect(staticAssetIdx).toBeGreaterThan(-1);
    for (const swLoc of ['location = /sw.js', 'location = /registerSW.js', 'location ~ ^/workbox-.*\\.js$']) {
      const idx = dockerfile.indexOf(swLoc);
      expect(idx, swLoc).toBeGreaterThan(-1);
      expect(idx, swLoc).toBeLessThan(staticAssetIdx);
    }

    expect(dockerfile).toContain('/etc/nginx/security-headers.conf');
    expect(dockerfile).toContain('X-Frame-Options "DENY"');
    expect(dockerfile).toContain('Permissions-Policy');
    expect(dockerfile).toContain('location ~ ^/_(worker\\.js|headers|redirects)$');
    expect(dockerfile).toContain(
      'rm -f /usr/share/nginx/html/_worker.js /usr/share/nginx/html/_headers /usr/share/nginx/html/_redirects'
    );
  });
});
