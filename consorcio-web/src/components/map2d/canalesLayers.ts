/**
 * canalesLayers
 *
 * Colocated registry for the 2 Pilar Azul (Canales) line layers:
 *   - Palette constants (`CANALES_COLORS`)
 *   - Z-order tuple (`CANALES_Z_ORDER` — relevados below propuestos in the
 *     documentation sense; layer-add order in MapLibre follows the pattern
 *     used by `PILAR_VERDE_Z_ORDER`: iterate and `moveLayer` to hoist).
 *   - Paint factories (pure — one for each estado)
 *   - Filter builders (per-canal id filter + combined per-canal + etapas
 *     filter for propuestos)
 *
 * Consumers:
 *   - `mapLayerEffectHelpers.ts::syncCanalesLayers` uses paint + filter
 *     factories to mount / update the two line layers idempotently.
 *   - `LegendPanel.tsx` reads the palette to render the chip swatches.
 *   - `InfoPanel.tsx` / `CanalCard.tsx` reuse the palette for Badge colors.
 *
 * @see spec `sdd/canales-relevados-y-propuestas/spec` § Color Palette + Map Source Registry
 * @see design `sdd/canales-relevados-y-propuestas/design` § 4 Frontend Architecture
 */

import type { ExpressionSpecification, LineLayerSpecification } from 'maplibre-gl';

import type { Etapa } from '../../types/canales';
import { PILAR_AZUL_LAYER_IDS } from '../../stores/mapLayerSyncStore';

/**
 * Render z-order. Relevados mounted FIRST; propuestos mounted AFTER so they
 * draw on top of the blue baseline. Matches the tuple exported from the store
 * (`PILAR_AZUL_LAYER_IDS`) 1:1 so the toggle↔render mapping is predictable.
 */
export const CANALES_Z_ORDER = [
  'canales_relevados',
  'canales_propuestos',
] as const satisfies readonly (typeof PILAR_AZUL_LAYER_IDS)[number][];

export type CanalesLayerId = (typeof CANALES_Z_ORDER)[number];

/**
 * Palette — Tailwind-aligned hexes so future Tailwind migrations stay
 * coherent. All 8 core colors are locked by the spec ("Color Palette"
 * requirement) — change these constants, not downstream code.
 */
export const CANALES_COLORS = {
  // Relevados — solid blue family keyed by `source_style`.
  /** blue-700 — relevados without intervención programada. */
  relevadoSinObra: '#1D4ED8',
  /** blue-500 — relevados con readecuación. */
  relevadoReadec: '#3B82F6',
  /** blue-400 — canales asociados (red receptora / interconexión). */
  relevadoAsociada: '#60A5FA',
  // Propuestos — warm family keyed by `prioridad` (Etapa).
  /** red-600 — Etapa 1 (Alta). */
  propuestoAlta: '#DC2626',
  /** orange-600 — Etapa 2 (Media-Alta). */
  propuestoMediaAlta: '#EA580C',
  /** yellow-600 — Etapa 3 (Media). */
  propuestoMedia: '#CA8A04',
  /** slate-500 — Etapa 4 (Opcional). */
  propuestoOpcional: '#64748B',
  /** slate-400 — Etapa 5 (Largo plazo). */
  propuestoLargoPlazo: '#94A3B8',
  // Outlines — darker than their fills so the 2 line families read as a
  // cohesive block even when overlapping.
  /** Shared relevado outline — blue-900. */
  outlineRelevado: '#1E3A8A',
  /** Shared propuesto outline — slate-700. */
  outlinePropuesto: '#334155',
} as const;

// ---------------------------------------------------------------------------
// Paint factories
// ---------------------------------------------------------------------------

type LinePaint = NonNullable<LineLayerSpecification['paint']>;

