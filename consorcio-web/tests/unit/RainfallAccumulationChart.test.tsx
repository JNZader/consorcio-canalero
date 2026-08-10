/**
 * RainfallAccumulationChart.test.tsx (Lluvia insights — slice 4, D8)
 *
 * The accumulated-rainfall chart the owner asked for: "si selecciono un año
 * podría mostrarse además en el gráfico de arriba como comparando con el
 * histórico". Locks the disclosures that make that comparison honest:
 *   - 4.1 BOTH SERIES AND BOTH DATES: the selected year's accumulation and the
 *     1991-2020 normal curve are two separate lines, a `ReferenceLine` marks
 *     `comparison_end`, and the footer states `comparison_end` AND
 *     `available_through` — under provider lag those are different days, and a
 *     chart that shows only the first reads as a dry spell.
 *   - 4.2 STALENESS: `consistent_with_snapshot: false` renders the curve PLUS
 *     an alert and a re-request action (design D3: "a silent redraw is
 *     prohibited"); absent when the pin is true.
 *   - 4.2b NORMAL-CURVE STATE: `integrity_refused` MUST read differently from
 *     `suppressed` — both arrive with every `normal_accumulated: null`, so a
 *     chart that keys on "is there a curve?" erases the observable half of
 *     LI3A-001. Asserted on TEXT and on a state attribute, never on colour:
 *     a colour-only distinction is not a distinction for the operator this
 *     disclosure exists for.
 *   - 4.3 RE-REQUEST: the action re-POSTs `/analyses` and handles a newer
 *     revision (200), a labelled queued answer (202) through the panel's
 *     existing poll path, and the honest no-op (200 with the SAME revision).
 *   - 4.5 CAMPAIGN PRESET: a display window over the SAME series — no
 *     `/analyses` request may fire, which is what keeps spec.md:117-125 intact.
 *
 * HOW THE CHART IS MADE ASSERTABLE: same seam as `PrecipChart.test.tsx` —
 * recharts' `ResponsiveContainer` measures through `ResizeObserver` and
 * happy-dom reports 0x0, so it is swapped for a fixed-size pass-through. The
 * rest of recharts is the real library.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { type ReactElement, cloneElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Hoisted before the component import: the component pulls `ResponsiveContainer`
// in at module scope.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    // The generic on `ReactElement` is what lets `cloneElement` accept the
    // size props: with a bare `ReactElement` the props type is `unknown` and
    // `tsc` rejects them. `PrecipChart.test.tsx` has the same seam and never
    // showed it — that file is outside the typecheck project (LI3A-004).
    ResponsiveContainer: ({
      children,
    }: {
      children: ReactElement<{ width?: number; height?: number }>;
    }) => cloneElement(children, { width: 600, height: 300 }),
  };
});

vi.mock('../../src/lib/api/rainfall', async () => {
  const actual = await vi.importActual<typeof import('../../src/lib/api/rainfall')>(
    '../../src/lib/api/rainfall'
  );
  return {
    ...actual,
    fetchRainfallSeries: vi.fn(),
    fetchRainfallAnalysis: vi.fn(),
  };
});

import type {
  RainfallAnalysisSnapshot,
  RainfallMetric,
  RainfallSeriesPoint,
  RainfallSeriesResponse,
} from '../../src/lib/api/rainfall';
import { fetchRainfallAnalysis, fetchRainfallSeries } from '../../src/lib/api/rainfall';
import { RainfallAccumulationChart } from '../../src/components/map2d/rainfall/RainfallAccumulationChart';
import { rainfallAnalysisQueryKey } from '../../src/hooks/useRainfallAnalysis';

const ZONE = { kind: 'zone' as const, id: 'zona-ne', version: '3' };
const YEAR = 2025;
/** The last day the provider published — deliberately BEFORE `comparison_end`. */
const AVAILABLE_THROUGH = '2025-10-05';
const COMPARISON_END = '2025-10-05';

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
      freshness: '2025-10-06T00:00:00Z',
      available_through: `${AVAILABLE_THROUGH}T00:00:00Z`,
    },
    fallback_used: false,
    ...overrides,
  };
}

