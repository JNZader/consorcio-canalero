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

vi.mock('../../src/lib/api/rainfall', () => ({
  resolveRainfallScopes: vi.fn(),
  fetchRainfallAnalysis: vi.fn(),
  downloadRainfallCsv: vi.fn(),
}));

import type { RainfallAnalysisSnapshot, RainfallMetric } from '../../src/lib/api/rainfall';
import {
  downloadRainfallCsv,
  fetchRainfallAnalysis,
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
    await screen.findByTestId('rainfall-metrics');
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
    const metrics = await screen.findByTestId('rainfall-metrics');

    expect(within(metrics).getAllByText('Disponible').length).toBeGreaterThan(0);
    expect(within(metrics).getByText('Parcial')).toBeInTheDocument();
    expect(within(metrics).getByText(/Suprimida/)).toBeInTheDocument();
    expect(within(metrics).getByText(/coverage_below_threshold/)).toBeInTheDocument();
    expect(within(metrics).getByText(/No disponible/)).toBeInTheDocument();
    expect(within(metrics).getByText(/sin fuente elegible/)).toBeInTheDocument();
  });

  it('never renders a suppressed or unavailable metric as zero', async () => {
    renderPanel();
    const metrics = await screen.findByTestId('rainfall-metrics');

    const suppressedRow = screen.getByTestId('rainfall-metric-d30');
    // The value renders "—". NB: the assertion targets the VALUE slot — the
    // provenance line legitimately contains "0.05°" (nominal resolution).
    expect(suppressedRow.textContent).not.toContain('0.0 mm');
    expect(suppressedRow.textContent).not.toMatch(/\b0 mm\b/);
    expect(metrics).toBeInTheDocument();
  });

  it('shows a provisional badge only for provisional metrics', async () => {
    renderPanel();
    const peakRow = await screen.findByTestId('rainfall-metric-peak');
    expect(within(peakRow).getByText('Provisional')).toBeInTheDocument();

    const selectedRow = screen.getByTestId('rainfall-metric-selected');
    expect(within(selectedRow).queryByText('Provisional')).toBeNull();
  });

  it('exposes provenance: source, nominal resolution and revision', async () => {
    renderPanel();
    const row = await screen.findByTestId('rainfall-metric-selected');
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
