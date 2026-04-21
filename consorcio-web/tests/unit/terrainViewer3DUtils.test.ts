import type { Feature, FeatureCollection } from 'geojson';
import { describe, expect, it } from 'vitest';

import {
  buildCuencasCollection,
  buildSoilCollection,
  buildWaterwaysCollection,
} from '../../src/components/terrain/terrainViewer3DUtils';

function pointFeature(
  id: string,
  properties: Record<string, unknown> = {},
): Feature {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [-62.68, -32.62] },
    properties: { id, ...properties },
  };
}

function featureCollection(features: Feature[]): FeatureCollection {
  return { type: 'FeatureCollection', features };
}

describe('terrainViewer3DUtils', () => {
  it('builds colored cuencas from GEE layers', () => {
    const result = buildCuencasCollection({
      candil: featureCollection([pointFeature('candil-1')]),
      ml: featureCollection([pointFeature('ml-1')]),
      noroeste: null,
      norte: null,
    });

    expect(result?.features).toHaveLength(2);
    expect(result?.features[0]?.properties?.__label).toBe('Candil');
    expect(result?.features[1]?.properties?.__label).toBe('ML');
  });

  it('decorates soils with CAP color', () => {
    const result = buildSoilCollection(
      featureCollection([pointFeature('soil-1', { cap: 'III' })]),
    );

    expect(result?.features[0]?.properties?.__color).toBeTruthy();
  });

  it('decorates waterways using layer style and label', () => {
    const result = buildWaterwaysCollection([
      {
        nombre: 'Canal Norte',
        style: { color: '#123456' },
        data: featureCollection([pointFeature('w-1')]),
      },
    ]);

    expect(result?.features[0]?.properties?.__color).toBe('#123456');
    expect(result?.features[0]?.properties?.__label).toBe('Canal Norte');
  });
});
