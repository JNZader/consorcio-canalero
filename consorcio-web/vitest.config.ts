import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

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
        statements: 60,
        branches: 60,
        functions: 60,
        lines: 60,
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
      '@': resolve(__dirname, './src'),
      '@components': resolve(__dirname, './src/components'),
      '@lib': resolve(__dirname, './src/lib'),
      '@types': resolve(__dirname, './src/types'),
      '@constants': resolve(__dirname, './src/constants'),
    },
  },
});
