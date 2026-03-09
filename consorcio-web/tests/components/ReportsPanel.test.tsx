import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ReportsPanel from '../../src/components/admin/reports/ReportsPanel';
import { apiFetch, reportsApi } from '../../src/lib/api';

vi.mock('../../src/lib/api', () => ({
  reportsApi: {
    getAll: vi.fn(),
  },
  apiFetch: vi.fn(),
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

const baseReport = {
  id: 'rep-1',
  created_at: '2026-03-01T10:00:00Z',
  categoria: 'inundacion',
  descripcion: 'Canal desbordado en zona norte',
  ubicacion_texto: 'Ruta 9 km 500',
  estado: 'pendiente',
  latitud: -32.62,
  longitud: -62.7,
  imagenes: ['https://cdn.example.com/img-1.jpg'],
  contacto_nombre: 'Juan Perez',
  contacto_telefono: '3534000000',
};

const renderPanel = () =>
  render(
    <MantineProvider>
      <ReportsPanel />
    </MantineProvider>
  );

describe('ReportsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(reportsApi.getAll).mockResolvedValue({
      items: [baseReport],
      total: 1,
      page: 1,
    });

    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/management/seguimiento/reporte/rep-1') {
        return [
          {
            id: 'seg-1',
            estado_anterior: 'pendiente',
            estado_nuevo: 'en_revision',
            comentario_publico: 'Se agenda visita tecnica',
            comentario_interno: 'Notificar a cuadrilla',
            fecha: '2026-03-02T10:00:00Z',
          },
        ];
      }

      if (path === '/management/seguimiento' && options?.method === 'POST') {
        return { id: 'seg-2' };
      }

      return [];
    });
  });

  it('loads reports and opens detail modal with history', async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(await screen.findByText('Gestion de Denuncias')).toBeInTheDocument();
    expect(screen.getByText('Canal desbordado en zona norte')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /ver detalle de denuncia/i }));

    const modal = await screen.findByRole('dialog', { name: /detalle de denuncia/i });
    expect(within(modal).getByText('Canal desbordado en zona norte')).toBeInTheDocument();
    expect(within(modal).getByText(/historial de seguimiento/i)).toBeInTheDocument();
    expect(within(modal).getByText(/se agenda visita tecnica/i)).toBeInTheDocument();
  });

  it('registers management update and refreshes list', async () => {
    const user = userEvent.setup();
    renderPanel();

    await screen.findByText('Canal desbordado en zona norte');
    await user.click(screen.getByRole('button', { name: /ver detalle de denuncia/i }));

    const modal = await screen.findByRole('dialog', { name: /detalle de denuncia/i });
    await user.type(within(modal).getByLabelText(/comentario publico/i), 'Inspeccion programada');
    await user.type(within(modal).getByLabelText(/notas internas/i), 'Asignar maquinaria');
    await user.click(within(modal).getByRole('button', { name: /registrar gestion/i }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith(
        '/management/seguimiento',
        expect.objectContaining({ method: 'POST' })
      );
    });
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Reporte actualizado', color: 'green' })
    );
    expect(reportsApi.getAll).toHaveBeenCalledTimes(2);
  });
});
