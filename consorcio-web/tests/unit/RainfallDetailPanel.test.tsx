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
import type { ReactElement, ReactNode } from 'react';
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
  options: {
    pollIntervalMs?: number;
    maxQueuedPolls?: number;
    prioritizeAnswer?: boolean;
  } = {}
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

function renderPanelWithClient(
  queryClient: QueryClient,
  props: {
    nomenclatura: string;
    pollIntervalMs?: number;
    maxQueuedPolls?: number;
  }
) {
  function Wrapper({ children }: { readonly children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MantineProvider env="test">{children}</MantineProvider>
      </QueryClientProvider>
    );
  }
  return render(<RainfallDetailPanel {...props} />, { wrapper: Wrapper });
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

    // Two surfaces, on purpose, and each asserted for what it owns: the CHIP is
    // presentation and exception-only (OWN-003), so `Disponible` has none; the
    // row's TEXT is the contract and states every state, chip or no chip.
    expect(within(metrics).getAllByText(/^Estado: Disponible$/).length).toBeGreaterThan(0);
    expect(within(metrics).queryByText('Disponible')).toBeNull();

    expect(within(antecedents).getByText('Parcial')).toBeInTheDocument();
    expect(within(antecedents).getByText('Estado: Parcial')).toBeInTheDocument();
    expect(within(antecedents).getByText('Suprimida')).toBeInTheDocument();
    expect(within(antecedents).getByText('Estado: Suprimida')).toBeInTheDocument();
    expect(within(antecedents).getByText(/coverage_below_threshold/)).toBeInTheDocument();

    expect(within(metrics).getByText('No disponible')).toBeInTheDocument();
    expect(within(metrics).getByText('Estado: No disponible')).toBeInTheDocument();
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

  // A MARKER, not a badge, since OWN-003: three badges per row is what
  // truncated all three into fragments in the 380 px panel. Still the same
  // fact, still a whole word, just no longer competing for the value's row.
  it('shows the provisional marker only for provisional metrics', async () => {
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

    // The spec scenario, unchanged in what it demands and MIGRATED in where it
    // looks: since the slice-2 hoist (D5) a homogeneous displayed set states
    // its provenance ONCE for the set, and the metric's own fields are read as
    // `shared ∪ row`. Asserting the ROW alone would now be asserting that the
    // consolidation the spec explicitly permits did not happen — which is the
    // opposite of the requirement ("Provenance MAY be presented once for a
    // displayed set… no required field of any metric becomes unreachable").
    expect(within(technical).getByTestId('rainfall-metric-selected')).toBeInTheDocument();
    expect(technical.textContent).toContain('chirps-v3-final');
    expect(technical.textContent).toContain('0.05°');
    expect(technical.textContent).toContain('policy-v1');
    // …and it is reachable with ONE control operated: this fold, and no other.
    expect(screen.getByTestId('rainfall-antecedents-header')).toHaveAttribute(
      'aria-expanded',
      'false'
    );
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
    // The CUT DATE, not the year: "Año 2025: 850.2 mm" reads as a closed annual
    // total, which mid-year it is not.
    expect(text).toHaveTextContent('Acumulado hasta el 2025-12-30: 850.2 mm');
    // The baseline period prints AS SERVED (server-driven, RISK-001 lesson),
    // and the normal says which period it accumulated over.
    expect(text).toHaveTextContent('Normal 1991-2020 al mismo período: 1013.8 mm');
  });

  it('labels the queued state and announces it live (no silent spinner)', async () => {
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
    expect(queued.textContent).toMatch(/se actualiza/i);
    // The served reason is still DISCLOSED, as an inspectable attribute rather
    // than as copy: `analysis_missing` is a backend job identifier, and the
    // owner's screenshot of it rendered mid-sentence is why (OWN-002).
    expect(queued).toHaveAttribute('data-queued-labels', 'analysis_missing');
    expect(queued.textContent).not.toContain('analysis_missing');

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
    // Counted PER YEAR, not in total. A queued selected year also asks for the
    // previous one now (the one-step fallback), so a bare call count would be
    // measuring two queries at once — and this test is about the budget of the
    // SELECTED year's query.
    const selectedYear = new Date().getFullYear();
    let selectedCalls = 0;
    let release: (value: Awaited<ReturnType<typeof fetchRainfallAnalysis>>) => void = () => {};
    vi.mocked(fetchRainfallAnalysis).mockImplementation((_scope, requestedYear) => {
      if (requestedYear !== selectedYear) return Promise.resolve(queued);
      selectedCalls += 1;
      // The third call is the one the retry fires; hold it open so the
      // in-flight pending state below is observable.
      if (selectedCalls === 3) return new Promise((resolve) => { release = resolve; });
      return Promise.resolve(queued);
    });

    renderPanel({ pollIntervalMs: 5, maxQueuedPolls: 2 });

    await screen.findByTestId('rainfall-unavailable');
    expect(selectedCalls).toBe(2);

    fireEvent.click(screen.getByTestId('rainfall-retry'));

    // The retry re-runs the fetch; while in flight the terminal state is gone
    // (budget reset) and the labelled pending state is back.
    await waitFor(() => expect(selectedCalls).toBe(3));
    expect(screen.queryByTestId('rainfall-unavailable')).toBeNull();
    expect(screen.getByTestId('rainfall-queued')).toBeInTheDocument();

    release(queued);

    // Fresh budget: it polls again and eventually gives up once more.
    await waitFor(() => expect(screen.getByTestId('rainfall-unavailable')).toBeInTheDocument());
    expect(selectedCalls).toBe(4);
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
 * Defects the OWNER found on the deployed surface (2026-08-11, screenshots).
 * Both live on controls this slice is already rebuilding, so they are fixed
 * here rather than filed: a slice that reorders this surface and leaves an
 * unusable control on it has not fixed the reader's problem.
 */
describe('RainfallDetailPanel — owner-reported defects on the live UI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAuth('operador');
    vi.mocked(fetchRainfallSeries).mockResolvedValue(seriesAnswer());
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: snapshot() });
  });
  afterEach(() => setAuth(null));

  it('OWN-001 names every scope option distinctly when a kind repeats', async () => {
    // The real case: a Bell Ville parcel (nomenclatura 3603403896547762)
    // resolves to FIVE scopes and the control offered
    // `Zona | Zona | Cuenca | Cuenca | Cuenca` — three of them identical, so
    // the reader could only guess which basin they were asking for.
    vi.mocked(resolveRainfallScopes).mockResolvedValue({
      kind: 'choices',
      choices: [
        { kind: 'zone', id: 'zona_bell_ville', version: '1' },
        { kind: 'zone', id: 'zona_norte', version: '1' },
        { kind: 'basin', id: 'cuenca_rio_tercero', version: '1' },
        { kind: 'basin', id: 'cuenca_algodon', version: '1' },
        { kind: 'basin', id: 'cuenca_litin', version: '1' },
      ],
      regional_estimate: true,
    });
    renderPanel();

    const control = await screen.findByTestId('rainfall-scope-switch');
    const labels = within(control)
      .getAllByRole('option')
      .map((option) => option.textContent ?? '');

    expect(labels).toHaveLength(5);
    expect(new Set(labels).size).toBe(5);
    expect(labels).toContain('Zona · Bell Ville');
    expect(labels).toContain('Cuenca · Rio Tercero');
    // Five segments cannot fit 348 px, so the control is the SELECT variant —
    // forcing them into one row would be the truncation defect one level up.
    expect(within(control).queryAllByRole('radio')).toHaveLength(0);
    expect(control).toHaveAttribute('aria-label', 'Ámbito regional');
  });

  it('OWN-001 keeps the segmented control for the ordinary zone+basin pair', async () => {
    vi.mocked(resolveRainfallScopes).mockResolvedValue({
      kind: 'choices',
      choices: [ZONE, BASIN],
      regional_estimate: true,
    });
    renderPanel();

    const control = await screen.findByTestId('rainfall-scope-switch');
    expect(within(control).getAllByRole('radio')).toHaveLength(2);
    // Two kinds, each unique: no id noise on a control that never needed it.
    expect(within(control).getByText('Zona')).toBeInTheDocument();
    expect(within(control).getByText('Cuenca')).toBeInTheDocument();
  });

  it('OWN-002 never prints the backend job labels as user copy', async () => {
    // The owner's screenshot: "Análisis en preparación: role:daily,
    // analysis_missing. Se actualiza automáticamente." Those are internal job
    // labels. They stay INSPECTABLE — a data attribute — and stop being copy.
    vi.mocked(resolveRainfallScopes).mockResolvedValue({
      kind: 'choices',
      choices: [ZONE],
      regional_estimate: true,
    });
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'queued',
      queued: {
        status: 'queued',
        outbox_id: 'ob-1',
        scope: ZONE,
        year: 2025,
        labels: ['role:daily', 'analysis_missing'],
      },
    });
    renderPanel();

    const queued = await screen.findByTestId('rainfall-queued');
    // Still a LABELLED pending state, never a bare spinner: it says what is
    // happening and that it resolves itself.
    expect(queued.textContent).toMatch(/preparaci[oó]n/i);
    expect(queued.textContent).toMatch(/se actualiza/i);
    // …in words, not in job identifiers.
    expect(queued.textContent).not.toContain('role:daily');
    expect(queued.textContent).not.toContain('analysis_missing');
    expect(queued).toHaveAttribute('data-queued-labels', 'role:daily, analysis_missing');

    // The announcement is the same sentence: a screen reader must not be the
    // only reader who gets handed raw identifiers.
    const live = screen.getByTestId('rainfall-live');
    await waitFor(() => expect(live.textContent).toMatch(/preparaci[oó]n/i));
    expect(live.textContent).not.toContain('role:daily');
    expect(live.textContent).not.toContain('analysis_missing');
  });
});

