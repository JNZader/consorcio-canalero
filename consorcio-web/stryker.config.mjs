/**
 * Stryker config — THE one. A `stryker.config.json` used to sit next to this
 * file and win (StrykerJS resolves .json first), so CI mutated a single file
 * (`src/hooks/useAuth.ts`) and this curated scope had never run. That .json is
 * gone; keep it that way — do not re-add a .json/.js config beside this one.
 *
 * Measured on the full scope (2026-07-27): score 80.96%, up from 63.09% over
 * four passes — `authStore.initialize()` (26.8% -> 66.12%), the email recovery
 * flows of `lib/auth` (40.9% -> 66.91%), the boundary cases of `lib/typeGuards`
 * (65.27% -> 89.75%), the protected-photo URL guard and helpers of
 * `lib/api/core` (53.60% -> 74.82%) and the config merge of
 * `stores/configStore` (42.31% -> 75.00%).
 *
 * No file sits under 70 any more. What remains is a long tail, and the shape
 * of the survivors changed: they are no longer whole untested functions but
 * individual conditions inside covered code. Worth a pass when it gets in the
 * way, not before:
 *   lib/api/core.ts        74.82%  (50 survived — the largest remaining pool)
 *   stores/configStore.ts  75.00%  (9 survived)
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
    // Rainfall v2 (archived lluvia-v2 change, follow-up registered 2026-08-07):
    // the authenticated ficha analysis slice. Registered AFTER the archive, when
    // task 3.4's mutation-target deferral was closed. Covered by
    // tests/unit/rainfallApi.test.ts, tests/unit/RainfallDetailPanel.test.tsx,
    // tests/unit/rainfallFormat.test.ts, tests/hooks/useRainfallAnalysis.test.tsx
    // and tests/e2e/rainfall-v2-detail.spec.ts. `rainfallFormat.ts` is the
    // shared display/export formatter and the highest-value pure target.
    'src/lib/api/rainfall.ts',
    'src/hooks/useRainfallAnalysis.ts',
    'src/components/map2d/rainfall/RainfallDetailPanel.tsx',
    'src/components/map2d/rainfall/rainfallFormat.ts',
    'src/components/map2d/rainfall/RainfallMetricList.tsx',
  ],
  thresholds: {
    high: 85,
    low: 60,
    // Sube con el score medido: 50 -> 65 -> 70 -> 75. Con el global en 80.96%
    // la brecha contra 70 paso los 10 puntos que fija el criterio de arriba,
    // asi que corresponde. 75 conserva ~6 de holgura.
    //
    // Se dejo pasar A PROPOSITO la oportunidad anterior (PR #48, brecha de 10
    // justos): el criterio dice "no en cada PR", y una regla que uno no
    // respeta a la primera oportunidad no es una regla. Subirlo una vez por
    // tanda, no una vez por commit.
    break: 75,
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
