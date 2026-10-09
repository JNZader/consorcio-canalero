import type { Feature, LineString } from 'geojson';
import { describe, expect, it } from 'vitest';

import {
  mergeAdditiveFeatures,
  pickPrimaryTramo,
  selectionKey,
} from '../../src/components/map2d/mergeAdditiveFeatures';
import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';

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

describe('pickPrimaryTramo', () => {
  it('prefers a canal over a waterway in the same bbox', () => {
    const waterway = line('rio', `${SOURCE_IDS.WATERWAYS}-rio-tercero-line`);
    const canal = line('c1', `${SOURCE_IDS.CANALES_RELEVADOS}-line`);
    expect(pickPrimaryTramo([waterway, canal])).toBe(canal);
  });

  it('falls back to a road when no canal is hit', () => {
    const road = line('r1', `${SOURCE_IDS.ROADS}-hit`);
    expect(pickPrimaryTramo([road])).toBe(road);
  });

  it('ignores waterways when they are the only line', () => {
    const waterway = line('rio', `${SOURCE_IDS.WATERWAYS}-rio-tercero-line`);
    expect(pickPrimaryTramo([waterway])).toBeNull();
  });
});
