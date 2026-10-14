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
import { mapColorTokens } from '../../lib/mapColorTokens';
import type { PILAR_AZUL_LAYER_IDS } from '../../stores/mapLayerSyncStore';
import type { Etapa } from '../../types/canales';

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
  relevadoSinObra: mapColorTokens.h1D4ED8,
  /** blue-500 — relevados con readecuación. */
  relevadoReadec: mapColorTokens.h3B82F6,
  /** blue-400 — canales asociados (red receptora / interconexión). */
  relevadoAsociada: mapColorTokens.h60A5FA,
  // Propuestos — ColorBrewer YlOrRd (CART-01, safer for deutan).
  /** YlOrRd 9 — Etapa 1 (Alta). */
  propuestoAlta: mapColorTokens.hB10026,
  /** YlOrRd 7 — Etapa 2 (Media-Alta). */
  propuestoMediaAlta: mapColorTokens.hE31A1C,
  /** YlOrRd 5 — Etapa 3 (Media). */
  propuestoMedia: mapColorTokens.hFC4E2A,
  /** YlOrRd 3 — Etapa 4 (Opcional). */
  propuestoOpcional: mapColorTokens.hFD8D3C,
  /** YlOrRd 2 — Etapa 5 (Largo plazo). */
  propuestoLargoPlazo: mapColorTokens.hFEB24C,
  // Outlines — darker than their fills so the 2 line families read as a
  // cohesive block even when overlapping.
  /** Shared relevado outline — blue-900. */
  outlineRelevado: mapColorTokens.h1E3A8A,
  /** Shared propuesto outline — slate-700. */
  outlinePropuesto: mapColorTokens.h334155,
  /** Official APRHI SR PA opted into the public map. */
  aprhiSrPa: mapColorTokens.hc2410c,
} as const;

/**
 * Relevados-only: map from the ETL's `source_style` category to the render
 * color used by `buildCanalesRelevadosPaint` above. Kept as a plain Record so
 * non-MapLibre consumers (e.g. the PDF export legend builder) can resolve the
 * same color without re-parsing the `match` expression.
 *
 * Keys MUST match the 3 spec-locked `source_style` values emitted by the ETL
 * (`sin_obra`, `readec`, `asociada`). The fallback matches the MapLibre
 * expression's default branch (`relevadoSinObra`).
 *
 * Invariants (pinned by tests):
 *   - Every hex value here MUST equal the corresponding entry in
 *     `CANALES_COLORS` — do not duplicate literals, import them back.
 *   - Consumers SHOULD treat unknown keys as the same fallback (sin_obra).
 */
export const CANAL_STYLE_COLORS: Record<string, string> = {
  sin_obra: CANALES_COLORS.relevadoSinObra,
  readec: CANALES_COLORS.relevadoReadec,
  asociada: CANALES_COLORS.relevadoAsociada,
  aprhi_sr_pa: CANALES_COLORS.aprhiSrPa,
};

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
      'aprhi_sr_pa',
      CANALES_COLORS.aprhiSrPa,
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
    'line-dasharray': [
      'match',
      ['get', 'prioridad'],
      'Alta',
      ['literal', [1, 0]],
      'Media-Alta',
      ['literal', [4, 2]],
      'Media',
      ['literal', [2, 2]],
      'Opcional',
      ['literal', [1, 2]],
      'Largo plazo',
      ['literal', [1, 3]],
      ['literal', [4, 2]],
    ] as ExpressionSpecification,
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
  visibleIds: readonly string[]
): ExpressionSpecification {
  return ['in', ['get', 'id'], ['literal', [...visibleIds]]] as ExpressionSpecification;
}

/**
 * Propuestos filter — combine the per-canal filter AND the etapas filter.
 *
 * Structure: `["all", idFilter, etapasFilter]` — MapLibre short-circuits on
 * the first false, which is typically the id filter (cheaper to evaluate).
 *
 * Missing/null `prioridad` must still paint. The public catalog GeoJSON only
 * ships id/nombre/estado/longitud_m, so a strict etapa `in` hid every
 * propuesto on `/mapa`. v1 policy: null prioridad stays visible.
 */
export function buildCanalesPropuestasFilter(
  visibleIds: readonly string[],
  activeEtapas: readonly Etapa[]
): ExpressionSpecification {
  const idFilter: ExpressionSpecification = [
    'in',
    ['get', 'id'],
    ['literal', [...visibleIds]],
  ] as ExpressionSpecification;
  const etapaFilter: ExpressionSpecification = [
    'any',
    ['==', ['get', 'prioridad'], null],
    ['in', ['get', 'prioridad'], ['literal', [...activeEtapas]]],
  ] as ExpressionSpecification;
  return ['all', idFilter, etapaFilter] as ExpressionSpecification;
}