/**
 * Owner decision: while the selected year is being prepared, show the previous
 * one rather than an empty panel — with a notice that says so.
 */
describe('RainfallDetailPanel — the one-step year fallback', () => {
  const YEAR = new Date().getFullYear();

  beforeEach(() => {
    vi.clearAllMocks();
    setAuth('operador');
    vi.mocked(fetchRainfallSeries).mockResolvedValue(seriesAnswer());
    vi.mocked(resolveRainfallScopes).mockResolvedValue({
      kind: 'choices',
      choices: [ZONE],
      regional_estimate: true,
    });
  });
  afterEach(() => setAuth(null));

  const queuedAnswer = {
    type: 'queued' as const,
    queued: {
      status: 'queued' as const,
      outbox_id: 'ob-1',
      scope: ZONE,
      year: YEAR,
      labels: ['analysis_missing'],
    },
  };

  it('shows the PREVIOUS year with a notice naming both years', async () => {
    vi.mocked(fetchRainfallAnalysis).mockImplementation((_scope, requestedYear) =>
      Promise.resolve(
        requestedYear === YEAR
          ? queuedAnswer
          : { type: 'ready', snapshot: snapshot({ year: requestedYear }) }
      )
    );
    renderPanel();

    // The previous year's analysis is what the reader gets — a real answer
    // instead of a spinner over an empty panel.
    const card = await screen.findByTestId('rainfall-answer-card');
    expect(card).toBeInTheDocument();
    expect(screen.getByTestId('rainfall-annual-text').textContent).toContain('Acumulado');

    // …and the notice says WHICH year that is, and what is happening to the
    // one that was asked for. "Which year am I looking at" is not a question a
    // reader can answer from the numbers.
    const notice = screen.getByTestId('rainfall-queued');
    expect(notice.textContent).toContain(`Mostrando ${YEAR - 1}`);
    expect(notice.textContent).toContain(`el análisis ${YEAR} se está preparando`);
    expect(notice).toHaveAttribute('data-showing-year', String(YEAR - 1));
    // Still no job identifiers in copy (OWN-002).
    expect(notice.textContent).not.toContain('analysis_missing');
    expect(notice).toHaveAttribute('data-queued-labels', 'analysis_missing');
  });

  it('stops after ONE step: a queued previous year triggers no third request', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue(queuedAnswer);
    renderPanel();

    await screen.findByTestId('rainfall-queued');
    await waitFor(() =>
      expect(vi.mocked(fetchRainfallAnalysis).mock.calls.length).toBeGreaterThanOrEqual(2)
    );

    // A fallback that keeps walking backwards turns one slow answer into a
    // queue of them. Exactly two YEARS are ever asked for.
    const years = new Set(vi.mocked(fetchRainfallAnalysis).mock.calls.map((call) => call[1]));
    expect(years).toEqual(new Set([YEAR, YEAR - 1]));
    expect(years.has(YEAR - 2)).toBe(false);

    // …and with nothing to show, the reader gets the plain queued state.
    expect(screen.queryByTestId('rainfall-answer-card')).toBeNull();
    expect(screen.getByTestId('rainfall-queued').textContent).toMatch(/se actualiza/i);
    expect(screen.getByTestId('rainfall-queued')).not.toHaveAttribute('data-showing-year');
  });

  /**
   * The INTERSECTION the fallback tests and the gave-up tests each missed
   * (review R3-001 / R4-001): the selected year is queued AND the poll budget
   * is exhausted WHILE the previous year is on screen. Before the fix the
   * queued block — which owned both the substitution notice and
   * `data-showing-year` — unmounted, leaving a fully rendered Y-1 card under a
   * selector reading Y beside an alert that named neither year.
   */
  function giveUpWithFallbackOnScreen() {
    vi.mocked(fetchRainfallAnalysis).mockImplementation((_scope, requestedYear) =>
      Promise.resolve(
        requestedYear === YEAR
          ? queuedAnswer
          : { type: 'ready', snapshot: snapshot({ year: requestedYear }) }
      )
    );
    // A budget of 2 at a 5 ms cadence: the selected year exhausts it while the
    // previous year's ready snapshot stays mounted.
    return renderPanel({ pollIntervalMs: 5, maxQueuedPolls: 2 });
  }

  it('keeps a terminal disclosure naming BOTH years once polling gives up on the fallback', async () => {
    giveUpWithFallbackOnScreen();

    const terminal = await screen.findByTestId('rainfall-unavailable');
    // The previous year is still the answer on screen — the fallback is not
    // withdrawn because the poll budget ran out.
    expect(screen.getByTestId('rainfall-answer-card')).toBeInTheDocument();

    // …and the disclosure still says WHICH year that is and what happened to
    // the one that was asked for, in TERMINAL form.
    expect(terminal.textContent).toContain(`Mostrando el análisis ${YEAR - 1}`);
    expect(terminal.textContent).toContain(`El análisis ${YEAR} no está disponible aún`);
    expect(terminal).toHaveAttribute('data-showing-year', String(YEAR - 1));
    expect(within(terminal).getByRole('button', { name: 'Reintentar' })).toBeInTheDocument();

    // No auto-update promise survives the stop: polling is over.
    expect(screen.queryByTestId('rainfall-queued')).toBeNull();
    expect(document.body.textContent).not.toContain('se actualizará solo');
    expect(document.body.textContent).not.toContain('se está preparando');
  });

  it('announces the terminal fallback state instead of re-promising an update', async () => {
    giveUpWithFallbackOnScreen();

    await screen.findByTestId('rainfall-unavailable');
    const live = screen.getByTestId('rainfall-live');
    // The alert and the live region state the SAME terminal fact (the file's
    // own contract): both years, no auto-update promise, manual retry.
    await waitFor(() =>
      expect(live.textContent).toContain(`El análisis ${YEAR} no está disponible aún`)
    );
    expect(live.textContent).toContain(`Mostrando el análisis ${YEAR - 1}`);
    expect(live.textContent).toContain('Puede reintentar manualmente');
    expect(live.textContent).not.toContain('se está preparando');
  });

  it('asks for no previous year at all once the selected one answers', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'ready',
      snapshot: snapshot({ year: YEAR }),
    });
    renderPanel();

    await screen.findByTestId('rainfall-answer-card');
    const years = new Set(vi.mocked(fetchRainfallAnalysis).mock.calls.map((call) => call[1]));
    expect(years).toEqual(new Set([YEAR]));
    expect(screen.queryByTestId('rainfall-queued')).toBeNull();
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
    // The chart is gated on a SECOND query (`fetchRainfallSeries`): until it
    // resolves the block renders `rainfall-accumulation-loading`, a different
    // testid. Awaiting the card only proves the ANALYSIS query landed, so a
    // synchronous `getByTestId` here is a race — it passes whenever the two
    // mocked promises happen to flush in the same tick and fails on a loaded
    // runner. Await the element that has its own async dependency.
    const chart = await screen.findByTestId('rainfall-accumulation');
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

  it('(a2) puts the answer before controls when the mobile ficha prioritizes it', async () => {
    renderPanel({ prioritizeAnswer: true });

    const card = await screen.findByTestId('rainfall-answer-card');
    expect(precedes(card, screen.getByTestId('rainfall-controls'))).toBe(true);
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
    // Same second-query dependency as (a): await it rather than assume the
    // series mock resolved in the same tick as the analysis mock.
    expect(await screen.findByTestId('rainfall-accumulation')).toBeInTheDocument();
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

/**
 * The technical disclosure (design D5/D8/D9/D9a, spec delta "Metric Provenance
 * and State Metadata").
 *
 * The floor is ENUMERATED and bound to what the snapshot serves: every field it
 * carries must be reachable by operating at most ONE disclosure control — not
 * necessarily the same control for every field — and a field it does NOT carry
 * must be absent, not a dash, not an empty label, not a placeholder.
 */
describe('RainfallDetailPanel — the enumerated field floor', () => {
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

  it('the enumerated field floor is reachable with one disclosure control', async () => {
    renderPanel();
    const technical = await expandFold('rainfall-technical');

    // The consolidated block, and the words that make ONE control enough: it
    // speaks for the metrics of BOTH folds, so opening the antecedents alone
    // still leaves their provenance reachable through this one (UXJA-107).
    const shared = within(technical).getByTestId('rainfall-provenance-shared');
    expect(shared.textContent).toContain('Vale para todas las métricas mostradas');
    expect(shared.textContent).toContain('chirps-v3-final');
    expect(shared.textContent).toContain('0.05°');
    expect(shared.textContent).toContain('policy-v1');
    expect(shared.textContent).toContain('2026-01-02T00:00:00Z');

    // …and the per-metric half of `shared ∪ row`: the fields that are the
    // metric's OWN and are never hoisted (D5).
    const row = within(technical).getByTestId('rainfall-metric-selected');
    expect(row.textContent).toContain('Intervalo: 2025-01-01T00:00:00Z → 2026-01-01T00:00:00Z');
    expect(row.textContent).toContain('Cobertura: 100%');
    expect(row.textContent).toContain('Completitud: 100%');
    expect(row.textContent).toContain('Calidad: score=0.9');
    expect(row.textContent).toContain('Estado temporal: final');
    expect(row.textContent).toContain('Origen: fuente primaria');
    // The evidence statement is the metric's OWN, gated per metric, and never
    // the analysis-scoped sentence (UXJA-205).
    expect(row.textContent).toContain('Evidencia publicada hasta el 2025-12-30');
    expect(row.textContent).not.toContain('en este análisis');
  });

  it('renders source health ONCE for the analysis, at the fold foot', async () => {
    renderPanel();
    const technical = await expandFold('rainfall-technical');

    // `source_health` is a ROOT key of the snapshot, not a member of
    // `RainfallMetric`: rendering it per metric would attribute one
    // analysis-wide fact to six metrics that never carried it.
    const health = within(technical).getAllByTestId('rainfall-source-health');
    expect(health).toHaveLength(1);
    expect(health[0]?.textContent).toContain('Estado de fuentes: chirps-v3-final=ok');
    expect(within(technical).getByTestId('rainfall-metric-selected').textContent).not.toContain(
      'Estado de fuentes'
    );
  });

  it('renders NO source-health placeholder when the analysis does not serve it', async () => {
    const served = snapshot();
    const { source_health: _omitted, ...withoutHealth } = served;
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'ready',
      snapshot: withoutHealth as RainfallAnalysisSnapshot,
    });
    renderPanel();
    const technical = await expandFold('rainfall-technical');

    expect(within(technical).queryByTestId('rainfall-source-health')).toBeNull();
    expect(technical.textContent).not.toContain('Estado de fuentes');
  });

  it('keeps a divergent metric own provenance at the metric', async () => {
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'ready',
      snapshot: snapshot({
        annual: {
          selected: metric({ metric: 'selected', value: 850.24 }),
          normal: metric({ metric: 'normal', value: 1013.8, revision: 'policy-v2' }),
        },
        antecedents: undefined,
        intensity: undefined,
      }),
    });
    renderPanel();
    const technical = await expandFold('rainfall-technical');

    // The revision diverges, so it leaves the shared block and lands on BOTH
    // rows — the consolidated presentation may only state what is identical.
    const shared = within(technical).getByTestId('rainfall-provenance-shared');
    expect(shared.textContent).not.toContain('policy-v1');
    expect(shared.textContent).not.toContain('policy-v2');
    expect(shared.textContent).toContain('chirps-v3-final');

    expect(within(technical).getByTestId('rainfall-metric-selected').textContent).toContain(
      'Revisión: policy-v1'
    );
    expect(within(technical).getByTestId('rainfall-metric-normal').textContent).toContain(
      'Revisión: policy-v2'
    );
  });

  it('an unserved field renders no line, and a stripped metric renders only its state', async () => {
    // D9a rule 3. The stripped four-field shape (`service.py:466-472`) is what
    // a contract, policy or quality rejection produces: no provenance, no
    // coverage, no intervals. Nothing may be invented to prove the field was
    // considered.
    const stripped = {
      metric: 'd7',
      value: null,
      state: 'unavailable',
      reason: 'metric_contract_rejected',
    } as unknown as RainfallMetric;
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'ready',
      snapshot: snapshot({
        annual: {
          selected: metric({ metric: 'selected', quality: {}, discrepancies: [] }),
        },
        antecedents: { d7: stripped },
        intensity: undefined,
      }),
    });
    renderPanel();
    const antecedents = await expandFold('rainfall-antecedents');
    const technical = await expandFold('rainfall-technical');

    const strippedRow = within(antecedents).getByTestId('rainfall-metric-d7');
    expect(strippedRow.textContent).toContain('Estado: No disponible');
    expect(strippedRow.textContent).toContain('Motivo: metric_contract_rejected');
    for (const absent of [
      'Cobertura',
      'Completitud',
      'Intervalo',
      'Frescura',
      'Fuente:',
      'Revisión',
      'Evidencia',
      'Estado temporal',
      'Origen',
    ]) {
      expect(strippedRow.textContent).not.toContain(absent);
    }
    // No dash, no empty label, no `null` printed to fill the gap.
    expect(strippedRow.textContent).not.toContain('undefined');
    expect(strippedRow.textContent).not.toContain('null');
    expect(strippedRow.textContent).not.toContain('NaN');

    // …and the shared block SCOPES ITSELF to what it actually compared
    // (S2R3-001). `hoistProvenance` excludes the stripped metric from the
    // comparison set (UXJB-110), so the universal wording would claim a set
    // membership `d7` never had — a fabricated claim about a displayed metric,
    // which the delta forbids as much as a fabricated field.
    const shared = within(technical).getByTestId('rainfall-provenance-shared');
    expect(shared.textContent).toContain(
      'Vale solo para las métricas con procedencia servida, en este plegable y en Antecedentes.'
    );
    expect(shared.textContent).not.toContain('todas las métricas mostradas');

    // An empty `quality` and an empty `discrepancies` are the same rule one
    // level down: the guard yields nothing, so there is no line.
    const servedRow = within(technical).getByTestId('rainfall-metric-selected');
    expect(servedRow.textContent).not.toContain('Calidad');
    expect(servedRow.textContent).not.toContain('Discrepancias');
  });

  it('the shared block names Antecedentes only when that fold is on screen', async () => {
    // S2R4-001(b)/S2R3-002. The block is rendered inside the technical fold and
    // speaks for BOTH folds — but the antecedents fold only mounts when the
    // snapshot carries a non-empty `antecedents` group. With none served,
    // naming it points the reader at a control that is not there.
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'ready',
      snapshot: snapshot({
        annual: { selected: metric({ metric: 'selected', value: 850.24 }) },
        antecedents: undefined,
        intensity: undefined,
      }),
    });
    renderPanel();
    const technical = await expandFold('rainfall-technical');

    expect(screen.queryByTestId('rainfall-antecedents')).toBeNull();
    const shared = within(technical).getByTestId('rainfall-provenance-shared');
    expect(shared.textContent).toContain('Vale para todas las métricas mostradas en este plegable.');
    expect(shared.textContent).not.toContain('Antecedentes');
  });

  it('nothing served disappears', async () => {
    // Success criterion 4: with EVERY disclosure expanded, the rendered metric
    // set equals the snapshot's own, and each metric carries its state, its
    // reason where it has one, and its provenance as `shared ∪ row`.
    const served = snapshot({
      annual: {
        selected: metric({ metric: 'selected', value: 850.24 }),
        percentile: metric({ metric: 'percentile', value: 72, unit: 'percentil' }),
      },
      antecedents: { d7: metric({ metric: 'd7', value: 31 }) },
      intensity: { p24h: metric({ metric: 'p24h', value: 12.5 }) },
    });
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({ type: 'ready', snapshot: served });
    renderPanel();
    await expandFold('rainfall-antecedents');
    await expandFold('rainfall-technical');

    const expected = ['selected', 'percentile', 'd7', 'p24h'];
    const rendered = [...document.querySelectorAll('[data-testid^="rainfall-metric-"]')].map(
      (node) => node.getAttribute('data-testid')?.replace('rainfall-metric-', '') ?? ''
    );
    expect([...rendered].sort()).toEqual([...expected].sort());

    for (const name of expected) {
      const row = screen.getByTestId(`rainfall-metric-${name}`);
      expect(row.textContent).toContain('Estado: Disponible');
      expect(row.textContent).toContain('Cobertura: 100%');
    }
    // The unknown group came along, under its raw key (R6).
    expect(screen.getByText('intensity')).toBeInTheDocument();
    // …and the provenance every row shares is one block away, one control.
    expect(screen.getByTestId('rainfall-provenance-shared').textContent).toContain(
      'chirps-v3-final'
    );
  });

  it('places the summary under the shared block, inside the technical fold', async () => {
    renderPanel();
    const technical = await expandFold('rainfall-technical');

    const shared = within(technical).getByTestId('rainfall-provenance-shared');
    const summary = within(technical).getByTestId('rainfall-summary');
    expect(
      (shared.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING) ===
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBe(true);
  });
});

