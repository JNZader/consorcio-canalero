/**
 * admin-pages.test.tsx
 * Unit: contenedor unificado de Participacion Ciudadana (ParticipacionPanel).
 *
 * Los wrappers `Admin*Page` (Reports/Sugerencias/Dashboard) se borraron al
 * unificar: eran codigo muerto — `routeTree.gen.tsx` monta los paneles
 * directamente dentro de `AdminLayoutContent`, nunca paso por ellos.
 */

import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ParticipacionPanel from '../../src/components/admin/participacion/ParticipacionPanel';
import { useCanales } from '../../src/hooks/useCanales';
import { reportsApi, sugerenciasApi } from '../../src/lib/api';

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
  apiFetch: vi.fn(async () => []),
  API_URL: 'http://localhost:8000',
}));

// `useCanales` es el costo que justifica el montaje perezoso: dispara el
// fetch del GeoJSON de relevados apenas monta `SugerenciasPanel`. Lo
// espiamos para probar que NO se paga mientras se mira Reportes.
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

const report = {
  id: 'rep-1',
  created_at: '2026-03-01T10:00:00Z',
  categoria: 'inundacion',
  descripcion: 'Canal desbordado en zona norte',
  ubicacion_texto: 'Ruta 9 km 500',
  estado: 'pendiente',
  latitud: -32.62,
  longitud: -62.7,
  imagenes: [],
};

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

const renderPanel = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider env="test">
        <ParticipacionPanel />
      </MantineProvider>
    </QueryClientProvider>
  );
};

describe('ParticipacionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(reportsApi.getAll).mockResolvedValue({
      items: [report],
      total: 1,
      page: 1,
    });
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
  });

  it('renders the unified header and both tabs', async () => {
    renderPanel();

    expect(screen.getByText('Participacion Ciudadana')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /reportes/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /sugerencias/i })).toBeInTheDocument();
    expect(await screen.findByText('Canal desbordado en zona norte')).toBeInTheDocument();
  });

  it('opens on the Reportes tab', async () => {
    renderPanel();

    expect(screen.getByRole('tab', { name: /reportes/i })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    expect(screen.getByRole('tab', { name: /sugerencias/i })).toHaveAttribute(
      'aria-selected',
      'false'
    );
    await screen.findByText('Canal desbordado en zona norte');
  });

  it('opens on the Sugerencias tab when the URL carries ?tab=sugerencias', async () => {
    // El redirect de la ruta vieja `/admin/sugerencias` llega con este search
    // param; sin honrarlo, el marcador viejo aterrizaria en Reportes.
    window.history.replaceState({}, '', '/admin/participacion?tab=sugerencias');
    try {
      renderPanel();

      expect(await screen.findByText('Limpiar desagues secundarios')).toBeInTheDocument();
      // Y Reportes NO se monto: su fetch nunca corrio (lazy-mount al reves).
      expect(vi.mocked(reportsApi.getAll).mock.calls).toHaveLength(0);
    } finally {
      window.history.replaceState({}, '', '/');
    }
  });

  it('does not mount SugerenciasPanel until its tab is activated', async () => {
    const user = userEvent.setup();
    renderPanel();

    await screen.findByText('Canal desbordado en zona norte');
    // Nada de sugerencias en vuelo mientras se mira Reportes.
    expect(sugerenciasApi.getAll).not.toHaveBeenCalled();
    expect(useCanales).not.toHaveBeenCalled();
    expect(screen.queryByText('Limpiar desagues secundarios')).not.toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /sugerencias/i }));

    expect(await screen.findByText('Limpiar desagues secundarios')).toBeInTheDocument();
    expect(sugerenciasApi.getAll).toHaveBeenCalled();
    expect(useCanales).toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /nuevo tema interno/i })).not.toBeInTheDocument();
    expect(sugerenciasApi).not.toHaveProperty('createInternal');
    expect(sugerenciasApi).not.toHaveProperty('delete');
  });

  it('keeps SugerenciasPanel mounted after switching back to Reportes', async () => {
    const user = userEvent.setup();
    renderPanel();

    await screen.findByText('Canal desbordado en zona norte');
    await user.click(screen.getByRole('tab', { name: /sugerencias/i }));
    await screen.findByText('Limpiar desagues secundarios');

    const sugerenciasLoads = vi.mocked(sugerenciasApi.getAll).mock.calls.length;

    await user.click(screen.getByRole('tab', { name: /reportes/i }));

    // Sigue en el DOM (oculto) y no se remonta: no hay refetch ni se
    // pierden filtros/pagina al volver.
    expect(screen.getByText('Limpiar desagues secundarios')).toBeInTheDocument();
    expect(vi.mocked(sugerenciasApi.getAll).mock.calls).toHaveLength(sugerenciasLoads);
  });
});
