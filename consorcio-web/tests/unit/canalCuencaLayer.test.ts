/**
 * canalCuencaLayer.test.ts
 *
 * The on-map canal CATCHMENT outline (A7 slice 2). Confirms `syncCanalCuencaLayer`:
 *   - adds a geojson source + fill + line layers when given a geometry;
 *   - wraps the bare GeoJSON geometry into a one-feature FeatureCollection;
 *   - removes source + both layers when the geometry is null (cleared on a
 *     mode/selection switch), removing layers BEFORE the source;
 *   - is idempotent (re-sync updates the source data, does not duplicate layers).
 */

import type { Geometry } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { describe, expect, it, vi } from 'vitest';

import {
  CANAL_CUENCA_FILL_LAYER,
  CANAL_CUENCA_LINE_LAYER,
  CANAL_CUENCA_SOURCE,
  syncCanalCuencaLayer,
} from '../../src/components/map2d/canalCuencaLayer';

interface FakeLayer {
  id: string;
  type: string;
  source?: string;
}

function createFakeMap() {
  const sources = new Map<string, { data: unknown; setData: ReturnType<typeof vi.fn> }>();
  const layers = new Map<string, FakeLayer>();

  const map = {
    getSource: (id: string) => sources.get(id),
    addSource: (id: string, source: { data: unknown }) => {
      sources.set(id, {
        data: source.data,
        setData: vi.fn((next: unknown) => {
          const existing = sources.get(id);
          if (existing) existing.data = next;
        }),
      });
    },
    removeSource: (id: string) => {
      for (const layer of layers.values()) {
        if (layer.source === id) {
          throw new Error(
            `Source "${id}" cannot be removed while layer "${layer.id}" is using it.`
          );
        }
      }
      sources.delete(id);
    },
    getLayer: (id: string) => layers.get(id),
    addLayer: (layer: FakeLayer) => {
      layers.set(layer.id, layer);
    },
    removeLayer: (id: string) => {
      layers.delete(id);
    },
  } as unknown as maplibregl.Map;

  return { map, sources, layers };
}

const CUENCA: Geometry = {
  type: 'Polygon',
  coordinates: [
    [
      [-62, -32],
      [-61.99, -32],
      [-61.99, -31.99],
      [-62, -31.99],
      [-62, -32],
    ],
  ],
};

describe('syncCanalCuencaLayer', () => {
  it('adds a source + fill + line layers and wraps the geometry into a FeatureCollection', () => {
    const { map, sources, layers } = createFakeMap();

    syncCanalCuencaLayer(map, CUENCA);

    expect(sources.has(CANAL_CUENCA_SOURCE)).toBe(true);
    expect(layers.has(CANAL_CUENCA_FILL_LAYER)).toBe(true);
    expect(layers.has(CANAL_CUENCA_LINE_LAYER)).toBe(true);

    const data = sources.get(CANAL_CUENCA_SOURCE)?.data as {
      type: string;
      features: { geometry: Geometry }[];
    };
    expect(data.type).toBe('FeatureCollection');
    expect(data.features).toHaveLength(1);
    expect(data.features[0].geometry).toEqual(CUENCA);
  });

  it('removes source + both layers when the geometry is null (cleared on switch)', () => {
    const { map, sources, layers } = createFakeMap();
    syncCanalCuencaLayer(map, CUENCA);

    // A null geometry (mode/selection switch, or a non-cuenca tipo) tears it down.
    expect(() => syncCanalCuencaLayer(map, null)).not.toThrow();
    expect(sources.has(CANAL_CUENCA_SOURCE)).toBe(false);
    expect(layers.has(CANAL_CUENCA_FILL_LAYER)).toBe(false);
    expect(layers.has(CANAL_CUENCA_LINE_LAYER)).toBe(false);
  });

  it('is idempotent — a second sync updates the source data without duplicating layers', () => {
    const { map, sources, layers } = createFakeMap();
    syncCanalCuencaLayer(map, CUENCA);

    const other: Geometry = {
      type: 'MultiPolygon',
      coordinates: [CUENCA.type === 'Polygon' ? CUENCA.coordinates : []],
    };
    syncCanalCuencaLayer(map, other);

    expect(sources.get(CANAL_CUENCA_SOURCE)?.setData).toHaveBeenCalledTimes(1);
    expect(layers.size).toBe(2); // still just fill + line, not duplicated
  });
});
