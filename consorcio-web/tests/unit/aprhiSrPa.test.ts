import type { FeatureCollection } from 'geojson';
import { describe, expect, it } from 'vitest';

import {
  isSrPaListId,
  parseSrPaRows,
  srPaFeatureById,
  srPaFeatureId,
  tagSrPaListIds,
} from '../../src/lib/aprhiSrPa';

const collection: FeatureCollection = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      id: 'CA00140',
      geometry: {
        type: 'LineString',
        coordinates: [
          [-62.5, -32.5],
          [-62.4, -32.4],
        ],
      },
      properties: {
        Identificador: 'CA00140',
        Nombre_Obra: 'Tramo Nuevo - Canal San Marcos',
        Estado_Registro: 'Vigente',
        Tipo_Obra_Lineal: 'Canal (CA)',
        OBJECTID: 140,
      },
    },
    {
      type: 'Feature',
      id: 3513,
      geometry: {
        type: 'LineString',
        coordinates: [
          [-62.6, -32.6],
          [-62.5, -32.5],
        ],
      },
      properties: {
        Nombre_Obra: 'Canal Los Patos',
        Estado_Registro: 'Eliminado',
        Tipo_Obra_Lineal: 'Canal (CA)',
        OBJECTID: 3513,
      },
    },
  ],
};

describe('srPaFeatureId', () => {
  it('prefers the CA code and prefixes srpa:', () => {
    expect(srPaFeatureId({ Identificador: 'CA00140', OBJECTID: 140 })).toBe('srpa:CA00140');
  });

  it('falls back to OBJECTID when Identificador is missing', () => {
    expect(srPaFeatureId({ OBJECTID: 3513 })).toBe('srpa:3513');
  });
});

describe('parseSrPaRows', () => {
  it('lists vigentes first and keeps the work without a CA code', () => {
    const rows = parseSrPaRows(collection);
    expect(rows.map((row) => row.id)).toEqual(['srpa:CA00140', 'srpa:3513']);
    expect(rows[0]?.identificador).toBe('CA00140');
    expect(rows[1]?.identificador).toBe('');
    expect(rows[1]?.nombre).toBe('Canal Los Patos');
  });
});

describe('tagSrPaListIds', () => {
  it('stamps list_id so the map can highlight the sidebar selection', () => {
    const tagged = tagSrPaListIds(collection);
    expect(tagged.features[0]?.properties?.list_id).toBe('srpa:CA00140');
    expect(isSrPaListId('srpa:CA00140')).toBe(true);
    expect(srPaFeatureById(tagged, 'srpa:3513')?.properties?.OBJECTID).toBe(3513);
  });
});
