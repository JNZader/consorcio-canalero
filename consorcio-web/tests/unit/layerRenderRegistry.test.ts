/**
 * layerRenderRegistry.test.ts
 *
 * Locks the UI-id → MapLibre-layer registry that powers per-layer opacity /
 * order controls (map-redesign Fase 3).
 *
 * The most important guarantees:
 *   1. Every renderable UI vector layer id has a registry entry (a newly-added
 *      toggleable layer fails this suite until it is registered).
 *   2. `applyLayerOpacity` NEVER mutates paint for an absent / ===1 multiplier
 *      (byte-identical default rendering).
 *   3. `applyLayerOrder` is a no-op on an empty order list.
 */

import { describe, expect, it, vi } from 'vitest';

import {
  DEFAULT_LAYER_ORDER,
  LAYER_RENDER_REGISTRY,
  OPACITY_PROP,
  RENDERABLE_UI_LAYER_IDS,
  applyLayerOpacity,
  applyLayerOrder,
  type MapLayerImperativeApi,
} from '../../src/components/map2d/layerRenderRegistry';
import { CATASTRO_FILL_OPACITY, SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import { CATASTRO_FILL_OPACITY as CATASTRO_FILL_OPACITY_FROM_PAINT } from '../../src/components/map2d/mapLayerEffectHelpers';

const VALID_OPACITY_PROPS = new Set(Object.values(OPACITY_PROP));

function makeMap(overrides?: Partial<MapLayerImperativeApi>): {
  map: MapLayerImperativeApi;
  setPaintProperty: ReturnType<typeof vi.fn>;
  moveLayer: ReturnType<typeof vi.fn>;
} {
  const setPaintProperty = vi.fn();
  const moveLayer = vi.fn();
  const map: MapLayerImperativeApi = {
    // Default: every layer is "mounted".
    getLayer: (_id: string) => ({}),
    setPaintProperty,
    moveLayer,
    ...overrides,
  };
  return { map, setPaintProperty, moveLayer };
}

describe('layerRenderRegistry — coverage', () => {
  it('every renderable UI layer id has a registry entry', () => {
    for (const id of RENDERABLE_UI_LAYER_IDS) {
      expect(LAYER_RENDER_REGISTRY[id], `missing registry entry for ${id}`).toBeDefined();
      expect(LAYER_RENDER_REGISTRY[id].mlLayers.length).toBeGreaterThan(0);
    }
  });

  it('catastro-fill defaultOpacity IS the shared paint constant (no mirror drift)', () => {
    // Regression guard (R4-001): the registry used to hard-code 0.08 while the
    // paint used 0.12. `applyLayerOpacity` multiplies `defaultOpacity` by ANY
    // present multiplier, so a persisted catastro opacity stomped the fill back
    // to an effectively invisible value.
    const entry = LAYER_RENDER_REGISTRY.catastro.mlLayers.find(
      (layer) => layer.id === `${SOURCE_IDS.CATASTRO}-fill`
    );
    expect(entry).toBeDefined();
    expect(entry?.defaultOpacity).toBe(CATASTRO_FILL_OPACITY);
    // …and the paint module re-exports the very same binding.
    expect(CATASTRO_FILL_OPACITY_FROM_PAINT).toBe(CATASTRO_FILL_OPACITY);
  });

  it('every registry key is a declared renderable UI layer id (no strays)', () => {
    const declared = new Set<string>(RENDERABLE_UI_LAYER_IDS);
    for (const key of Object.keys(LAYER_RENDER_REGISTRY)) {
      expect(declared.has(key), `registry key ${key} not in RENDERABLE_UI_LAYER_IDS`).toBe(true);
    }
  });

  it('registers precip_normal as the CHIRPS raster layer', () => {
    expect(LAYER_RENDER_REGISTRY.precip_normal).toMatchObject({
      mlLayers: [
        {
          id: 'map2d-precip-normal-layer',
          opacityProp: 'raster-opacity',
          defaultOpacity: 0.55,
        },
      ],
      family: 'precipitation',
      supportsDate: false,
    });
  });

  it('every ml layer declares a valid opacity prop and a 0..1 default', () => {
    for (const id of RENDERABLE_UI_LAYER_IDS) {
      for (const ml of LAYER_RENDER_REGISTRY[id].mlLayers) {
        expect(VALID_OPACITY_PROPS.has(ml.opacityProp)).toBe(true);
        expect(ml.defaultOpacity).toBeGreaterThanOrEqual(0);
        expect(ml.defaultOpacity).toBeLessThanOrEqual(1);
        expect(typeof ml.id).toBe('string');
        expect(ml.id.length).toBeGreaterThan(0);
      }
    }
  });

  it('waterways explodes into 5 per-file line layers', () => {
    const waterways = LAYER_RENDER_REGISTRY.waterways.mlLayers;
    expect(waterways).toHaveLength(5);
    for (const ml of waterways) {
      expect(ml.opacityProp).toBe(OPACITY_PROP.line);
      expect(ml.defaultOpacity).toBe(0.9);
      expect(ml.id.endsWith('-line')).toBe(true);
    }
  });

  it('soil maps to a fill (0.3) + line (0.85) pair — mirrors mapLayerEffectHelpers', () => {
    const soil = LAYER_RENDER_REGISTRY.soil.mlLayers;
    expect(soil).toEqual([
      { id: 'map2d-soil-fill', opacityProp: 'fill-opacity', defaultOpacity: 0.3 },
      { id: 'map2d-soil-line', opacityProp: 'line-opacity', defaultOpacity: 0.85 },
    ]);
  });
});

describe('DEFAULT_LAYER_ORDER', () => {
  it('contains EXACTLY the RENDERABLE_UI_LAYER_IDS set (no missing/extra) — cannot drift', () => {
    expect([...DEFAULT_LAYER_ORDER].sort()).toEqual([...RENDERABLE_UI_LAYER_IDS].sort());
  });

  it('has no duplicate ids', () => {
    expect(new Set(DEFAULT_LAYER_ORDER).size).toBe(DEFAULT_LAYER_ORDER.length);
  });

  it('includes precip_normal exactly once after basins', () => {
    const basinsIndex = DEFAULT_LAYER_ORDER.indexOf('basins');
    expect(DEFAULT_LAYER_ORDER.filter((id) => id === 'precip_normal')).toHaveLength(1);
    expect(DEFAULT_LAYER_ORDER[basinsIndex + 1]).toBe('precip_normal');
  });

  it('lists roads at the bottom and escuelas at the top (documented z-order)', () => {
    expect(DEFAULT_LAYER_ORDER[0]).toBe('roads');
    expect(DEFAULT_LAYER_ORDER.at(-1)).toBe('escuelas');
  });
});

describe('applyLayerOpacity', () => {
  it('is a NO-OP with an empty override map (byte-identical default)', () => {
    const { map, setPaintProperty } = makeMap();
    applyLayerOpacity(map, {});
    expect(setPaintProperty).not.toHaveBeenCalled();
  });

  it('a PRESENT multiplier of exactly 1 RESETS to the hardcoded default (reset-on-clear)', () => {
    // FF-A1: dragging a slider back to 1.0 must restore the default, not leave
    // the layer stuck at a previously-lowered value. `default * 1` === default,
    // so this is numerically byte-identical to the untouched paint.
    const { map, setPaintProperty } = makeMap();
    applyLayerOpacity(map, { soil: 1 });
    expect(setPaintProperty).toHaveBeenCalledWith('map2d-soil-fill', 'fill-opacity', 0.3);
    expect(setPaintProperty).toHaveBeenCalledWith('map2d-soil-line', 'line-opacity', 0.85);
  });

  it('applies default * multiplier for each ml layer of an overridden UI id', () => {
    const { map, setPaintProperty } = makeMap();
    applyLayerOpacity(map, { soil: 0.5 });
    // soil → fill(0.3) + line(0.85)
    expect(setPaintProperty).toHaveBeenCalledWith('map2d-soil-fill', 'fill-opacity', 0.15);
    expect(setPaintProperty).toHaveBeenCalledWith('map2d-soil-line', 'line-opacity', 0.425);
    expect(setPaintProperty).toHaveBeenCalledTimes(2);
  });

  it('applies to ALL 5 waterway ml layers when waterways is overridden', () => {
    const { map, setPaintProperty } = makeMap();
    applyLayerOpacity(map, { waterways: 0.5 });
    expect(setPaintProperty).toHaveBeenCalledTimes(5);
    for (const call of setPaintProperty.mock.calls) {
      expect(call[1]).toBe('line-opacity');
      expect(call[2]).toBeCloseTo(0.45);
    }
  });

  it('clamps out-of-range multipliers to 0..1', () => {
    const { map, setPaintProperty } = makeMap();
    applyLayerOpacity(map, { roads: 5 });
    // clamped to 1 → 0.9 * 1
    expect(setPaintProperty).toHaveBeenCalledWith('map2d-roads-line', 'line-opacity', 0.9);
  });

  it('skips ml layers that are not yet mounted (getLayer undefined)', () => {
    const { map, setPaintProperty } = makeMap({ getLayer: () => undefined });
    applyLayerOpacity(map, { soil: 0.5 });
    expect(setPaintProperty).not.toHaveBeenCalled();
  });

  it('ignores unknown UI ids', () => {
    const { map, setPaintProperty } = makeMap();
    applyLayerOpacity(map, { totally_unknown_layer: 0.5 });
    expect(setPaintProperty).not.toHaveBeenCalled();
  });

  it('is null-safe: undefined override map does not throw and makes zero calls (FF-A2)', () => {
    const { map, setPaintProperty } = makeMap();
    expect(() =>
      applyLayerOpacity(map, undefined as unknown as Record<string, number>)
    ).not.toThrow();
    expect(setPaintProperty).not.toHaveBeenCalled();
  });
});

describe('applyLayerOrder', () => {
  it('is a NO-OP on an empty order list (today ordering untouched)', () => {
    const { map, moveLayer } = makeMap();
    applyLayerOrder(map, []);
    expect(moveLayer).not.toHaveBeenCalled();
  });

  it('hoists each UI id ml-layer group in list order', () => {
    const { map, moveLayer } = makeMap();
    applyLayerOrder(map, ['waterways', 'roads']);
    // waterways = 5 line layers, roads = 1 → 6 moveLayer calls
    expect(moveLayer).toHaveBeenCalledTimes(6);
    // roads (last in list) is hoisted last → ends on top
    expect(moveLayer.mock.calls.at(-1)?.[0]).toBe('map2d-roads-line');
  });

  it('swallows moveLayer throws (racing style edits)', () => {
    const { map } = makeMap({
      moveLayer: () => {
        throw new Error('layer gone');
      },
    });
    expect(() => applyLayerOrder(map, ['roads'])).not.toThrow();
  });

  it('skips unmounted layers and unknown ids', () => {
    const { map, moveLayer } = makeMap({ getLayer: () => undefined });
    applyLayerOrder(map, ['roads', 'unknown']);
    expect(moveLayer).not.toHaveBeenCalled();
  });

  it('is null-safe: undefined order list does not throw and makes zero calls (FF-A2)', () => {
    const { map, moveLayer } = makeMap();
    expect(() => applyLayerOrder(map, undefined as unknown as readonly string[])).not.toThrow();
    expect(moveLayer).not.toHaveBeenCalled();
  });
});
