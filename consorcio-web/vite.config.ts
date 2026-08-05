import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { resolve } from 'path';

// ---------------------------------------------------------------------------
// FOUT / CLS: build-time <link rel="preload"> for the above-the-fold webfonts.
//
// The five @font-face rules live in ``src/styles/global.css``, so the browser
// only DISCOVERS them once ``index.css`` has landed and parsed, and only
// REQUESTS them once the text they style reaches layout. Measured on the
// landing page: stylesheet at ~2.1 s, font request at ~3.0 s — a late ``swap``
// with a visible reflow, ~0.07 of residual CLS.
//
// A preload link moves the request into the document's preload-scanner pass,
// so the woff2 bytes are already in flight while the CSS is still downloading.
// The hrefs cannot be hardcoded in ``index.html``: Vite content-hashes the
// font assets (``inter-latin-400-normal-C38fXH4l.woff2``), so this plugin
// reads the final emitted names straight out of the Rollup bundle.
//
// Only the two faces the first paint actually needs are preloaded — the hero
// ``h1`` serif and the body sans. The other three Inter weights (500/600/700)
// are deliberately left out: every extra preload competes with the critical JS
// chunks for the same bandwidth, and none of them is on the shell's paint path.
const CRITICAL_FONT_STEMS = ['dm-serif-display-latin-400-normal', 'inter-latin-400-normal'];

function preloadCriticalFonts(): Plugin {
  let base = '/';
  return {
    name: 'consorcio:preload-critical-fonts',
    apply: 'build',
    configResolved(config) {
      // Vite always normalises the resolved base to a trailing slash.
      base = config.base;
    },
    transformIndexHtml: {
      // ``post`` so the Rollup bundle is fully populated: the woff2 assets are
      // emitted while the CSS that references them is processed.
      order: 'post',
      handler(html, ctx) {
        const emitted = Object.keys(ctx.bundle ?? {});
        const tags = CRITICAL_FONT_STEMS.map((stem) => {
          const fileName = emitted.find((name) => {
            const assetName = name.split('/').pop() ?? '';
            return assetName.startsWith(`${stem}-`) && assetName.endsWith('.woff2');
          });
          if (!fileName) {
            // Fail the build instead of silently shipping no preload. A silent
            // miss reintroduces exactly the regression this plugin exists to
            // prevent, and nothing downstream would catch it.
            throw new Error(
              `[preload-critical-fonts] no emitted .woff2 matched "${stem}-*.woff2". Check the @font-face src URLs in src/styles/global.css.`
            );
          }
          return {
            tag: 'link',
            attrs: {
              rel: 'preload',
              as: 'font',
              type: 'font/woff2',
              href: `${base}${fileName}`,
              // Fonts are always fetched in anonymous CORS mode. Without the
              // (empty == anonymous) crossorigin attribute the preload lands in
              // a different cache partition than the CSS-driven request and the
              // file is downloaded twice.
              crossorigin: '',
            },
            // Earliest possible discovery. This pushes <meta charset> down by
            // ~260 bytes, still far inside the 1024-byte window browsers scan
            // for the declaration.
            injectTo: 'head-prepend' as const,
          };
        });
        return { html, tags };
      },
    },
  };
}

// Proxy de dev OPCIONAL (demo local contra un API remoto sin pelearse con
// CORS): con `DEV_PROXY_TARGET=https://api.ejemplo.com npm run dev` el dev
// server reenvia /api y /uploads a ese destino (server-a-server, el browser
// ve todo same-origin). Requiere VITE_API_URL=http://localhost:5173 para que
// el front genere URLs same-origin. Sin la variable, no cambia NADA.
// DEV_PROXY_HOST (opcional) fuerza el header Host saliente: necesario si el
// destino valida Host (TrustedHostMiddleware) y se llega por tunel/IP.
const devProxyTarget = process.env.DEV_PROXY_TARGET;
const devProxyHost = process.env.DEV_PROXY_HOST;
// OJO: changeOrigin pisa headers.host (setea Host = host del target DESPUES
// de mergear headers). Con DEV_PROXY_HOST explicito, va sin changeOrigin.
const devProxyOpts = devProxyHost
  ? { target: devProxyTarget, headers: { host: devProxyHost } }
  : { target: devProxyTarget, changeOrigin: true };
const devProxy = devProxyTarget
  ? {
      '/api': devProxyOpts,
      '/uploads': devProxyOpts,
    }
  : undefined;

