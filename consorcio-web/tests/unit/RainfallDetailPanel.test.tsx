/**
 * RainfallDetailPanel.test.tsx  (Lluvia v2 — Task 3.1 RED)
 *
 * The authenticated Rainfall v2 detail mounted inside the ficha's Lluvia tab.
 * Locks the spec scenarios for this slice:
 *   - ACCESS: anonymous visitors and authenticated non-staff (ciudadano) never
 *     see the technical detail (spec "Authenticated Technical Rainfall
 *     Detail"); the public PrecipChart is untouched.
 *   - RESOLVE/SWITCH: a parcel resolves to its zone AND basin; staff can switch
 *     scopes and every parcel-originated result stays labelled "Estimación
 *     regional" (spec "Supported Analysis Scope and Parcel Semantics").
 *   - STATES/BADGES/REASONS: available/partial/suppressed/unavailable are
 *     visibly distinct, suppression carries its reason, provisional data gets
 *     a provisional badge, and suppressed/unavailable values are never
 *     rendered as zero (spec "Partial, Suppressed, and Unavailable Data
 *     States", "Provisional Data and Revision Visibility").
 *   - PROVENANCE: source id, nominal resolution and revision are displayed;
 *     nominal resolution is never presented as parcel-level accuracy.
 *   - LIVE ANNOUNCEMENTS: state changes go through an aria-live region.
 *   - QUEUED: a 202 answer is a LABELLED pending state, never a bare spinner.
 *   - TERMINAL: when the bounded queued polling gives up, an honest labelled
 *     "no disponible aún" state with a manual retry replaces the pending
 *     block; the auto-update promise is gone once polling has stopped.
 *   - EXPORT: the CSV button only exists for a ready snapshot and downloads
 *     the revision CSV.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// `importActual` and NOT a bare factory: the panel now mounts
// `RainfallAccumulationChart`, which imports the `RAINFALL_NORMAL_CURVE_STATE`
// const object as a VALUE. A factory listing only the functions would leave it
// `undefined` at module scope and the failure would read as a chart bug.
vi.mock('../../src/lib/api/rainfall', async () => {
  const actual =
    await vi.importActual<typeof import('../../src/lib/api/rainfall')>(
      '../../src/lib/api/rainfall'
    );
  return {
    ...actual,
    resolveRainfallScopes: vi.fn(),
    fetchRainfallAnalysis: vi.fn(),
    fetchRainfallSeries: vi.fn(),
    downloadRainfallCsv: vi.fn(),
    downloadRainfallXlsx: vi.fn(),
  };
});

import type {
  RainfallAnalysisSnapshot,
  RainfallMetric,
  RainfallSeriesResponse,
} from '../../src/lib/api/rainfall';
import {
  downloadRainfallCsv,
  downloadRainfallXlsx,
  fetchRainfallAnalysis,
  fetchRainfallSeries,
  resolveRainfallScopes,
} from '../../src/lib/api/rainfall';
import { RainfallDetailPanel } from '../../src/components/map2d/rainfall/RainfallDetailPanel';
import { useAuthStore } from '../../src/stores/authStore';

const ZONE = { kind: 'zone' as const, id: 'zona-ne', version: '3' };
const BASIN = { kind: 'basin' as const, id: 'zo-12', version: 'abc123' };

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
    // Required on the served envelope since task 3a.12 injects it at
    // disclosure time; the fixture was missing it, and nothing compiled this
    // file until LI3A-004 put `tests/` behind `npm run typecheck`.
    data_revision: 'ab'.repeat(32),
    scope: ZONE,
    regional_estimate: true,
    year: 2025,
    comparison_end: '2025-12-31',
    baseline: '1991-2020',
    annual: {
      selected: metric({ metric: 'selected', value: 850.24 }),
      normal: metric({ metric: 'normal', value: 1013.8 }),
      percentile: metric({ metric: 'percentile', value: 72, unit: '%' }),
    },
    antecedents: {
      d30: metric({
        metric: 'd30',
        value: null,
        state: 'suppressed',
        reason: 'coverage_below_threshold',
      }),
    },
    intensity: {
      p3h: metric({ metric: 'p3h', value: null, state: 'unavailable', reason: 'sin fuente elegible' }),
      peak: metric({ metric: 'peak', value: 41.2, temporal_state: 'provisional' }),
    },
    summary: 'Año húmedo.',
    source_health: { 'chirps-v3-final': 'ok' },
    ...overrides,
  };
}

/** The `/series` answer the mounted chart reads. Minimal on purpose: this file
 *  proves the panel MOUNTS the chart; the chart's own contract lives in
 *  `RainfallAccumulationChart.test.tsx`. */
