/**
 * roadFlowLayers — paint specs and kind filter for the ranked road crossings
 * (flujo-caminos, design D6).
 *
 * Both kinds render as MapLibre `circle` layers. A `symbol` layer was rejected:
 * `OPACITY_PROP` enumerates exactly `{fill, line, raster, circle}`
 * (`layerRenderRegistry.ts:37-44`) and `symbol` opacity is split across
 * `icon-opacity` / `text-opacity` — it is not one property at all, so the
 * registry has nothing to drive. Drawing a square is not worth widening a union
 * consumed across the whole render pipeline.
 *
 * ⚠️ DISTINCTION IS NOT CARRIED BY COLOUR ⚠️
 * A different fill colour fails for the ~8 % of male operators with a
 * colour-vision deficiency, and fails again on a phone screen in direct sun —
 * which is the actual usage condition. The two kinds are therefore separated on
 * THREE non-chromatic channels at once:
 *
 *   1. `circle-stroke-width` — 1 (flujo natural) vs 3 (canal).
 *   2. `circle-opacity`      — a near-solid disc vs a hollow RING (0.15 fill
 *                              under a heavy stroke). A texture difference.
 *   3. `circle-radius`       — graduated by rank vs a fixed size.
 *
 * Low confidence is likewise non-chromatic: `circle-stroke-opacity` drops for a
 * `confianza='baja'` point (a circle cannot take a true dash, so the reduced
 * stroke is the available texture channel). The point is still drawn and still
 * ranked — marking is not demotion.
 *
 * `tests/unit/roadFlowLayers.test.ts` FAILS if the only difference between the
 * two specs is `circle-color` / `circle-stroke-color`. That is the test that
 * stops a later "let's just tweak the palette".
 *
 * ⚠️ MIRROR CONTRACT ⚠️ the `circle-opacity` literals below are mirrored as
 * `defaultOpacity` in `layerRenderRegistry.ts`. Change one, change the other.
 */

import type { ExpressionSpecification, FilterSpecification } from 'maplibre-gl';

import { ROAD_FLOW_KINDS, type RoadFlowKind } from '../../lib/api/roadFlow';
import { SOURCE_IDS } from './map2dConfig';

/** The two MapLibre layer ids owned by the single `road_flow` registry entry. */
export const ROAD_FLOW_LAYER_IDS = {
  FLUJO: `${SOURCE_IDS.ROAD_FLOW}-flujo`,
  CANAL: `${SOURCE_IDS.ROAD_FLOW}-canal`,
} as const;

export type RoadFlowLayerId = (typeof ROAD_FLOW_LAYER_IDS)[keyof typeof ROAD_FLOW_LAYER_IDS];

/**
 * Hard floor, in px, for EITHER kind's radius. The graduated `flujo_natural`
 * scale must not be able to shrink a low-ranked point into a dot
 * indistinguishable from a canal marker.
 */
export const ROAD_FLOW_MIN_RADIUS_PX = 5;

/** Radius of the top-ranked `flujo_natural` point. */
export const ROAD_FLOW_MAX_RADIUS_PX = 13;

/** Fixed radius of a `canal` candidate — it carries no rank, so it has no scale. */
export const ROAD_FLOW_CANAL_RADIUS_PX = 8;

/** Mirrored as `defaultOpacity` in the registry — see MIRROR CONTRACT above. */
export const ROAD_FLOW_FLUJO_FILL_OPACITY = 0.85;
/** The RING: a nearly hollow disc under a heavy stroke. Mirrored in the registry. */
export const ROAD_FLOW_CANAL_FILL_OPACITY = 0.15;

/** Stroke opacity of a low-confidence point vs a confident one (texture, not hue). */
export const ROAD_FLOW_BAJA_STROKE_OPACITY = 0.4;
export const ROAD_FLOW_ALTA_STROKE_OPACITY = 1;

/**
 * Stroke opacity keyed on `confianza`. Applied to BOTH kinds: a collinear canal
 * overlap carries `confianza='baja'` too, and a value the operator cannot see is
 * a value that does not exist.
 */
function buildConfianzaStrokeOpacity(): ExpressionSpecification {
  return [
    'case',
    ['==', ['get', 'confianza'], 'baja'],
    ROAD_FLOW_BAJA_STROKE_OPACITY,
    ROAD_FLOW_ALTA_STROKE_OPACITY,
  ];
}

/**
 * Radius graduated by `orden_ranking`, rank 1 largest.
 *
 * The floor is STRUCTURAL: the whole interpolation sits inside
 * `['max', ROAD_FLOW_MIN_RADIUS_PX, …]`, so no rank, no missing property and no
 * future stop edit can produce a radius below the floor. A test that merely
 * sampled a few ranks would prove nothing about the ones it did not sample.
 */
