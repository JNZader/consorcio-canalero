import { describe, expect, it, vi } from 'vitest';

import { syncWaterwayLayers } from '../../src/components/map2d/mapLayerEffectHelpers';
import { WATERWAY_DEFS } from '../../src/hooks/useWaterways';

function fakeMap() {
  const sources = new Set<string>();
  const layers = new Set<string>();
  const visibility = new Map<string, string>();
  return {
    getSource: (id: string) => (sources.has(id) ? {} : undefined),
    getLayer: (id: string) => (layers.has(id) ? {} : undefined),
    addSource: vi.fn((id: string) => {
      sources.add(id);
    }),
    addLayer: vi.fn((layer: { id: string }, before?: string) => {
      layers.add(layer.id);
      return before;
    }),
    setLayoutProperty: vi.fn((id: string, key: string, value: string) => {
      if (key === 'visibility') visibility.set(id, value);
    }),
    visibility,
  };
}

describe('syncWaterwayLayers CART-05', () => {
  it('adds a casing under every waterway color line', () => {
    const map = fakeMap();
    syncWaterwayLayers(map as never, WATERWAY_DEFS, true);
    const casings = map.addLayer.mock.calls.filter((call) =>
      String(call[0].id).endsWith('-casing'),
    );
    expect(casings.length).toBe(WATERWAY_DEFS.length);
    for (const [layer, before] of casings) {
      expect(before).toBe(String(layer.id).replace(/-casing$/, ''));
    }
  });

  it('hides casing with the color line', () => {
    const map = fakeMap();
    syncWaterwayLayers(map as never, WATERWAY_DEFS, false);
    expect(map.visibility.get('map2d-waterways-rio-tercero-line')).toBe('none');
    expect(map.visibility.get('map2d-waterways-rio-tercero-line-casing')).toBe('none');
    expect(map.visibility.get('map2d-waterways-canal-desviador-line-casing')).toBe('none');
    expect(map.visibility.get('map2d-waterways-arroyo-algodon-line-casing')).toBe('none');
  });
});
