/** @type {import('@stryker-mutator/api/core').PartialStrykerOptions} */
export default {
  packageManager: 'npm',
  testRunner: 'vitest',
  reporters: ['clear-text', 'progress'],
  vitest: {
    configFile: 'vitest.config.ts',
  },
  mutate: [
    // Core API logic
    'src/lib/api/core.ts',
    // Auth
    'src/lib/auth.ts',
    // Stores (business state)
    'src/stores/authStore.ts',
    'src/stores/configStore.ts',
    // Utilities with logic
    'src/lib/validators.ts',
    'src/lib/formatters.ts',
    'src/lib/errorHandler.ts',
    'src/lib/typeGuards.ts',
    // Pilar Verde pure helpers (Phase 3 — ≥85% target)
    'src/components/map2d/bpaPracticas.ts',
  ],
  thresholds: {
    high: 85,
    low: 60,
    break: 50,
  },
  timeoutMS: 30000,
  concurrency: 4,
};
