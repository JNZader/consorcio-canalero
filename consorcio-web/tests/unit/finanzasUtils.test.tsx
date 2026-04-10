import { describe, expect, it } from 'vitest';

import {
  addNormalizedOption,
  buildOptionData,
  getFinanzasOptions,
  normalizeArray,
} from '../../src/components/admin/management/finanzas/finanzasUtils';

describe('finanzasUtils', () => {
  it('normalizes arrays from plain arrays and paginated payloads', () => {
    expect(normalizeArray([{ id: 1 }])).toEqual([{ id: 1 }]);
    expect(normalizeArray({ items: [{ id: 2 }] })).toEqual([{ id: 2 }]);
  });

  it('builds default and derived finance options', () => {
    expect(
      getFinanzasOptions(
        [
          {
            id: 'g1',
            fecha: '2026-01-01',
            descripcion: 'Diesel',
            monto: 10,
            categoria: 'combustible',
          },
        ],
        [
          {
            id: 'i1',
            fecha: '2026-01-01',
            descripcion: 'Cuota',
            monto: 25,
            fuente: 'subsidio',
          },
        ],
        ['obras'],
        ['cuotas_extra'],
      ),
    ).toEqual({
      categoryOptions: ['combustible'],
      sourceOptions: ['subsidio'],
    });

    expect(getFinanzasOptions([], [], ['obras'], ['cuotas_extra'])).toEqual({
      categoryOptions: ['obras'],
      sourceOptions: ['cuotas_extra'],
    });
  });

  it('adds normalized options without duplicating existing values', () => {
    expect(addNormalizedOption(['obras'], '  Viaticos ')).toEqual({
      normalized: 'viaticos',
      nextOptions: ['obras', 'viaticos'],
      changed: true,
    });

    expect(addNormalizedOption(['obras', 'viaticos'], 'Viaticos')).toEqual({
      normalized: 'viaticos',
      nextOptions: ['obras', 'viaticos'],
      changed: false,
    });
  });

  it('maps options into mantine select data', () => {
    expect(buildOptionData(['obras', 'combustible'])).toEqual([
      { value: 'obras', label: 'obras' },
      { value: 'combustible', label: 'combustible' },
    ]);
  });
});
