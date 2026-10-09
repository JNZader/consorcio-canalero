import type { Feature, LineString } from 'geojson';
import { describe, expect, it } from 'vitest';

import { mergeAdditiveFeatures, selectionKey } from '../../src/components/map2d/mergeAdditiveFeatures';

function line(id: string, layer: string): Feature<LineString> & { layer: { id: string } } {
  return {
    type: 'Feature',
    id,
    layer: { id: layer },
    geometry: {
      type: 'LineString',
      coordinates: [
        [-62.7, -32.6],
        [-62.71, -32.61],
      ],
    },
    properties: { id },
  };
}

describe('mergeAdditiveFeatures', () => {
  it('appends a new tramo', () => {
    const a = line('t1', 'canales-relevados');
    const b = line('t2', 'canales-relevados');
    expect(mergeAdditiveFeatures([a], [b]).map(selectionKey)).toEqual([
      'canales-relevados::t1',
      'canales-relevados::t2',
    ]);
  });

  it('toggles off a tramo already in the selection', () => {
    const a = line('t1', 'canales-relevados');
    const b = line('t2', 'canales-relevados');
    expect(mergeAdditiveFeatures([a, b], [a]).map(selectionKey)).toEqual(['canales-relevados::t2']);
  });

  it('does nothing when incoming is empty', () => {
    const a = line('t1', 'canales-relevados');
    expect(mergeAdditiveFeatures([a], [])).toEqual([a]);
  });
});
