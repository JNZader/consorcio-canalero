import { Badge } from '@mantine/core';
import { RISK_CONFIG, type RiskLevel } from '../floodFlowConstants';

export function RiskBadge({ nivel }: Readonly<{ nivel: RiskLevel }>) {
  const config = RISK_CONFIG[nivel];
  return (
    <Badge color={config.color} variant="filled" size="sm" radius="sm">
      {config.label}
    </Badge>
  );
}
