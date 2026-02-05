import { Badge } from '@mantine/core';
import { STATUS_CONFIG } from '../../constants';

type StatusType = keyof typeof STATUS_CONFIG;

interface StatusBadgeProps {
  readonly status: StatusType | string;
  readonly size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
}

export function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status as StatusType] || { color: 'gray', label: status };
  return (
    <Badge color={config.color} variant="light" radius="sm" size={size}>
      {config.label}
    </Badge>
  );
}
