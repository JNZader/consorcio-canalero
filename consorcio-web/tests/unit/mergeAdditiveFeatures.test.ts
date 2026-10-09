import type { Feature, LineString } from 'geojson';
import { describe, expect, it } from 'vitest';

import {
  expandTramoGroup,
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

  it('keeps two T269-03 road pieces that share ruta but have no id', () => {
    const layer = `${SOURCE_IDS.ROADS}-hit`;
    const a: Feature<LineString> & { layer: { id: string } } = {
      type: 'Feature',
      layer: { id: layer },
      geometry: {
        type: 'LineString',
        coordinates: [
          [-62.5, -32.58],
          [-62.504, -32.58],
        ],
      },
      properties: { ruta: 'T269-03', nombre: 'Camino Provincial T269-03' },
    };
    const b: Feature<LineString> & { layer: { id: string } } = {
      type: 'Feature',
      layer: { id: layer },
      geometry: {
        type: 'LineString',
        coordinates: [
          [-62.504, -32.58],
          [-62.496, -32.55],
        ],
      },
      properties: { ruta: 'T269-03', nombre: 'Camino Provincial T269-03' },
    };
    expect(mergeAdditiveFeatures([a], [b])).toHaveLength(2);
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

  it('picks the road under the click even if a canal is in the bbox', () => {
    const canal = line('c1', `${SOURCE_IDS.CANALES_RELEVADOS}-line`);
    canal.geometry = {
      type: 'LineString',
      coordinates: [
        [0, 1],
        [0, 1.01],
      ],
    };
    const road: Feature<LineString> & { layer: { id: string } } = {
      type: 'Feature',
      layer: { id: `${SOURCE_IDS.ROADS}-hit` },
      geometry: {
        type: 'LineString',
        coordinates: [
          [0, 0],
          [1, 0],
        ],
      },
      properties: { ruta: 'T269-03' },
    };
    expect(pickPrimaryTramo([canal, road], [0.5, 0])).toBe(road);
  });
});

describe('expandTramoGroup', () => {
  it('expands a T269-03 hit to every catalog piece with that ruta', () => {
    const layer = `${SOURCE_IDS.ROADS}-hit`;
    const a: Feature<LineString> = {
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [0, 0],
          [1, 0],
        ],
      },
      properties: { ruta: 'T269-03' },
    };
    const b: Feature<LineString> = {
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [1, 0],
          [2, 0],
        ],
      },
      properties: { ruta: 'T269-03' },
    };
    const other: Feature<LineString> = {
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [0, 1],
          [1, 1],
        ],
      },
      properties: { ruta: 'T135-06' },
    };
    const hit = { ...a, layer: { id: layer } };
    const group = expandTramoGroup(hit, [a, b, other]);
    expect(group).toHaveLength(2);
    expect(group.every((feature) => feature.properties?.ruta === 'T269-03')).toBe(true);
  });
});
