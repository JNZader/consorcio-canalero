import type { ReactNode } from 'react';
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
