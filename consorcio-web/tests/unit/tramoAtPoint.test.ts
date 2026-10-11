import type { Feature, LineString } from 'geojson';
import { describe, expect, it } from 'vitest';

import { nearestLineStringIndex } from '../../src/components/map2d/tramoAtPoint';

function line(coordinates: LineString['coordinates'], name: string): Feature {
  return {
    type: 'Feature',
    geometry: { type: 'LineString', coordinates },
    properties: { nombre: name },
  };
}

describe('nearestLineStringIndex', () => {
  const south = line(
    [
      [-62.7, -32.6],
      [-62.69, -32.6],
    ],
    'south',
  );
  const north = line(
    [
      [-62.7, -32.59],
      [-62.69, -32.59],
    ],
    'north',
  );

  it('picks the closer of two parallel tramos', () => {
    expect(nearestLineStringIndex([south, north], -62.695, -32.6002)).toBe(0);
    expect(nearestLineStringIndex([south, north], -62.695, -32.5902)).toBe(1);
  });

  it('returns null when the point is far from every tramo', () => {
    expect(nearestLineStringIndex([south], -62.0, -32.0)).toBeNull();
  });

  it('ignores Points', () => {
    const point: Feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [-62.695, -32.6] },
      properties: {},
    };
    expect(nearestLineStringIndex([point, south], -62.695, -32.6)).toBe(1);
  });
});
