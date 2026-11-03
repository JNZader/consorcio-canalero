import { describe, expect, it } from 'vitest';

import { dropLastVertex, formatRumbo, moveLineVertex, rumboDegrees } from '../../src/components/map2d/measurement/measurementEdit';
import { savePersonalMeasurement, readPersonalMeasurements } from '../../src/components/map2d/measurement/personalMeasurements';

describe('measurement editing', () => {
  it('reports a northbound bearing and drops the last vertex', () => {
    const north = rumboDegrees([-64, -32], [-64, -31.9]);
    expect(formatRumbo(north)).toBe('rumbo 0°');
    expect(dropLastVertex([[0, 0], [1, 1], [2, 2]])).toEqual([[0, 0], [1, 1]]);
    expect(dropLastVertex([[0, 0], [1, 1]])).toBeNull();
  });

  it('moves one vertex and keeps the others', () => {
    const next = moveLineVertex(
      { type: 'LineString', coordinates: [[0, 0], [1, 1]] },
      1,
      [2, 3]
    );
    expect(next.coordinates[1]).toEqual([2, 3]);
    expect(next.coordinates[0]).toEqual([0, 0]);
  });

  it('stores a personal measurement', () => {
    localStorage.clear();
    savePersonalMeasurement({
      id: 'm1',
      kind: 'distance',
      geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] },
    });
    expect(readPersonalMeasurements().map((item) => item.id)).toEqual(['m1']);
  });
});
