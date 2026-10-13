import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const rootDir = import.meta.dirname;

export default defineConfig({
  plugins: [react()],

  test: {
    // Environment
    environment: 'happy-dom',

    // Setup files
    setupFiles: ['./tests/setup.ts'],

    // Global test configuration
    globals: true,

    // Include patterns
    include: ['tests/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],

    // Exclude patterns
    exclude: [
      'node_modules',
      'dist',
      'tests/accessibility/**', // E2E tests handled by Playwright
      'tests/e2e/**',
    ],

    // Coverage configuration
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      reportsDirectory: './coverage',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.d.ts',
        'src/**/*.test.{ts,tsx}',
        'src/**/*.spec.{ts,tsx}',
        'src/env.d.ts',
        'src/types/**',
        'src/constants/**',
      ],
      thresholds: {
        // CI-04: pisos al entero de la medición en main (2026-10-13):
        // statements 78.17, branches 73.53, functions 76.43, lines 79.47.
        // Hacia 80, sin pasar la cobertura real.
        statements: 78,
        branches: 73,
        functions: 76,
        lines: 79,
      },
    },

    // Test timeout
    testTimeout: 10000,

    // Reporter
    reporters: ['verbose'],

    // Watch mode
    watch: false,
  },

  resolve: {
    alias: {
      '@': resolve(rootDir, './src'),
      '@components': resolve(rootDir, './src/components'),
      '@lib': resolve(rootDir, './src/lib'),
      '@types': resolve(rootDir, './src/types'),
      '@constants': resolve(rootDir, './src/constants'),
      'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url': resolve(
        rootDir,
        './tests/stubs/maplibre-worker-url.ts',
      ),
    },
  },
});
