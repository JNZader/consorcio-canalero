/**
 * Unit-formatting helpers for ephemeral map measurements.
 *
 * Distance thresholds: < 1000 m → "N m" (integer); >= 1000 m → "X.Y km" (1 decimal).
 * Area thresholds:     < 10_000 m² → "N m²" (integer);
 *                      < 10_000_000 m² → "X.Y ha" (1 decimal);
 *                      >= 10_000_000 m² → "X.Y km²" (1 decimal).
 *
 * Threshold checks use the PRE-rounding value, so 999.9 m stays in the meter
 * branch and renders as "1000 m" (rounded up but still formatted as meters).
 * This keeps the helper cheap and predictable; see the test file for the
 * full edge-case matrix.
 *
 * Negative and NaN/Infinity inputs are treated as soft errors (no throw).
 */

const METER_TO_KM_THRESHOLD_M = 1000;
const M2_TO_HA_THRESHOLD_M2 = 10_000;
const M2_TO_KM2_THRESHOLD_M2 = 10_000_000;

export function formatDistance(meters: number): string {
  if (!Number.isFinite(meters)) return '— m';
  const safe = Math.max(0, meters);
  if (safe < METER_TO_KM_THRESHOLD_M) return `${Math.round(safe)} m`;
  return `${(safe / 1000).toFixed(1)} km`;
}

export function formatArea(squareMeters: number): string {
  if (!Number.isFinite(squareMeters)) return '— m²';
  const safe = Math.max(0, squareMeters);
  if (safe < M2_TO_HA_THRESHOLD_M2) return `${Math.round(safe)} m²`;
  if (safe < M2_TO_KM2_THRESHOLD_M2) return `${(safe / 10_000).toFixed(1)} ha`;
  return `${(safe / 1_000_000).toFixed(1)} km²`;
}
