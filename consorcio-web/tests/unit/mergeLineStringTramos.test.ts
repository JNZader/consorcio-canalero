import type { Feature, LineString } from 'geojson';
import { describe, expect, it } from 'vitest';

import { mergeLineStringTramos } from '../../src/components/map2d/mergeLineStringTramos';

function line(coordinates: LineString['coordinates']): Feature {
  return {
    type: 'Feature',
    geometry: { type: 'LineString', coordinates },
    properties: {},
  };
}

describe('mergeLineStringTramos', () => {
  it('returns null when there is no LineString', () => {
    expect(
      mergeLineStringTramos([
        { type: 'Feature', geometry: { type: 'Point', coordinates: [0, 0] }, properties: {} },
      ]),
    ).toBeNull();
  });

  it('returns the single line unchanged', () => {
    const feature = line([
      [0, 0],
      [1, 0],
    ]);
    expect(mergeLineStringTramos([feature])).toEqual(feature.geometry);
  });

  it('concatenates two tramos in selection order and drops a shared vertex', () => {
    const merged = mergeLineStringTramos([
      line([
        [0, 0],
        [1, 0],
      ]),
      line([
        [1, 0],
        [2, 0],
      ]),
    ]);
    expect(merged?.coordinates).toEqual([
      [0, 0],
      [1, 0],
      [2, 0],
    ]);
  });

  it('reverses the next tramo when it meets at the far end', () => {
    const merged = mergeLineStringTramos([
      line([
        [0, 0],
        [1, 0],
      ]),
      line([
        [2, 0],
        [1, 0],
      ]),
    ]);
    expect(merged?.coordinates).toEqual([
      [0, 0],
      [1, 0],
      [2, 0],
    ]);
  });
});
