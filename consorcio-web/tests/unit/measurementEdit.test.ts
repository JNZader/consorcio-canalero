import { describe, expect, it } from 'vitest';

import {
  dropLastPolygonVertex,
  dropLastVertex,
  formatRumbo,
  moveLineVertex,
  rumboDegrees,
} from '../../src/components/map2d/measurement/measurementEdit';
import {
  clearPersonalMeasurements,
  readPersonalMeasurements,
  savePersonalMeasurement,
} from '../../src/components/map2d/measurement/personalMeasurements';

describe('measurement editing', () => {
  it('reports a northbound bearing and drops the last vertex', () => {
    const north = rumboDegrees([-64, -32], [-64, -31.9]);
    expect(formatRumbo(north)).toBe('rumbo 0°');
    expect(dropLastVertex([[0, 0], [1, 1], [2, 2]])).toEqual([[0, 0], [1, 1]]);
    expect(dropLastVertex([[0, 0], [1, 1]])).toBeNull();
  });

  it('drops the last non-closing vertex of a Polygon ring and preserves closure (MAP-02)', () => {
    expect(
      dropLastPolygonVertex([
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 1],
        [0, 0],
      ])
    ).toEqual([
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 0],
    ]);
    expect(
      dropLastPolygonVertex([
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 0],
      ])
    ).toBeNull();
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

  it('stores and clears personal measurements', () => {
    localStorage.clear();
    savePersonalMeasurement({
      id: 'm1',
      kind: 'distance',
      geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] },
    });
    expect(readPersonalMeasurements().map((item) => item.id)).toEqual(['m1']);
    clearPersonalMeasurements();
    expect(readPersonalMeasurements()).toEqual([]);
  });
});
