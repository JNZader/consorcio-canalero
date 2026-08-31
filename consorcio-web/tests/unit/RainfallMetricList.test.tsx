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

import {
  RainfallMetricGroup,
  RainfallMetricList,
} from '../../src/components/map2d/rainfall/RainfallMetricList';
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

  it('shows NO chip at all for a plain available, definitive metric', () => {
    // Exception-only: a chip on every row is a row of chips nobody reads, and
    // in 380 px they fragment. The state is still in the row's text.
    renderList(snapshot({ antecedents: { d7: metric({ metric: 'd7', value: 31 }) } }));

    const row = screen.getByTestId('rainfall-metric-d7');
    expect(row.querySelectorAll('[data-metric-state]')).toHaveLength(0);
    // The chip is gone; the FACT is not. Dropping a chip must never drop a
    // served field — the fold is where the disclosure floor is discharged.
    expect(row.textContent).toContain('Estado: Disponible');
  });

  it('shows exactly one Spanish chip for a fallback-fed value', () => {
    renderList(
      snapshot({
        antecedents: { d7: metric({ metric: 'd7', value: 31, fallback_used: true }) },
      })
    );

    const row = screen.getByTestId('rainfall-metric-d7');
    const chips = row.querySelectorAll('[data-metric-state]');
    expect(chips).toHaveLength(1);
    // A full Spanish word, never the wire token: `FALLBACK` is not copy.
    expect(chips[0]?.textContent).toBe('Dato provisorio');
    expect(chips[0]?.textContent).not.toMatch(/…|\.\.\.|FALLBACK/i);
    // …and the precise fact stays in the text, which is where the disclosure
    // floor is discharged.
    expect(within(row).getByText('Fuente alternativa')).toBeInTheDocument();
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
    expect(within(row).getByText('Fuente alternativa')).toBeInTheDocument();
    expect(row.textContent).not.toMatch(/…|\.\.\./);
  });

  it('renders the percentile as a phrase, not as a suffix', () => {
    // 1.28(b): `percentil` is a RANK, so in Spanish the word leads and the
    // number qualifies it. The suffix pattern produced "46.9 percentil" while
    // the card three lines up said "Percentil 47" — one fact, two spellings,
    // one of them not a phrase at all.
    renderList(
      snapshot({
        annual: { percentile: metric({ metric: 'percentile', value: 46.9, unit: 'percentil' }) },
      })
    );

    const row = screen.getByTestId('rainfall-metric-percentile');
    expect(row.textContent).toContain('Percentil 46.9');
    expect(row.textContent).not.toContain('46.9 percentil');
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

describe('RainfallMetricList — the key-driven renderer (R6, design D8)', () => {
  /** A root key the wire carried and this frontend has no title for. Cast
   *  through `unknown` because `RainfallAnalysisSnapshot` declares the groups it
   *  knows — which is exactly the assumption R6 says must not be load-bearing. */
  function withRootKey(key: string, value: unknown): RainfallAnalysisSnapshot {
    return { ...snapshot(), [key]: value } as unknown as RainfallAnalysisSnapshot;
  }

  it('isMetricGroup is total — a scalar, null, an array or {} renders no group and does NOT throw', () => {
    // `'metric' in "texto"` is a `TypeError`, so a partial guard would take the
    // whole panel down the day the backend adds a scalar root key. The e2e
    // fixture already serves `summary: 'Año seco…'` and
    // `source_health: {stations: 1}` at the root, so this is not hypothetical.
    for (const value of ['texto', 42, null, [metric()], {}, true] as const) {
      const rendered = renderList(withRootKey('novedad', value));
      expect(screen.getByTestId('rainfall-metrics')).toBeInTheDocument();
      expect(screen.queryByText('novedad')).toBeNull();
      rendered.unmount();
    }
  });

  it('an unknown group renders under its RAW key, with raw metric labels', () => {
    // The repo's standing rule for an untranslated fact (`metricLabel ?? key`,
    // `export._label`): show it, never drop it. A group nobody named still
    // reaches the reader, titled with the key the server used.
    renderList(withRootKey('intensity', { p24h: metric({ metric: 'p24h', value: 12.5 }) }));

    expect(screen.getByText('intensity')).toBeInTheDocument();
    const row = screen.getByTestId('rainfall-metric-p24h');
    expect(row.textContent).toContain('p24h');
    expect(row.textContent).toContain('12.5 mm');
  });

  it('renders every served group, known first and then the unknown ones', () => {
    const snap = withRootKey('turbulencia', { x1: metric({ metric: 'x1', value: 4 }) });
    renderList(snap);

    for (const testId of [
      'rainfall-metric-selected',
      'rainfall-metric-normal',
      'rainfall-metric-percentile',
      'rainfall-metric-x1',
    ]) {
      expect(screen.getByTestId(testId)).toBeInTheDocument();
    }
    // Known groups keep their published order; the unrecognised one lands after
    // them rather than in the middle of the vocabulary the reader knows.
    const rendered = screen.getByTestId('rainfall-metrics');
    const selected = screen.getByTestId('rainfall-metric-selected');
    const unknown = screen.getByTestId('rainfall-metric-x1');
    expect(
      (selected.compareDocumentPosition(unknown) & Node.DOCUMENT_POSITION_FOLLOWING) ===
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBe(true);
    expect(rendered).toContainElement(unknown);
  });

  it('never renders a non-group root key as a group', () => {
    // The deny-list. `scope` is an object of strings and `source_health` is
    // `unknown` on the wire: a future `{chirps: {metric, state}}` shape would
    // pass the guard and render as a metric group ON TOP of the single
    // analysis-level line D9 gives it — the double-rendering the enumerated
    // floor forbids.
    renderList(
      withRootKey('source_health', { chirps: metric({ metric: 'chirps', value: 1 }) })
    );

    expect(screen.queryByText('source_health')).toBeNull();
    expect(screen.queryByTestId('rainfall-metric-chirps')).toBeNull();
  });

  it('the excluded group stays excluded even when it is unknown', () => {
    renderList(withRootKey('turbulencia', { x1: metric({ metric: 'x1', value: 4 }) }), [
      'turbulencia',
    ]);

    expect(screen.queryByTestId('rainfall-metric-x1')).toBeNull();
    expect(screen.getByTestId('rainfall-metric-selected')).toBeInTheDocument();
  });
});

/**
 * The antecedents fold, after the six rolling-window reference metrics joined
 * the group (SDD S3, backend design D1/D7).
 *
 * The fold mounts `RainfallMetricGroup` directly — that is what these tests
 * render, rather than driving the whole panel, so a failure names the renderer
 * and not the panel's plumbing.
 */
describe('RainfallMetricGroup — the antecedent reference rows (S3)', () => {
  /** The nine keys `compute.build_snapshot` emits into `antecedents`, in the
   *  order it emits them (total → normal → percentile, per window). */
  function antecedentsGroup(): Record<string, RainfallMetric> {
    const reference = (name: string, unit: string, value: number | null): RainfallMetric =>
      metric({
        metric: name,
        unit,
        value,
        state: value === null ? 'suppressed' : 'available',
        reason: value === null ? 'baseline_years_below_minimum' : null,
        quality: { score: 1, reference_scope: 'zone' },
      });
    return {
      d7: metric({ metric: 'd7', value: 21 }),
      d7_normal: reference('d7_normal', 'mm', 7),
      d7_percentile: reference('d7_percentile', 'percentil', 96.9),
      d30: metric({ metric: 'd30', value: 90 }),
      d30_normal: reference('d30_normal', 'mm', 30),
      d30_percentile: reference('d30_percentile', 'percentil', 96.9),
      d90: metric({ metric: 'd90', value: null, state: 'suppressed', reason: 'antecedent_window_incomplete' }),
      d90_normal: reference('d90_normal', 'mm', null),
      d90_percentile: reference('d90_percentile', 'percentil', null),
    };
  }

  function renderGroup(group: Record<string, RainfallMetric>, baseline = '1991-2020') {
    return render(
      <MantineProvider env="test">
        <RainfallMetricGroup group={group} baseline={baseline} />
      </MantineProvider>
    );
  }

  it('states the reference scope in NAMED Spanish, not as a raw quality fragment', () => {
    // D7's correction to r1: `quality` renders through `stringifyUnknownFields`
    // as raw English `key=value` under `Calidad:`, and `reference_scope=zone`
    // does not discharge the spec's "the fold STATES that limit". One named
    // line, beside the quality line, is what does.
    renderGroup(antecedentsGroup());

    expect(screen.getByTestId('rainfall-metric-d7_normal')).toHaveTextContent(
      'Alcance de la referencia: zona'
    );
  });

  it('states it on a SUPPRESSED reference metric too', () => {
    // The limit is the REQUIRED scope of the reference, not the scope this
    // analysis ran at — so it is exactly as true when the value is withheld,
    // and that is the case where a reader most needs to know what was asked
    // for. (`compute._antecedent_reference_metrics` emits it off-zone too.)
    renderGroup(antecedentsGroup());

    const row = screen.getByTestId('rainfall-metric-d90_percentile');
    expect(row).toHaveTextContent('Alcance de la referencia: zona');
    expect(row).toHaveTextContent('Motivo: baseline_years_below_minimum');
  });

  it('never emits the line for a metric that does not carry the key', () => {
    // The whole failure mode of a scope line: a row that always prints one
    // states a limit about a metric that has none. The antecedent TOTALS are
    // the live example — they are not zone-limited, and they sit in this very
    // group beside the six that are.
    renderGroup(antecedentsGroup());

    expect(screen.getByTestId('rainfall-metric-d7')).not.toHaveTextContent(
      'Alcance de la referencia'
    );
    // …and a reference metric served with NO quality at all, which is the
    // stripped four-field shape `service._unavailable` rewrites to.
    renderGroup({
      d7_normal: metric({ metric: 'd7_normal', value: null, state: 'unavailable', quality: {} }),
    });
    expect(screen.getAllByTestId('rainfall-metric-d7_normal').at(-1)).not.toHaveTextContent(
      'Alcance de la referencia'
    );
  });

  it('renders all NINE antecedent rows, each under its own Spanish name', () => {
    // Spec R4 S1: a suppressed row is still a row. Nine keys in, nine rows out
    // — the fold is where the reader goes for what was served, and a dropped
    // suppression is a suppression nobody can act on.
    renderGroup(antecedentsGroup(), '2001-2030');

    for (const key of Object.keys(antecedentsGroup())) {
      expect(screen.getByTestId(`rainfall-metric-${key}`)).toBeInTheDocument();
    }
    // The period travels to the three window normals, exactly as it does to
    // the annual one — the LI4-004 comparison, on the surface it happens on.
    for (const key of ['d7_normal', 'd30_normal', 'd90_normal']) {
      expect(screen.getByTestId(`rainfall-metric-${key}`)).toHaveTextContent('2001-2030');
    }
    // …and NOT to the percentiles.
    for (const key of ['d7_percentile', 'd30_percentile', 'd90_percentile']) {
      expect(screen.getByTestId(`rainfall-metric-${key}`)).not.toHaveTextContent('2001-2030');
    }
  });
});

describe('RainfallMetricList — compressed discrepancies (ficha wall)', () => {
  const DAY_MS = 86_400_000;

  function expectedIntervalDays(count: number, startIso = '2024-01-02T00:00:00+00:00'): string[] {
    const startMs = Date.parse(startIso);
    return Array.from({ length: count }, (_, index) => {
      const iso = new Date(startMs + index * DAY_MS).toISOString().replace('.000Z', '+00:00');
      return `expected_interval=${iso}`;
    });
  }

  it('renders many expected_interval values as one range, not the raw wall', () => {
    const count = 153;
    const firstIso = '2024-01-02T00:00:00+00:00';
    const lastIso = new Date(Date.parse(firstIso) + (count - 1) * DAY_MS)
      .toISOString()
      .replace('.000Z', '+00:00');
    renderList(
      snapshot({
        annual: {
          selected: metric({ metric: 'selected', discrepancies: expectedIntervalDays(count) }),
        },
      })
    );

    const row = screen.getByTestId('rainfall-metric-selected');
    expect(row).toHaveTextContent(
      `Discrepancias: expected_interval=${firstIso} → ${lastIso} (${count})`
    );
    expect(row.textContent).not.toContain('expected_interval=2024-01-03T00:00:00+00:00');
    expect(row.textContent).not.toMatch(
      /expected_interval=2024-01-02T00:00:00\+00:00; expected_interval=/
    );
  });

  it('omits the line when discrepancies are empty', () => {
    renderList(snapshot());
    expect(screen.getByTestId('rainfall-metric-selected')).not.toHaveTextContent('Discrepancias:');
  });
});
