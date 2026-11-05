import { describe, expect, it } from 'vitest';
import { getCategoriaLabel, getStatusBadge } from '../../src/components/admin/sugerencias/sugerenciasPanelUtils';

describe('sugerenciasPanelUtils', () => {
  it('returns friendly category labels', () => {
    expect(getCategoriaLabel('infraestructura')).toBe('Infraestructura');
    expect(getCategoriaLabel(undefined)).toBe('Sin categoría');
  });

  it('creates a status badge element', () => {
    expect(getStatusBadge('pendiente')).toBeTruthy();
  });
});
