import type { Feature, LineString } from 'geojson';
import { describe, expect, it } from 'vitest';
import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import {
  expandCanalGroup,
  expandTramoGroup,
  mergeAdditiveFeatures,
  pickPrimaryTramo,
  selectionKey,
} from '../../src/components/map2d/mergeAdditiveFeatures';

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

  it('expands using GEE `rtn` when `ruta` is absent', () => {
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
      properties: { id: '20745', rtn: 'T269-03' },
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
      properties: { id: '28445', rtn: 'T269-03' },
    };
    const hit = { ...a, layer: { id: layer } };
    expect(expandTramoGroup(hit, [a, b])).toHaveLength(2);
  });

  it('keeps a unified MultiLineString route as the whole group', () => {
    const layer = `${SOURCE_IDS.ROADS}-hit`;
    const route: Feature = {
      type: 'Feature',
      geometry: {
        type: 'MultiLineString',
        coordinates: [
          [
            [0, 0],
            [1, 0],
          ],
          [
            [1, 0],
            [2, 0],
          ],
        ],
      },
      properties: { ruta: 'T269-03' },
    };
    const hit = { ...route, layer: { id: layer } };
    expect(expandTramoGroup(hit, [route])).toHaveLength(1);
    expect(pickPrimaryTramo([hit], [0.5, 0])).toBe(hit);
  });
});

describe('expandCanalGroup', () => {
  const layer = `${SOURCE_IDS.CANALES_RELEVADOS}-line`;

  it('replaces the tile clip with the full catalog line of that canal', () => {
    const catalog: Feature<LineString> = {
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [-62.4, -32.4],
          [-62.5, -32.5],
          [-62.6, -32.6],
        ],
      },
      properties: { id: 'canal-ne-sin-intervencion', nombre: 'Canal NE' },
    };
    const clip = line('canal-ne-sin-intervencion', layer);
    clip.id = 99;
    clip.geometry = {
      type: 'LineString',
      coordinates: [
        [-62.5, -32.5],
        [-62.5001, -32.5001],
      ],
    };

    const [selected] = expandCanalGroup(clip, [catalog], []);

    expect(selected?.geometry).toEqual(catalog.geometry);
    expect(selected).not.toBe(clip);
    expect(selectionKey(selected as Feature)).toBe(`${layer}::canal-ne-sin-intervencion`);
  });

  it('uses the same key when a later click hits another tile of the same canal', () => {
    const catalog: Feature<LineString> = {
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [-62.4, -32.4],
          [-62.6, -32.6],
        ],
      },
      properties: { id: 'cgic-canal_10_de_mayo' },
    };
    const first = line('cgic-canal_10_de_mayo', layer);
    first.id = 1;
    const second = line('cgic-canal_10_de_mayo', layer);
    second.id = 2;

    const [a] = expandCanalGroup(first, [catalog], []);
    const [b] = expandCanalGroup(second, [catalog], []);

    expect(selectionKey(a as Feature)).toBe(selectionKey(b as Feature));
  });

  it('keeps the clicked feature when the catalog has no matching id', () => {
    const hit = line('canal-sin-catalogo', layer);
    expect(expandCanalGroup(hit, [], [])).toEqual([hit]);
  });

  it('reads a propuesto from the propuestas catalog only', () => {
    const propuestoLayer = `${SOURCE_IDS.CANALES_PROPUESTOS}-line`;
    const propuesto: Feature<LineString> = {
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [-62.39, -32.45],
          [-62.4, -32.46],
        ],
      },
      properties: { id: 'n3-tramo-faltante-de-interconexion' },
    };
    const relevado: Feature<LineString> = {
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [0, 0],
          [1, 1],
        ],
      },
      properties: { id: 'n3-tramo-faltante-de-interconexion' },
    };
    const hit = line('n3-tramo-faltante-de-interconexion', propuestoLayer);

    const [selected] = expandCanalGroup(hit, [relevado], [propuesto]);

    expect(selected?.geometry).toEqual(propuesto.geometry);
  });
});
