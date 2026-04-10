import { describe, expect, it } from 'vitest';
import { filterSugerenciasByQuery, getCategoriaLabel, getStatusBadge } from '../../src/components/admin/sugerencias/sugerenciasPanelUtils';

const baseSuggestion = {
  id: 'sug-1',
  tipo: 'ciudadana' as const,
  titulo: 'Limpiar desagues secundarios',
  descripcion: 'Solicitamos limpieza por acumulacion de barro',
  categoria: 'infraestructura',
  estado: 'pendiente' as const,
  prioridad: 'alta' as const,
  created_at: '2026-03-01T09:00:00Z',
  updated_at: '2026-03-01T09:00:00Z',
};

describe('sugerenciasPanelUtils', () => {
  it('filters suggestions by title or description query', () => {
    expect(filterSugerenciasByQuery([baseSuggestion], 'desagues')).toHaveLength(1);
    expect(filterSugerenciasByQuery([baseSuggestion], 'barro')).toHaveLength(1);
    expect(filterSugerenciasByQuery([baseSuggestion], 'inexistente')).toHaveLength(0);
  });

  it('returns friendly category labels', () => {
    expect(getCategoriaLabel('infraestructura')).toBe('Infraestructura');
    expect(getCategoriaLabel(undefined)).toBe('Sin categoria');
  });

  it('creates a status badge element', () => {
    expect(getStatusBadge('pendiente')).toBeTruthy();
  });
});
