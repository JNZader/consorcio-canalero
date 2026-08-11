/**
 * RainfallMetricList.test.tsx (Lluvia insights — slice 4, tasks 4.7/4.8)
 *
 * `AnnualText` is the chart's TEXTUAL EQUIVALENT (design "charts have textual
 * equivalents"), which is why the percentile belongs there and not only in the
 * badged row below: a reader who cannot see the two lines still has to be able
 * to answer "was this year wet or dry against the record?".
 *
 * The rules this file locks are the ones the repo has already paid for twice:
 *   - the baseline period prints AS SERVED (`snapshot.baseline`), never as a
 *     constant in the frontend — the RISK-001 lesson from `PrecipChart`;
 *   - a metric with no value prints "—", never "0"; a served percentile of 0 IS
 *     data and must survive as "0";
 *   - a percentile the analysis did not carry produces no phrase at all rather
 *     than an empty slot that reads like a broken render.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';

import { RainfallMetricList } from '../../src/components/map2d/rainfall/RainfallMetricList';
import type { RainfallAnalysisSnapshot, RainfallMetric } from '../../src/lib/api/rainfall';

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

function snapshot(overrides: Partial<RainfallAnalysisSnapshot> = {}): RainfallAnalysisSnapshot {
  return {
    analysis_revision_id: 'rev-9',
    data_revision: 'ab'.repeat(32),
    scope: { kind: 'zone', id: 'zona-ne', version: '3' },
    regional_estimate: true,
    year: 2025,
    comparison_end: '2025-12-31',
    baseline: '1991-2020',
    annual: {
      selected: metric({ metric: 'selected', value: 850.24 }),
      normal: metric({ metric: 'normal', value: 1013.8 }),
      percentile: metric({ metric: 'percentile', value: 27.4, unit: 'percentil' }),
    },
    ...overrides,
  };
}

function renderList(snap: RainfallAnalysisSnapshot): ReturnType<typeof render> {
  const ui: ReactElement = (
    <MantineProvider env="test">
      <RainfallMetricList snapshot={snap} />
    </MantineProvider>
  );
  return render(ui);
}

describe('RainfallMetricList — AnnualText percentile phrase (4.7)', () => {
  it('states the percentile beside the year and the normal', () => {
    renderList(snapshot());

    const text = screen.getByTestId('rainfall-annual-text');
    expect(text).toHaveTextContent('Año 2025: 850.2 mm');
    expect(text).toHaveTextContent('Normal 1991-2020: 1013.8 mm');
    // Whole percentiles: a Weibull rank over 31 samples moves in steps of ~3,
    // so a tenth of a percentile is precision the number does not have.
    expect(text).toHaveTextContent('Percentil 27 de 1991-2020');
  });

  it('prints the baseline period AS SERVED, in the phrase too', () => {
    // RISK-001 all over again: regenerating the normals over another period
    // must change this line by itself, with no frontend edit involved.
    renderList(snapshot({ baseline: '2001-2030' }));

    const text = screen.getByTestId('rainfall-annual-text');
    expect(text).toHaveTextContent('Percentil 27 de 2001-2030');
    expect(text.textContent).not.toContain('1991-2020');
  });

  it('keeps a served percentile of 0 as a number, never as a missing value', () => {
    // The driest year on record ranks at the bottom. That is DATA — the single
    // most expensive thing this UI could round away into "—".
    renderList(
      snapshot({
        annual: {
          selected: metric({ metric: 'selected', value: 12.5 }),
          percentile: metric({ metric: 'percentile', value: 0, unit: 'percentil' }),
        },
      })
    );

    expect(screen.getByTestId('rainfall-annual-text')).toHaveTextContent('Percentil 0 de 1991-2020');
  });

  it('renders no value for a suppressed percentile, and never a zero', () => {
    renderList(
      snapshot({
        annual: {
          selected: metric({ metric: 'selected', value: 850.24 }),
          percentile: metric({
            metric: 'percentile',
            value: null,
            unit: 'percentil',
            state: 'suppressed',
            reason: 'baseline_years_below_minimum',
          }),
        },
      })
    );

    const text = screen.getByTestId('rainfall-annual-text');
    expect(text.textContent).toContain('—');
    expect(text.textContent).not.toMatch(/Percentil 0\b/);
    // The reason is not lost: the badged row below still carries it verbatim.
    expect(screen.getByTestId('rainfall-metric-percentile').textContent).toContain(
      'baseline_years_below_minimum'
    );
  });

  it('omits the phrase entirely when the analysis carries no percentile', () => {
    renderList(
      snapshot({
        annual: { selected: metric({ metric: 'selected', value: 850.24 }) },
      })
    );

    const text = screen.getByTestId('rainfall-annual-text');
    expect(text).toHaveTextContent('Año 2025: 850.2 mm');
    expect(text.textContent).not.toMatch(/Percentil/i);
  });
});
