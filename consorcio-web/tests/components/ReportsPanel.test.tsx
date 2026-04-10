import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ReportsPanel from '../../src/components/admin/reports/ReportsPanel';
import { apiFetch, reportsApi } from '../../src/lib/api';

const announceMock = vi.fn();

vi.mock('../../src/lib/api', () => ({
  reportsApi: {
    getAll: vi.fn(),
  },
  apiFetch: vi.fn(),
}));

vi.mock('../../src/components/ui/accessibility', () => ({
  LiveRegionProvider: ({ children }: { children: React.ReactNode }) => children,
  useLiveRegion: () => ({ announce: announceMock }),
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

function renderPanel() {
  return render(
    <MantineProvider>
      <ReportsPanel />
    </MantineProvider>
  );
}

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

  it('loads reports, announces the result and shows the main list state', async () => {
    renderPanel();

    expect(await screen.findByText('Gestion de Denuncias')).toBeInTheDocument();
    expect(screen.getByText('Canal desbordado en zona norte')).toBeInTheDocument();
    expect(screen.getByText('Ruta 9 km 500')).toBeInTheDocument();
    expect(screen.getByLabelText(/ver ubicacion de denuncia en el mapa/i)).toHaveAttribute(
      'href',
      '/mapa?lat=-32.62&lng=-62.7&zoom=15'
    );
    expect(announceMock).toHaveBeenCalledWith('Cargando reportes...');
    expect(announceMock).toHaveBeenCalledWith('1 reportes cargados');
  });

  it('shows the empty state when no reports are returned', async () => {
    vi.mocked(reportsApi.getAll).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
    });

    renderPanel();

    expect(await screen.findByText('No hay denuncias')).toBeInTheDocument();
    expect(screen.getByText('No se encontraron denuncias con los filtros aplicados')).toBeInTheDocument();
  });

  it('opens the detail modal and loads report history', async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole('button', { name: /ver detalle de denuncia/i }));

    const modal = await screen.findByRole('dialog', { name: /detalle de denuncia/i });
    expect(within(modal).getByText('Canal desbordado en zona norte')).toBeInTheDocument();
    expect(within(modal).getByText(/historial de seguimiento/i)).toBeInTheDocument();
    expect(within(modal).getByText(/se agenda visita tecnica/i)).toBeInTheDocument();
    expect(within(modal).getByText(/interno: notificar a cuadrilla/i)).toBeInTheDocument();
  });

  it('registers a management update, shows success feedback and refreshes the list', async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole('button', { name: /ver detalle de denuncia/i }));

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

    const postCall = vi.mocked(apiFetch).mock.calls.find(
      ([path, options]) => path === '/management/seguimiento' && options?.method === 'POST'
    );
    expect(postCall).toBeDefined();
    expect(JSON.parse(String(postCall?.[1]?.body))).toMatchObject({
      entidad_tipo: 'reporte',
      entidad_id: 'rep-1',
      estado_anterior: 'pendiente',
      estado_nuevo: 'pendiente',
      comentario_publico: 'Inspeccion programada',
      comentario_interno: 'Asignar maquinaria',
    });

    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Reporte actualizado', color: 'green' })
    );
    expect(announceMock).toHaveBeenCalledWith('Reporte actualizado correctamente');
    expect(reportsApi.getAll).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('shows an error notification when the initial load fails', async () => {
    vi.mocked(reportsApi.getAll).mockRejectedValueOnce(new Error('network'));

    renderPanel();
    await screen.findByText('Gestion de Denuncias');

    await waitFor(() => {
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Error',
          message: 'No se pudieron cargar los reportes',
          color: 'red',
        })
      );
    });
    expect(announceMock).toHaveBeenCalledWith('Error al cargar los reportes');
  });

  it('shows an error notification when the management update fails', async () => {
    const user = userEvent.setup();
    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/management/seguimiento/reporte/rep-1') {
        return [];
      }
      if (path === '/management/seguimiento' && options?.method === 'POST') {
        throw new Error('failed update');
      }
      return [];
    });

    renderPanel();
    await user.click(await screen.findByRole('button', { name: /ver detalle de denuncia/i }));

    const modal = await screen.findByRole('dialog', { name: /detalle de denuncia/i });
    await user.click(within(modal).getByRole('button', { name: /registrar gestion/i }));

    await waitFor(() => {
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Error',
          message: 'No se pudo actualizar el reporte',
          color: 'red',
        })
      );
    });
    expect(announceMock).toHaveBeenCalledWith('Error al actualizar el reporte');
  });

  it('hides the map action when report coordinates are missing', async () => {
    vi.mocked(reportsApi.getAll).mockResolvedValueOnce({
      items: [{ ...baseReport, latitud: null, longitud: null }],
      total: 1,
      page: 1,
    });

    renderPanel();

    expect(await screen.findByText('Canal desbordado en zona norte')).toBeInTheDocument();
    expect(screen.queryByLabelText(/ver ubicacion de denuncia en el mapa/i)).not.toBeInTheDocument();
  });
});
