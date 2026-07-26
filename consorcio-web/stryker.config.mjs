/**
 * Stryker config — THE one. A `stryker.config.json` used to sit next to this
 * file and win (StrykerJS resolves .json first), so CI mutated a single file
 * (`src/hooks/useAuth.ts`) and this curated scope had never run. That .json is
 * gone; keep it that way — do not re-add a .json/.js config beside this one.
 *
 * Measured on the full scope (2026-07-26): 1880 mutants, 25m20s, score 63.09%.
 * Weak spots worth attention (mutants that survive = untested behaviour):
 * stores/authStore.ts 26.8%, lib/auth.ts 40.9%, lib/api/core.ts 53.2% and
 * lib/typeGuards.ts 65.3% — the last one guards tile_url against a host
 * allowlist, so its survivors are security-relevant.
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
    break: 50,
  },
  timeoutMS: 30000,
  concurrency: 4,
};
