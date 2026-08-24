/**
 * roadFlowLayers.test.ts — flujo-caminos S4, tasks 4.3 / 4.10 / 4.15.
 *
 * The ACCESSIBILITY CONTRACT of the two road-crossing circle layers, plus the
 * panel-level kind filter and the default-hidden rollout guard.
 *
 * The load-bearing assertion is the negative one: if the ONLY difference
 * between the two paint specs is `circle-color` / `circle-stroke-color`, this
 * suite FAILS. That is what stops a later "let's just tweak the palette" from
 * quietly deleting the non-chromatic distinction the ~8 % of operators with a
 * colour-vision deficiency — and everybody reading a phone in direct sun —
 * actually depend on.
 */

import { describe, expect, it, vi } from 'vitest';

import {
  DEFAULT_LAYER_ORDER,
  LAYER_RENDER_REGISTRY,
} from '../../src/components/map2d/layerRenderRegistry';
import {
  ROAD_FLOW_ALTA_STROKE_OPACITY,
  ROAD_FLOW_BAJA_STROKE_OPACITY,
  ROAD_FLOW_LAYER_IDS,
  ROAD_FLOW_MIN_RADIUS_PX,
  type RoadFlowFilterApi,
  applyRoadFlowKindFilter,
  buildRoadFlowCanalPaint,
  buildRoadFlowFlujoPaint,
  buildRoadFlowFlujoRadius,
} from '../../src/components/map2d/roadFlowLayers';
import { ROAD_FLOW_KINDS } from '../../src/lib/api/roadFlow';
import { useMapLayerSyncStore } from '../../src/stores/mapLayerSyncStore';

/** Paint keys that carry HUE. A difference in one of these proves nothing. */
const COLOUR_KEYS = new Set(['circle-color', 'circle-stroke-color']);

function differingKeys(a: Record<string, unknown>, b: Record<string, unknown>): string[] {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  return [...keys].filter((k) => JSON.stringify(a[k]) !== JSON.stringify(b[k]));
}

/**
 * Minimal evaluator for the subset of MapLibre expressions these paints use.
 * Enough to prove the radius floor holds for REAL inputs, not just structurally.
 */
function evaluate(expr: unknown, props: Record<string, unknown>): number {
  if (typeof expr === 'number') return expr;
  if (!Array.isArray(expr)) throw new Error(`unsupported literal: ${JSON.stringify(expr)}`);
  const [op, ...args] = expr as [string, ...unknown[]];
  switch (op) {
    case 'max':
      return Math.max(...args.map((a) => evaluate(a, props)));
    case 'get': {
      const value = props[args[0] as string];
      return typeof value === 'number' ? value : Number.NaN;
    }
    case 'coalesce': {
      for (const arg of args) {
        const value = evaluate(arg, props);
        if (Number.isFinite(value)) return value;
      }
      return Number.NaN;
    }
    case 'interpolate': {
      const [, input, ...stops] = args as [unknown, unknown, ...number[]];
      const x = evaluate(input, props);
      const pairs: Array<[number, number]> = [];
      for (let i = 0; i < stops.length; i += 2) pairs.push([stops[i], stops[i + 1]]);
      if (x <= pairs[0][0]) return pairs[0][1];
      const last = pairs[pairs.length - 1];
      if (x >= last[0]) return last[1];
      for (let i = 0; i < pairs.length - 1; i += 1) {
        const [x0, y0] = pairs[i];
        const [x1, y1] = pairs[i + 1];
        if (x >= x0 && x <= x1) return y0 + ((x - x0) / (x1 - x0)) * (y1 - y0);
      }
      return last[1];
    }
    default:
      throw new Error(`unsupported expression op: ${op}`);
  }
}

describe('roadFlowLayers — the two kinds are distinguished WITHOUT colour', () => {
  const flujo = buildRoadFlowFlujoPaint(12) as unknown as Record<string, unknown>;
  const canal = buildRoadFlowCanalPaint() as unknown as Record<string, unknown>;

  it('differs in circle-stroke-width: 1 (flujo natural) vs 3 (canal)', () => {
    expect(flujo['circle-stroke-width']).toBe(1);
    expect(canal['circle-stroke-width']).toBe(3);
  });

  it('ALSO differs in at least one OTHER non-colour property', () => {
    // The whole point: strip the hue keys AND the stroke width, and there must
    // STILL be a difference left. A palette tweak cannot satisfy this.
    const remaining = differingKeys(flujo, canal).filter(
      (key) => !COLOUR_KEYS.has(key) && key !== 'circle-stroke-width'
    );
    expect(
      remaining.length,
      'the two kinds are separated only by hue and stroke width — the ring/size treatment was removed'
    ).toBeGreaterThan(0);
  });

  it('FAILS when the only difference is colour (the guard proves itself)', () => {
    // A hypothetical "palette-only" pair: identical everywhere except hue.
    const paletteOnlyA = { 'circle-color': '#111111', 'circle-radius': 6 };
    const paletteOnlyB = { 'circle-color': '#222222', 'circle-radius': 6 };
    const nonColour = differingKeys(paletteOnlyA, paletteOnlyB).filter(
      (key) => !COLOUR_KEYS.has(key)
    );
    expect(nonColour).toHaveLength(0);
  });
});

