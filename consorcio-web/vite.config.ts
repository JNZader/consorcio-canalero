import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { resolve } from 'path';

export default defineConfig({
  plugins: [
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
      includeAssets: ['favicon.ico', 'robots.txt', 'capas/*.geojson'],
      manifest: {
        name: 'Consorcio Canalero 10 de Mayo',
        short_name: 'CC10M',
        description:
          'Sistema de gestion y monitoreo del Consorcio Canalero 10 de Mayo - Infraestructura hidrica para el desarrollo agricola',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        // ``any`` so tablet users (Marcos Juárez inspectors using
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
            // ``/reportes`` is the actual route name in routeTree.gen.tsx;
            // ``/denuncias`` was the legacy URL that never existed in
            // the router and made the shortcut 404 on every install.
            url: '/reportes',
          },
        ],
      },
      workbox: {
        // ``geojson`` removed from precache pattern — those files are
        // 0.5–3 MB each and only loaded by users who actually open the
        // map. PWA precache used to bloat every install by ~7 MB on
        // first visit, including users who only use the form / admin
        // routes and never touch the map.
        globPatterns: ['**/*.{js,css,html,ico,png,svg,json}'],
        globIgnores: [
          // Belt-and-braces — any new ``.geojson`` that lands in the
          // build directory also stays out of precache. Runtime loads
          // them on demand via the public viewer hooks.
          '**/*.geojson',
          'data/suelos_cu.geojson',
          // version.json is the freshness probe — never precache it,
          // otherwise the SW happily serves the build's own SHA forever
          // and the in-app "Reload to update" banner never fires.
          'version.json',
          // ``vendor-maplibre`` was intentionally precached (~500 kb) so the
          // 3D viewer doesn't pay a cold network fetch the first time the
          // user opens it — the entire app is map-centric, the trade-off
          // pays back immediately. The remaining heavy vendor chunks stay
          // in runtime CacheFirst because they're only used on niche pages.
          '**/vendor-map-draw-*.js',
          '**/vendor-pmtiles-*.js',
          '**/vendor-charts-*.js',
          '**/vendor-mantine-extras-*.js',
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
                maxEntries: 1500,  // ~3 zoom levels of a small AOI
                maxAgeSeconds: 60 * 60 * 24 * 14,  // 14 days
              },
              cacheableResponse: {
                statuses: [0, 200],
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
              /\/assets\/vendor-(maplibre|map-draw|pmtiles|charts|mantine-extras)-.*\.js$/i,
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
            urlPattern: /\/api\/v2\/(auth|admin|padron|denuncias|finanzas|tramites|reuniones|monitoring|users|capas)\b/i,
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
          // ``vendor-mantine-extras`` (charts + dropzone) stays lazy.
          // Without this split, DatesProvider would pull the entire
          // 200+ KB extras bundle into the initial entry.
          'vendor-mantine-dates': ['@mantine/dates'],
          'vendor-mantine-extras': ['@mantine/charts', '@mantine/dropzone'],
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
