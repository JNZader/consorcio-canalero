import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HelmetProvider } from 'react-helmet-async';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ReportsPanel from '../../src/components/admin/reports/ReportsPanel';
import SugerenciasPanel from '../../src/components/admin/sugerencias/SugerenciasPanel';
import { RootLayout } from '../../src/components/RootLayout';
import { LiveRegionProvider, useLiveRegion } from '../../src/components/ui/accessibility';
import { apiFetch, reportsApi, sugerenciasApi } from '../../src/lib/api';

vi.mock('../../src/components/Header', () => ({
  default: () => <div data-testid="mock-header">Header</div>,
}));

vi.mock('../../src/components/Footer', () => ({
  default: () => <div data-testid="mock-footer">Footer</div>,
}));

vi.mock('../../src/lib/api', () => ({
  reportsApi: {
    getAll: vi.fn(),
  },
  sugerenciasApi: {
    getAll: vi.fn(),
    get: vi.fn(),
    getStats: vi.fn(),
    getProximaReunion: vi.fn(),
    agendar: vi.fn(),
  },
  apiFetch: vi.fn(),
  API_URL: 'http://localhost:8000',
}));

vi.mock('../../src/hooks/useCanales', () => ({
  useCanales: vi.fn(() => ({
    relevados: null,
    propuestas: null,
    index: null,
    isLoading: false,
    isError: false,
  })),
}));

vi.mock('@mantine/notifications', () => ({
  notifications: {
    show: vi.fn(),
  },
}));

vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}));

describe('LiveRegionProvider hoisting (A11Y-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(reportsApi.getAll).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
    });
    vi.mocked(sugerenciasApi.getAll).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      limit: 10,
    });
    vi.mocked(sugerenciasApi.getStats).mockResolvedValue({
      pendiente: 0,
      en_agenda: 0,
      tratado: 0,
      descartado: 0,
      total: 0,
      ciudadanas: 0,
      internas: 0,
    });
    vi.mocked(sugerenciasApi.getProximaReunion).mockResolvedValue([]);
    vi.mocked(apiFetch).mockResolvedValue([]);
  });

  it('populates the RootLayout polite and assertive live regions when child calls announce()', async () => {
    const user = userEvent.setup();

    function ChildConsumer() {
      const { announce } = useLiveRegion();
      return (
        <div>
          <button
            type="button"
            onClick={() => announce('Reporte enviado correctamente', 'polite')}
          >
            Anunciar polite
          </button>
          <button type="button" onClick={() => announce('Error crítico', 'assertive')}>
            Anunciar assertive
          </button>
        </div>
      );
    }

    render(
      <HelmetProvider>
        <RootLayout title="Participación">
          <ChildConsumer />
        </RootLayout>
      </HelmetProvider>
    );

    await user.click(screen.getByRole('button', { name: 'Anunciar polite' }));
    await waitFor(() => {
      expect(screen.getByTestId('live-region-polite')).toHaveTextContent(
        'Reporte enviado correctamente'
      );
    });

    await user.click(screen.getByRole('button', { name: 'Anunciar assertive' }));
    await waitFor(() => {
      expect(screen.getByTestId('live-region-assertive')).toHaveTextContent('Error crítico');
    });
  });

  it('does not mount duplicate live region DOM nodes when nested inside RootLayout', () => {
    render(
      <HelmetProvider>
        <RootLayout title="Nested Test">
          <LiveRegionProvider>
            <div>Contenido anidado</div>
          </LiveRegionProvider>
        </RootLayout>
      </HelmetProvider>
    );

    expect(screen.getAllByTestId('live-region-polite')).toHaveLength(1);
    expect(screen.getAllByTestId('live-region-assertive')).toHaveLength(1);
  });

  it('populates the root live region when ReportsPanel loads inside RootLayout', async () => {
    render(
      <HelmetProvider>
        <MantineProvider env="test">
          <RootLayout title="Admin Reportes" hideHeader hideFooter>
            <ReportsPanel />
          </RootLayout>
        </MantineProvider>
      </HelmetProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('live-region-polite')).toHaveTextContent('0 reportes cargados');
    });
  });

  it('populates the root live region when SugerenciasPanel loads inside RootLayout', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <HelmetProvider>
        <QueryClientProvider client={queryClient}>
          <MantineProvider env="test">
            <RootLayout title="Admin Sugerencias" hideHeader hideFooter>
              <SugerenciasPanel />
            </RootLayout>
          </MantineProvider>
        </QueryClientProvider>
      </HelmetProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('live-region-polite')).toHaveTextContent(
        '0 sugerencias cargadas'
      );
    });
  });
});
