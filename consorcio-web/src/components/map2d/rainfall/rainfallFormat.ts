/**
 * rainfallFormat.ts (Lluvia v2 — shared by display and export, Task 3.4)
 *
 * ONE formatter for the metric state a user reads on screen and the text an
 * export summary carries, so displayed and exported states keep the same
 * meaning (spec "CSV Export Parity"). Rules: null is UNKNOWN, never "0" (a
 * served zero IS data); suppressed/unavailable always carry their reason
 * verbatim so the disclosure matches the CSV; partial exposes its coverage.
 */

import type { RainfallMetric, RainfallMetricState } from '../../../lib/api/rainfall';

/** Human label per metric key (the server sends machine keys only). */
const RAINFALL_METRIC_LABELS: Record<string, string> = {
  selected: 'Acumulado del año',
  normal: 'Normal 1991–2020',
  percentile: 'Percentil histórico',
  d7: 'Antecedente 7 días',
  d30: 'Antecedente 30 días',
  d90: 'Antecedente 90 días',
  p30: 'P30 (mm en 30 min)',
  p60: 'P60 (mm en 1 h)',
  p3h: 'P3h (mm en 3 h)',
  p24h: 'P24h (mm en 24 h)',
  i30: 'I30 (mm/h)',
  i60: 'I60 (mm/h)',
  peak: 'Pico del evento',
  duration: 'Duración del evento',
};

const RAINFALL_STATE_LABELS: Record<RainfallMetricState, string> = {
  available: 'Disponible',
  partial: 'Parcial',
  suppressed: 'Suprimida',
  unavailable: 'No disponible',
};

export function metricLabel(key: string): string {
  return RAINFALL_METRIC_LABELS[key] ?? key;
}

/** Value with unit; unknown stays "—", never "0". */
export function formatMetricValue(metric: RainfallMetric): string {
  if (metric.value === null) return '—';
  return `${metric.value.toFixed(1)} ${metric.unit}`;
}

/** State sentence with its reason where the contract carries one. */
export function describeMetricState(metric: RainfallMetric): string {
  const label = RAINFALL_STATE_LABELS[metric.state];
  if ((metric.state === 'suppressed' || metric.state === 'unavailable') && metric.reason) {
    return `${label}: ${metric.reason}`;
  }
  return label;
}

/** One full textual line per metric — the textual-chart row. */
export function describeMetricLine(key: string, metric: RainfallMetric): string {
  const base = `${metricLabel(key)}: ${formatMetricValue(metric)} — ${describeMetricState(metric)}`;
  return metric.state === 'partial'
    ? `${base} (cobertura ${Math.round(metric.coverage * 100)}%)`
    : base;
}
