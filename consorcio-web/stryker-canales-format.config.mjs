/**
 * Stryker config scoped to the Pilar Azul (Canales) pure formatter.
 *
 * Target: `src/components/map2d/canalesFormat.ts` — the `formatLongitud` and
 * `formatLongitudMeters` helpers. Tests live in `tests/unit/CanalCard.test.tsx`
 * which exercises the helper both directly (via `formatLongitud` equality
 * assertions) AND through `<CanalCard>` rendering.
 *
 * Runner: `command` (NOT `@stryker-mutator/vitest-runner`). Same rationale as
 * `stryker-bpa-practicas.config.mjs` — the vitest-runner package is NOT
 * compatible with Vitest 4 (`project.server.moduleGraph` API was removed in
 * Vitest 4 but the runner still calls it). Until the upstream runner is
 * updated, every SDD target in this repo uses the `command` fallback.
 *
 * Run with:
 *   npx stryker run stryker-canales-format.config.mjs
 *
 * Threshold: ≥85% mutation score (per spec §Test Coverage "Stryker mutation").
 */
export default {
  $schema:
    'https://raw.githubusercontent.com/stryker-mutator/stryker-js/master/packages/core/schema/stryker-schema.json',
  testRunner: 'command',
  commandRunner: {
    command: 'npm run test:run -- tests/unit/CanalCard.test.tsx',
  },
  coverageAnalysis: 'off',
  mutate: ['src/components/map2d/canalesFormat.ts'],
  reporters: ['html', 'json', 'clear-text'],
  htmlReporter: {
    fileName: 'reports/mutation/canales-format/index.html',
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
