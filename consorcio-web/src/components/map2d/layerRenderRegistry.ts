/**
 * layerRenderRegistry
 *
 * Single source of truth mapping each USER-FACING (UI) vector layer id — the
 * ids used in `vectorVisibility` / the layer-controls panel — to the concrete
 * MapLibre layer id(s) it renders as, together with each ml-layer's opacity
 * paint property and its HARDCODED DEFAULT opacity value.
 *
 * WHY this exists
 * ---------------
 * A single UI item (e.g. `soil`) renders as MULTIPLE MapLibre layers (a fill
 * layer + an outline line layer). `canales_*` and `waterways` explode into
 * several ml layers. Per-layer opacity/order controls (map-redesign Fase 3)
 * need to translate ONE UI id → its group of ml ids to apply
 * `setPaintProperty` / `moveLayer` imperatively.
 *
 * ⚠️ MIRROR CONTRACT ⚠️
 * The `defaultOpacity` literals below MIRROR the hardcoded paint values in
 * `mapLayerEffectHelpers.ts`, `pilarVerdeLayers.ts`, `canalesLayers.ts`,
 * `escuelasLayers.ts` and `mapRasterOverlayHelpers.ts`. If you change an
 * opacity literal in any of those files, update it HERE too — otherwise a
 * user opacity override multiplies the wrong base and the default rendering
 * silently drifts. `tests/unit/layerRenderRegistry.test.ts` locks the set of
 * covered UI ids so a newly-added layer fails the suite until it is
 * registered here.
 *
 * The applied value is `defaultOpacity * multiplier` where `multiplier` is the
 * user's 0..1 slider value. A multiplier of exactly 1 (or absent) is NEVER
 * applied — the untouched default MUST stay byte-identical to today.
 */

import { buildWaterwayLayerConfigs } from './map2dConfig';
import { SOURCE_IDS } from './map2dConfig';
import { ESCUELAS_LAYER_ID } from './escuelasLayers';

/** MapLibre opacity paint property, keyed by layer geometry type. */
export const OPACITY_PROP = {
  fill: 'fill-opacity',
  line: 'line-opacity',
  raster: 'raster-opacity',
  circle: 'circle-opacity',
} as const;

export type OpacityProp = (typeof OPACITY_PROP)[keyof typeof OPACITY_PROP];

/** One concrete MapLibre layer rendered by a UI layer item. */
export interface MlLayerRender {
  /** MapLibre layer id (the `id` passed to `map.addLayer`). */
  readonly id: string;
  /** Which opacity paint property this ml layer exposes. */
  readonly opacityProp: OpacityProp;
  /**
   * The hardcoded default opacity baked into the paint factory. MIRRORS the
   * literal in the corresponding sync helper — see MIRROR CONTRACT above.
   */
  readonly defaultOpacity: number;
}

export interface LayerRenderEntry {
  readonly mlLayers: readonly MlLayerRender[];
}

/**
 * The set of UI vector layer ids that participate in per-layer opacity/order
 * controls. This tuple is the authoritative coverage list — the registry unit
 * test asserts every id here has an entry AND every registry key is listed
 * here, so adding a new toggleable layer without registering it fails CI.
 *
 * Deliberately EXCLUDED (not user-controllable via opacity/order sliders):
 *   - `zona` (always-on GEE outline), `ign_historico` (raster overlay handled
 *     by the raster-opacity pipeline), `cuencas` / `hydraulic_risk` (not
 *     rendered as vector layers in map2d), and the `waterways_*` sub-filters
 *     (internal — the parent `waterways` id owns all 5 ml layers).
 */
export const RENDERABLE_UI_LAYER_IDS = [
  'basins',
  'approved_zones',
  'waterways',
  'roads',
  'soil',
  'catastro',
  'puntos_conflicto',
  'pilar_verde_bpa_historico',
  'pilar_verde_agro_aceptada',
  'pilar_verde_agro_presentada',
  'pilar_verde_agro_zonas',
  'pilar_verde_porcentaje_forestacion',
  'canales_relevados',
  'canales_propuestos',
  'escuelas',
] as const;

export type RenderableUiLayerId = (typeof RENDERABLE_UI_LAYER_IDS)[number];

/**
 * The 5 waterway per-file line layer ids. Generated from the SAME source of
 * truth (`buildWaterwayLayerConfigs`) the sync helper uses, so the id set can
 * never drift. Each waterway line layer paints `line-opacity: 0.9`
 * (`mapLayerEffectHelpers.ts::syncWaterwayLayers`).
 */
const WATERWAY_ML_LAYERS: readonly MlLayerRender[] = buildWaterwayLayerConfigs([]).map((cfg) => ({
  id: `${cfg.id}-line`,
  opacityProp: OPACITY_PROP.line,
  defaultOpacity: 0.9,
}));

