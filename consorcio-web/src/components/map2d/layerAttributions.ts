/**
 * Layer attribution registry.
 *
 * When a group of map layers requires a data-source credit line (e.g. IDECor
 * for Pilar Verde), register it here instead of adding another `if` branch in
 * `LayerControlsPanel.tsx`. The legend footer loops `getActiveAttributions()`
 * and renders one `<Text>` per active attribution string, deduplicated.
 *
 * Adding a new group:
 *   1. Append a new `LayerAttribution` to `LAYER_ATTRIBUTIONS`.
 *   2. The footer will pick it up automatically. No component changes needed.
 *
 * Contract:
 *   - Each entry's `layerIds` must be non-empty.
 *   - `text` is the exact Spanish string to render (no template placeholders).
 *   - `getActiveAttributions()` returns the set of texts whose `layerIds`
 *     intersect the visible-vectors set, in registry order, deduplicated.
 */

import { PILAR_VERDE_LAYER_IDS } from '../../stores/mapLayerSyncStore';

export interface LayerAttribution {
  readonly layerIds: readonly string[];
  readonly text: string;
}

export const LAYER_ATTRIBUTIONS: readonly LayerAttribution[] = [
  {
    layerIds: PILAR_VERDE_LAYER_IDS,
    text: 'Datos: IDECor — Gobierno de Córdoba',
  },
];

/**
 * Returns the attribution strings whose layer group has at least one visible
 * layer. Duplicates (same `text` across multiple registry entries) collapse
 * to a single output.
 */
export function getActiveAttributions(visibleVectors: Set<string>): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const { layerIds, text } of LAYER_ATTRIBUTIONS) {
    if (seen.has(text)) continue;
    for (const id of layerIds) {
      if (visibleVectors.has(id)) {
        out.push(text);
        seen.add(text);
        break;
      }
    }
  }
  return out;
}
