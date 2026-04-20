/**
 * PilarVerdeWidgetConnected.test.tsx
 *
 * Smoke test for the HOOK-wired wrapper that AdminDashboard actually imports.
 * Uses MSW-less `vi.stubGlobal` on `fetch` to feed the 9 Pilar Verde slots and
 * asserts that the widget ends up showing the KPI rows (NOT the "Datos no
 * disponibles" alert).
 *
 * Why this lives apart from `PilarVerdeWidget.test.tsx`:
 *   - That file covers the PROP-DRIVEN presentational layer (fast, zero mocks).
 *   - This file covers the CONNECT LAYER — hook → widget glue — which is the
 *     only thing AdminDashboard really sees.
 */

import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PilarVerdeWidgetConnected } from '../../src/components/admin/pilarVerdeWidget/PilarVerdeWidget';
import { PILAR_VERDE_PUBLIC_PATHS } from '../../src/hooks/usePilarVerde';
import pilarVerdeAggregatesFixture from '../fixtures/pilarVerdeAggregates';

function renderConnected(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>{children}</MantineProvider>
    </QueryClientProvider>,
  );
}

/** Minimal empty GeoJSON feature collection (used for the 6 GeoJSON slots). */
const EMPTY_FC = {
  type: 'FeatureCollection' as const,
  features: [] as unknown[],
};

const EMPTY_ENRICHED = {
  schema_version: '1.0',
  generated_at: '2026-04-20T05:37:59Z',
  source: 'test',
  parcels: [] as unknown[],
};

const EMPTY_HISTORY = {
  schema_version: '1.0',
  generated_at: '2026-04-20T05:37:59Z',
  history: {} as Record<string, unknown>,
};

function buildPayloadForUrl(url: string): unknown {
  if (url.endsWith(PILAR_VERDE_PUBLIC_PATHS.aggregates)) {
    return pilarVerdeAggregatesFixture;
  }
  if (url.endsWith(PILAR_VERDE_PUBLIC_PATHS.bpaEnriched)) {
    return EMPTY_ENRICHED;
  }
  if (url.endsWith(PILAR_VERDE_PUBLIC_PATHS.bpaHistory)) {
    return EMPTY_HISTORY;
  }
  return EMPTY_FC;
}

describe('<PilarVerdeWidgetConnected />', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString();
        const payload = buildPayloadForUrl(url);
        return {
          ok: true,
          status: 200,
          json: async () => payload,
        } as Response;
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the KPI rows once the connected hook resolves', async () => {
    renderConnected(<PilarVerdeWidgetConnected />);
    await waitFor(() => {
      expect(screen.getByTestId('kpi-ley-cumplen')).toBeInTheDocument();
    });
    expect(screen.getByTestId('kpi-bpa-activos')).toBeInTheDocument();
    expect(screen.getByTestId('kpi-historico')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /Ver mapa Pilar Verde/i }),
    ).toHaveAttribute('href', '/mapa');
  });
});