function seriesAnswer(overrides: Partial<RainfallSeriesResponse> = {}): RainfallSeriesResponse {
  return {
    analysis_revision_id: 'rev-9',
    data_revision: 'ab'.repeat(32),
    scope: ZONE,
    year: 2025,
    unit: 'mm',
    comparison_end: '2025-12-31',
    available_through: '2025-12-31T00:00:00+00:00',
    consistent_with_snapshot: true,
    consistency_reason: null,
    normal_curve_state: 'available',
    points: [
      { date: '2025-01-01', mm: 3, accumulated: 3, normal_accumulated: 2.5, state: 'available' },
      { date: '2025-01-02', mm: 4, accumulated: 7, normal_accumulated: 5.1, state: 'available' },
    ],
    ...overrides,
  };
}

function setAuth(rol: 'admin' | 'operador' | 'ciudadano' | null) {
  useAuthStore.setState({
    user: rol ? { id: 'u1', email: 'staff@consorcio.test' } : null,
    loading: false,
    initialized: true,
    profile: rol ? ({ rol } as never) : null,
  });
}

function renderPanel(
  options: { pollIntervalMs?: number; maxQueuedPolls?: number } = {}
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui: ReactElement = (
    <QueryClientProvider client={client}>
      <MantineProvider env="test">
        <RainfallDetailPanel nomenclatura="13-06-01" {...options} />
      </MantineProvider>
    </QueryClientProvider>
  );
  return render(ui);
}

/**
 * Expand a fold before reaching what it contains, and hand back its body.
 *
 * `CollapsibleSection` UNMOUNTS its body when closed (`CollapsibleSection.tsx:113`),
 * so the queries below have to ask for these rows the way a reader does. That
 * is the POINT of the reorder, not an inconvenience of it: the datum is one
 * click away, never gone — and a test that could still find it without the
 * click would be proving the fold does not fold.
 */
async function expandFold(
  testId: 'rainfall-antecedents' | 'rainfall-technical'
): Promise<HTMLElement> {
  fireEvent.click(await screen.findByTestId(`${testId}-header`));
  return screen.findByTestId(`${testId}-body`);
}

// File-scoped: the panel mounts the chart for every ready snapshot, so every
// describe below needs a `/series` answer. The per-describe `clearAllMocks`
// wipes call history, not implementations, so this survives them.
beforeEach(() => {
  vi.mocked(fetchRainfallSeries).mockResolvedValue(seriesAnswer());
});

describe('RainfallDetailPanel — access control', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(resolveRainfallScopes).mockResolvedValue({
      kind: 'choices',
      choices: [ZONE, BASIN],
      regional_estimate: true,
    });
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: snapshot() });
  });
  afterEach(() => setAuth(null));

  it('renders nothing for an anonymous visitor', async () => {
    setAuth(null);
    renderPanel();
    await new Promise((resolve) => setTimeout(resolve, 20));
    // No detail, no technical control — and no resolve request went out. (Not
    // `toBeEmptyDOMElement`: MantineProvider injects a <style> into the root.)
    expect(screen.queryByTestId('rainfall-detail')).toBeNull();
    expect(resolveRainfallScopes).not.toHaveBeenCalled();
  });

  it('renders nothing for an authenticated ciudadano (no technical authorization)', async () => {
    setAuth('ciudadano');
    renderPanel();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.queryByTestId('rainfall-detail')).toBeNull();
    expect(resolveRainfallScopes).not.toHaveBeenCalled();
  });

  it('renders the technical detail for staff (operador)', async () => {
    setAuth('operador');
    renderPanel();
    expect(await screen.findByTestId('rainfall-detail')).toBeInTheDocument();
  });
});

