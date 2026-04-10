import { describe, expect, it } from 'vitest';

import {
  buildAgendaReferences,
  buildAgendaTopicPayload,
  buildReferrableOptions,
  getAgendaReferenceColor,
  hasAgendaItems,
  normalizeArrayResponse,
} from '../../src/components/admin/management/reuniones/reunionesUtils';

describe('reunionesUtils', () => {
  it('normalizes wrapped array responses', () => {
    expect(normalizeArrayResponse([{ id: '1' }])).toEqual([{ id: '1' }]);
    expect(normalizeArrayResponse({ items: [{ id: '2' }] })).toEqual([{ id: '2' }]);
    expect(normalizeArrayResponse({ data: [{ id: '3' }] })).toEqual([{ id: '3' }]);
    expect(normalizeArrayResponse({ results: [{ id: '4' }] })).toEqual([{ id: '4' }]);
    expect(normalizeArrayResponse({})).toEqual([]);
  });

  it('builds referrable options and references', () => {
    const options = buildReferrableOptions(
      [{ id: 'r1', tipo: 'rotura_canal', ubicacion_texto: 'Canal Norte' }],
      [{ id: 't1', titulo: 'Expediente', numero_expediente: '123' }],
      [{ id: 'a1', nombre: 'Bomba', tipo: 'maquinaria' }],
    );

    expect(options).toEqual([
      { value: 'r1', label: 'rotura canal - Canal Norte', group: 'Reportes', type: 'reporte' },
      { value: 't1', label: 'Expediente (123)', group: 'Tramites', type: 'tramite' },
      { value: 'a1', label: 'Bomba (maquinaria)', group: 'Infraestructura', type: 'infraestructura' },
    ]);

    expect(buildAgendaReferences(['r1'], options)).toEqual([
      { entidad_id: 'r1', entidad_tipo: 'reporte', metadata: { label: 'rotura canal - Canal Norte' } },
    ]);
  });

  it('builds topic payload and helper colors', () => {
    const options = [{ value: 'r1', label: 'Reporte 1', group: 'Reportes', type: 'reporte' }];
    expect(
      buildAgendaTopicPayload(
        { titulo: 'Tema', descripcion: 'Detalle', referencias: ['r1'] },
        [],
        options,
      ),
    ).toEqual({
      titulo: 'Tema',
      descripcion: 'Detalle',
      orden: 1,
      referencias: [{ entidad_id: 'r1', entidad_tipo: 'reporte', metadata: { label: 'Reporte 1' } }],
    });

    expect(getAgendaReferenceColor('reporte')).toBe('red');
    expect(getAgendaReferenceColor('tramite')).toBe('blue');
    expect(getAgendaReferenceColor('infraestructura')).toBe('green');
    expect(getAgendaReferenceColor('otro')).toBe('gray');
    expect(hasAgendaItems(['uno'])).toBe(true);
    expect(hasAgendaItems([])).toBe(false);
  });
});
