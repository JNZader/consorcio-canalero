/**
 * Targeted Stryker config for Pilar Verde `bpaPracticas.ts`.
 *
 * Run with:
 *   npx stryker run stryker-bpa-practicas.config.mjs
 *
 * Uses the `command` runner (same as the repo's `stryker.config.json`) to bypass
 * the `@stryker-mutator/vitest-runner` + Vitest 4 `project.server` incompatibility.
 * Each mutant triggers a targeted `vitest run tests/unit/bpaPracticas.test.ts`
 * instead of the full suite, so feedback stays fast.
 *
 * Threshold: break at 85% mutation score per tasks.md 3.7.
 */
export default {
  $schema:
    'https://raw.githubusercontent.com/stryker-mutator/stryker-js/master/packages/core/schema/stryker-schema.json',
  testRunner: 'command',
  commandRunner: {
    command: 'npm run test:run -- tests/unit/bpaPracticas.test.ts',
  },
  coverageAnalysis: 'off',
  mutate: ['src/components/map2d/bpaPracticas.ts'],
  reporters: ['html', 'json', 'clear-text'],
  htmlReporter: {
    fileName: 'reports/mutation/bpa-practicas/index.html',
  },
  timeoutMS: 60000,
  thresholds: {
    high: 90,
    low: 80,
    break: 85,
  },
  concurrency: 1,
  allowEmpty: false,
  cleanTempDir: true,
};