describe('RainfallDetailPanel — resolve and scope switch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAuth('operador');
    vi.mocked(resolveRainfallScopes).mockResolvedValue({
      kind: 'choices',
      choices: [ZONE, BASIN],
      regional_estimate: true,
    });
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: snapshot() });
  });
  afterEach(() => setAuth(null));

  it('offers the resolved zone and basin and labels the result as a regional estimate', async () => {
    renderPanel();

    const switcher = await screen.findByTestId('rainfall-scope-switch');
    expect(within(switcher).getByText('Zona')).toBeInTheDocument();
    expect(within(switcher).getByText('Cuenca')).toBeInTheDocument();
    expect(screen.getByTestId('rainfall-regional-estimate')).toBeInTheDocument();

    // The default scope is the first resolved choice (the zone).
    await waitFor(() =>
      expect(fetchRainfallAnalysis).toHaveBeenCalledWith(ZONE, expect.any(Number), expect.anything())
    );
  });

  it('replaces the result with the basin analysis on switch, keeping the regional label', async () => {
    renderPanel();
    const switcher = await screen.findByTestId('rainfall-scope-switch');

    fireEvent.click(within(switcher).getByText('Cuenca'));

    await waitFor(() =>
      expect(fetchRainfallAnalysis).toHaveBeenCalledWith(BASIN, expect.any(Number), expect.anything())
    );
    expect(screen.getByTestId('rainfall-regional-estimate')).toBeInTheDocument();
  });

  it('never claims parcel-level accuracy from nominal grid resolution', async () => {
    renderPanel();
    const detail = await screen.findByTestId('rainfall-detail');
    await expandFold('rainfall-technical');
    expect(detail.textContent).toContain('0.05°');
    expect(detail.textContent).not.toMatch(/precisi[oó]n de parcela|a nivel parcela/i);
  });
});

describe('RainfallDetailPanel — metric states, badges and reasons', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAuth('admin');
    vi.mocked(resolveRainfallScopes).mockResolvedValue({
      kind: 'choices',
      choices: [ZONE],
      regional_estimate: true,
    });
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: snapshot() });
  });
  afterEach(() => setAuth(null));

  it('distinguishes available, partial, suppressed and unavailable with reasons', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'ready',
      snapshot: snapshot({
        antecedents: {
          d7: metric({ metric: 'd7', state: 'partial', coverage: 0.8 }),
          d30: metric({
            metric: 'd30',
            value: null,
            state: 'suppressed',
            reason: 'coverage_below_threshold',
          }),
        },
      }),
    });
    renderPanel();
    // The four states are spread across BOTH folds now: partial and suppressed
    // are antecedents, available and unavailable are annual/intensity. Each one
    // is still one click from the answer.
    const antecedents = await expandFold('rainfall-antecedents');
    const technical = await expandFold('rainfall-technical');
    const metrics = within(technical).getByTestId('rainfall-metrics');

    expect(within(metrics).getAllByText('Disponible').length).toBeGreaterThan(0);
    expect(within(antecedents).getByText('Parcial')).toBeInTheDocument();
    expect(within(antecedents).getByText(/Suprimida/)).toBeInTheDocument();
    expect(within(antecedents).getByText(/coverage_below_threshold/)).toBeInTheDocument();
    expect(within(metrics).getByText(/No disponible/)).toBeInTheDocument();
    expect(within(metrics).getByText(/sin fuente elegible/)).toBeInTheDocument();
  });

  it('never renders a suppressed or unavailable metric as zero', async () => {
    renderPanel();
    const antecedents = await expandFold('rainfall-antecedents');

    const suppressedRow = within(antecedents).getByTestId('rainfall-metric-d30');
    // The value renders "—". NB: the assertion targets the VALUE slot — the
    // provenance line legitimately contains "0.05°" (nominal resolution).
    expect(suppressedRow.textContent).not.toContain('0.0 mm');
    expect(suppressedRow.textContent).not.toMatch(/\b0 mm\b/);
    // …and the COLLAPSED header the reader saw before clicking did not invent
    // one either. The fold changed where the value lives, not the rule.
    expect(screen.getByTestId('rainfall-antecedents').textContent).not.toMatch(/30d 0\b/);
  });

  it('shows a provisional badge only for provisional metrics', async () => {
    renderPanel();
    const technical = await expandFold('rainfall-technical');

    const peakRow = within(technical).getByTestId('rainfall-metric-peak');
    expect(within(peakRow).getByText('Provisional')).toBeInTheDocument();

    const selectedRow = within(technical).getByTestId('rainfall-metric-selected');
    expect(within(selectedRow).queryByText('Provisional')).toBeNull();
  });

  it('exposes provenance: source, nominal resolution and revision', async () => {
    renderPanel();
    const technical = await expandFold('rainfall-technical');

    const row = within(technical).getByTestId('rainfall-metric-selected');
    expect(row.textContent).toContain('chirps-v3-final');
    expect(row.textContent).toContain('0.05°');
    expect(row.textContent).toContain('policy-v1');
  });
});