export function buildRoadFlowFlujoRadius(totalFlujoNatural: number): ExpressionSpecification {
  // Two ascending stops are required; a run with 0 or 1 ranked points still has
  // to produce a valid interpolation.
  const lastRank = Math.max(totalFlujoNatural, 2);
  return [
    'max',
    ROAD_FLOW_MIN_RADIUS_PX,
    [
      'interpolate',
      ['linear'],
      ['coalesce', ['get', 'orden_ranking'], lastRank],
      1,
      ROAD_FLOW_MAX_RADIUS_PX,
      lastRank,
      ROAD_FLOW_MIN_RADIUS_PX + 1,
    ],
  ];
}

/** Paint for the ranked natural-drainage crossings. */
export function buildRoadFlowFlujoPaint(totalFlujoNatural: number) {
  return {
    'circle-radius': buildRoadFlowFlujoRadius(totalFlujoNatural),
    'circle-color': '#1565C0',
    'circle-opacity': ROAD_FLOW_FLUJO_FILL_OPACITY,
    'circle-stroke-width': 1,
    'circle-stroke-color': '#0D47A1',
    'circle-stroke-opacity': buildConfianzaStrokeOpacity(),
  } as const;
}

/** Paint for the unranked canal culvert/bridge candidates — the ring treatment. */
export function buildRoadFlowCanalPaint() {
  return {
    'circle-radius': ROAD_FLOW_CANAL_RADIUS_PX,
    'circle-color': '#00838F',
    'circle-opacity': ROAD_FLOW_CANAL_FILL_OPACITY,
    'circle-stroke-width': 3,
    'circle-stroke-color': '#006064',
    'circle-stroke-opacity': buildConfianzaStrokeOpacity(),
  } as const;
}

/**
 * The `tipo` value a HIDDEN layer filters on: no feature carries it, so the
 * layer draws nothing while staying mounted. A sentinel rather than a removed
 * layer, so re-showing a kind costs no remount and the registry never observes
 * a missing id.
 */
export const ROAD_FLOW_NO_KIND_SENTINEL = '__ningun_tipo__';

/**
 * The per-layer `tipo` filter. Each ml layer is pinned to its own kind, so one
 * shared source feeds both without either drawing the other's points.
 */
export function buildRoadFlowTipoFilter(
  kind: RoadFlowKind | typeof ROAD_FLOW_NO_KIND_SENTINEL
): ExpressionSpecification {
  return ['==', ['get', 'tipo'], kind];
}

/** Which kinds the panel currently shows. Both true is the mounted default. */
export interface RoadFlowKindVisibility {
  readonly flujo_natural: boolean;
  readonly canal: boolean;
}

export const ROAD_FLOW_ALL_KINDS_VISIBLE: RoadFlowKindVisibility = {
  flujo_natural: true,
  canal: true,
};

/**
 * Minimal MapLibre surface the kind filter touches — keeps the tests light.
 *
 * `setFilter` is typed against MapLibre's own `FilterSpecification` rather than
 * `unknown`: a looser parameter type here would make the real `maplibregl.Map`
 * fail to satisfy this interface (contravariance), and the fix for that is a
 * cast at the call site — which is exactly the place a bad filter would then go
 * unnoticed. Returning `unknown` absorbs the real method's fluent `Map` return.
 */
export interface RoadFlowFilterApi {
  getLayer: (id: string) => unknown;
  setFilter: (id: string, filter?: FilterSpecification | null) => unknown;
}

/**
 * Narrow the rendered set to the selected kinds (task 4.10).
 *
 * Implemented with `setFilter` on the two ml layers — NOT with a second
 * registry id, and NOT by unmounting a layer. Hiding one kind therefore cannot
 * disturb the other, and the single `road_flow` registry entry stays untouched,
 * which is what keeps the opacity/order controls driving both together.
 *
 * A hidden kind gets a filter that matches nothing rather than a removed layer:
 * a layer that survives the toggle can be re-shown without a remount, and the
 * registry never observes a missing id.
 */
export function applyRoadFlowKindFilter(
  map: RoadFlowFilterApi,
  visibility: RoadFlowKindVisibility
): void {
  const pairs = [
    [ROAD_FLOW_LAYER_IDS.FLUJO, ROAD_FLOW_KINDS.FLUJO_NATURAL, visibility.flujo_natural],
    [ROAD_FLOW_LAYER_IDS.CANAL, ROAD_FLOW_KINDS.CANAL, visibility.canal],
  ] as const;

  for (const [layerId, kind, shown] of pairs) {
    if (!map.getLayer(layerId)) continue;
    map.setFilter(
      layerId,
      shown ? buildRoadFlowTipoFilter(kind) : buildRoadFlowTipoFilter(ROAD_FLOW_NO_KIND_SENTINEL)
    );
  }
}
