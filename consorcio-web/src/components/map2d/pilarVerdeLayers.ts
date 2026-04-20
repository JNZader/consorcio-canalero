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
  'pilar_verde_bpa_historico',
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
  /**
   * Historical BPA gradient stops (by años_bpa 1..7).
   * Pale green (sporadic) → dark green (fully committed).
   * Kept as individual keys so the legend can render matching color chips.
   */
  bpaHistoricoStop1: '#BBF7D0', // 1 año — sporadic
  bpaHistoricoStop3: '#4ADE80', // 3 años
  bpaHistoricoStop5: '#22C55E', // 5 años
  bpaHistoricoStop7: '#15803D', // 7 años — full commitment
  /** Outline for the historical BPA layer (thin dark-green line). */
  bpaHistoricoLine: '#166534',
  /** Agro-aceptada (compliant). Green @ 0.30 opacity. */
  agroAceptadaFill: '#22C55E',
  /** Agro-presentada (non-compliant). Red @ 0.30 opacity. */
  agroPresentadaFill: '#EF4444',
  /**
   * Agroforestal zonas (context). Cyan @ 0.20 opacity — subtle. Used as the
   * FALLBACK color inside the per-zone `match` expression for any zone whose
   * `leyenda` doesn't match one of the 3 known systems below. Keeping it as
   * cyan preserves backward compatibility with the original single-color look.
   */
  agroZonasFill: '#06B6D4',
  /**
   * Per-zone agroforestal colors. The consorcio zone has EXACTLY 3 systems,
   * each identified by a distinct `leyenda` property. Using one color per
   * system lets the user read the map + legend without clicking each polygon.
   *
   *   - Río Tercero Este   → cyan-500  (same as the legacy cyan — keeps visual continuity)
   *   - Río Carcarañá      → teal-500
   *   - Arroyo Tortugas    → sky-500
   *
   * All three sit in the same cool-blue family so the layer still reads as a
   * cohesive "agroforestal zonas" block but the 3 systems are distinguishable.
   */
  agroZonaRioTercero: '#06B6D4',
  agroZonaCarcarana: '#14B8A6',
  agroZonaTortugas: '#0EA5E9',
  /**
   * Porcentaje forestación obligatoria — categorized into 3 tiers by
   * `forest_obligatoria` (%). Real zone data ranges 2.1–2.88%, not the
   * provincial 2–5% band, so a linear gradient is indistinguishable. The
   * buckets track the two dominant peaks (2.10 and 2.60) observed on the
   * 1,222 features of the layer.
   *
   *   - Baja  (≤ 2.30%)  — violet-300
   *   - Media (2.31–2.60%) — violet-400 (historical default)
   *   - Alta  (≥ 2.61%)  — violet-600
   *
   * Keys map 1:1 to the legend chips in `LeyendaPanel` — single source of
   * truth for the MapLibre `step` paint expression.
   */
  porcentajeForestacionBaja: '#C4B5FD',
  porcentajeForestacionMedia: '#A78BFA',
  porcentajeForestacionAlta: '#7C3AED',
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

/**
 * BPA historical gradient fill — colored by ``años_bpa`` (1..7) using a
 * MapLibre ``interpolate`` expression. Phase 7 replaces the single-color
 * BPA 2025 fill.
 */
export function buildBpaHistoricoFillPaint(): FillPaint {
  return {
    'fill-color': [
      'interpolate',
      ['linear'],
      ['get', 'años_bpa'],
      1,
      PILAR_VERDE_COLORS.bpaHistoricoStop1,
      3,
      PILAR_VERDE_COLORS.bpaHistoricoStop3,
      5,
      PILAR_VERDE_COLORS.bpaHistoricoStop5,
      7,
      PILAR_VERDE_COLORS.bpaHistoricoStop7,
    ],
    'fill-opacity': 0.45,
  };
}

/** BPA historical outline — thin dark-green stroke. */
export function buildBpaHistoricoLinePaint(): LinePaint {
  return {
    'line-color': PILAR_VERDE_COLORS.bpaHistoricoLine,
    'line-width': 0.5,
    'line-opacity': 0.8,
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

/**
 * Agro zonas fill — per-zone colors via a MapLibre `match` expression on the
 * `leyenda` property. The consorcio has exactly 3 agroforestal systems, each
 * with its own color so the legend and map read consistently without needing
 * to click each polygon.
 *
 * TODO: if a future `agro_zonas.geojson` adds a new system beyond these 3,
 * the FALLBACK (`agroZonasFill`) will be used — extend the match expression
 * AND add the new color to `PILAR_VERDE_COLORS` before that ships.
 */
export function buildAgroZonasFillPaint(): FillPaint {
  return {
    'fill-color': [
      'match',
      ['get', 'leyenda'],
      '11 - Sist Rio Tercero - Este',
      PILAR_VERDE_COLORS.agroZonaRioTercero,
      '50 - Sist. Rio Carcarañá',
      PILAR_VERDE_COLORS.agroZonaCarcarana,
      '48 - Sist Arroyo Tortugas - Este',
      PILAR_VERDE_COLORS.agroZonaTortugas,
      PILAR_VERDE_COLORS.agroZonaRioTercero,
    ],
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
 * Porcentaje-forestación fill — violet, categorized into 3 tiers by
 * `forest_obligatoria`. The raw data for the zone spans 2.10–2.88%, so the
 * MapLibre `step` expression discretizes it into 3 visually distinguishable
 * buckets instead of a gradient that would collapse into a single tone.
 *
 * Tier breakpoints:
 *   - < 2.31          → Baja  (violet-300)
 *   - [2.31, 2.61)    → Media (violet-400)
 *   - ≥ 2.61          → Alta  (violet-600)
 *
 * Opacity raised from 0.15 → 0.30 so the three tiers stay distinguishable
 * on top of the basemap. No line layer by design: low-contrast context fill.
 */
export function buildPorcentajeForestacionFillPaint(): FillPaint {
  return {
    'fill-color': [
      'step',
      ['get', 'forest_obligatoria'],
      PILAR_VERDE_COLORS.porcentajeForestacionBaja,
      2.31,
      PILAR_VERDE_COLORS.porcentajeForestacionMedia,
      2.61,
      PILAR_VERDE_COLORS.porcentajeForestacionAlta,
    ],
    'fill-opacity': 0.3,
  };
}