describe('RainfallDetailPanel — textual chart, live region, queued and export', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAuth('operador');
    vi.mocked(resolveRainfallScopes).mockResolvedValue({
      kind: 'choices',
      choices: [ZONE],
      regional_estimate: true,
    });
  });
  afterEach(() => setAuth(null));

  it('renders the annual comparison as text (textual chart equivalent)', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: snapshot() });
    renderPanel();

    const text = await screen.findByTestId('rainfall-annual-text');
    expect(text).toHaveTextContent('Año 2025: 850.2 mm');
    // The baseline period prints AS SERVED (server-driven, RISK-001 lesson).
    expect(text).toHaveTextContent('Normal 1991-2020: 1013.8 mm');
  });

  it('labels the queued state with its reason and announces it live (no silent spinner)', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'queued',
      queued: {
        status: 'queued',
        outbox_id: 'ob-1',
        scope: ZONE,
        year: 2025,
        labels: ['analysis_missing'],
      },
    });
    renderPanel();

    const queued = await screen.findByTestId('rainfall-queued');
    expect(queued.textContent).toMatch(/preparaci[oó]n/i);
    expect(queued.textContent).toContain('analysis_missing');

    const live = screen.getByTestId('rainfall-live');
    expect(live).toHaveAttribute('aria-live', 'polite');
    await waitFor(() => expect(live.textContent).toMatch(/preparaci[oó]n/i));
  });

  it('announces the available analysis through the live region', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: snapshot() });
    renderPanel();

    const live = screen.getByTestId('rainfall-live');
    await waitFor(() => expect(live.textContent).toMatch(/disponible/i));
  });

  it('exports the CSV of the displayed revision, only when ready', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: snapshot() });
    vi.mocked(downloadRainfallCsv).mockResolvedValue(undefined);
    renderPanel();

    const button = await screen.findByTestId('rainfall-export-csv');
    fireEvent.click(button);

    await waitFor(() => expect(downloadRainfallCsv).toHaveBeenCalledWith('rev-9'));
  });

  it('hides the export button while the analysis is queued', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'queued',
      queued: { status: 'queued', outbox_id: 'ob-1', scope: ZONE, year: 2025, labels: [] },
    });
    renderPanel();

    await screen.findByTestId('rainfall-queued');
    expect(screen.queryByTestId('rainfall-export-csv')).toBeNull();
  });

  it('shows a labelled terminal state with a manual retry once polling gives up', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'queued',
      queued: { status: 'queued', outbox_id: 'ob-1', scope: ZONE, year: 2025, labels: [] },
    });
    renderPanel({ pollIntervalMs: 5, maxQueuedPolls: 3 });

    const terminal = await screen.findByTestId('rainfall-unavailable');
    expect(terminal.textContent).toMatch(/no disponible aún/i);
    // No auto-update promise once auto-refresh has stopped.
    expect(screen.queryByTestId('rainfall-queued')).toBeNull();
    expect(terminal.textContent).not.toMatch(/se actualiza automáticamente/i);
    expect(within(terminal).getByRole('button', { name: 'Reintentar' })).toBeInTheDocument();
  });

  it('reintentar re-runs the fetch and resets the queued budget', async () => {
    const queued = {
      type: 'queued' as const,
      queued: { status: 'queued' as const, outbox_id: 'ob-1', scope: ZONE, year: 2025, labels: [] },
    };
    let release: (value: Awaited<ReturnType<typeof fetchRainfallAnalysis>>) => void = () => {};
    vi.mocked(fetchRainfallAnalysis)
      .mockResolvedValueOnce(queued)
      .mockResolvedValueOnce(queued)
      .mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }))
      .mockResolvedValue(queued);

    renderPanel({ pollIntervalMs: 5, maxQueuedPolls: 2 });

    await screen.findByTestId('rainfall-unavailable');
    expect(fetchRainfallAnalysis).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByTestId('rainfall-retry'));

    // The retry re-runs the fetch; while in flight the terminal state is gone
    // (budget reset) and the labelled pending state is back.
    await waitFor(() => expect(fetchRainfallAnalysis).toHaveBeenCalledTimes(3));
    expect(screen.queryByTestId('rainfall-unavailable')).toBeNull();
    expect(screen.getByTestId('rainfall-queued')).toBeInTheDocument();

    release(queued);

    // Fresh budget: it polls again and eventually gives up once more.
    await waitFor(() => expect(screen.getByTestId('rainfall-unavailable')).toBeInTheDocument());
    expect(fetchRainfallAnalysis).toHaveBeenCalledTimes(4);
  });

  it('announces the terminal state through the live region', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'queued',
      queued: { status: 'queued', outbox_id: 'ob-1', scope: ZONE, year: 2025, labels: [] },
    });
    renderPanel({ pollIntervalMs: 5, maxQueuedPolls: 2 });

    await screen.findByTestId('rainfall-unavailable');
    const live = screen.getByTestId('rainfall-live');
    await waitFor(() => expect(live.textContent).toMatch(/no disponible aún/i));
  });
});

