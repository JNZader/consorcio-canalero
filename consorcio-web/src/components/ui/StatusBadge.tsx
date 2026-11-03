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

interface StatusBadgeProps {
  readonly status: StatusType | string;
  readonly size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
}

export function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const config = getStatusConfig(status);
  return (
    <Badge color={config.color} variant="light" radius="sm" size={size}>
      {config.label}
    </Badge>
  );
}
