/**
 * canalesFormat.ts
 *
 * Pure formatting helpers for the Pilar Azul (Canales) UI layer. Extracted
 * to its own module so the unit tests live in isolation AND Stryker can
 * target mutation testing at a focused file without pulling in React tree
 * dependencies from `CanalCard.tsx`.
 *
 * All helpers are intentionally locale-aware (Rioplatense `es-AR`) — they
 * render the two canal length figures that appear in `<CanalCard>`:
 *
 *   formatLongitud(1355)            === '1.355 m'
 *   formatLongitud(1355, 1500)      === '1.355 m · (1.500 m declarada)'
 *   formatLongitud(1355, 1355)      === '1.355 m'                (match suppressed)
 *   formatLongitud(1355, null)      === '1.355 m'                (null suppressed)
 *
 * Formatter choice: `Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 })`.
 * That yields dotted thousands separators (1.355) and no decimals — matching
 * the KMZ `<name>` declarations (e.g. "1.355 m", "2.456 m") verbatim so users
 * can cross-reference the card against source docs without mental math.
 *
 * This module has ZERO runtime deps (no React, no Mantine, no maplibre). It
 * is safe to import from tests, Storybook stories, and headless scripts.
 */

const FORMATTER = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 });

/**
 * Round-half-to-even is fine here — all inputs are already whole meters or
 * single-decimal floats from the ETL (`pyproj.Geod(ellps='WGS84')` returns
 * 1-decimal floats; KMZ declared values are always integers).
 */
export function formatLongitudMeters(meters: number): string {
  return `${FORMATTER.format(meters)} m`;
}

/**
 * Render the full longitud string used by `<CanalCard>`. When `declared` is
 * present AND different from `computed`, the declared value is appended as
 * a parenthetical annotation so the user can spot discrepancies at a glance.
 *
 * Rules:
 *   - `declared === null`  → render computed only.
 *   - `declared === computed` → render computed only (no noisy annotation).
 *   - Otherwise → "<computed> m · (<declared> m declarada)".
 *
 * We compare with `Math.round(computed)` so a geodesic float like `1355.4`
 * matches a declared `1355` — the 0.5 m drift from the KMZ round-trip is
 * irrelevant for UI purposes and suppressing the annotation keeps the card
 * clean.
 */
export function formatLongitud(
  computed: number,
  declared: number | null | undefined = null,
): string {
  const primary = formatLongitudMeters(computed);
  if (declared === null || declared === undefined) return primary;
  if (Math.round(computed) === Math.round(declared)) return primary;
  return `${primary} · (${formatLongitudMeters(declared)} declarada)`;
}
