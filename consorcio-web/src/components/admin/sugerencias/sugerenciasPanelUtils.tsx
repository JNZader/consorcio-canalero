import { Badge } from '@mantine/core';
import type { ReactNode } from 'react';
import type { Sugerencia } from '../../../lib/api';
import { CATEGORIA_OPTIONS, ESTADO_OPTIONS } from './constants';

export function getStatusBadge(status: string): ReactNode {
  const option = ESTADO_OPTIONS.find((o) => o.value === status);
  return (
    <Badge color={option?.color || 'gray'} variant="light">
      {option?.label || status}
    </Badge>
  );
}

export function getCategoriaLabel(categoria?: string | null): string {
  return (
    CATEGORIA_OPTIONS.find((c) => c.value === categoria)?.label || categoria || 'Sin categoria'
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
