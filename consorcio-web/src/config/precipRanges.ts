/**
 * Shared frontend contract for CHIRPS precipitation-normal rescale ranges.
 *
 * Single source of truth consumed by BOTH the tile-rescale builder
 * (`mapRasterOverlayHelpers.syncPrecipNormalLayer`) AND the legend ramp
 * (`LeyendaPanel.HazardPrecipRamp`). Previously the annual / monthly maxima
 * were duplicated as independent magic numbers (`1800` / `200`) in two places;
 * centralizing them here guarantees the tile URL and the legend can never drift
 * apart, and both stay in lockstep with the backend `rescale_policy.py`
 * canonical ranges (monthly `0–200` mm, annual `0–1800` mm).
 */

/** Minimum of every CHIRPS precip-normal rescale / legend range (mm). */
export const PRECIP_MIN_MM = 0;

/** Annual CHIRPS normal rescale + legend maximum (mm). */
export const PRECIP_ANNUAL_MAX_MM = 1800;

/** Single-monthly CHIRPS normal rescale + legend maximum (mm). */
export const PRECIP_MONTHLY_MAX_MM = 200;

/**
 * Resolve the rescale + legend maximum for a given precipitation month.
 *
 * @param precipMonth `'anual'` for the annual aggregate, or `'01'`–`'12'` for a
 *   single month. Any non-annual value is treated as a monthly normal.
 * @returns The upper bound of the precip-normal range for that month (mm).
 */
export function precipMaxForMonth(precipMonth: string): number {
  return precipMonth === 'anual' ? PRECIP_ANNUAL_MAX_MM : PRECIP_MONTHLY_MAX_MM;
}

/**
 * Full rescale + legend range for a given precipitation month.
 *
 * Shared by the tile URL builder and the legend ramp so both boundaries derive
 * from the same contract instead of being recomputed independently.
 */
export function precipRangeForMonth(precipMonth: string): { min: number; max: number } {
  return { min: PRECIP_MIN_MM, max: precipMaxForMonth(precipMonth) };
}
