/**
 * kmzPiiStrip
 *
 * Defensive PII sanitizer for KMZ export feature properties.
 *
 * Phase 3's Placemark emitter does NOT currently write `<description>` or
 * `<ExtendedData>` blocks — meaning no property values reach the KML
 * output today. This module exists so the FIRST time a future change
 * adds either block, PII removal is already wired and tested.
 *
 * Denylist (case-insensitive): `cue`, `telefono`, `teléfono`, `email`,
 * `directivo`, `sector`, `departamento`. Matches the same invariant the
 * escuelas GeoJSON applies (proposal §4 US-4 — privacy-safe).
 *
 * Semantics:
 *   - Pure, non-mutating: returns a new object, never touches the input.
 *   - Recurses into plain-object values (sanitizes at every depth).
 *   - Arrays pass through by reference — Phase 3 contract keeps the
 *     input shape for arrays; extending to array items is a future hook.
 *   - `null` / `undefined` values for preserved keys are kept as-is.
 */

const PII_KEYS_LOWER = new Set<string>([
  'cue',
  'telefono',
  'teléfono',
  'email',
  'directivo',
  'sector',
  'departamento',
]);

/** True when the value is a "plain object" we should recurse into. */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (value === null || value === undefined) return false;
  if (typeof value !== 'object') return false;
  if (Array.isArray(value)) return false;
  // Defensive: skip class instances (Date, Map, etc.) — keep them as-is.
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/**
 * Return a new object with all denylisted keys removed (case-insensitive).
 * Nested plain-object values are sanitized recursively. Non-plain-object
 * values (arrays, Dates, primitives) pass through by reference.
 */
export function stripPii(properties: Record<string, unknown>): Record<string, unknown> {
  const output: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(properties)) {
    if (PII_KEYS_LOWER.has(key.toLowerCase())) {
      continue;
    }
    if (isPlainObject(value)) {
      output[key] = stripPii(value);
    } else {
      output[key] = value;
    }
  }

  return output;
}