/**
 * Relevados paint — solid line, color by `source_style`.
 *
 * The `match` expression covers the 3 known categories (spec-locked) and
 * falls back to `relevadoSinObra` when the ETL emits an unknown or null
 * `source_style`. Width is a constant 3px — widget behavior is consistent
 * with the Pilar Verde line layers (they use 0.5–1px outlines — 3px here
 * is intentional since canales are the primary feature, not context).
 */
export function buildCanalesRelevadosPaint(): LinePaint {
  return {
    'line-color': [
      'match',
      ['get', 'source_style'],
      'sin_obra',
      CANALES_COLORS.relevadoSinObra,
      'readec',
      CANALES_COLORS.relevadoReadec,
      'asociada',
      CANALES_COLORS.relevadoAsociada,
      CANALES_COLORS.relevadoSinObra,
    ] as ExpressionSpecification,
    'line-width': 3,
    'line-opacity': 0.95,
  };
}

/**
 * Propuestos paint — DASHED line, color by `prioridad` (Etapa).
 *
 * Dashed pattern `[4, 2]` reads as "proposed / not yet built" without a
 * separate icon. Width 2.5px pairs with the 3px relevados line so the stack
 * reads top-down as thicker-solid vs. thinner-dashed.
 *
 * Fallback (null prioridad) uses slate-500 — matches the Opcional tier so
 * null-etapa propuestos still read as proposed without shouting a priority.
 */
export function buildCanalesPropuestasPaint(): LinePaint {
  return {
    'line-color': [
      'match',
      ['get', 'prioridad'],
      'Alta',
      CANALES_COLORS.propuestoAlta,
      'Media-Alta',
      CANALES_COLORS.propuestoMediaAlta,
      'Media',
      CANALES_COLORS.propuestoMedia,
      'Opcional',
      CANALES_COLORS.propuestoOpcional,
      'Largo plazo',
      CANALES_COLORS.propuestoLargoPlazo,
      CANALES_COLORS.propuestoOpcional,
    ] as ExpressionSpecification,
    'line-dasharray': [4, 2],
    'line-width': 2.5,
    'line-opacity': 0.95,
  };
}

// ---------------------------------------------------------------------------
// Filter builders
// ---------------------------------------------------------------------------

/**
 * Relevados filter — restrict the layer to the given slug set.
 *
 * The filter uses `["in", ["get", "id"], ["literal", ids]]` — MapLibre
 * evaluates this as O(n) per feature but n is at most ~50 and the feature
 * set is constant per tile, so it's effectively free.
 */
export function buildCanalesRelevadosFilter(
  visibleIds: readonly string[],
): ExpressionSpecification {
  return ['in', ['get', 'id'], ['literal', [...visibleIds]]] as ExpressionSpecification;
}

/**
 * Propuestos filter — combine the per-canal filter AND the etapas filter.
 *
 * Structure: `["all", idFilter, etapasFilter]` — MapLibre short-circuits on
 * the first false, which is typically the id filter (cheaper to evaluate).
 *
 * Null prioridad handling: if `activeEtapas` contains ANY prioridad string,
 * a feature with `prioridad === null` will fail the etapa match and be
 * excluded. The store-level `getVisiblePropuestaIds` already drops
 * null-prioridad propuestos from `visibleIds` when all etapas are off and
 * includes them otherwise — the MapLibre expression doesn't need to be
 * clever about null here, since the id filter already does the work.
 */
export function buildCanalesPropuestasFilter(
  visibleIds: readonly string[],
  activeEtapas: readonly Etapa[],
): ExpressionSpecification {
  const idFilter: ExpressionSpecification = [
    'in',
    ['get', 'id'],
    ['literal', [...visibleIds]],
  ] as ExpressionSpecification;
  const etapaFilter: ExpressionSpecification = [
    'in',
    ['get', 'prioridad'],
    ['literal', [...activeEtapas]],
  ] as ExpressionSpecification;
  return ['all', idFilter, etapaFilter] as ExpressionSpecification;
}