describe('RainfallDetailPanel — accumulation chart and xlsx export (4.9)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAuth('operador');
    vi.mocked(resolveRainfallScopes).mockResolvedValue({
      kind: 'choices',
      choices: [ZONE],
      regional_estimate: true,
    });
    vi.mocked(fetchRainfallSeries).mockResolvedValue(seriesAnswer());
  });
  afterEach(() => setAuth(null));

  it('mounts the accumulation chart for the served revision', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: snapshot() });
    renderPanel();

    await screen.findByTestId('rainfall-accumulation');
    // Fed by THIS revision's series, not by a second analysis request.
    await waitFor(() =>
      expect(fetchRainfallSeries).toHaveBeenCalledWith('rev-9', expect.anything())
    );
    // The textual equivalent stays beside it: the chart never replaces the text.
    expect(screen.getByTestId('rainfall-annual-text')).toBeInTheDocument();
  });

  it('mounts no chart while the analysis is queued (there is no revision to chart)', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'queued',
      queued: { status: 'queued', outbox_id: 'ob-1', scope: ZONE, year: 2025, labels: [] },
    });
    renderPanel();

    await screen.findByTestId('rainfall-queued');
    expect(screen.queryByTestId('rainfall-accumulation')).toBeNull();
    // …and no series is requested for a revision that does not exist yet.
    expect(fetchRainfallSeries).not.toHaveBeenCalled();
  });

  it('exports the xlsx of the displayed revision, beside the audit CSV', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: snapshot() });
    vi.mocked(downloadRainfallXlsx).mockResolvedValue(undefined);
    renderPanel();

    fireEvent.click(await screen.findByTestId('rainfall-export-xlsx'));

    await waitFor(() => expect(downloadRainfallXlsx).toHaveBeenCalledWith('rev-9'));
    // The audit CSV is untouched and still its own button — the friendly
    // workbook is an addition, never a replacement (spec: the audit route and
    // contract MUST remain unchanged).
    expect(screen.getByTestId('rainfall-export-csv')).toBeInTheDocument();
    expect(downloadRainfallCsv).not.toHaveBeenCalled();
  });

  it('reports a denied xlsx export without touching the CSV path', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: snapshot() });
    vi.mocked(downloadRainfallXlsx).mockRejectedValue(
      new Error('La descarga no está autorizada para este usuario.')
    );
    renderPanel();

    fireEvent.click(await screen.findByTestId('rainfall-export-xlsx'));

    const error = await screen.findByTestId('rainfall-export-error');
    expect(error.textContent).toContain('no está autorizada');
  });
});

