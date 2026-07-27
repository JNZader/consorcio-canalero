/**
 * Stryker config — THE one. A `stryker.config.json` used to sit next to this
 * file and win (StrykerJS resolves .json first), so CI mutated a single file
 * (`src/hooks/useAuth.ts`) and this curated scope had never run. That .json is
 * gone; keep it that way — do not re-add a .json/.js config beside this one.
 *
 * Measured on the full scope (2026-07-27): score 76.91%, up from 63.09% over
 * three passes — `authStore.initialize()` (26.8% -> 66.12%), the email
 * recovery flows of `lib/auth` (40.9% -> 66.91%) and the boundary cases of
 * `lib/typeGuards` (65.27% -> 89.75%).
 *
 * Weak spots that remain (mutants that survive = untested behaviour):
 *   stores/configStore.ts  42.31%  (26 survived — the worst of the scope)
 *   lib/api/core.ts        53.60%  (74 survived, 55 with no coverage at all)
 *   lib/formatters.ts      82.63%  (22 survived)
 *
 * On the `break` threshold: raise it when the gap to the measured score grows
 * past ~10 points, not on every PR. A floor far below the real score is a
 * decorative gate; one glued to it turns normal incremental noise into red
 * builds.
 *
 * @type {import('@stryker-mutator/api/core').PartialStrykerOptions}
 */
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
    // Pilar Verde widget pure helpers (Phase 4 — ≥85% target)
    'src/components/admin/pilarVerdeWidget/computeKpis.ts',
    'src/components/admin/pilarVerdeWidget/fmt.ts',
    // Pilar Azul pure formatter (Phase 3 — ≥85% target).
    // `formatLongitud` + `formatLongitudMeters` drive the longitud row of
    // `<CanalCard>` — tests pin all 4 branches (null/equal/different/default).
    'src/components/map2d/canalesFormat.ts',
  ],
  thresholds: {
    high: 85,
    low: 60,
    // Sube con el score medido: 50 -> 65 -> 70. Con el global en 76.91% un
    // piso de 65 volvia a dejar 12 puntos de caida libre. 70 conserva ~7
    // puntos de holgura para el ruido de la corrida incremental y aun asi
    // muerde si entra codigo sin tests.
    break: 70,
  },
  timeoutMS: 30000,
  concurrency: 4,
  // Incremental mode: on a PR, Stryker re-tests only the mutants the diff can
  // affect and reuses the stored verdicts for the rest. The full scope takes
  // ~46 min on a GH runner (measured: 1840/1880 in 45 min) — too expensive per
  // PR for a project that already had to disable a workflow over Actions quota.
  // The weekly `mutation-full` job refreshes this file with a complete run;
  // `--force` rebuilds it from scratch.
  incremental: true,
  incrementalFile: 'reports/mutation/stryker-incremental.json',
};
