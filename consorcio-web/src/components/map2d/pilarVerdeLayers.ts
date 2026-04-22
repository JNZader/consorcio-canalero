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

import type { PILAR_VERDE_LAYER_IDS } from '../../stores/mapLayerSyncStore';

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
   * Pale green (sporadic) → dark green (fully committed). Each PV layer now
   * lives in its OWN hue family after the holistic palette redesign — the
   * gradient is stretched across the Tailwind green scale (100 → 900) so all
   * four stops read as distinct tiers even when overlaid on the basemap.
   * Kept as individual keys so the legend can render matching color chips.
   */
  bpaHistoricoStop1: '#DCFCE7', // 1 año — sporadic (green-100)
  bpaHistoricoStop3: '#86EFAC', // 3 años (green-300)
  bpaHistoricoStop5: '#16A34A', // 5 años (green-600)
  bpaHistoricoStop7: '#14532D', // 7 años — full commitment (green-900)
  /** Outline for the historical BPA layer (thin green-900 line). */
  bpaHistoricoLine: '#14532D',
  /**
   * Agro-aceptada (compliant). Solid blue-600 @ 0.30 opacity. Was green but
   * collided with the BPA green gradient when both layers were on → moved to
   * blue so each layer family is unique.
   */
  agroAceptadaFill: '#2563EB',
  /** Agro-aceptada outline — blue-800, darker than the fill for separation. */
  agroAceptadaLine: '#1E40AF',
  /** Agro-presentada (non-compliant). Solid red-600 @ 0.30 opacity. */
  agroPresentadaFill: '#DC2626',
  /** Agro-presentada outline — red-800. */
  agroPresentadaLine: '#991B1B',
  /**
   * Agroforestal zonas — FALLBACK color for zones whose `leyenda` doesn't
   * match one of the 3 known systems. Uses the same warm anchor as the
   * Río Tercero zone so the fallback still reads as part of the zonas block.
   */
  agroZonasFill: '#FCD34D',
  /**
   * Per-zone agroforestal colors. The consorcio zone has EXACTLY 3 systems,
   * each identified by a distinct `leyenda` property. Palette redesign moved
   * these from cool cyan/teal/sky (indistinguishable from each other) to 3
   * warm hues with strong visual separation:
   *
   *   - Río Tercero Este   → amber-300   (#FCD34D — pale warm yellow)
   *   - Río Carcarañá      → orange-500  (#F97316 — punchy orange)
   *   - Arroyo Tortugas    → amber-700   (#B45309 — deep amber/brown)
   *
   * All three sit in the warm family so the layer still reads as a cohesive
   * "zonas agroforestales" block but the 3 systems are now distinguishable
   * at a glance without clicking each polygon.
   */
  agroZonaRioTercero: '#FCD34D',
  agroZonaCarcarana: '#F97316',
  agroZonaTortugas: '#B45309',
  /** Shared outline for all 3 zonas — amber-700, darker than any of the fills. */
  agroZonasLine: '#B45309',
  /**
   * Porcentaje forestación obligatoria — categorized into 3 tiers by
   * `forest_obligatoria` (%). Real zone data ranges 2.1–2.88%, not the
   * provincial 2–5% band, so a linear gradient is indistinguishable. The
   * buckets track the two dominant peaks (2.10 and 2.60) observed on the
   * 1,222 features of the layer.
   *
   *   - Baja  (≤ 2.30%)   — violet-100  (#EDE9FE)
   *   - Media (2.31–2.60%) — violet-500 (#8B5CF6)
   *   - Alta  (≥ 2.61%)   — violet-900  (#4C1D95)
   *
   * Stops jump 100 → 500 → 900 (not 300/400/600) so the 3 tiers have MUCH
   * stronger contrast inside the gradient — the old violet-300/400/600 set
   * collapsed into a single tone on real zone data.
   *
   * Keys map 1:1 to the legend chips in `LeyendaPanel` — single source of
   * truth for the MapLibre `step` paint expression.
   */
  porcentajeForestacionBaja: '#EDE9FE',
  porcentajeForestacionMedia: '#8B5CF6',
  porcentajeForestacionAlta: '#4C1D95',
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

/** Agro-aceptada line — blue-800 outline (darker than the blue-600 fill). */
export function buildAgroAceptadaLinePaint(): LinePaint {
  return {
    'line-color': PILAR_VERDE_COLORS.agroAceptadaLine,
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

/** Agro-presentada line — red-800 outline (darker than the red-600 fill). */
export function buildAgroPresentadaLinePaint(): LinePaint {
  return {
    'line-color': PILAR_VERDE_COLORS.agroPresentadaLine,
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
    // Opacity raised 0.20 → 0.30 after the cool→warm palette swap: pale warm
    // hues (amber-300) looked washed out at 0.20 and the 3 systems need to
    // stay distinguishable when layered over soil/catastro.
    'fill-opacity': 0.3,
  };
}

/** Agro zonas line — thin amber-700 outline, darker than any of the 3 fills. */
export function buildAgroZonasLinePaint(): LinePaint {
  return {
    'line-color': PILAR_VERDE_COLORS.agroZonasLine,
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
