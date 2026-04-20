/**
 * canalesSyncHelpers.test.ts
 *
 * Tests for `syncCanalesLayers` — the unified sync helper that mounts both
 * relevados + propuestos line layers on the MapLibre map.
 *
 * Contract:
 *   - First call: addSource(relevados) + addSource(propuestos) + addLayer(
 *     relevados-line) + addLayer(propuestos-line) + setFilter + setLayerVisibility.
 *   - Second call with same args: only setFilter + setLayerVisibility, no
 *     duplicate addSource/addLayer (idempotency).
 *   - `map.moveLayer` is called for each layer after mount so the canales
 *     stack stays on top of waterways but BELOW Pilar Verde fills.
 *   - The filter expression is built via `buildCanalesRelevadosFilter` /
 *     `buildCanalesPropuestasFilter` — we assert the shape by reading back
 *     what was passed to `setFilter`.
 */

import type { FeatureCollection, LineString } from 'geojson';
import { describe, expect, it, vi } from 'vitest';

import type { CanalFeatureProperties } from '../../src/types/canales';
import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import { syncCanalesLayers } from '../../src/components/map2d/mapLayerEffectHelpers';

function emptyFC(): FeatureCollection<LineString, CanalFeatureProperties> {
  return { type: 'FeatureCollection', features: [] };
}

function createMapMock(options?: { layers?: string[]; sources?: string[] }) {
  const layers = new Set(options?.layers ?? []);
  const sources = new Set(options?.sources ?? []);
  return {
    layers,
    sources,
    map: {
      getLayer: vi.fn((id: string) => (layers.has(id) ? { id } : undefined)),
      getSource: vi.fn((id: string) =>
        sources.has(id) ? { id, setData: vi.fn() } : undefined,
      ),
      addSource: vi.fn((id: string) => {
        sources.add(id);
      }),
      addLayer: vi.fn((layer: { id: string }) => {
        layers.add(layer.id);
      }),
      moveLayer: vi.fn(),
      setLayoutProperty: vi.fn(),
      setFilter: vi.fn(),
    },
  };
}

describe('syncCanalesLayers · mount', () => {
  const relevadosId = SOURCE_IDS.CANALES_RELEVADOS;
  const propuestosId = SOURCE_IDS.CANALES_PROPUESTOS;
  const relevadosLayerId = `${relevadosId}-line`;
  const propuestosLayerId = `${propuestosId}-line`;

  it('mounts both sources + both line layers on first call', () => {
    const { map } = createMapMock();
    syncCanalesLayers(map as never, {
      relevados: emptyFC(),
      propuestas: emptyFC(),
      relevadosVisible: true,
      propuestasVisible: true,
      visibleRelevadoIds: [],
      visiblePropuestaIds: [],
      activeEtapas: ['Alta', 'Media-Alta', 'Media', 'Opcional', 'Largo plazo'],
    });

    expect(map.addSource).toHaveBeenCalledWith(relevadosId, expect.any(Object));
    expect(map.addSource).toHaveBeenCalledWith(propuestosId, expect.any(Object));
    const addedLayerIds = map.addLayer.mock.calls.map((c) => (c[0] as { id: string }).id);
    expect(addedLayerIds).toContain(relevadosLayerId);
    expect(addedLayerIds).toContain(propuestosLayerId);
  });

  it('sets visibility from masters', () => {
    const { map } = createMapMock();
    syncCanalesLayers(map as never, {
      relevados: emptyFC(),
      propuestas: emptyFC(),
      relevadosVisible: true,
      propuestasVisible: false,
      visibleRelevadoIds: [],
      visiblePropuestaIds: [],
      activeEtapas: [],
    });
    expect(map.setLayoutProperty).toHaveBeenCalledWith(relevadosLayerId, 'visibility', 'visible');
    expect(map.setLayoutProperty).toHaveBeenCalledWith(propuestosLayerId, 'visibility', 'none');
  });

  it('applies the per-canal id filter on relevados', () => {
    const { map } = createMapMock();
    syncCanalesLayers(map as never, {
      relevados: emptyFC(),
      propuestas: emptyFC(),
      relevadosVisible: true,
      propuestasVisible: true,
      visibleRelevadoIds: ['slug-a', 'slug-b'],
      visiblePropuestaIds: [],
      activeEtapas: [],
    });

    const relevadosFilterCall = map.setFilter.mock.calls.find(
      (c) => c[0] === relevadosLayerId,
    );
    expect(relevadosFilterCall).toBeTruthy();
    expect(relevadosFilterCall?.[1]).toEqual([
      'in',
      ['get', 'id'],
      ['literal', ['slug-a', 'slug-b']],
    ]);
  });

  it('applies the combined `all` filter on propuestos', () => {
    const { map } = createMapMock();
    syncCanalesLayers(map as never, {
      relevados: emptyFC(),
      propuestas: emptyFC(),
      relevadosVisible: true,
      propuestasVisible: true,
      visibleRelevadoIds: [],
      visiblePropuestaIds: ['slug-x'],
      activeEtapas: ['Alta'],
    });

    const call = map.setFilter.mock.calls.find((c) => c[0] === propuestosLayerId);
    expect(call).toBeTruthy();
    const filter = call?.[1] as unknown[];
    expect(filter?.[0]).toBe('all');
    expect(filter?.[1]).toEqual(['in', ['get', 'id'], ['literal', ['slug-x']]]);
    expect(filter?.[2]).toEqual(['in', ['get', 'prioridad'], ['literal', ['Alta']]]);
  });
});

describe('syncCanalesLayers · idempotency', () => {
  it('second call does not duplicate source/layer, only updates filter + visibility', () => {
    const { map } = createMapMock();
    syncCanalesLayers(map as never, {
      relevados: emptyFC(),
      propuestas: emptyFC(),
      relevadosVisible: true,
      propuestasVisible: true,
      visibleRelevadoIds: [],
      visiblePropuestaIds: [],
      activeEtapas: [],
    });
    map.addSource.mockClear();
    map.addLayer.mockClear();
    map.setFilter.mockClear();
    map.setLayoutProperty.mockClear();

    syncCanalesLayers(map as never, {
      relevados: emptyFC(),
      propuestas: emptyFC(),
      relevadosVisible: false,
      propuestasVisible: true,
      visibleRelevadoIds: ['a'],
      visiblePropuestaIds: ['b'],
      activeEtapas: ['Alta'],
    });

    expect(map.addSource).not.toHaveBeenCalled();
    expect(map.addLayer).not.toHaveBeenCalled();
    expect(map.setFilter).toHaveBeenCalled();
    expect(map.setLayoutProperty).toHaveBeenCalled();
  });
});

describe('syncCanalesLayers · null tolerance', () => {
  it('accepts null relevados/propuestas — renders empty source rather than throwing', () => {
    const { map } = createMapMock();
    expect(() =>
      syncCanalesLayers(map as never, {
        relevados: null,
        propuestas: null,
        relevadosVisible: false,
        propuestasVisible: false,
        visibleRelevadoIds: [],
        visiblePropuestaIds: [],
        activeEtapas: [],
      }),
    ).not.toThrow();
    // Source is always mounted (empty collection) so the visibility
    // toggle has something to act on.
    expect(map.addSource).toHaveBeenCalled();
  });
});