function snapshot(overrides: Partial<RainfallAnalysisSnapshot> = {}): RainfallAnalysisSnapshot {
  return {
    analysis_revision_id: 'rev-9',
    data_revision: 'ab'.repeat(32),
    scope: ZONE,
    regional_estimate: true,
    year: YEAR,
    comparison_end: COMPARISON_END,
    baseline: '1991-2020',
    annual: {
      selected: metric({ metric: 'selected', value: 850.24 }),
      normal: metric({ metric: 'normal', value: 1013.8 }),
    },
    ...overrides,
  };
}

/**
 * A daily series spanning Jan 1 → `AVAILABLE_THROUGH`, so the September window
 * of the campaign preset has real points on both sides of its boundary.
 */
function points(): RainfallSeriesPoint[] {
  const built: RainfallSeriesPoint[] = [];
  let accumulated = 0;
  let normal = 0;
  const cursor = new Date(Date.UTC(YEAR, 0, 1));
  const last = new Date(`${AVAILABLE_THROUGH}T00:00:00Z`);
  while (cursor <= last) {
    accumulated += 3;
    normal += 3.5;
    built.push({
      date: cursor.toISOString().slice(0, 10),
      mm: 3,
      accumulated,
      normal_accumulated: normal,
      state: 'available',
    });
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return built;
}

function series(overrides: Partial<RainfallSeriesResponse> = {}): RainfallSeriesResponse {
  return {
    analysis_revision_id: 'rev-9',
    data_revision: 'ab'.repeat(32),
    scope: ZONE,
    year: YEAR,
    unit: 'mm',
    comparison_end: COMPARISON_END,
    available_through: `${AVAILABLE_THROUGH}T00:00:00+00:00`,
    consistent_with_snapshot: true,
    consistency_reason: null,
    normal_curve_state: 'available',
    points: points(),
    ...overrides,
  };
}

/** A curve-less series: BOTH no-curve states arrive in exactly this shape. */
function curvelessPoints(): RainfallSeriesPoint[] {
  return points().map((point) => ({ ...point, normal_accumulated: null }));
}

let client: QueryClient;

function renderChart(snap: RainfallAnalysisSnapshot = snapshot()) {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui: ReactElement = (
    <QueryClientProvider client={client}>
      <MantineProvider env="test">
        <RainfallAccumulationChart snapshot={snap} />
      </MantineProvider>
    </QueryClientProvider>
  );
  return render(ui);
}

describe('RainfallAccumulationChart — both series and both dates (4.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series());
  });

  it('draws the selected year and the normal curve as two separate lines', async () => {
    const { container } = renderChart();

    await screen.findByTestId('rainfall-accumulation-chart');
    // TWO lines: the year and the 1991-2020 normal. One line would be the
    // owner's request half-implemented — there is nothing to compare against.
    await waitFor(() => expect(container.querySelectorAll('.recharts-line')).toHaveLength(2));
  });

  it('marks comparison_end with a reference line and states BOTH dates in the footer', async () => {
    const { container } = renderChart();

    await screen.findByTestId('rainfall-accumulation-chart');
    await waitFor(() =>
      expect(container.querySelectorAll('.recharts-reference-line-line').length).toBeGreaterThan(0)
    );

    const footer = screen.getByTestId('rainfall-accumulation-dates');
    expect(footer.textContent).toContain(COMPARISON_END);
    expect(footer.textContent).toContain(AVAILABLE_THROUGH);
  });

  it('says so when the provider has not published up to comparison_end', async () => {
    // Provider lag is the documented steady state (design D5/D6). The series
    // stops where the evidence does, and a reader who is not told that will
    // read the missing tail as a dry spell.
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({ comparison_end: '2025-12-31', available_through: `${AVAILABLE_THROUGH}T00:00:00Z` })
    );
    renderChart(snapshot({ comparison_end: '2025-12-31' }));

    const footer = await screen.findByTestId('rainfall-accumulation-dates');
    expect(footer.textContent).toContain('2025-12-31');
    expect(footer.textContent).toContain(AVAILABLE_THROUGH);
    expect(screen.getByTestId('rainfall-accumulation-lag')).toBeInTheDocument();
  });

  it('carries a textual equivalent of the plotted window and both end values', async () => {
    // The chart is `role="img"` over a label that names the window and both
    // final values, because a screen reader gets nothing from an SVG of ticks.
    renderChart();

    const chart = await screen.findByTestId('rainfall-accumulation-chart');
    expect(chart).toHaveAttribute('role', 'img');
    const label = chart.getAttribute('aria-label') ?? '';
    expect(label).toContain('2025-01-01');
    expect(label).toContain(AVAILABLE_THROUGH);
    expect(label).toMatch(/mm/);
  });
});