/**
 * UI id → ml-layer render group.
 *
 * `defaultOpacity` values are copied verbatim from:
 *   - basins            → mapLayerEffectHelpers.ts:193 (fill 0.08) / :202 (line 0.95)
 *   - approved_zones    → mapLayerEffectHelpers.ts:244 (fill 0.18) / :257 (line 0.95)
 *   - waterways         → mapLayerEffectHelpers.ts:62  (line 0.9, ×5 files)
 *   - roads             → mapLayerEffectHelpers.ts:162 (line 0.9)
 *   - soil              → mapLayerEffectHelpers.ts:86  (fill 0.3)  / :95  (line 0.85)
 *   - catastro          → mapLayerEffectHelpers.ts:119 (fill 0.08) / :129 (line 0.85)
 *   - puntos_conflicto  → mapRasterOverlayHelpers.ts:274 (circle 0.85 = MARTIN_SOURCES.puntos_conflicto.style.fillOpacity)
 *   - pilar_verde_*     → pilarVerdeLayers.ts paint factories
 *   - canales_*         → canalesLayers.ts (line 0.95 both)
 *   - escuelas          → escuelasLayers.ts buildEscuelasCirclePaint has NO
 *                         circle-opacity → MapLibre default is 1.0
 */
export const LAYER_RENDER_REGISTRY: Readonly<Record<RenderableUiLayerId, LayerRenderEntry>> = {
  basins: {
    mlLayers: [
      { id: `${SOURCE_IDS.BASINS}-fill`, opacityProp: OPACITY_PROP.fill, defaultOpacity: 0.08 },
      { id: `${SOURCE_IDS.BASINS}-line`, opacityProp: OPACITY_PROP.line, defaultOpacity: 0.95 },
    ],
  },
  approved_zones: {
    mlLayers: [
      {
        id: `${SOURCE_IDS.APPROVED_ZONES}-fill`,
        opacityProp: OPACITY_PROP.fill,
        defaultOpacity: 0.18,
      },
      {
        id: `${SOURCE_IDS.APPROVED_ZONES}-line`,
        opacityProp: OPACITY_PROP.line,
        defaultOpacity: 0.95,
      },
    ],
  },
  waterways: {
    mlLayers: WATERWAY_ML_LAYERS,
  },
  roads: {
    mlLayers: [
      { id: `${SOURCE_IDS.ROADS}-line`, opacityProp: OPACITY_PROP.line, defaultOpacity: 0.9 },
    ],
  },
  soil: {
    mlLayers: [
      { id: `${SOURCE_IDS.SOIL}-fill`, opacityProp: OPACITY_PROP.fill, defaultOpacity: 0.3 },
      { id: `${SOURCE_IDS.SOIL}-line`, opacityProp: OPACITY_PROP.line, defaultOpacity: 0.85 },
    ],
  },
  catastro: {
    mlLayers: [
      { id: `${SOURCE_IDS.CATASTRO}-fill`, opacityProp: OPACITY_PROP.fill, defaultOpacity: 0.08 },
      { id: `${SOURCE_IDS.CATASTRO}-line`, opacityProp: OPACITY_PROP.line, defaultOpacity: 0.85 },
    ],
  },
  puntos_conflicto: {
    mlLayers: [
      {
        id: `${SOURCE_IDS.MARTIN_PUNTOS}-circle`,
        opacityProp: OPACITY_PROP.circle,
        defaultOpacity: 0.85,
      },
    ],
  },
  pilar_verde_bpa_historico: {
    mlLayers: [
      {
        id: `${SOURCE_IDS.PILAR_VERDE_BPA_HISTORICO}-fill`,
        opacityProp: OPACITY_PROP.fill,
        defaultOpacity: 0.45,
      },
      {
        id: `${SOURCE_IDS.PILAR_VERDE_BPA_HISTORICO}-line`,
        opacityProp: OPACITY_PROP.line,
        defaultOpacity: 0.8,
      },
    ],
  },
  pilar_verde_agro_aceptada: {
    mlLayers: [
      {
        id: `${SOURCE_IDS.PILAR_VERDE_AGRO_ACEPTADA}-fill`,
        opacityProp: OPACITY_PROP.fill,
        defaultOpacity: 0.3,
      },
      {
        id: `${SOURCE_IDS.PILAR_VERDE_AGRO_ACEPTADA}-line`,
        opacityProp: OPACITY_PROP.line,
        defaultOpacity: 0.85,
      },
    ],
  },
  pilar_verde_agro_presentada: {
    mlLayers: [
      {
        id: `${SOURCE_IDS.PILAR_VERDE_AGRO_PRESENTADA}-fill`,
        opacityProp: OPACITY_PROP.fill,
        defaultOpacity: 0.3,
      },
      {
        id: `${SOURCE_IDS.PILAR_VERDE_AGRO_PRESENTADA}-line`,
        opacityProp: OPACITY_PROP.line,
        defaultOpacity: 0.85,
      },
    ],
  },
  pilar_verde_agro_zonas: {
    mlLayers: [
      {
        id: `${SOURCE_IDS.PILAR_VERDE_AGRO_ZONAS}-fill`,
        opacityProp: OPACITY_PROP.fill,
        defaultOpacity: 0.45,
      },
      {
        id: `${SOURCE_IDS.PILAR_VERDE_AGRO_ZONAS}-line`,
        opacityProp: OPACITY_PROP.line,
        defaultOpacity: 0.75,
      },
    ],
  },
  pilar_verde_porcentaje_forestacion: {
    // No line layer by design — low-contrast context fill only.
    mlLayers: [
      {
        id: `${SOURCE_IDS.PILAR_VERDE_PORCENTAJE_FORESTACION}-fill`,
        opacityProp: OPACITY_PROP.fill,
        defaultOpacity: 0.3,
      },
    ],
  },
  canales_relevados: {
    mlLayers: [
      {
        id: `${SOURCE_IDS.CANALES_RELEVADOS}-line`,
        opacityProp: OPACITY_PROP.line,
        defaultOpacity: 0.95,
      },
    ],
  },
  canales_propuestos: {
    mlLayers: [
      {
        id: `${SOURCE_IDS.CANALES_PROPUESTOS}-line`,
        opacityProp: OPACITY_PROP.line,
        defaultOpacity: 0.95,
      },
    ],
  },
  escuelas: {
    // buildEscuelasCirclePaint sets no circle-opacity → MapLibre default 1.0.
    mlLayers: [{ id: ESCUELAS_LAYER_ID, opacityProp: OPACITY_PROP.circle, defaultOpacity: 1 }],
  },
};

