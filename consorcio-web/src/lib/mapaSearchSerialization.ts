/**
 * Route-scoped search (de)serialization for the `/mapa` Multi-Hazard viewer.
 *
 * WHY THIS MODULE EXISTS (H5 / defect fix)
 * ----------------------------------------
 * The global TanStack `stringifySearch` used to switch to the hazard-aware
 * serializer whenever a *generic* key such as `layers`, `hazard`, `basin`,
 * `riskClasses` or `precipMonth` appeared in the search object. That is unsafe:
 * a future non-map route that happens to use one of those keys (e.g. `layers`)
 * would be serialized by the hazard writer and produce the wrong URL.
 *
 * The fix scopes the custom serializer to the `/mapa` route ONLY, via an
 * internal Symbol marker (`HAZARD_ROUTE_MARKER`). The `/mapa` route attaches
 * the marker inside its `validateSearch`; the global `stringifySearch` below
 * switches to the hazard writer *only* when the marker is present.
 *
 * The marker is a Symbol, not a string key, so it is invisible to
 * `Object.entries`, `JSON.stringify` and `URLSearchParams`. It therefore can
 * NEVER leak into the URL, and a non-map search object that merely contains a
 * `layers` array/object (or `hazard`/`basin` keys) without the marker is always
 * serialized by TanStack's default serializer.
 */

import { defaultStringifySearch } from '@tanstack/react-router';

/** Internal route-scoped marker. A Symbol so it can never appear in the URL. */
export const HAZARD_ROUTE_MARKER = Symbol.for('consorcio.hazardRouteMarker');

/**
 * True only for validated `/mapa` hazard search state (i.e. an object that
 * carries the internal marker). Everything else falls through to the default
 * serializer.
 */
export function isHazardSearchState(search: unknown): boolean {
  if (typeof search !== 'object' || search === null) return false;
  return (search as Record<symbol, unknown>)[HAZARD_ROUTE_MARKER] === true;
}

// ---------------------------------------------------------------------------
// Parser (mirrors the legacy `/mapa` validateSearch — kept here so the
// serializer and parser live together and can be unit-tested in isolation).
// ---------------------------------------------------------------------------

export const RISK_CLASS_LABELS = ['Bajo', 'Medio', 'Alto', 'Crítico'] as const;
export type RiskClass = (typeof RISK_CLASS_LABELS)[number];

export const VALID_PRECIP_MONTHS = new Set<string>([
  'anual',
  '01', '02', '03', '04', '05', '06',
  '07', '08', '09', '10', '11', '12',
]);

/**
 * Parse a risk-class / layer value into a clean string array.
 *
 * Backward-compatible with the old JSON-array serialization
 * (e.g. `["Bajo","Medio"]`) and the legacy `layers` default `[]`, while also
 * accepting repeated/CSV/semicolon-separated params from the custom writer.
 */
export function parseRiskClasses(input: unknown): string[] {
  if (input === undefined || input === null) return [];
  if (typeof input === 'string') {
    const trimmed = input.trim();
    if (trimmed === '' || trimmed === '[]') return [];
    if (trimmed.startsWith('[')) {
      try {
        const parsed = JSON.parse(trimmed);
        if (Array.isArray(parsed)) {
          return parsed.filter((v): v is string => typeof v === 'string' && v.trim() !== '');
        }
      } catch {
        /* fall through to comma splitting */
      }
    }
    return trimmed
      .split(/[,;]/)
      .map((s) => s.trim())
      .filter(Boolean);
  }
  if (Array.isArray(input)) {
    return input.filter((v): v is string => typeof v === 'string' && v.trim() !== '');
  }
  return [];
}

function parseStringParam(input: unknown): string | undefined {
  if (typeof input === 'string' && input.trim() !== '') return input.trim();
  return undefined;
}

/**
 * Validate raw `/mapa` search params into typed hazard state.
 *
 * Always attaches `HAZARD_ROUTE_MARKER` so the global `stringifySearch` knows
 * this object belongs to the `/mapa` hazard route and must use the custom
 * writer. Unknown keys are ignored; malformed values fall back to safe
 * defaults (precipMonth -> `anual`).
 */
export function validateMapaSearch(search: Record<string, unknown>): Record<string, unknown> {
  return {
    hazard: search.hazard === '1' || search.hazard === 1 || search.hazard === true,
    basin: parseStringParam(search.basin),
    riskClasses: parseRiskClasses(search.riskClasses),
    layers: parseRiskClasses(search.layers),
    precipMonth: VALID_PRECIP_MONTHS.has(String(search.precipMonth))
      ? String(search.precipMonth)
      : 'anual',
    [HAZARD_ROUTE_MARKER]: true,
  } as Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Serializer (custom writer for `/mapa` hazard state)
// ---------------------------------------------------------------------------

function appendHazardParam(params: URLSearchParams, value: unknown): void {
  if (value === true || value === 1 || value === '1') {
    params.set('hazard', '1');
  }
}

function appendArrayParam(params: URLSearchParams, key: string, value: unknown): void {
  if (!Array.isArray(value) || value.length === 0) return;
  for (const item of value) {
    params.append(key, String(item));
  }
}

function appendStringParam(
  params: URLSearchParams,
  key: string,
  value: unknown,
  defaultValue?: string,
): void {
  if (typeof value !== 'string') return;
  const trimmed = value.trim();
  if (trimmed === '') return;
  if (defaultValue !== undefined && trimmed === defaultValue) return;
  params.set(key, trimmed);
}

/**
 * Deterministic, human-readable serializer for `/mapa` hazard state.
 *
 * Iterates `Object.entries`, which skips the Symbol marker, so the marker is
 * never written to the URL. Booleans become `hazard=1`, arrays become repeated
 * params, and the default `precipMonth=anual` is omitted.
 */
export function stringifyHazardSearch(search: Record<string, unknown>): string {
  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(search)) {
    if (value === undefined || value === null) continue;

    switch (key) {
      case 'hazard':
        appendHazardParam(params, value);
        break;
      case 'basin':
        appendStringParam(params, 'basin', value);
        break;
      case 'riskClasses':
      case 'layers':
        appendArrayParam(params, key, value);
        break;
      case 'precipMonth':
        appendStringParam(params, 'precipMonth', value, 'anual');
        break;
      default:
        if (Array.isArray(value)) {
          appendArrayParam(params, key, value);
        } else {
          params.set(key, String(value));
        }
        break;
    }
  }

  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

/**
 * Router-level search serializer.
 *
 * Uses the hazard writer ONLY for validated `/mapa` state (marker present),
 * delegating everything else to TanStack's default serializer. This is the
 * core of H5: a non-map route — even one carrying a generic `layers` array or
 * `hazard`/`basin` key — never triggers the custom writer.
 */
export function stringifySearch(search: Record<string, unknown>): string {
  if (isHazardSearchState(search)) {
    return stringifyHazardSearch(search);
  }
  return defaultStringifySearch(search);
}
