import { describe, expect, it } from 'vitest';

import { cursorCollection } from '../../src/components/map2d/elevationCursor';

describe('elevation cursor follows sampled lon/lat linearly', () => {
  it('each profile sample places the map point on that sample, not turf.along', () => {
    const samples = [
      { distance_m: 0, lon: -62.5, lat: -32.58 },
      { distance_m: 1500, lon: -62.504, lat: -32.57 },
      { distance_m: 3500, lon: -62.504, lat: -32.55 },
    ];
    const lons: number[] = [];
    const lats: number[] = [];
    for (const sample of samples) {
      const collection = cursorCollection({ lon: sample.lon, lat: sample.lat });
      const point = collection.features[0]?.geometry;
      expect(point?.type).toBe('Point');
      if (point?.type !== 'Point') {
        continue;
      }
      expect(point.coordinates[0]).toBe(sample.lon);
      expect(point.coordinates[1]).toBe(sample.lat);
      lons.push(point.coordinates[0]);
      lats.push(point.coordinates[1]);
    }
    expect(lats[0]).not.toBe(lats[2]);
  });
});
