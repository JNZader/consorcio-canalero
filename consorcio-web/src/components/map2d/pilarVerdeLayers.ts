/**
 * pilarVerdeLayers
 *
 * Colocated registry for the 5 Pilar Verde vector layers:
 *   - colors (semantic DEFAULT palette — user can override these constants)
 *   - z-order (bottom → top; topmost wins click precedence)
 *   - MapLibre paint factories (pure, deterministic, no dynamic values)
 *
 * Consumers:
 *   - `mapLayerEffectHelpers.ts` — sync helpers import paint factories
 *   - `useMapLayerEffects.ts` — passes z-order to `map.moveLayer()`
 *   - `LayerControlsPanel.tsx` (Phase 5) — reads `PILAR_VERDE_LAYER_IDS` (from store)
 *   - Phase 6 Playwright e2e — asserts `PILAR_VERDE_Z_ORDER` against DOM layer order
 *
 * Palette rationale:
 *   - Semantic ("green = cumplen", "red = no cumplen", "amber = BPA")
 *   - Tailwind-aligned hexes so a future Tailwind migration stays coherent
 *   - Top-most layer (bpa) has highest opacity; bottom-most (forestación) is very transparent
 *
 * @see spec `sdd/pilar-verde-bpa-agroforestal/spec` § Map Source Registry Additions
 * @see design `sdd/pilar-verde-bpa-agroforestal/design` § 4 Frontend Architecture
 */

import type { FillLayerSpecification, LineLayerSpecification } from 'maplibre-gl';

import { PILAR_VERDE_LAYER_IDS } from '../../stores/mapLayerSyncStore';

/**
 * Render z-order, bottom → top.
 *
 * When a sync helper mounts these layers, each `map.moveLayer(id)` call
 * (with no beforeId) raises the layer to the TOP of the style — so iterating
 * in this exact order produces the documented stacking:
 *
 *   1. agro_zonas                  (bottom — subtle cyan context)
 *   2. porcentaje_forestacion      (violet, very transparent)
 *   3. agro_presentada             (red — non-compliant)
 *   4. agro_aceptada               (green — compliant, wins over presentada on overlap)
 *   5. pilar_verde_bpa             (top — amber, most specific, wins click precedence)
 *
 * Order must match the tuple exported from the store (`PILAR_VERDE_LAYER_IDS`)
 * for a predictable toggle↔render mapping.
 */
export const PILAR_VERDE_Z_ORDER = [
  'pilar_verde_agro_zonas',
  'pilar_verde_porcentaje_forestacion',
  'pilar_verde_agro_presentada',
  'pilar_verde_agro_aceptada',
  'pilar_verde_bpa',
] as const satisfies readonly (typeof PILAR_VERDE_LAYER_IDS)[number][];

export type PilarVerdeLayerId = (typeof PILAR_VERDE_Z_ORDER)[number];

/**
 * Default color palette. All hex values are Tailwind 500-level equivalents.
 *
 * [DEFAULT — user can override in PilarVerde color constants]
 * Change these values (not downstream code) to repaint the whole pillar.
 *
 * `eje*` colors mirror the spec eje palette used by InfoPanel (Phase 3). They
 * live here so the whole Pilar Verde visual system is one import away.
 */
export const PILAR_VERDE_COLORS = {
  /** Top layer — BPA 2025 fill. Amber/yellow @ 0.40 opacity. */
  bpaFill: '#FACC15',
  /** Agro-aceptada (compliant). Green @ 0.30 opacity. */
  agroAceptadaFill: '#22C55E',
  /** Agro-presentada (non-compliant). Red @ 0.30 opacity. */
  agroPresentadaFill: '#EF4444',
  /** Agroforestal zonas (context). Cyan @ 0.20 opacity — subtle. */
  agroZonasFill: '#06B6D4',
  /** Porcentaje forestación obligatoria (background context). Violet @ 0.15 opacity. */
  porcentajeForestacionFill: '#A78BFA',
  // ── Eje palette (mirrored by InfoPanel in Phase 3) ──
  /** Persona — blue-500. */
  ejePersona: '#3B82F6',
  /** Planeta — emerald-500. */
  ejePlaneta: '#10B981',
  /** Prosperidad — amber-500. */
  ejeProsperidad: '#F59E0B',
  /** Alianza — violet-500. */
  ejeAlianza: '#8B5CF6',
} as const;

// ---------------------------------------------------------------------------
// Paint factories
// Each returns a plain MapLibre paint object (no layer id / no source).
// Kept as factories (not frozen constants) so the consumer can spread them
// into `addLayer({ ... paint })` without mutating the registry object.
// ---------------------------------------------------------------------------

type FillPaint = NonNullable<FillLayerSpecification['paint']>;
type LinePaint = NonNullable<LineLayerSpecification['paint']>;

/** BPA 2025 fill — topmost, most specific, amber/yellow. */
export function buildBpaFillPaint(): FillPaint {
  return {
    'fill-color': PILAR_VERDE_COLORS.bpaFill,
    'fill-opacity': 0.4,
  };
}

/** BPA 2025 line — amber outline. Matches fill color for visual cohesion. */
export function buildBpaLinePaint(): LinePaint {
  return {
    'line-color': PILAR_VERDE_COLORS.bpaFill,
    'line-width': 1.5,
    'line-opacity': 0.9,
  };
}

/** Agro-aceptada fill — green, compliant. */
export function buildAgroAceptadaFillPaint(): FillPaint {
  return {
    'fill-color': PILAR_VERDE_COLORS.agroAceptadaFill,
    'fill-opacity': 0.3,
  };
}

/** Agro-aceptada line — green outline. */
export function buildAgroAceptadaLinePaint(): LinePaint {
  return {
    'line-color': PILAR_VERDE_COLORS.agroAceptadaFill,
    'line-width': 1,
    'line-opacity': 0.85,
  };
}

/** Agro-presentada fill — red, non-compliant. */
export function buildAgroPresentadaFillPaint(): FillPaint {
  return {
    'fill-color': PILAR_VERDE_COLORS.agroPresentadaFill,
    'fill-opacity': 0.3,
  };
}

/** Agro-presentada line — red outline. */
export function buildAgroPresentadaLinePaint(): LinePaint {
  return {
    'line-color': PILAR_VERDE_COLORS.agroPresentadaFill,
    'line-width': 1,
    'line-opacity': 0.85,
  };
}

/** Agro zonas fill — cyan, subtle context layer. */
export function buildAgroZonasFillPaint(): FillPaint {
  return {
    'fill-color': PILAR_VERDE_COLORS.agroZonasFill,
    'fill-opacity': 0.2,
  };
}

/** Agro zonas line — thin cyan outline. */
export function buildAgroZonasLinePaint(): LinePaint {
  return {
    'line-color': PILAR_VERDE_COLORS.agroZonasFill,
    'line-width': 1,
    'line-opacity': 0.75,
  };
}

/**
 * Porcentaje-forestación fill — violet, very transparent background context.
 * Intentionally no line layer: this is a low-contrast raster-like context fill
 * so it does not dominate the map even when toggled on.
 */
export function buildPorcentajeForestacionFillPaint(): FillPaint {
  return {
    'fill-color': PILAR_VERDE_COLORS.porcentajeForestacionFill,
    'fill-opacity': 0.15,
  };
}
