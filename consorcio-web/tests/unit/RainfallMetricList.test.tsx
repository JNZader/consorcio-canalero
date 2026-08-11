/**
 * RainfallMetricList.test.tsx (Lluvia insights — slice 4, tasks 4.7/4.8;
 * Lluvia UX — the row/group/list split, slice 1)
 *
 * The badged metric surface. `AnnualText` and its percentile phrase moved to
 * `RainfallAnswerCard` when the hierarchy was reordered — the equivalent has to
 * live above the first fold, and this list now renders INSIDE one.
 *
 * The rules this file still locks are the ones the repo has already paid for:
 *   - the baseline period prints AS SERVED (`snapshot.baseline`), never as a
 *     constant in the frontend — the RISK-001 lesson from `PrecipChart`;
 *   - a metric with no value prints "—", never "0";
 *   - `exclude` takes a group OUT OF THIS LIST without dropping it from the
 *     view: the antecedents render in their own fold, and the technical fold
 *     shows everything the card and that fold did not already show.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
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

function renderList(
  snap: RainfallAnalysisSnapshot,
  exclude?: readonly string[]
): ReturnType<typeof render> {
  const ui: ReactElement = (
    <MantineProvider env="test">
      <RainfallMetricList snapshot={snap} exclude={exclude} />
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

describe('RainfallMetricList — a state badge is a word, not a fragment (OWN-003)', () => {
  // The owner's screenshot of the deployed 380 px panel: `PROVISIO… FALLB…
  // DISPONI…`. Three badges competed for one row's width and every one of them
  // ellipsized. A truncated badge is worse than no badge: it is unreadable AND
  // it still looks like data.
  //
  // jsdom has NO LAYOUT, so this cannot assert pixels — and pretending
  // otherwise would be the fake measurement this repo keeps refusing. What it
  // asserts is the CONTENT BOUND that makes truncation unreachable: ONE badge
  // per row, carrying a short vocabulary word and nothing else.
  const loudMetric = () =>
    metric({
      metric: 'd7',
      value: null,
      state: 'suppressed',
      reason: 'coverage_below_threshold',
      temporal_state: 'provisional',
      fallback_used: true,
    });

  it('renders exactly one state badge, whole, with every other fact still reachable', () => {
    renderList(snapshot({ antecedents: { d7: loudMetric() } }));

    const row = screen.getByTestId('rainfall-metric-d7');
    const badges = row.querySelectorAll('[data-metric-state]');
    expect(badges).toHaveLength(1);

    const badgeText = badges[0]?.textContent ?? '';
    expect(badgeText).toBe('Suprimida');
    expect(badgeText).not.toMatch(/…|\.\.\./);
    expect(['Disponible', 'Parcial', 'Suprimida', 'No disponible']).toContain(badgeText);
    // The badge no longer carries the reason — which is the whole reason it
    // used to overflow — but the reason is not lost, it has its own line.
    expect(badgeText).not.toContain('coverage_below_threshold');
    expect(row.textContent).toContain('coverage_below_threshold');
  });

  it('keeps the provisional and fallback facts as readable markers', () => {
    renderList(snapshot({ antecedents: { d7: loudMetric() } }));

    const row = screen.getByTestId('rainfall-metric-d7');
    // Still stated, still whole words — they are simply no longer competing
    // with the state badge and the value for one nowrap row.
    expect(within(row).getByText('Provisional')).toBeInTheDocument();
    expect(within(row).getByText('Fallback')).toBeInTheDocument();
    expect(row.textContent).not.toMatch(/…|\.\.\./);
  });

  it('states the state of every metric, one badge each', () => {
    renderList(
      snapshot({
        antecedents: {
          d7: metric({ metric: 'd7', state: 'partial', coverage: 0.8 }),
          d30: metric({ metric: 'd30', value: null, state: 'unavailable', reason: 'sin fuente' }),
        },
      })
    );

    expect(
      screen.getByTestId('rainfall-metric-d7').querySelectorAll('[data-metric-state]')
    ).toHaveLength(1);
    expect(screen.getByTestId('rainfall-metric-d7').textContent).toContain('Parcial');
    expect(screen.getByTestId('rainfall-metric-d30').textContent).toContain('No disponible');
    expect(screen.getByTestId('rainfall-metric-d30').textContent).toContain('sin fuente');
  });
});

describe('RainfallMetricList — the exclude seam (slice 1 fold split)', () => {
  const withAntecedents = () =>
    snapshot({
      antecedents: {
        d7: metric({ metric: 'd7', value: 31 }),
        d30: metric({ metric: 'd30', value: 83.7 }),
      },
    });

  it('exclude keeps a group out of this list without dropping it from the snapshot', () => {
    // The antecedents get their own fold with the values in its collapsed
    // header, so the technical fold must not print them a second time — but
    // the SNAPSHOT is untouched and the group is still rendered, elsewhere.
    const snap = withAntecedents();

    const first = renderList(snap);
    expect(screen.getByTestId('rainfall-metric-d7')).toBeInTheDocument();
    expect(screen.getByTestId('rainfall-metric-d30')).toBeInTheDocument();
    first.unmount();

    renderList(snap, ['antecedents']);
    expect(screen.queryByTestId('rainfall-metric-d7')).toBeNull();
    expect(screen.queryByTestId('rainfall-metric-d30')).toBeNull();
    // Everything else is still here — exclusion is one group, not a filter on
    // the whole list.
    expect(screen.getByTestId('rainfall-metric-selected')).toBeInTheDocument();
    expect(screen.getByTestId('rainfall-metric-normal')).toBeInTheDocument();
    expect(screen.getByTestId('rainfall-summary')).toBeInTheDocument();
  });

  it('excluding a group the snapshot does not serve changes nothing', () => {
    renderList(withAntecedents(), ['intensity']);

    expect(screen.getByTestId('rainfall-metric-d7')).toBeInTheDocument();
    expect(screen.getByTestId('rainfall-metric-selected')).toBeInTheDocument();
  });

  it('renders every served group when nothing is excluded', () => {
    // `exclude`, not `include`: a group nobody named still renders. An
    // include-list would silently drop whatever the server adds next (R6).
    renderList(withAntecedents());

    for (const testId of [
      'rainfall-metric-selected',
      'rainfall-metric-normal',
      'rainfall-metric-percentile',
      'rainfall-metric-d7',
      'rainfall-metric-d30',
    ]) {
      expect(screen.getByTestId(testId)).toBeInTheDocument();
    }
  });
});
