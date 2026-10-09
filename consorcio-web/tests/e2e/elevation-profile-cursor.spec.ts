/**
 * The map cursor must sit on the DEM sample (lon/lat), not turf.along the
 * coarse WGS84 sketch. This is the linearity contract; the live /mapa flow
 * still needs operator login + dem_filled.
 */
import { expect, test } from '@playwright/test';

import { cursorCollection } from '../../src/components/map2d/elevationCursor';

test.describe('elevation profile cursor linearity', () => {
  test('hovered sample lon/lat is the map point', () => {
    const samples = [
      { distance_m: 0, lon: -62.50424, lat: -32.57999 },
      { distance_m: 1740, lon: -62.49666, lat: -32.54913 },
      { distance_m: 3457, lon: -62.51306, lat: -32.54226 },
    ];
    for (let index = 0; index < samples.length; index += 1) {
      const sample = samples[index];
      const point = cursorCollection({ lon: sample.lon, lat: sample.lat }).features[0]?.geometry;
      expect(point).toEqual({ type: 'Point', coordinates: [sample.lon, sample.lat] });
      if (index === 0) {
        continue;
      }
      expect(sample.distance_m).toBeGreaterThan(samples[index - 1].distance_m);
    }
  });
});
