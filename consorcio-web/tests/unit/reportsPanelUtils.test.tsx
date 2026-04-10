import { describe, expect, it } from 'vitest';
import { filterReports, getCategoryLabel, getStatusBadge } from '../../src/components/admin/reports/reportsPanelUtils';

const baseReport = {
  id: 'rep-1',
  created_at: '2026-03-01T10:00:00Z',
  categoria: 'inundacion',
  descripcion: 'Canal desbordado en zona norte',
  ubicacion_texto: 'Ruta 9 km 500',
  estado: 'pendiente',
  latitud: -32.62,
  longitud: -62.7,
  imagenes: [],
  contacto_nombre: 'Juan Perez',
  contacto_telefono: '3534000000',
};

describe('reportsPanelUtils', () => {
  it('filters reports and counts pending/in-review stats', () => {
    const reports = [
      baseReport,
      { ...baseReport, id: 'rep-2', estado: 'en_revision', descripcion: 'Otro caso' },
    ];

    const result = filterReports(reports, null, 'canal');
    expect(result.filteredReports).toHaveLength(1);
    expect(result.pendingCount).toBe(1);
    expect(result.inReviewCount).toBe(1);
  });

  it('returns a friendly category label', () => {
    expect(getCategoryLabel('inundacion')).toBeTruthy();
  });

  it('creates a status badge element', () => {
    expect(getStatusBadge('pendiente')).toBeTruthy();
  });
});
