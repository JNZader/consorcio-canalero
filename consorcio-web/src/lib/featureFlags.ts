/**
 * Build-time feature flags, read from Vite's `import.meta.env`.
 *
 * The convention mirrors `VITE_FEATURE_MULTI_HAZARD_VIEWER` (see
 * `src/hooks/useMultiHazardGate.ts`). A flag defaults to ENABLED when the env
 * var is absent, so existing behaviour never changes just because a variable is
 * missing; it is turned OFF by setting the var to `false` / `'false'` / `'0'`.
 */
function isFeatureEnabled(value: unknown): boolean {
  return value === true || value === 'true' || value === '1';
}

/**
 * `cruces de camino` (road flow) plus the direction chevrons it feeds.
 *
 * Turned off while the tramo-unification migration is in flight, because that
 * migration rewrites `tramo_id` and this feature references it — decoupling the
 * two means the migration does not have to keep road flow alive and consistent.
 */
export function isRoadFlowEnabled(): boolean {
  const raw = import.meta.env.VITE_FEATURE_ROAD_FLOW;
  return raw === undefined ? true : isFeatureEnabled(raw);
}
