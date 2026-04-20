/**
 * Targeted Stryker config for the Pilar Verde widget's PURE helpers.
 *
 * Run with:
 *   npx stryker run stryker-pilar-verde-widget.config.mjs
 *
 * Uses the `command` runner (same as `stryker-bpa-practicas.config.mjs`) to
 * bypass the `@stryker-mutator/vitest-runner` + Vitest 4 incompatibility.
 * Each mutant triggers the focused Vitest files that cover these helpers:
 *   - tests/unit/computeKpis via pilarVerdeKpis.test.ts (14 tests)
 *   - tests/unit/fmt.test.ts (10 tests)
 *
 * Threshold: break at 85% mutation score per Phase 4 task 4.7.
 */
export default {
  $schema:
    'https://raw.githubusercontent.com/stryker-mutator/stryker-js/master/packages/core/schema/stryker-schema.json',
  testRunner: 'command',
  commandRunner: {
    command:
      'npm run test:run -- tests/unit/pilarVerdeKpis.test.ts tests/unit/fmt.test.ts',
  },
  coverageAnalysis: 'off',
  mutate: [
    'src/components/admin/pilarVerdeWidget/computeKpis.ts',
    'src/components/admin/pilarVerdeWidget/fmt.ts',
  ],
  reporters: ['html', 'json', 'clear-text'],
  htmlReporter: {
    fileName: 'reports/mutation/pilar-verde-widget/index.html',
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
