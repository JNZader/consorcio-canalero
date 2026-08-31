import { describe, expect, it } from 'vitest';

import { filterCanonicalTramites } from '../../src/components/admin/management/tramitesCanonical';

describe('filterCanonicalTramites', () => {
  it('keeps canonical states and returns discarded list for non-canonical items', () => {
    const result = filterCanonicalTramites([
      {
        id: 'ok-1',
        titulo: 'Valido',
        numero_expediente: 'A-1',
        estado: 'ingresado',
        ultima_actualizacion: '2026-03-01T10:00:00Z',
      },
      {
        id: 'legacy-pendiente',
        titulo: 'Legacy pendiente',
        numero_expediente: 'B-2',
        estado: 'pendiente',
        ultima_actualizacion: '2026-03-01T10:00:00Z',
      },
      {
        id: 'legacy-iniciado',
        titulo: 'Legacy iniciado',
        numero_expediente: 'B-3',
        estado: 'iniciado',
        ultima_actualizacion: '2026-03-01T10:00:00Z',
      },
    ]);

    expect(result.canonical).toHaveLength(1);
    expect(result.canonical[0].id).toBe('ok-1');
    expect(result.discarded).toHaveLength(2);
    expect(result.discarded.map((item) => item.id)).toEqual([
      'legacy-pendiente',
      'legacy-iniciado',
    ]);
  });

  it('returns empty arrays when input is empty', () => {
    const result = filterCanonicalTramites([]);

    expect(result.canonical).toEqual([]);
    expect(result.discarded).toEqual([]);
  });
});