/** Minimal MapLibre surface the apply helpers touch — keeps tests light. */
export interface MapLayerImperativeApi {
  getLayer: (id: string) => unknown;
  setPaintProperty: (id: string, prop: string, value: unknown) => void;
  moveLayer: (id: string, beforeId?: string) => void;
}

/**
 * Apply per-layer opacity overrides IMPERATIVELY.
 *
 * Guarantees:
 *   - Byte-identical default: an EMPTY override map (`{}`) has no entries, so
 *     nothing is applied and the default paint is untouched.
 *   - Reset-on-clear: a key that is PRESENT with value `1` (user dragged a
 *     slider back to 1.0) DOES call `setPaintProperty(mlId, prop,
 *     defaultOpacity * 1)` — i.e. writes the exact hardcoded default, restoring
 *     it. We only skip a key whose value is nullish (absent-but-listed). This
 *     is why the guard is `== null` and NOT `=== 1`: skipping `=== 1` would
 *     leave a previously-lowered layer stuck at the old multiplied value.
 *   - Missing ml layers (not yet mounted) are skipped via `getLayer`, mirroring
 *     the moveLayer try/catch guards in `mapLayerEffectHelpers.ts`.
 */
export function applyLayerOpacity(
  map: MapLayerImperativeApi,
  opacityByLayer: Record<string, number> | undefined
): void {
  for (const [uiId, multiplier] of Object.entries(opacityByLayer ?? {})) {
    // Only skip an absent/nullish value — a present `1` resets to default.
    if (multiplier == null) continue;
    const entry = LAYER_RENDER_REGISTRY[uiId as RenderableUiLayerId];
    if (!entry) continue;
    const clamped = Math.min(1, Math.max(0, multiplier));
    for (const ml of entry.mlLayers) {
      if (!map.getLayer(ml.id)) continue;
      map.setPaintProperty(ml.id, ml.opacityProp, ml.defaultOpacity * clamped);
    }
  }
}

/**
 * Apply per-layer render ORDER IMPERATIVELY.
 *
 * `orderByLayer` is a bottom → top list of UI ids. We iterate it in order and
 * `moveLayer(mlId)` (no beforeId) to hoist each group to the TOP — so the last
 * UI id in the list ends up drawn on top, matching the `PILAR_VERDE_Z_ORDER`
 * hoisting convention. Within a group the ml layers keep their registry order
 * (fill below line). EMPTY list → no-op, so today's ordering is untouched.
 * moveLayer is wrapped in try/catch (layers may not exist yet).
 *
 * ⚠️ CONTRACT — `orderByLayer` MUST be the COMPLETE bottom→top set of the
 * reorderable UI layers, never a partial subset. The algorithm hoists each id
 * to the ABSOLUTE top in sequence, so a partial list would lift its members
 * above unrelated layers that were intentionally left out. The Tanda B reorder
 * UI must therefore always write the full ordered set (e.g. seed it from the
 * current effective order, then move items within it) — not just the ids the
 * user dragged.
 */
export function applyLayerOrder(
  map: MapLayerImperativeApi,
  orderByLayer: readonly string[] | undefined
): void {
  const order = orderByLayer ?? [];
  if (order.length === 0) return;
  for (const uiId of order) {
    const entry = LAYER_RENDER_REGISTRY[uiId as RenderableUiLayerId];
    if (!entry) continue;
    for (const ml of entry.mlLayers) {
      if (!map.getLayer(ml.id)) continue;
      try {
        map.moveLayer(ml.id);
      } catch {
        // moveLayer can race with concurrent style edits — safe to ignore,
        // next sync pass retries.
      }
    }
  }
}
