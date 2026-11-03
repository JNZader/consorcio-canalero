import type { ReactNode } from 'react';
import type { Sugerencia } from '../../../lib/api';
import { StatusBadge } from '../../ui/StatusBadge';
import { CATEGORIA_OPTIONS } from './constants';

export function getStatusBadge(status: string): ReactNode {
  return <StatusBadge status={status} />;
}

export function getCategoriaLabel(categoria?: string | null): string {
  return (
    CATEGORIA_OPTIONS.find((c) => c.value === categoria)?.label || categoria || 'Sin categoría'
  );
}

export function filterSugerenciasByQuery(sugerencias: Sugerencia[], searchQuery: string) {
  if (!searchQuery) return sugerencias;
  const query = searchQuery.toLowerCase();
  return sugerencias.filter(
    (sug) =>
      sug.titulo.toLowerCase().includes(query) || sug.descripcion.toLowerCase().includes(query)
  );
}
