import { Badge } from '@mantine/core';
import { STATUS_CONFIG } from '../../constants';

export type StatusType = keyof typeof STATUS_CONFIG;

export interface StatusConfigItem {
  readonly color: string;
  readonly label: string;
}

export function getStatusConfig(status: StatusType | string): StatusConfigItem {
  return STATUS_CONFIG[status as StatusType] || { color: 'gray', label: status };
}

/**
 * Color de estado de denuncia/sugerencia, tomado de los tokens semánticos.
 * El fallback es el texto atenuado para estados que el frontend no conoce.
 */
export const STATUS_COLOR_VAR: Record<string, string> = {
  pendiente: 'var(--cc-color-warning)',
  en_revision: 'var(--cc-color-status-review)',
  revisada: 'var(--cc-color-status-review)',
  resuelto: 'var(--cc-color-success)',
  implementada: 'var(--cc-color-success)',
  descartado: 'var(--cc-color-danger)',
  descartada: 'var(--cc-color-text-muted)',
};

export function statusColorVar(status: string): string {
  return STATUS_COLOR_VAR[status] ?? 'var(--cc-color-text-muted)';
}

interface StatusBadgeProps {
  readonly status: StatusType | string;
  readonly size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
}

export function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const config = getStatusConfig(status);
  const token = statusColorVar(status);
  return (
    <Badge
      variant="light"
      radius="sm"
      size={size}
      data-status={status}
      style={{
        color: token,
        backgroundColor: `color-mix(in srgb, ${token} 16%, transparent)`,
        borderColor: `color-mix(in srgb, ${token} 40%, transparent)`,
      }}
    >
      {config.label}
    </Badge>
  );
}
