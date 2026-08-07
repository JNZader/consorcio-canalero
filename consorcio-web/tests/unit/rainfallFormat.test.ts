/**
 * rainfallFormat.test.ts  (Lluvia v2 — Task 3.1 RED)
 *
 * Shared state/value formatting used by BOTH the rendered ficha and the export
 * summary (Task 3.4): one formatter, so the badge a user reads and the text the
 * CSV carries can never disagree. Null is never rendered as zero (spec
 * "Partial, Suppressed, and Unavailable Data States").
 */

import { describe, expect, it } from 'vitest';

import type { RainfallMetric } from '../../src/lib/api/rainfall';
import {
  describeMetricLine,
  describeMetricState,
  formatMetricValue,
  metricLabel,
} from '../../src/components/map2d/rainfall/rainfallFormat';

function metric(overrides: Partial<RainfallMetric> = {}): RainfallMetric {
  return {
    metric: 'selected',
    value: 850.24,
    unit: 'mm',
    state: 'available',
    reason: null,
    interval_start: '2025-01-01T00:00:00Z',
    interval_end: '2026-01-01T00:00:00Z',
    coverage: 1,
    completeness: 1,
    quality: { score: 0.9 },
    discrepancies: [],
    temporal_state: 'final',
    revision: 'policy-v1',
    provenance: {
      source_id: 'chirps-v3-final',
      source_class: 'estimated_satellite',
      method: 'sum',
      nominal_resolution: '0.05°',
      aggregation: 'daily',
      spatial_scope: 'zone',
      freshness: '2026-01-02T00:00:00Z',
      available_through: '2025-12-31T00:00:00Z',
    },
    fallback_used: false,
    ...overrides,
  };
}

describe('metricLabel', () => {
  it('labels the known metrics in Spanish', () => {
    expect(metricLabel('selected')).toBe('Acumulado del año');
    expect(metricLabel('normal')).toBe('Normal 1991–2020');
    expect(metricLabel('d30')).toBe('Antecedente 30 días');
    expect(metricLabel('duration')).toBe('Duración del evento');
  });

  it('falls back to the raw key for an unknown metric', () => {
    expect(metricLabel('p95')).toBe('p95');
  });
});

describe('formatMetricValue', () => {
  it('formats value and unit, never inventing a zero for null', () => {
    expect(formatMetricValue(metric())).toBe('850.2 mm');
    expect(formatMetricValue(metric({ value: null, state: 'unavailable', reason: 'sin fuente' }))).toBe(
      '—'
    );
    // A SERVED zero is data and must survive.
    expect(formatMetricValue(metric({ value: 0 }))).toBe('0.0 mm');
  });
});

describe('describeMetricState', () => {
  it('distinguishes the four states, carrying the reason where applicable', () => {
    expect(describeMetricState(metric())).toBe('Disponible');
    expect(describeMetricState(metric({ state: 'partial', coverage: 0.8 }))).toBe('Parcial');
    expect(describeMetricState(metric({ state: 'suppressed', value: null, reason: 'coverage_below_threshold' }))).toBe(
      'Suprimida: coverage_below_threshold'
    );
    expect(describeMetricState(metric({ state: 'unavailable', value: null, reason: 'sin fuente' }))).toBe(
      'No disponible: sin fuente'
    );
  });

  it('never renders suppressed or unavailable as zero or as a bare label', () => {
    const text = describeMetricState(metric({ state: 'suppressed', value: null, reason: 'cadence_unsupported' }));
    expect(text).not.toContain('0');
    expect(text).toContain('cadence_unsupported');
  });
});

describe('describeMetricLine', () => {
  it('composes label, value and state in one textual line (textual chart row)', () => {
    expect(describeMetricLine('selected', metric())).toBe(
      'Acumulado del año: 850.2 mm — Disponible'
    );
  });

  it('exposes coverage on a partial metric', () => {
    const line = describeMetricLine('d7', metric({ state: 'partial', coverage: 0.8 }));
    expect(line).toContain('Antecedente 7 días');
    expect(line).toContain('Parcial');
    expect(line).toContain('80%');
  });
});
