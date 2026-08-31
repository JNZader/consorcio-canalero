import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SugerenciasPanel from '../../src/components/admin/sugerencias/SugerenciasPanel';
import { apiFetch, sugerenciasApi } from '../../src/lib/api';

vi.mock('../../src/lib/api', () => ({
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

// Batch 5 (2026-04-20): swapped `useWaterways` mock for `useCanales` mock —
// `SugerenciasPanel` migrated to `useCanales().relevados` for the admin
// reference-map backdrop. Return `relevados: null` so the panel's `useMemo`
// emits an empty canales array (no-op reference layer — test-friendly).
vi.mock('../../src/hooks/useCanales', () => ({
  useCanales: vi.fn(() => ({
    relevados: null,
    propuestas: null,
    index: null,
    isLoading: false,
    isError: false,
  })),
}));

vi.mock('../../src/components/ui/accessibility', () => ({
  LiveRegionProvider: ({ children }: { children: React.ReactNode }) => children,
  useLiveRegion: () => ({ announce: vi.fn() }),
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

const suggestion = {
  id: 'sug-1',
  tipo: 'ciudadana' as const,
  titulo: 'Limpiar desagues secundarios',
  descripcion: 'Solicitamos limpieza por acumulacion de barro',
  categoria: 'infraestructura',
  estado: 'pendiente' as const,
  prioridad: 'alta' as const,
  created_at: '2026-03-01T09:00:00Z',
  updated_at: '2026-03-01T09:00:00Z',
};

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

const renderPanel = () => {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider env="test">
        <SugerenciasPanel />
      </MantineProvider>
    </QueryClientProvider>
  );
};

describe('SugerenciasPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(sugerenciasApi.get).mockResolvedValue(suggestion);
    vi.mocked(sugerenciasApi.getAll).mockResolvedValue({
      items: [suggestion],
      total: 1,
      page: 1,
      limit: 10,
    });
    vi.mocked(sugerenciasApi.getStats).mockResolvedValue({
      pendiente: 1,
      en_agenda: 0,
      tratado: 0,
      descartado: 0,
      total: 1,
      ciudadanas: 1,
      internas: 0,
    });
    vi.mocked(sugerenciasApi.getProximaReunion).mockResolvedValue([]);

    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/sugerencias/sug-1/historial') {
        return [
          {
            id: 'hist-1',
            estado_anterior: 'pendiente',
            estado_nuevo: 'en_agenda',
            comentario_publico: 'Se incluye en el orden del dia',
            comentario_interno: 'Prioridad alta',
            fecha: '2026-03-02T10:00:00Z',
          },
        ];
      }

      if (path.startsWith('/sugerencias/') && options?.method === 'PATCH') {
        return { id: 'sug-1' };
      }

      return [];
    });
  });

  it('renders cards and suggestions table, then opens detail', async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(await screen.findByText('Pendientes')).toBeInTheDocument();
    expect(screen.getByText('Limpiar desagues secundarios')).toBeInTheDocument();
    expect(screen.getByText('Pendientes')).toBeInTheDocument();

    const row = screen.getByRole('row', {
      name: /limpiar desagues secundarios infraestructura ciudadana pendiente/i,
    });
    await user.click(within(row).getByRole('button'));
    const modal = await screen.findByRole('dialog', { name: /detalle de sugerencia/i });
    expect(within(modal).getByText('Solicitamos limpieza por acumulacion de barro')).toBeInTheDocument();

    const historyToggle = within(modal).getByRole('button', { name: /mostrar/i });
    expect(historyToggle).toHaveAttribute('aria-expanded', 'false');
    expect(historyToggle).toHaveAttribute('aria-controls', 'suggestion-history-region');

    await user.click(historyToggle);

    expect(historyToggle).toHaveAttribute('aria-expanded', 'true');
    expect(
      within(modal).getByRole('region', { name: /historial de gestión de la sugerencia/i })
    ).toHaveAttribute('id', 'suggestion-history-region');
    expect(within(modal).queryByRole('button', { name: /eliminar/i })).not.toBeInTheDocument();
  });

  it('does not render create-internal or delete controls', async () => {
    renderPanel();

    await screen.findByText('Pendientes');
    expect(screen.queryByRole('button', { name: /nuevo tema interno/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: /nuevo tema interno/i })).not.toBeInTheDocument();
    expect(sugerenciasApi).not.toHaveProperty('createInternal');
    expect(sugerenciasApi).not.toHaveProperty('delete');
  });

  it('submits management update', async () => {
    const user = userEvent.setup();
    renderPanel();

    await screen.findByText('Pendientes');

    const row = screen.getByRole('row', {
      name: /limpiar desagues secundarios infraestructura ciudadana pendiente/i,
    });
    await user.click(within(row).getByRole('button'));
    const detailModal = await screen.findByRole('dialog', { name: /detalle de sugerencia/i });
    await user.type(within(detailModal).getByPlaceholderText(/vecino/i), 'Pasa a agenda');
    await user.click(within(detailModal).getByRole('button', { name: /registrar gestión/i }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith(
        '/sugerencias/sug-1',
        expect.objectContaining({ method: 'PATCH' })
      );
    });
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Sugerencia actualizada', color: 'green' })
    );
  });

  it('shows empty state when no suggestions are returned', async () => {
    vi.mocked(sugerenciasApi.getAll).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      limit: 10,
    });

    renderPanel();

    expect(await screen.findByText('No hay sugerencias')).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'No hay sugerencias' })).toHaveAccessibleDescription(
      'No se encontraron sugerencias con los filtros aplicados'
    );
    expect(
      screen.getByText('No se encontraron sugerencias con los filtros aplicados')
    ).toBeInTheDocument();
  });

  it('shows error notification when listing suggestions fails', async () => {
    vi.mocked(sugerenciasApi.getAll).mockRejectedValueOnce(new Error('network'));

    renderPanel();
    await screen.findByText('Pendientes');

    await waitFor(() => {
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Error',
          message: 'No se pudieron cargar las sugerencias',
          color: 'red',
        })
      );
    });
  });

  it('agendas a pending suggestion from detail modal', async () => {
    const user = userEvent.setup();
    vi.mocked(sugerenciasApi.getAll).mockResolvedValueOnce({
      items: [{ ...suggestion, fecha_reunion: '2026-04-10' }],
      total: 1,
      page: 1,
      limit: 10,
    });
    vi.mocked(sugerenciasApi.agendar).mockResolvedValueOnce({ id: 'sug-1' } as never);

    renderPanel();
    const row = await screen.findByRole('row', {
      name: /limpiar desagues secundarios infraestructura ciudadana pendiente/i,
    });
    await user.click(within(row).getByRole('button'));

    const modal = await screen.findByRole('dialog', { name: /detalle de sugerencia/i });
    await user.click(within(modal).getByRole('button', { name: /^agendar$/i }));

    await waitFor(() => {
      expect(sugerenciasApi.agendar).toHaveBeenCalledWith('sug-1', '2026-04-10');
    });

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Sugerencia agendada', color: 'blue' })
    );
  });
});
