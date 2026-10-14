import type { Feature, LineString } from 'geojson';
import length from '@turf/length';
import { describe, expect, it } from 'vitest';

import { snapDistanceToRoads } from '../../src/components/map2d/measurement/measurementSnap';

function road(coordinates: LineString['coordinates']): Feature {
  return {
    type: 'Feature',
    geometry: { type: 'LineString', coordinates },
    properties: {},
  };
}

describe('snapDistanceToRoads', () => {
  it('measures along the road, not the offset freehand zigzag', () => {
    const axis = road([
      [0, 0],
      [0.02, 0],
    ]);
    const drawn: LineString = {
      type: 'LineString',
      coordinates: [
        [0, 0.00005],
        [0.01, -0.00004],
        [0.02, 0.00005],
      ],
    };
    const snapped = snapDistanceToRoads(drawn, [axis]);
    const axisM = length(axis, { units: 'meters' });
    expect(snapped.snapped).toBe(true);
    expect(snapped.meters).toBeCloseTo(axisM, 0);
    expect(snapped.meters).toBeLessThan(length({ type: 'Feature', geometry: drawn, properties: {} }, { units: 'meters' }));
  });

  it('keeps the drawn length when both ends miss the network', () => {
    const axis = road([
      [0, 0],
      [0.01, 0],
    ]);
    const drawn: LineString = {
      type: 'LineString',
      coordinates: [
        [1, 1],
        [1.01, 1],
      ],
    };
    const snapped = snapDistanceToRoads(drawn, [axis]);
    expect(snapped.snapped).toBe(false);
    expect(snapped.meters).toBeCloseTo(
      length({ type: 'Feature', geometry: drawn, properties: {} }, { units: 'meters' }),
      5,
    );
  });
});
