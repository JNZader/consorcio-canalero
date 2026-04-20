/**
 * fmt — locale-aware number formatter for the Pilar Verde widget.
 *
 * Rendering rules (all Rioplatense):
 *   - Locale `es-AR`  → thousands separator "." and decimal ","
 *   - Up to ONE decimal place (matches `aggregates.json` rounding upstream)
 *   - Trailing ",0" is NOT stripped when the caller explicitly passes a unit
 *     that carries a decimal semantic — `fmt(33, "%")` returns "33,0%" while
 *     `fmt(33, "ha")` returns "33 ha". Rationale: percentages are always shown
 *     with one decimal for consistency with the ETL cumplimiento_pct fields;
 *     integer-looking hectare counts (e.g. 88307 → "88.307 ha") stay compact.
 *   - `null` / `undefined` / `NaN` → "—" (em dash sentinel)
 *   - `0` is a VALID value — "0 ha" is correct, do NOT collapse to the sentinel.
 *   - `%` attaches directly (no space); every other unit gets a single space.
 *
 * Pure, no I/O, no globals. Safe to tree-shake.
 */

const EM_DASH = '—' as const;

const DECIMAL_FORMATTER = new Intl.NumberFormat('es-AR', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const INTEGER_FORMATTER = new Intl.NumberFormat('es-AR', {
  maximumFractionDigits: 0,
});

function isNumericSentinel(value: number | null | undefined): value is null | undefined {
  return value === null || value === undefined || Number.isNaN(value);
}

function formatNumberValue(value: number, unit: string | undefined): string {
  // Percentage is ALWAYS one decimal (matches the ETL cumplimiento_pct* rounding).
  if (unit === '%') {
    return DECIMAL_FORMATTER.format(value);
  }
  // Integer path: values with no meaningful fractional part render without ",0".
  if (Number.isInteger(value)) {
    return INTEGER_FORMATTER.format(value);
  }
  return DECIMAL_FORMATTER.format(value);
}

/**
 * Format a number for Pilar Verde UI surfaces.
 *
 * @param value the raw number (may be `null` / `undefined` / `NaN`)
 * @param unit  optional suffix — `"%"` attaches directly, everything else gets
 *              a single space ("ha", "parcelas", etc.). Omit for a bare number.
 * @returns the formatted string, or "—" (em dash) for missing / NaN input.
 */
export function fmt(value: number | null | undefined, unit?: string): string {
  if (isNumericSentinel(value)) return EM_DASH;

  const numeric = formatNumberValue(value, unit);
  if (!unit) return numeric;
  if (unit === '%') return `${numeric}%`;
  return `${numeric} ${unit}`;
}
