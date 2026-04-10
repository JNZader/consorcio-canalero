import { Badge } from '@mantine/core';

export const MONTH_NAMES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
] as const;

export const DAY_NAMES = ['Lu', 'Ma', 'Mi', 'Ju', 'Vi', 'Sa', 'Do'] as const;

interface ZonePaint {
  color: string;
  fillColor: string;
  fillOpacity: number;
}

export function getZonePaint(zonaId: string, labeledZones: Record<string, boolean>): ZonePaint {
  const label = labeledZones[zonaId];
  if (label === true) return { color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.4 };
  if (label === false) return { color: '#22c55e', fillColor: '#22c55e', fillOpacity: 0.4 };
  return { color: '#6b7280', fillColor: '#9ca3af', fillOpacity: 0.1 };
}

export function getRainfallColor(mm: number | undefined): string | undefined {
  if (mm == null || mm <= 0) return undefined;
  if (mm <= 10) return 'rgba(147, 197, 253, 0.5)';
  if (mm <= 30) return 'rgba(59, 130, 246, 0.5)';
  if (mm <= 50) return 'rgba(29, 78, 216, 0.5)';
  return 'rgba(220, 38, 38, 0.55)';
}

export function getRainfallLabel(mm: number): string {
  if (mm <= 10) return 'Lluvia leve';
  if (mm <= 30) return 'Lluvia moderada';
  if (mm <= 50) return 'Lluvia intensa';
  return 'Lluvia muy intensa';
}

export function formatZScore(z: number): string {
  const sign = z >= 0 ? '+' : '';
  return `${sign}${z.toFixed(1)}σ`;
}

export function getZScoreColor(z: number): string {
  const abs = Math.abs(z);
  if (abs > 2) return 'red';
  if (abs > 1) return 'orange';
  return 'green';
}

export function getLabelBadge(zonaId: string, labeledZones: Record<string, boolean>) {
  const label = labeledZones[zonaId];
  if (label === true) return <Badge color="red" size="xs">Inundado</Badge>;
  if (label === false) return <Badge color="green" size="xs">No inundado</Badge>;
  return <Badge color="gray" size="xs">Sin etiquetar</Badge>;
}
