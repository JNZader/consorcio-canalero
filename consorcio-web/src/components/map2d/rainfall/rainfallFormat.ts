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

/**
 * A series value with its unit — the chart's counterpart to
 * {@link formatMetricValue}, which only knows how to read a `RainfallMetric`.
 *
 * Same rule, stated once for both: `null` is UNKNOWN and prints "—", never
 * "0". A daily point with no published evidence carries `null`, and a chart
 * caption that renders it as a zero invents a dry day.
 */
export function formatAccumulated(value: number | null | undefined, unit: string): string {
  return value === null || value === undefined ? '—' : `${value.toFixed(1)} ${unit}`;
}

/**
 * The percentile as a PHRASE, for the annual textual equivalent.
 *
 * Not `formatMetricValue`: the server sends `unit: "percentil"` (deliberately
 * not `"%"`, so nobody reads a rank as a share of anything), and "27.4
 * percentil" is not a sentence a reader parses. `baseline` is passed in rather
 * than hardcoded — the period is server-driven, and a constant here is the
 * RISK-001 defect that let the UI keep asserting 1991-2020 after the normals
 * were regenerated over another period.
 *
 * Rounded to a whole percentile: a Weibull rank over ~31 samples moves in
 * steps of roughly 3, so the tenth is precision the number does not have. A
 * served 0 stays "0" — the driest year on record is data, not a missing value.
 */
export function percentilePhrase(metric: RainfallMetric, baseline: string): string {
  return metric.value === null
    ? `Percentil de ${baseline}: —`
    : `Percentil ${Math.round(metric.value)} de ${baseline}`;
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
