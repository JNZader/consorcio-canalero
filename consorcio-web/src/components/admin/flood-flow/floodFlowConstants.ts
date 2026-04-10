import type { ZonaFloodFlowResult } from '../../../lib/api/floodFlow';

export type RiskLevel = ZonaFloodFlowResult['nivel_riesgo'];

export const RISK_CONFIG: Record<RiskLevel, { color: string; label: string; rowBg: string }> = {
  bajo: { color: 'green', label: 'Bajo', rowBg: 'var(--mantine-color-green-0)' },
  moderado: { color: 'yellow', label: 'Moderado', rowBg: 'var(--mantine-color-yellow-0)' },
  alto: { color: 'orange', label: 'Alto', rowBg: 'var(--mantine-color-orange-0)' },
  critico: { color: 'red', label: 'Crítico', rowBg: 'var(--mantine-color-red-0)' },
  sin_capacidad: { color: 'gray', label: 'Sin cap.', rowBg: 'transparent' },
};