/**
 * The answer-first hierarchy (design D2/D2a/D1a, spec delta "Answer-First
 * Rainfall Presentation Hierarchy" + "Progressive Disclosure Without Data
 * Loss").
 *
 * jsdom has NO LAYOUT — every box is 0×0 — so this file asserts STRUCTURE and
 * never pretends to measure a viewport: document order, fold state on first
 * paint, and which node the freshness date came from. The zero-scroll criterion
 * itself is an e2e case with a real browser (design D13); a unit test with a
 * faked `innerWidth` would be a criterion measuring nothing.
 */
describe('RainfallDetailPanel — answer-first hierarchy', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAuth('operador');
    vi.mocked(resolveRainfallScopes).mockResolvedValue({
      kind: 'choices',
      choices: [ZONE],
      regional_estimate: true,
    });
    vi.mocked(fetchRainfallSeries).mockResolvedValue(seriesAnswer());
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: snapshot() });
  });
  afterEach(() => setAuth(null));

  /** True when `first` precedes `second` in document order. */
  function precedes(first: HTMLElement, second: HTMLElement): boolean {
    return (
      (first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING) ===
      Node.DOCUMENT_POSITION_FOLLOWING
    );
  }

  it('(a) puts the answer before the chart, and both before every fold', async () => {
    renderPanel();

    const card = await screen.findByTestId('rainfall-answer-card');
    const chart = screen.getByTestId('rainfall-accumulation');
    const antecedents = screen.getByTestId('rainfall-antecedents');
    const technical = screen.getByTestId('rainfall-technical');

    expect(precedes(card, chart)).toBe(true);
    expect(precedes(chart, antecedents)).toBe(true);
    expect(precedes(antecedents, technical)).toBe(true);
    // The plot itself is inside the chart block, not a sibling of it.
    expect(within(chart).getByTestId('rainfall-accumulation-chart')).toBeInTheDocument();
    // The controls that re-query sit above the answer they change.
    expect(precedes(screen.getByTestId('rainfall-controls'), card)).toBe(true);
  });

  it('(b) opens with BOTH folds collapsed, at every size', async () => {
    // Owner-ratified 2026-08-11: collapsed on desktop too. One behaviour is one
    // thing to test, and a 380 px floating card pays the same scroll cost as
    // the 390 px sheet.
    renderPanel();

    await screen.findByTestId('rainfall-answer-card');
    expect(screen.getByTestId('rainfall-antecedents-header')).toHaveAttribute(
      'aria-expanded',
      'false'
    );
    expect(screen.getByTestId('rainfall-technical-header')).toHaveAttribute(
      'aria-expanded',
      'false'
    );
    // Collapsed means UNMOUNTED here (`CollapsibleSection.tsx:113`), which is
    // exactly why R7's witness below matters.
    expect(screen.queryByTestId('rainfall-metrics')).toBeNull();
  });

  it("(c) R7 witness — the chart's textual equivalent survives every fold being closed", async () => {
    renderPanel();

    await screen.findByTestId('rainfall-answer-card');
    // Both folds closed, the chart visible: the equivalent MUST still be in the
    // accessibility tree. It is on the card, above the first fold, so no fold
    // state can remove it — structure, not discipline.
    expect(screen.getByTestId('rainfall-antecedents-header')).toHaveAttribute(
      'aria-expanded',
      'false'
    );
    expect(screen.getByTestId('rainfall-technical-header')).toHaveAttribute(
      'aria-expanded',
      'false'
    );
    expect(screen.getByTestId('rainfall-accumulation')).toBeInTheDocument();
    expect(screen.getByTestId('rainfall-annual-text')).toBeInTheDocument();
  });

  it('(d) derives the freshness of the ANALYSIS, not of the series', async () => {
    // D1a: two SUBJECTS, one derivation each. The card describes the stored
    // analysis; the chart footer describes the line it drew. Moving only the
    // series must move only the footer — if the card followed it, the card
    // would be restating the chart instead of stating the analysis, and the
    // disclosed divergence would silently disappear.
    vi.mocked(fetchRainfallSeries).mockResolvedValue(
      seriesAnswer({ available_through: '2025-06-15T00:00:00+00:00' })
    );
    renderPanel();

    const freshness = await screen.findByTestId('rainfall-freshness');
    // snapshot.annual.selected.provenance.available_through = 2025-12-31 →
    // the last day WITH evidence is the day before it.
    expect(freshness).toHaveTextContent('Evidencia publicada hasta el 2025-12-30');
    expect(freshness.textContent).not.toContain('2025-06-14');

    await waitFor(() =>
      expect(screen.getByTestId('rainfall-accumulation-dates').textContent).toContain(
        'Evidencia publicada hasta el 2025-06-14'
      )
    );
  });

  it('(e) states the antecedent values in the COLLAPSED header, unit once, reason reachable', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'ready',
      snapshot: snapshot({
        antecedents: {
          d7: metric({ metric: 'd7', value: 31 }),
          d30: metric({ metric: 'd30', value: 83.7 }),
          d90: metric({
            metric: 'd90',
            value: null,
            state: 'unavailable',
            reason: 'sin fuente elegible',
          }),
        },
      }),
    });
    renderPanel();

    const section = await screen.findByTestId('rainfall-antecedents');
    // Fixed d7 → d30 → d90 order, whole millimetres, unit stated exactly ONCE
    // at the end. Three units inside a ~26-character string is what makes the
    // header unreadable at 348 px, and a unit whose POSITION depends on the
    // data is a header a reader cannot learn to scan.
    expect(section.textContent).toContain('7d 31 · 30d 84 · 90d — mm');
    expect((section.textContent?.match(/mm/g) ?? []).length).toBe(1);
    // Never a zero for an unavailable antecedent; the state is reachable
    // WITHOUT expanding, which is what the collapsed-header requirement buys.
    expect(section.textContent).not.toMatch(/90d 0\b/);
    expect(within(section).getByTitle('sin fuente elegible')).toBeInTheDocument();
    // …and the body is still closed while all of that is true.
    expect(screen.getByTestId('rainfall-antecedents-header')).toHaveAttribute(
      'aria-expanded',
      'false'
    );
  });

  it('reveals the antecedent rows on ONE click, and the technical detail on one more', async () => {
    renderPanel();

    fireEvent.click(await screen.findByTestId('rainfall-antecedents-header'));
    const antecedentsBody = await screen.findByTestId('rainfall-antecedents-body');
    expect(within(antecedentsBody).getByTestId('rainfall-metric-d30')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('rainfall-technical-header'));
    const technicalBody = await screen.findByTestId('rainfall-technical-body');
    const metrics = within(technicalBody).getByTestId('rainfall-metrics');
    // The antecedents are NOT repeated in the technical fold — they have their
    // own, and `exclude` is what keeps one datum in one place.
    expect(within(metrics).queryByTestId('rainfall-metric-d30')).toBeNull();
    expect(within(metrics).getByTestId('rainfall-metric-selected')).toBeInTheDocument();
    // The badged percentile row lives HERE now, one click from the headline.
    expect(within(metrics).getByTestId('rainfall-metric-percentile')).toBeInTheDocument();
  });
});