describe('RainfallDetailPanel — cache freshness on parcel change', () => {
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

  it('starts a new analysis query when nomenclatura changes', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = renderPanelWithClient(queryClient, { nomenclatura: 'parcel-a' });
    await screen.findByTestId('rainfall-detail');
    await waitFor(() => expect(fetchRainfallAnalysis).toHaveBeenCalled());

    vi.mocked(fetchRainfallAnalysis).mockClear();
    rerender(<RainfallDetailPanel nomenclatura="parcel-b" />);
    await waitFor(() => expect(fetchRainfallAnalysis).toHaveBeenCalledTimes(1));
  });

  it('does not start a new analysis query when the same nomenclatura re-renders', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = renderPanelWithClient(queryClient, { nomenclatura: 'parcel-a' });
    await screen.findByTestId('rainfall-detail');
    await waitFor(() => expect(fetchRainfallAnalysis).toHaveBeenCalled());

    vi.mocked(fetchRainfallAnalysis).mockClear();
    rerender(<RainfallDetailPanel nomenclatura="parcel-a" />);
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(fetchRainfallAnalysis).not.toHaveBeenCalled();
  });
});

/**
 * The antecedents surfaces after the six rolling-window reference metrics
 * joined the group (SDD S3; backend design D1's closing paragraph).
 *
 * D1 makes the answer-surface requirement hold BY CONSTRUCTION rather than by
 * discipline: `ANTECEDENT_ORDER` is an explicit three-item list, and
 * `RainfallAnswerCard` reads only `snapshot.annual.*`. Both are one-line edits
 * away from being wrong, and neither has a test that would notice — so this
 * block is the standing guard, not a restatement of the fold test.
 */