describe('RainfallAccumulationChart — staleness disclosure (4.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series());
  });

  it('renders the curve PLUS an alert and a re-request action when the pin is false', async () => {
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({ consistent_with_snapshot: false, consistency_reason: 'data_revision_moved' })
    );
    const { container } = renderChart();

    const alert = await screen.findByTestId('rainfall-series-stale');
    // The data is the FRESHER evidence, not garbage: it is still drawn.
    expect(container.querySelectorAll('.recharts-line')).toHaveLength(2);
    expect(alert.textContent).toMatch(/corrigieron/i);
    expect(alert.textContent).toContain('data_revision_moved');
    expect(screen.getByTestId('rainfall-series-rerequest')).toBeInTheDocument();
  });

  it('shows no staleness alert when the pin is true', async () => {
    renderChart();

    await screen.findByTestId('rainfall-accumulation-chart');
    expect(screen.queryByTestId('rainfall-series-stale')).toBeNull();
    expect(screen.queryByTestId('rainfall-series-rerequest')).toBeNull();
  });

  it('catches a stale tab: the series echo disagreeing with the snapshot in hand', async () => {
    // The server pin is authoritative and says CONSISTENT here — this is the
    // cheap client cross-check design D3 promised, and the only thing that
    // catches a snapshot left open in a tab while the server moved on.
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series({ data_revision: 'cd'.repeat(32) }));
    renderChart();

    const alert = await screen.findByTestId('rainfall-series-stale');
    expect(alert.textContent).toMatch(/pestaña|anterior/i);
    expect(screen.getByTestId('rainfall-series-rerequest')).toBeInTheDocument();
  });
});

describe('RainfallAccumulationChart — normal-curve state (4.2b)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders integrity_refused DISTINCTLY from suppressed, in copy and in state', async () => {
    // THE regression this task exists for. Both states arrive with every
    // `normal_accumulated: null` (backend D3 "Normal-curve integrity
    // amendment"), so the wire cannot tell them apart by shape — only by this
    // field. An honest absence and a curve that was computed and thrown away
    // for contradicting the card beside it are different facts.
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({ normal_curve_state: 'suppressed', points: curvelessPoints() })
    );
    const suppressed = renderChart();
    const suppressedNotice = await screen.findByTestId('rainfall-normal-curve-state');
    const suppressedState = suppressedNotice.getAttribute('data-normal-curve-state');
    const suppressedText = suppressedNotice.textContent ?? '';
    suppressed.unmount();

    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({ normal_curve_state: 'integrity_refused', points: curvelessPoints() })
    );
    renderChart();
    const refusedNotice = await screen.findByTestId('rainfall-normal-curve-state');
    const refusedState = refusedNotice.getAttribute('data-normal-curve-state');
    const refusedText = refusedNotice.textContent ?? '';

    expect(suppressedState).toBe('suppressed');
    expect(refusedState).toBe('integrity_refused');
    // The COPY differs — and not by a colour class, which an operator reading
    // a printed screenshot or a colour-blind reader would never see.
    expect(refusedText).not.toEqual(suppressedText);
    expect(suppressedText).toMatch(/no hay/i);
    expect(refusedText).toMatch(/descartad/i);
    expect(refusedText).toMatch(/inconsistencia/i);
    // …and refusal is never described as an absence of data.
    expect(refusedText).not.toMatch(/no hay (línea )?normal para este análisis/i);
  });

  it('draws no normal line at all when the curve is refused', async () => {
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({ normal_curve_state: 'integrity_refused', points: curvelessPoints() })
    );
    const { container } = renderChart();

    await screen.findByTestId('rainfall-accumulation-chart');
    // ONE line, not two-with-one-empty: an empty line renders as a legend entry
    // and an axis that promise a comparison the response refused to make.
    await waitFor(() => expect(container.querySelectorAll('.recharts-line')).toHaveLength(1));
  });

  it('says nothing about the curve when it is available', async () => {
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series());
    renderChart();

    await screen.findByTestId('rainfall-accumulation-chart');
    expect(screen.queryByTestId('rainfall-normal-curve-state')).toBeNull();
  });
});

