import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { resolve } from 'path';

export default defineConfig({
  plugins: [
    react(),
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
        orientation: 'portrait-primary',
        theme_color: '#2d9970',
        background_color: '#0f1f1a',
        lang: 'es-AR',
        dir: 'ltr',
        categories: ['utilities', 'productivity', 'government'],
        icons: [
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
            url: '/denuncias',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,json,geojson}'],
        globIgnores: ['data/suelos_cu.geojson'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/health/],
        runtimeCaching: [
          // Geo raster tiles — NetworkOnly to avoid mixing stale DEM/PNG tiles
          // across backend rendering changes (critical for MapLibre raster-dem).
          {
            urlPattern: /\/api\/v2\/geo\/layers\/[^/]+\/tiles\/.*/i,
            handler: 'NetworkOnly',
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
            urlPattern: /^https:\/\/unpkg\.com\/leaflet@.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'leaflet-assets',
              expiration: {
                maxEntries: 10,
                maxAgeSeconds: 60 * 60 * 24 * 365, // 1 year
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
          // API calls — NetworkFirst (try network, fall back to cache when offline)
          {
            urlPattern: /\/api\/v2\/.*/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-responses',
              networkTimeoutSeconds: 10,
              expiration: {
                maxEntries: 200,
                maxAgeSeconds: 60 * 60 * 24, // 24 hours
              },
              cacheableResponse: {
                statuses: [0, 200],
              },
            },
          },
          // Health check — NetworkOnly (never cache, just check connectivity)
          {
            urlPattern: /\/health$/,
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
          'vendor-react': ['react', 'react-dom'],
          'vendor-mantine': [
            '@mantine/core',
            '@mantine/hooks',
            '@mantine/form',
            '@mantine/notifications',
          ],
          'vendor-mantine-extras': ['@mantine/charts', '@mantine/dates', '@mantine/dropzone'],
          'vendor-charts': ['recharts'],
          'vendor-map': ['maplibre-gl', '@mapbox/mapbox-gl-draw', 'leaflet', 'react-leaflet'],
'vendor-router': ['@tanstack/react-router'],
        },
      },
    },
    minify: 'esbuild',
    target: 'es2020',
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
      'leaflet',
      'react-leaflet',
    ],
  },

  css: {
    devSourcemap: true,
  },
});
