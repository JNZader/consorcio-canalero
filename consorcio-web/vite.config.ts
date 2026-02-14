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
        short_name: 'Consorcio',
        description: 'Gestion y monitoreo de cuencas hidricas',
        theme_color: '#228be6',
        icons: [
          {
            src: 'pwa-192x192.png', // User needs to provide these icons later
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,json,geojson}'],
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/server\.arcgisonline\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'arcgis-tiles',
              expiration: {
                maxEntries: 500,
                maxAgeSeconds: 60 * 60 * 24 * 30, // 30 Days
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
                maxAgeSeconds: 60 * 60 * 24 * 365, // 1 Year
              },
            },
          }
        ]
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
          'vendor-map': ['leaflet', 'react-leaflet'],
          'vendor-supabase': ['@supabase/supabase-js'],
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
      'leaflet',
      'react-leaflet',
    ],
  },

  css: {
    devSourcemap: true,
  },
});
