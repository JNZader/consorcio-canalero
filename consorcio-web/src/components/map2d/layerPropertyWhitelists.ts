/**
 * layerPropertyWhitelists.ts
 *
 * Phase 8 — click-feedback property filtering for InfoPanel.
 *
 * Some upstream layers (notably `caminos` / Red Vial — IDECOR KML-derived)
 * carry 20+ raw attribute fields, most of them KML-plumbing noise
 * (`altitudeMo`, `extrude`, `tessellate`, `begin`, `end`, …). Showing them
 * all clutters the InfoPanel and buries the 7 fields users actually care
 * about.
 *
 * This module exposes:
 *   - A small per-layer whitelist of keys (in display order)
 *   - A label map (key → Rioplatense Spanish label)
 *   - `getDisplayableProperties(layerId, props)` — returns the rows to render
 *
 * Layers not listed fall back to "show every key that doesn't start with
 * `__`" (pre-existing behavior), so this is additive: new layers stay
 * unchanged until someone decides they deserve a whitelist.
 */

import { SOURCE_IDS } from './map2dConfig';

/**
 * Per-layer list of property keys to display, IN ORDER. The order is the
 * on-screen order inside InfoPanel (no alphabetization).
 */
export const LAYER_PROPERTY_WHITELISTS: Record<string, readonly string[]> = {
  /**
   * Red Vial / caminos — IDECor provincial road network.
   *   ccn → Denominación (road identifier, e.g. "158")
   *   fna → Nombre (display name, e.g. "RN 158")
   *   gna → Tipo (road class — Ruta Nacional / Provincial / …)
   *   hct → Jerarquía (hierarchy — Primaria / Secundaria / …)
   *   red → Red (network — Nacional / Provincial / Local)
   *   rst → Superficie (surface — Pavimentada / Consolidada / …)
   *   rtn → Ruta (route number)
   *
   * The 13+ remaining KML fields (altitudeMo, begin, end, extrude,
   * tessellate, etc.) are plumbing and intentionally hidden.
   */
  caminos: ['ccn', 'fna', 'gna', 'hct', 'red', 'rst', 'rtn'],

  /**
   * Catastro rural — IDECor. Hides internal DB plumbing (created_at, id,
   * par_idparcela) and keeps only fields useful to the user.
   */
  catastro: [
    'nro_cuenta',
    'desig_oficial',
    'superficie_ha',
    'departamento',
    'pedania',
    'nomenclatura',
    'tipo_parcela',
  ],
} as const;

/**
 * Human-readable labels for whitelisted keys. Only the keys that appear in
 * a whitelist need an entry here; unknown keys fall back to the raw key.
 */
export const LAYER_PROPERTY_LABELS: Record<string, Record<string, string>> = {
  caminos: {
    ccn: 'Denominación',
    fna: 'Nombre',
    gna: 'Tipo',
    hct: 'Jerarquía',
    red: 'Red',
    rst: 'Superficie',
    rtn: 'Ruta',
  },
  catastro: {
    nro_cuenta: 'Cuenta catastral',
    desig_oficial: 'Designación',
    superficie_ha: 'Superficie (ha)',
    departamento: 'Departamento',
    pedania: 'Pedanía',
    nomenclatura: 'Nomenclatura',
    tipo_parcela: 'Tipo',
  },
} as const;

/**
 * Map a MapLibre layer id (e.g. `"map2d-roads-line"`) back to the key used
 * in `LAYER_PROPERTY_WHITELISTS` / `LAYER_PROPERTY_LABELS`. Returns `null`
 * when the layer has no whitelist.
 *
 * Exported separately so tests can assert the routing without exercising
 * the full `getDisplayableProperties` pipeline.
 */
export function resolveLayerWhitelistKey(layerId: string | undefined | null): string | null {
  if (!layerId) return null;
  if (layerId === `${SOURCE_IDS.ROADS}-line`) return 'caminos';
  if (layerId === `${SOURCE_IDS.CATASTRO}-fill` || layerId === `${SOURCE_IDS.CATASTRO}-line`)
    return 'catastro';
  return null;
}

export interface DisplayableProperty {
  readonly key: string;
  readonly label: string;
  readonly value: unknown;
}

function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === 'string' && value.trim().length === 0) return true;
  return false;
}

/**
 * Build the row list rendered in InfoPanel's generic branch.
 *
 *   - If the layer has a whitelist: filter to those keys (in the
 *     documented order), drop keys whose value is null/undefined/empty,
 *     humanize labels.
 *   - Otherwise: return every non-`__`-prefixed property in insertion
 *     order, with the raw key as its own label.
 */
export function getDisplayableProperties(
  layerId: string | undefined | null,
  props: Record<string, unknown>
): DisplayableProperty[] {
  const whitelistKey = resolveLayerWhitelistKey(layerId);

  if (whitelistKey !== null) {
    const keys = LAYER_PROPERTY_WHITELISTS[whitelistKey] ?? [];
    const labels = LAYER_PROPERTY_LABELS[whitelistKey] ?? {};
    const rows: DisplayableProperty[] = [];
    for (const key of keys) {
      const value = props[key];
      if (isEmpty(value)) continue;
      rows.push({ key, label: labels[key] ?? key, value });
    }
    return rows;
  }

  // Fallback: show everything that isn't a double-underscore internal field.
  return Object.entries(props)
    .filter(([key]) => !key.startsWith('__'))
    .map(([key, value]) => ({ key, label: key, value }));
}
