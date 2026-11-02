import type { Feature, Polygon } from 'geojson';
import { describe, expect, it } from 'vitest';

import { searchCanales, searchParcelas } from '../../src/components/map2d/mapSearch';
import type { IndexFile } from '../../src/types/canales';

const index = {
  schema_version: '1.0',
  generated_at: '2026-01-01T00:00:00Z',
  counts: { relevados: 1, propuestas: 1, total: 2 },
  relevados: [
    {
      id: 'canal-legua-monte-lena',
      nombre: 'Canal Legua Monte Leña',
      codigo: 'C-12',
      longitud_m: 10,
      featured: false,
    },
  ],
  propuestas: [
    {
      id: 'canal-nuevo',
      nombre: 'Canal nuevo',
      codigo: null,
      longitud_m: 4,
      featured: false,
    },
  ],
} as IndexFile;

function parcel(props: Record<string, string>): Feature<Polygon> {
  return {
    type: 'Feature',
    properties: props,
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [0, 0],
          [1, 0],
          [1, 1],
          [0, 0],
        ],
      ],
    },
  };
}

describe('searchCanales', () => {
  it('matches nombre ignoring accents, and codigo or id', () => {
    expect(searchCanales(index, 'leña').map((hit) => hit.id)).toEqual(['canal-legua-monte-lena']);
    expect(searchCanales(index, 'c-12').map((hit) => hit.estado)).toEqual(['relevado']);
    expect(searchCanales(index, 'canal-nuevo').map((hit) => hit.estado)).toEqual(['propuesto']);
  });

  it('stays quiet until two characters', () => {
    expect(searchCanales(index, 'c')).toEqual([]);
    expect(searchCanales(null, 'canal')).toEqual([]);
  });
});

describe('searchParcelas', () => {
  const features = [
    parcel({ Nro_Cuenta: '150332', desig_oficial: 'Lote norte' }),
    parcel({ Nomenclatura: '12-34-56', desig_oficial: 'Quinta sur' }),
  ];

  it('matches cuenta, nomenclatura and designación from three characters', () => {
    expect(searchParcelas(features, '15')).toEqual([]);
    expect(searchParcelas(features, '150').map((hit) => hit.label)).toEqual(['150332']);
    expect(searchParcelas(features, '12-34').map((hit) => hit.label)).toEqual(['12-34-56']);
    expect(searchParcelas(features, 'quinta').map((hit) => hit.detail)).toEqual(['Quinta sur']);
  });
});
