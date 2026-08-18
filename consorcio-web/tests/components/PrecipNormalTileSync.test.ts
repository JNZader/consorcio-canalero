/**
 * PrecipNormalTileSync.test.ts
 *
 * Proves the TILE URL side of H2 consumes the shared `precipRanges` contract:
 * `syncPrecipNormalLayer` must build a tile URL whose `rescale_max` is 1800 for the
 * annual aggregate and 200 for any single month — exactly matching the legend.
 */

import { describe, expect, it } from 'vitest';

import type { GeoLayerInfo } from '../../src/hooks/useGeoLayers';
import { syncPrecipNormalLayer } from '../../src/components/map2d/mapRasterOverlayHelpers';

interface MockSource {
  type: string;
  tiles?: string[];
  tileSize?: number;
}

interface MockMap {
  getSource: (id: string) => MockSource | null;
  getLayer: (id: string) => unknown;
  addSource: (id: string, def: MockSource) => void;
  removeSource: (id: string) => void;
  removeLayer: (id: string) => void;
  addLayer: (def: { id: string }, beforeId?: string) => void;
  setLayoutProperty: (id: string, prop: string, value: string) => void;
}

function makeMockMap(): { map: MockMap; added: MockSource[] } {
  const sources: Record<string, MockSource> = {};
  const layers: Record<string, unknown> = {};
  const added: MockSource[] = [];
  const map: MockMap = {
    getSource: (id) => sources[id] ?? null,
    getLayer: (id) => layers[id] ?? null,
    addSource: (id, def) => {
      sources[id] = def;
      added.push(def);
    },
    removeSource: (id) => {
      delete sources[id];
    },
    removeLayer: (id) => {
      delete layers[id];
    },
    addLayer: (def) => {
      layers[def.id] = def;
    },
    setLayoutProperty: () => {},
  };
  return { map, added };
}

const ANNUAL_LAYER = {
  id: 'geo-precip-normal-anual',
  tipo: 'precip_normal',
  metadata_extra: { mes: 'anual' },
} as unknown as GeoLayerInfo;

const JAN_LAYER = {
  id: 'geo-precip-normal-01',
  tipo: 'precip_normal',
  metadata_extra: { mes: '01' },
} as unknown as GeoLayerInfo;

function firstTileUrl(added: MockSource[]): string {
  const src = added.find((s) => s.tiles && s.tiles.length > 0);
  if (!src || !src.tiles) throw new Error('no raster source was added');
  return src.tiles[0];
}

describe('syncPrecipNormalLayer — tile rescale uses shared precipRanges contract (H2)', () => {
  it('builds an annual tile URL with rescale_min=0 & rescale_max=1800', () => {
    const { map, added } = makeMockMap();
    syncPrecipNormalLayer(map as unknown as Parameters<typeof syncPrecipNormalLayer>[0], {
      isHazardActive: true,
      precipMonth: 'anual',
      allGeoLayers: [ANNUAL_LAYER],
    });
    const url = firstTileUrl(added);
    expect(url).toContain('rescale_min=0');
    expect(url).toContain('rescale_max=1800');
  });

  it('builds a monthly tile URL with rescale_min=0 & rescale_max=200', () => {
    const { map, added } = makeMockMap();
    syncPrecipNormalLayer(map as unknown as Parameters<typeof syncPrecipNormalLayer>[0], {
      isHazardActive: true,
      precipMonth: '01',
      allGeoLayers: [JAN_LAYER],
    });
    const url = firstTileUrl(added);
    expect(url).toContain('rescale_min=0');
    expect(url).toContain('rescale_max=200');
  });

  it('adds no source when no precip layer matches the requested month', () => {
    const { map, added } = makeMockMap();
    syncPrecipNormalLayer(map as unknown as Parameters<typeof syncPrecipNormalLayer>[0], {
      isHazardActive: true,
      precipMonth: 'anual',
      allGeoLayers: [],
    });
    expect(added).toHaveLength(0);
  });
});