export default defineConfig({
  server: { proxy: devProxy },
  plugins: [
    // Injects the two critical-font preloads at build time — see the plugin
    // definition above. Build-only; the dev server serves fonts unhashed.
    preloadCriticalFonts(),
    // Phase 3 / F3-E: React Compiler — auto-memoises components and
    // hooks the way ``useMemo`` + ``useCallback`` would, except the
    // compiler is conservative and only inserts memos where it can
    // PROVE safety. React 19 is the minimum supported runtime
    // (already pinned in package.json). The plugin runs as a Babel
    // pass that ``@vitejs/plugin-react`` already hosts, so this is
    // a config-only change.
    react({
      babel: {
        plugins: [['babel-plugin-react-compiler', { target: '19' }]],
      },
    }),
    VitePWA({
      registerType: 'autoUpdate',
      // PERF — keep this list MINIMAL. ``includeAssets`` bypasses
      // ``workbox.globIgnores`` entirely: whatever is listed here lands in
      // the precache manifest even when the ignore list right below claims
      // to exclude it. ``capas/*.geojson`` (~340 KB) used to be here and
      // silently re-added the very files ``**/*.geojson`` was ignoring.
      // ``favicon.ico`` (~76 KB) is also gone: the browser fetches it lazily
      // for the tab, and the PWA install flow reads icons from the manifest,
      // not from the precache.
      includeAssets: ['robots.txt'],
      // PERF — vite-plugin-pwa defaults this to ``true``, which force-adds
      // EVERY file referenced by ``manifest.icons`` to the precache, behind
      // the back of both ``globPatterns`` and ``globIgnores``. That is a third
      // way into the manifest, and it was quietly re-adding ``favicon.ico``
      // plus both 512 px icons (~430 KB) after they had been removed from the
      // other two. The install flow reads icons from the webmanifest itself,
      // so precaching them buys nothing. ``icon-192.png`` (48 KB) still gets
      // in via ``globPatterns`` — it is the one the browser shows in the
      // install prompt, and it is small enough not to matter.
      includeManifestIcons: false,
      manifest: {
        name: 'Consorcio Canalero 10 de Mayo',
        short_name: 'CC10M',
        description:
          'Sistema de gestion y monitoreo del Consorcio Canalero 10 de Mayo - Infraestructura hidrica para el desarrollo agricola',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        // ``any`` so tablet users (departamento Unión inspectors using
        // iPads in the field) aren't force-rotated. Phone defaults
        // still display portrait via the device's own orientation
        // rules.
        orientation: 'any',
        theme_color: '#2d9970',
        background_color: '#0f1f1a',
        lang: 'es-AR',
        dir: 'ltr',
        categories: ['utilities', 'productivity', 'government'],
        icons: [
          // Phase 3 / F3-F: 192 + 512 + 512-maskable PNGs.
          // Generated programmatically (placeholder design with the
          // consorcio's primary green + "CC" mark). Operators can
          // replace the three files under ``public/icons/`` with a
          // real design without touching this manifest — the PNG
          // paths stay stable.
          {
            src: '/icons/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any',
          },
          {
            src: '/icons/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any',
          },
          {
            src: '/icons/icon-512-maskable.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
          {
            src: '/favicon.ico',
            sizes: '48x48 72x72 96x96 128x128 256x256',
            type: 'image/x-icon',
          },
        ],
        shortcuts: [
          {
            name: 'Ver Mapa',
            short_name: 'Mapa',
            description: 'Acceder al mapa interactivo de canales',
            url: '/mapa',
          },
          {
            name: 'Reportar Incidente',
            short_name: 'Reportar',
            description: 'Reportar un incidente en los canales',
            // ``/participacion`` es la ruta canonica (tab Reportar por
            // defecto); ``/reportes`` quedo como redirect de compatibilidad
            // — apuntar el shortcut directo evita pagar ese salto extra.
            url: '/participacion',
          },
        ],
      },
      workbox: {
        // ``geojson`` removed from precache pattern — those files are
        // 0.5–3 MB each and only loaded by users who actually open the
        // map. PWA precache used to bloat every install by ~7 MB on
        // first visit, including users who only use the form / admin
        // routes and never touch the map.
        //
        // ``ico`` removed from the pattern too — ``favicon.ico`` was the only
        // match and it does not belong in the install-time critical path.
        globPatterns: ['**/*.{js,css,html,png,svg,json}'],
        globIgnores: [
          // PERF — the service worker registers during the LCP window on a
          // cold mobile visit, and every byte listed here competes with the
          // route chunk and the fonts for the same link. The three groups
          // below are the ones that were pure dead weight.
          //
          // 1. Static data payloads: ``data/pilar-verde/bpa_enriched.json``
          //    alone is ~490 KB and is only read by the Pilar Verde panel.
          //    Fetched on demand at runtime.
          'data/**/*.json',
          // 2. The large PWA icons (~355 KB for the two 512s). The OS reads
          //    them from ``manifest.webmanifest`` when the user installs the
          //    app — the precache never serves that request. ``icon-192``
          //    stays (48 KB, used as the in-browser install prompt icon).
          '**/icon-512*.png',
          // 3. Belt-and-braces — any new ``.geojson`` that lands in the
          // build directory also stays out of precache. Runtime loads
          // them on demand via the public viewer hooks.
          '**/*.geojson',
          'data/suelos_cu.geojson',
          // version.json is the freshness probe — never precache it,
          // otherwise the SW happily serves the build's own SHA forever
          // and the in-app "Reload to update" banner never fires.
          'version.json',
          // ``vendor-maplibre`` was intentionally precached (~780 kb) so the
          // 3D viewer doesn't pay a cold network fetch the first time the
          // user opens it — the entire app is map-centric, the trade-off
          // pays back immediately. The remaining heavy vendor chunks stay
          // in runtime CacheFirst because they're only used on niche pages.
          //
          // TODO(perf): ``vendor-maplibre`` (~780 KB) + ``MapaMapLibre``
          // (~320 KB) are now BY FAR the largest slice of what the SW pulls
          // at install time, and a visitor who never opens ``/mapa`` pays
          // all of it. Dropping them would be the single biggest remaining
          // win — but it also kills ``/mapa`` offline, and that is a PRODUCT
          // decision nobody has taken yet. Do not remove them here without
          // an explicit call on whether offline map support still matters.
          '**/vendor-map-draw-*.js',
          '**/vendor-pmtiles-*.js',
          '**/vendor-charts-*.js',
          '**/vendor-mantine-charts-*.js',
          '**/vendor-mantine-dropzone-*.js',
        ],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/health/, /^\/version\.json$/],
        runtimeCaching: [
          // version.json — always go to network, never cached. The SW must
          // not interpose any cache layer on this file or `useVersionCheck`
          // is dead in the water.
          {
            urlPattern: /\/version\.json(\?.*)?$/i,
            handler: 'NetworkOnly',
          },
          // Geo raster tiles — Phase 3 / F3-H. Was NetworkOnly which
          // gave a black map on flaky mobile / offline; the original
          // concern (stale tiles after a backend rendering change)
          // resolves naturally because each backend-pipeline change
          // also bumps the layer SHA in the tile URL, so the cache
          // misses for the new SHA and revalidates against network.
          // StaleWhileRevalidate gives the user an immediate render
          // from cache while the new tile fetches in the background.
          {
            urlPattern: /\/api\/v2\/geo\/layers\/[^/]+\/tiles\/.*/i,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'geo-raster-tiles',
              expiration: {
                // Lowered from 1500 → 800 after the post-3vr review:
                // iOS Safari caps per-origin Cache Storage to ~50 MB
                // and 1500 × 50 KB = 75 MB silently evicted. 800
                // covers ~2 zoom levels of the AOI and stays within
                // the strictest mobile budget.
                maxEntries: 800,
                // 3 days — the ETL re-runs weekly, plus SWR keeps
                // serving stale tiles without re-rendering after the
                // background refresh, so a longer TTL would carry
                // bad-deploy tiles forward for too long. Three days
                // catches the next weekly cycle.
                maxAgeSeconds: 60 * 60 * 24 * 3,
              },
              cacheableResponse: {
                // Drop the ``0`` opaque-response status — these tiles
                // are SAME-origin so they always come back as 200,
                // 204, or an error. Allowing ``0`` would silently
                // cache CORS failures from any third-party that the
                // URL pattern ever matched.
                //
                // ``204`` is included because the geo-worker returns
                // it for tiles outside the layer AOI bounds — without
                // caching, every pan over an empty region re-fetches.
                statuses: [200, 204],
              },
            },
          },
          // Static assets from CDNs — CacheFirst (long-lived, rarely change)
          {
            urlPattern: /^https:\/\/server\.arcgisonline\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'arcgis-tiles',
              expiration: {
                maxEntries: 500,
                maxAgeSeconds: 60 * 60 * 24 * 30, // 30 days
              },
            },
          },
          {
            urlPattern: /^https:\/\/tile\.openstreetmap\.org\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'osm-tiles',
              expiration: {
                maxEntries: 500,
                maxAgeSeconds: 60 * 60 * 24 * 7, // 7 days
              },
            },
          },
          // Heavy lazy vendor chunks — do not precache on install; cache after first use.
          {
            urlPattern:
              /\/assets\/vendor-(maplibre|map-draw|pmtiles|charts|mantine-(extras|dates))-.*\.js$/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'lazy-vendor-chunks',
              expiration: {
                maxEntries: 20,
                maxAgeSeconds: 60 * 60 * 24 * 30, // 30 days
              },
              cacheableResponse: {
                statuses: [0, 200],
              },
            },
          },
          // PII-sensitive API surface — NEVER cache. The service worker
          // used to cache every /api/v2/* response NetworkFirst, which
          // means denuncia bodies, padron rows, finanzas, auth responses
          // stayed in the user's localStorage for 24 hours after logout.
          // On a shared device (phone in a kiosk, household laptop) the
          // next user could pop them out of the SW cache.
          //
          // The auth / admin / PII routes go NetworkOnly. The few routes
          // that legitimately benefit from offline caching (the public
          // viewer surface) are listed explicitly below.
          {
            urlPattern:
              /\/api\/v2\/(auth|admin|padron|denuncias|finanzas|tramites|reuniones|monitoring|users|capas)\b/i,
            handler: 'NetworkOnly',
          },
          // Public viewer endpoints — cacheable. These are intentionally
          // unauthenticated (catalog of public layers, branding, etc.)
          // and the user benefits from offline mode on a flaky mobile
          // connection.
          {
            urlPattern: /\/api\/v2\/public\/.*/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-public',
              networkTimeoutSeconds: 10,
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 60 * 60 * 6, // 6 hours
              },
              cacheableResponse: {
                statuses: [0, 200],
              },
            },
          },
          // Anything else under /api/v2/* not covered above also goes
          // NetworkOnly. Better to ship a 503 on offline than risk
          // leaking PII via a stale cached response.
          {
            urlPattern: /\/api\/v2\/.*/i,
            handler: 'NetworkOnly',
          },
          // Health check — NetworkOnly (never cache, just check connectivity)
          {
            urlPattern: /\/(health|live|ready)$/,
            handler: 'NetworkOnly',
          },
        ],
      },
    }),
  ],

  // Support both VITE_ and PUBLIC_ prefixes for backwards compatibility
  envPrefix: ['VITE_', 'PUBLIC_'],

  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
      '@components': resolve(__dirname, './src/components'),
      '@lib': resolve(__dirname, './src/lib'),
      '@types': resolve(__dirname, './src/types'),
      '@constants': resolve(__dirname, './src/constants'),
    },
  },

  build: {
    rollupOptions: {
      onwarn(warning, warn) {
        // Suppress unused import warnings from @tabler/icons-react
        if (
          warning.code === 'UNUSED_EXTERNAL_IMPORT' &&
          warning.exporter?.includes('@tabler/icons-react')
        ) {
          return;
        }
        warn(warning);
      },
      output: {
        manualChunks: {
          'vendor-mantine': [
            '@mantine/core',
            '@mantine/hooks',
            '@mantine/form',
            '@mantine/notifications',
          ],
          // @mantine/dates loaded eager via DatesProvider in main.tsx —
          // keep it in its own small chunk (~30 KB) so the heavier
          // charts/dropzone chunks stay lazy. Without this split,
          // DatesProvider would pull the entire 200+ KB extras bundle
          // into the initial entry.
          'vendor-mantine-dates': ['@mantine/dates'],
          // PERF-005 — charts and dropzone were a single ``vendor-mantine-extras``
          // chunk. They have DISJOINT consumers: dropzone is the photo picker in
          // ``/participacion``, charts only shows up in admin dashboards. Bundled
          // together, opening the report form downloaded ~113 KB of charting code
          // that page never renders. One chunk per library keeps each route paying
          // only for what it uses.
          'vendor-mantine-charts': ['@mantine/charts'],
          'vendor-mantine-dropzone': ['@mantine/dropzone'],
          'vendor-charts': ['recharts'],
          'vendor-maplibre': ['maplibre-gl'],
          'vendor-map-draw': ['@mapbox/mapbox-gl-draw'],
          'vendor-pmtiles': ['pmtiles'],
          'vendor-router': ['@tanstack/react-router'],
        },
      },
    },
    minify: 'esbuild',
    // Match tsconfig.json (target + lib both ES2022). Without aligning,
    // esbuild does NOT polyfill ES2022 built-ins like Array.prototype.at,
    // so any usage typed-OK at compile time can blow up at runtime in
    // older browsers. ES2022 ≅ Chrome 94+, Safari 16.4+, Firefox 93+,
    // which matches our actual user base.
    target: 'es2022',
    cssCodeSplit: true,
    sourcemap: false,
    chunkSizeWarningLimit: 500,
  },

  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      '@mantine/core',
      '@mantine/hooks',
      'maplibre-gl',
      '@mapbox/mapbox-gl-draw',
      'pmtiles',
    ],
  },

  css: {
    devSourcemap: true,
  },
});
