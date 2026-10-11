import { describe, expect, it } from 'vitest';

import { cursorCollection, rangeCollection } from '../../src/components/map2d/elevationCursor';

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

  it('puts min and max vertices on the selected stretch', () => {
    const collection = rangeCollection({
      length_m: 20,
      min_elevation_m: 118,
      max_elevation_m: 121,
      delta_m: 3,
      coordinates: [
        [-62.71, -32.6],
        [-62.72, -32.6],
        [-62.73, -32.6],
      ],
      min_point: { lon: -62.71, lat: -32.6, elevation_m: 118, distance_m: 10 },
      max_point: { lon: -62.73, lat: -32.6, elevation_m: 121, distance_m: 30 },
    });
    const kinds = collection.features.map((feature) => feature.properties?.kind);
    expect(kinds).toEqual(['span', 'min', 'max']);
  });
});
