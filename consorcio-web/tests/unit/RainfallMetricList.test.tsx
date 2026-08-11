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

/** The Spanish labels `service.SUMMARY_METRIC_LABELS` carries for the annual
 *  group. `normal` is period-LESS here for the same reason it is there: the
 *  period comes from the envelope. */
const SUMMARY_LABELS: Record<string, string> = {
  selected: 'Acumulado del año',
  normal: 'Normal',
  percentile: 'Percentil histórico',
};

/**
 * The narrative the BACKEND would serve for this envelope
 * (`service.rainfall_summary`), derived from the same metrics and the same
 * baseline the panel is about to render.
 *
 * Derived rather than hardcoded, and it is not decoration: the panel renders
 * `snapshot.summary` INSIDE `rainfall-metrics`, so without it the period sweep
 * below is blind to a whole third of its own subtree — and a hardcoded string
 * would go stale against the `baseline` override the sweep exists to test,
 * making the fixture itself the finding.
 */
function servedSummary(annual: Record<string, RainfallMetric>, baseline: string): string {
  const label = (name: string) =>
    name === 'normal' ? `Normal ${baseline}` : (SUMMARY_LABELS[name] ?? name);
  const available: string[] = [];
  const missing: string[] = [];
  for (const [name, entry] of Object.entries(annual)) {
    if (entry.state === 'available' && entry.value !== null) {
      available.push(`${label(name)} ${entry.value.toFixed(1)} ${entry.unit}`);
    } else {
      const state = entry.state === 'suppressed' ? 'suprimida' : 'no disponible';
      missing.push(`${label(name)} (${state}: ${entry.reason})`);
    }
  }
  return [
    available.length > 0 ? `Disponibles: ${available.join('; ')}.` : '',
    missing.length > 0 ? `Sin dato: ${missing.join('; ')}.` : '',
  ]
    .filter(Boolean)
    .join(' ');
}

function snapshot(overrides: Partial<RainfallAnalysisSnapshot> = {}): RainfallAnalysisSnapshot {
  const baseline = overrides.baseline ?? '1991-2020';
  const annual = overrides.annual ?? {
    selected: metric({ metric: 'selected', value: 850.24 }),
    normal: metric({ metric: 'normal', value: 1013.8 }),
    percentile: metric({ metric: 'percentile', value: 27.4, unit: 'percentil' }),
  };
  return {
    analysis_revision_id: 'rev-9',
    data_revision: 'ab'.repeat(32),
    scope: { kind: 'zone', id: 'zona-ne', version: '3' },
    regional_estimate: true,
    year: 2025,
    comparison_end: '2025-12-31',
    baseline,
    annual,
    summary: servedSummary(annual, baseline),
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

describe('RainfallMetricList — the served baseline on the badged surfaces (4.7)', () => {
  it('prints the baseline period AS SERVED, on every surface of the list', () => {
    // RISK-001 all over again: regenerating the normals over another period
    // must change this list by itself, with no frontend edit involved.
    const snap = snapshot({ baseline: '2001-2030' });
    renderList(snap);

    // The two surfaces the LIST names a period on, asserted one by one so a
    // failure says WHICH one regressed. The phrase's own half of this contract
    // moved to `RainfallAnswerCard.test.tsx` with `AnnualText`.
    expect(screen.getByTestId('rainfall-metric-normal')).toHaveTextContent('Normal 2001-2030');
    expect(screen.getByTestId('rainfall-summary')).toHaveTextContent('Normal 2001-2030 1013.8 mm');

    // …and the sweep that catches the surface nobody thought of. It compares
    // against `snapshot.baseline` rather than excluding the literal 1991-2020,
    // because a detector written as a denylist only ever catches the one
    // constant it was written for: this one fires on ANY period the server did
    // not serve, in either dash spelling.
    //
    // Two failure modes of the previous version, both real (LI4-004 / CC-002):
    // it was scoped to the annual-text node while the hardcode lived in the
    // badged row, and it spelled the period with a HYPHEN against a constant
    // that used an EN-DASH — so it could not fire against the one label it
    // existed to catch.
    const periods = [
      ...(screen.getByTestId('rainfall-metrics').textContent ?? '').matchAll(
        /\d{4}\s*[-–]\s*\d{4}/g
      ),
    ].map(([period]) => period);

    expect(periods.length).toBeGreaterThanOrEqual(2);
    expect([...new Set(periods)]).toEqual([snap.baseline]);
  });

  it('keeps a suppressed percentile reachable by state and reason in its row', () => {
    // The badged row is where the reason survives once the phrase above it
    // prints only "—" (the card carries it too, on the always-visible surface).
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

    const row = screen.getByTestId('rainfall-metric-percentile');
    expect(row.textContent).toContain('baseline_years_below_minimum');
    expect(row.textContent).not.toMatch(/\b0 percentil\b/);
  });
});