describe('RainfallAccumulationChart — re-request action (4.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      series({ consistent_with_snapshot: false, consistency_reason: 'data_revision_moved' })
    );
  });

  it('re-POSTs /analyses for the same scope and year and adopts a newer revision (200)', async () => {
    const newer = snapshot({ analysis_revision_id: 'rev-10', data_revision: 'cd'.repeat(32) });
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: newer });
    renderChart();

    fireEvent.click(await screen.findByTestId('rainfall-series-rerequest'));

    await waitFor(() => expect(fetchRainfallAnalysis).toHaveBeenCalledWith(ZONE, YEAR));
    // The answer lands on the panel's OWN query, so the whole panel moves to
    // the newer revision instead of the chart redrawing behind the card.
    await waitFor(() =>
      expect(client.getQueryData(rainfallAnalysisQueryKey(ZONE, YEAR))).toEqual({
        type: 'ready',
        snapshot: newer,
      })
    );
    expect((await screen.findByTestId('rainfall-series-rerequest-result')).textContent).toMatch(
      /actualiz/i
    );
  });

  it('hands a labelled 202 to the existing poll path', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'queued',
      queued: {
        status: 'queued',
        outbox_id: 'ob-1',
        scope: ZONE,
        year: YEAR,
        labels: ['data_revision_moved'],
      },
    });
    renderChart();

    fireEvent.click(await screen.findByTestId('rainfall-series-rerequest'));

    const result = await screen.findByTestId('rainfall-series-rerequest-result');
    expect(result.textContent).toContain('data_revision_moved');
    await waitFor(() =>
      expect(
        (client.getQueryData(rainfallAnalysisQueryKey(ZONE, YEAR)) as { type: string } | undefined)
          ?.type
      ).toBe('queued')
    );
  });

  it('says so when the server answers with the SAME revision (an honest no-op)', async () => {
    // Otherwise the button is indistinguishable from a broken one: nothing on
    // screen changes and the reader cannot tell whether the request happened.
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: snapshot() });
    renderChart();

    fireEvent.click(await screen.findByTestId('rainfall-series-rerequest'));

    const result = await screen.findByTestId('rainfall-series-rerequest-result');
    expect(result.textContent).toMatch(/mismo an[áa]lisis/i);
  });

  it('reports a failed re-request instead of failing silently', async () => {
    vi.mocked(fetchRainfallAnalysis).mockRejectedValue(new Error('429 demasiadas solicitudes'));
    renderChart();

    fireEvent.click(await screen.findByTestId('rainfall-series-rerequest'));

    expect((await screen.findByTestId('rainfall-series-rerequest-error')).textContent).toContain(
      '429 demasiadas solicitudes'
    );
  });
});

describe('RainfallAccumulationChart — campaign display preset (4.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchRainfallSeries).mockResolvedValue(series());
  });

  it('windows the SAME series and fires no /analyses request', async () => {
    renderChart();
    const chart = await screen.findByTestId('rainfall-accumulation-chart');
    expect(chart.getAttribute('aria-label')).toContain('2025-01-01');

    fireEvent.click(screen.getByText('Campaña'));

    await waitFor(() =>
      expect(screen.getByTestId('rainfall-accumulation-chart').getAttribute('aria-label')).toContain(
        '2025-09-01'
      )
    );
    // spec.md:117-125 — a display preset MUST NOT be requested as a period.
    expect(fetchRainfallAnalysis).not.toHaveBeenCalled();
    // …and it does not re-read the series either: same analysis, same data.
    expect(fetchRainfallSeries).toHaveBeenCalledTimes(1);
  });

  it('labels the campaign view as derived from the calendar-year analysis', async () => {
    renderChart();
    await screen.findByTestId('rainfall-accumulation-chart');

    fireEvent.click(screen.getByText('Campaña'));

    const note = await screen.findByTestId('rainfall-campaign-note');
    expect(note.textContent).toMatch(/1 de septiembre/i);
    // The accumulations are still counted from January 1 — saying otherwise
    // would turn a display preset into a different measurement.
    expect(note.textContent).toMatch(/1 de enero/i);
    expect(note.textContent).toContain(String(YEAR));
  });
});