describe('roadFlowLayers — the radius floor', () => {
  it('is STRUCTURAL: the whole scale sits inside max(5, …)', () => {
    const expr = buildRoadFlowFlujoRadius(40) as unknown as unknown[];
    expect(expr[0]).toBe('max');
    expect(expr[1]).toBe(ROAD_FLOW_MIN_RADIUS_PX);
  });

  it('never evaluates below 5 px for ANY rank, missing rank or run size', () => {
    for (const total of [0, 1, 2, 7, 40, 500]) {
      const expr = buildRoadFlowFlujoRadius(total);
      for (const rank of [1, 2, 3, 10, 50, 999, -1]) {
        expect(evaluate(expr, { orden_ranking: rank })).toBeGreaterThanOrEqual(
          ROAD_FLOW_MIN_RADIUS_PX
        );
      }
      // A row with no rank at all (canal features share the source).
      expect(evaluate(expr, {})).toBeGreaterThanOrEqual(ROAD_FLOW_MIN_RADIUS_PX);
    }
  });

  it('the canal kind never evaluates below the floor either', () => {
    const radius = buildRoadFlowCanalPaint()['circle-radius'];
    expect(evaluate(radius, {})).toBeGreaterThanOrEqual(ROAD_FLOW_MIN_RADIUS_PX);
  });

  it('rank 1 is drawn larger than the last rank (the scale means something)', () => {
    const expr = buildRoadFlowFlujoRadius(20);
    expect(evaluate(expr, { orden_ranking: 1 })).toBeGreaterThan(
      evaluate(expr, { orden_ranking: 20 })
    );
  });
});

describe('roadFlowLayers — low confidence is rendered non-chromatically', () => {
  it('a confianza=baja point differs from an alta one on circle-stroke-opacity', () => {
    for (const paint of [buildRoadFlowFlujoPaint(9), buildRoadFlowCanalPaint()]) {
      const expr = paint['circle-stroke-opacity'] as unknown[];
      expect(expr[0]).toBe('case');
      // The keyed property is `confianza`, and the outputs differ.
      expect(JSON.stringify(expr)).toContain('confianza');
      expect(expr).toContain(ROAD_FLOW_BAJA_STROKE_OPACITY);
      expect(expr).toContain(ROAD_FLOW_ALTA_STROKE_OPACITY);
      expect(ROAD_FLOW_BAJA_STROKE_OPACITY).not.toBe(ROAD_FLOW_ALTA_STROKE_OPACITY);
    }
  });

  it('the confidence channel is NOT a colour property', () => {
    const paint = buildRoadFlowFlujoPaint(9) as unknown as Record<string, unknown>;
    // Hue is a plain literal on both layers — confidence cannot be hiding in it.
    for (const key of COLOUR_KEYS) {
      expect(typeof paint[key]).toBe('string');
    }
  });
});

describe('applyRoadFlowKindFilter — the PANEL-level kind filter (task 4.10)', () => {
  function makeMap(overrides?: Partial<RoadFlowFilterApi>) {
    const setFilter = vi.fn();
    const map: RoadFlowFilterApi = {
      getLayer: () => ({}),
      setFilter,
      ...overrides,
    };
    return { map, setFilter };
  }

  it('hiding one kind does not unmount the other and touches no registry entry', () => {
    const { map, setFilter } = makeMap();
    const registryBefore = JSON.stringify(LAYER_RENDER_REGISTRY.road_flow);

    applyRoadFlowKindFilter(map, { flujo_natural: true, canal: false });

    // BOTH layers still receive a filter — neither is removed.
    const touched = setFilter.mock.calls.map((call) => call[0]);
    expect(touched).toContain(ROAD_FLOW_LAYER_IDS.FLUJO);
    expect(touched).toContain(ROAD_FLOW_LAYER_IDS.CANAL);

    // The shown kind keeps its own `tipo` filter…
    const flujoFilter = setFilter.mock.calls.find(
      (call) => call[0] === ROAD_FLOW_LAYER_IDS.FLUJO
    )?.[1];
    expect(JSON.stringify(flujoFilter)).toContain(ROAD_FLOW_KINDS.FLUJO_NATURAL);

    // …and the hidden one gets a filter that matches nothing, not a removal.
    const canalFilter = setFilter.mock.calls.find(
      (call) => call[0] === ROAD_FLOW_LAYER_IDS.CANAL
    )?.[1];
    expect(JSON.stringify(canalFilter)).not.toContain(ROAD_FLOW_KINDS.CANAL);

    expect(JSON.stringify(LAYER_RENDER_REGISTRY.road_flow)).toBe(registryBefore);
  });

  it('shows both kinds when both are selected', () => {
    const { map, setFilter } = makeMap();
    applyRoadFlowKindFilter(map, { flujo_natural: true, canal: true });
    expect(JSON.stringify(setFilter.mock.calls)).toContain(ROAD_FLOW_KINDS.CANAL);
    expect(JSON.stringify(setFilter.mock.calls)).toContain(ROAD_FLOW_KINDS.FLUJO_NATURAL);
  });

  it('skips layers that are not mounted yet', () => {
    const { map, setFilter } = makeMap({ getLayer: () => undefined });
    applyRoadFlowKindFilter(map, { flujo_natural: false, canal: true });
    expect(setFilter).not.toHaveBeenCalled();
  });
});

describe('road_flow rollout guard (task 4.15)', () => {
  it('mounts HIDDEN by default in map2d', () => {
    const visible = useMapLayerSyncStore.getState().map2d.visibleVectors;
    expect(visible).toHaveProperty('road_flow');
    expect(visible.road_flow).toBe(false);
  });

  it('is still a reorderable layer (hidden is not unregistered)', () => {
    expect(DEFAULT_LAYER_ORDER).toContain('road_flow');
  });
});