describe('RainfallDetailPanel — nine rows in the fold, three in the header (S3)', () => {
  /** The nine keys `build_snapshot` emits into `antecedents`, in its order. */
  function nineAntecedents(): Record<string, RainfallMetric> {
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

  beforeEach(() => {
    vi.clearAllMocks();
    setAuth('operador');
    vi.mocked(resolveRainfallScopes).mockResolvedValue({
      kind: 'choices',
      choices: [ZONE],
      regional_estimate: false,
    });
    vi.mocked(fetchRainfallAnalysis).mockResolvedValue({
      type: 'ready',
      snapshot: snapshot({ antecedents: nineAntecedents() }),
    });
  });
  afterEach(() => setAuth(null));

  it('the ALWAYS-VISIBLE collapsed header still states exactly three windows', async () => {
    // The contract `ANTECEDENT_ORDER` exists to hold: a header whose items
    // move with the data is a header nobody can learn to scan, and nine
    // entries in ~26 characters at 348 px is the badge-truncation defect
    // reproduced at the container level. Nine rows are one click away.
    renderPanel();
    const header = await screen.findByTestId('rainfall-antecedents-summary');

    expect(header.textContent?.split('·')).toHaveLength(3);
    expect(header.textContent).toContain('7d');
    expect(header.textContent).toContain('30d');
    expect(header.textContent).toContain('90d');
    // No reference value leaked into it — the header states the TOTALS.
    expect(header.textContent).not.toMatch(/normal|percentil/i);
  });

  it('the fold, once opened, renders all NINE rows', async () => {
    renderPanel();
    const antecedents = await expandFold('rainfall-antecedents');

    for (const key of Object.keys(nineAntecedents())) {
      expect(within(antecedents).getByTestId(`rainfall-metric-${key}`)).toBeInTheDocument();
    }
    // Spec R5: the fold STATES the zone limit where the reference is shown.
    expect(antecedents.textContent).toContain('Alcance de la referencia: zona');
  });

  it('the answer card above the folds still speaks only for the ANNUAL metrics', async () => {
    // `RainfallAnswerCard` reads `snapshot.annual.*` and nothing else. Six new
    // sibling keys in another group must not reach the one surface a reader
    // sees without operating a control — the answer-surface requirement.
    renderPanel();
    const card = await screen.findByTestId('rainfall-answer-card');

    expect(card.textContent).not.toMatch(/Antecedente/);
    expect(card.textContent).not.toMatch(/Alcance de la referencia/);
  });
});
