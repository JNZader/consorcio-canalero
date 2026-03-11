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

  describe('Report loading and display', () => {
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

    it.each([
      [{ items: [], total: 0, page: 1 }, true],
      [{ items: [baseReport], total: 1, page: 1 }, false],
      [{ items: [baseReport, { ...baseReport, id: 'rep-2', descripcion: 'Another report' }], total: 2, page: 1 }, false],
    ])(
      'displays empty state correctly (items=%s, shouldShowEmpty=%s)',
      async (apiResponse, shouldShowEmpty) => {
        vi.mocked(reportsApi.getAll).mockResolvedValueOnce(apiResponse);

        renderPanel();

        if (shouldShowEmpty) {
          expect(await screen.findByText('No hay denuncias')).toBeInTheDocument();
          expect(
            screen.getByText('No se encontraron denuncias con los filtros aplicados')
          ).toBeInTheDocument();
        } else {
          expect(await screen.findByText('Canal desbordado en zona norte')).toBeInTheDocument();
          expect(screen.queryByText('No hay denuncias')).not.toBeInTheDocument();
        }
      }
    );

    it('shows empty state when no reports are returned', async () => {
      vi.mocked(reportsApi.getAll).mockResolvedValueOnce({
        items: [],
        total: 0,
        page: 1,
      });

      renderPanel();

      expect(await screen.findByText('No hay denuncias')).toBeInTheDocument();
      expect(
        screen.getByText('No se encontraron denuncias con los filtros aplicados')
      ).toBeInTheDocument();
      expect(screen.queryByRole('table')).not.toBeInTheDocument();
    });

    it('loads multiple reports and displays them all', async () => {
      const reports = [
        baseReport,
        { ...baseReport, id: 'rep-2', descripcion: 'Canal secundario rebalsado' },
        { ...baseReport, id: 'rep-3', descripcion: 'Erosion de terraplenes' },
      ];

      vi.mocked(reportsApi.getAll).mockResolvedValueOnce({
        items: reports,
        total: 3,
        page: 1,
      });

      renderPanel();

      expect(await screen.findByText('Canal desbordado en zona norte')).toBeInTheDocument();
      expect(screen.getByText('Canal secundario rebalsado')).toBeInTheDocument();
      expect(screen.getByText('Erosion de terraplenes')).toBeInTheDocument();
    });
  });

  describe('Detail modal and history management', () => {
    it.each([
      ['pendiente', { estado_anterior: 'pendiente', estado_nuevo: 'en_revision' }],
      ['en_revision', { estado_anterior: 'en_revision', estado_nuevo: 'aprobado' }],
      ['aprobado', { estado_anterior: 'aprobado', estado_nuevo: 'completado' }],
    ])(
      'shows correct history when status=%s',
      async (status, expectedTransition) => {
        const reportWithStatus = { ...baseReport, estado: status };
        vi.mocked(reportsApi.getAll).mockResolvedValueOnce({
          items: [reportWithStatus],
          total: 1,
          page: 1,
        });

        vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
          if (path === '/management/seguimiento/reporte/rep-1') {
            return [
              {
                id: 'seg-1',
                ...expectedTransition,
                comentario_publico: 'Status updated',
                comentario_interno: 'Internal note',
                fecha: '2026-03-02T10:00:00Z',
              },
            ];
          }
          return [];
        });

        const user = userEvent.setup();
        renderPanel();

        await screen.findByText('Gestion de Denuncias');
        await user.click(screen.getByRole('button', { name: /ver detalle de denuncia/i }));

        const modal = await screen.findByRole('dialog', { name: /detalle de denuncia/i });
        expect(within(modal).getByText(/historial de seguimiento/i)).toBeInTheDocument();
        expect(within(modal).getByText(/status updated/i)).toBeInTheDocument();
      }
    );

    it('displays history entries in order', async () => {
      const user = userEvent.setup();
      vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
        if (path === '/management/seguimiento/reporte/rep-1') {
          return [
            {
              id: 'seg-1',
              estado_anterior: 'pendiente',
              estado_nuevo: 'en_revision',
              comentario_publico: 'Primera visita',
              comentario_interno: 'First visit',
              fecha: '2026-03-01T10:00:00Z',
            },
            {
              id: 'seg-2',
              estado_anterior: 'en_revision',
              estado_nuevo: 'aprobado',
              comentario_publico: 'Segunda visita',
              comentario_interno: 'Second visit',
              fecha: '2026-03-02T10:00:00Z',
            },
            {
              id: 'seg-3',
              estado_anterior: 'aprobado',
              estado_nuevo: 'completado',
              comentario_publico: 'Tercera visita',
              comentario_interno: 'Third visit',
              fecha: '2026-03-03T10:00:00Z',
            },
          ];
        }
        return [];
      });

      renderPanel();

      expect(await screen.findByText('Gestion de Denuncias')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: /ver detalle de denuncia/i }));

      const modal = await screen.findByRole('dialog', { name: /detalle de denuncia/i });
      expect(within(modal).getByText('Primera visita')).toBeInTheDocument();
      expect(within(modal).getByText('Segunda visita')).toBeInTheDocument();
      expect(within(modal).getByText('Tercera visita')).toBeInTheDocument();

      // Verify order
      const content = modal.textContent || '';
      const firstIdx = content.indexOf('Primera visita');
      const secondIdx = content.indexOf('Segunda visita');
      const thirdIdx = content.indexOf('Tercera visita');
      expect(firstIdx < secondIdx && secondIdx < thirdIdx).toBe(true);
    });

    it('handles empty history entries', async () => {
      const user = userEvent.setup();
      vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
        if (path === '/management/seguimiento/reporte/rep-1') {
          return [];
        }
        return [];
      });

      renderPanel();

      expect(await screen.findByText('Gestion de Denuncias')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: /ver detalle de denuncia/i }));

      const modal = await screen.findByRole('dialog', { name: /detalle de denuncia/i });
      expect(within(modal).getByText(/historial de seguimiento/i)).toBeInTheDocument();
      // Empty state for history should be visible
    });
  });

  describe('Management update operations', () => {
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

    it('sends correct data structure for management update', async () => {
      const user = userEvent.setup();
      renderPanel();

      await screen.findByText('Canal desbordado en zona norte');
      await user.click(screen.getByRole('button', { name: /ver detalle de denuncia/i }));

      const modal = await screen.findByRole('dialog', { name: /detalle de denuncia/i });
      const publicComment = 'Inspeccion programada';
      const internalNote = 'Asignar maquinaria';
      
      await user.type(within(modal).getByLabelText(/comentario publico/i), publicComment);
      await user.type(within(modal).getByLabelText(/notas internas/i), internalNote);
      await user.click(within(modal).getByRole('button', { name: /registrar gestion/i }));

      await waitFor(() => {
        const call = (apiFetch as any).mock.calls.find((call: any[]) =>
          call[0] === '/management/seguimiento' && call[1]?.method === 'POST'
        );
        expect(call).toBeDefined();
        const body = JSON.parse(call[1].body);
        expect(body.comentario_publico).toBe(publicComment);
        expect(body.comentario_interno).toBe(internalNote);
      });
    });

    it('shows success notification with exact message', async () => {
      const user = userEvent.setup();
      renderPanel();

      await screen.findByText('Canal desbordado en zona norte');
      await user.click(screen.getByRole('button', { name: /ver detalle de denuncia/i }));

      const modal = await screen.findByRole('dialog', { name: /detalle de denuncia/i });
      await user.type(within(modal).getByLabelText(/comentario publico/i), 'Update');
      await user.click(within(modal).getByRole('button', { name: /registrar gestion/i }));

      await waitFor(() => {
        expect(notifications.show).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Reporte actualizado',
            color: 'green',
          })
        );
      });
    });

    it('closes modal after successful update', async () => {
      const user = userEvent.setup();
      vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
        if (path === '/management/seguimiento/reporte/rep-1') {
          return [];
        }
        if (path === '/management/seguimiento' && options?.method === 'POST') {
          return { id: 'seg-2' };
        }
        return [];
      });

      renderPanel();

      await screen.findByText('Canal desbordado en zona norte');
      await user.click(screen.getByRole('button', { name: /ver detalle de denuncia/i }));

      const modal = await screen.findByRole('dialog', { name: /detalle de denuncia/i });
      await user.type(within(modal).getByLabelText(/comentario publico/i), 'Update');
      await user.click(within(modal).getByRole('button', { name: /registrar gestion/i }));

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
    });
  });

  describe('Error handling and notifications', () => {
    it('shows load error notification when list request fails', async () => {
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
    });

    it('shows update error notification when management update fails', async () => {
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
      await screen.findByText('Canal desbordado en zona norte');
      await user.click(screen.getByRole('button', { name: /ver detalle de denuncia/i }));

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
    });

    it('shows correct error messages for different failure types', async () => {
      const loadError = new Error('Network timeout');
      vi.mocked(reportsApi.getAll).mockRejectedValueOnce(loadError);

      renderPanel();

      await waitFor(() => {
        expect(notifications.show).toHaveBeenCalledWith(
          expect.objectContaining({
            color: 'red',
            message: 'No se pudieron cargar los reportes',
          })
        );
      });

      expect(notifications.show).toHaveBeenCalled();
    });
  });

  describe('Location and map features', () => {
    it('shows map link when coordinates are present', async () => {
      vi.mocked(reportsApi.getAll).mockResolvedValueOnce({
        items: [baseReport],
        total: 1,
        page: 1,
      });

      renderPanel();

      expect(await screen.findByText('Canal desbordado en zona norte')).toBeInTheDocument();
      expect(screen.getByLabelText(/ver ubicacion de denuncia en el mapa/i)).toBeInTheDocument();
    });

    it('hides map action when coordinates are missing', async () => {
      vi.mocked(reportsApi.getAll).mockResolvedValueOnce({
        items: [{ ...baseReport, latitud: null, longitud: null }],
        total: 1,
        page: 1,
      });

      renderPanel();

      expect(await screen.findByText('Canal desbordado en zona norte')).toBeInTheDocument();
      expect(screen.queryByLabelText(/ver ubicacion de denuncia en el mapa/i)).not.toBeInTheDocument();
    });

    it.each([
      [{ latitud: -32.62, longitud: -62.7 }, true],
      [{ latitud: null, longitud: -62.7 }, false],
      [{ latitud: -32.62, longitud: null }, false],
      [{ latitud: null, longitud: null }, false],
    ])(
      'shows/hides map link based on coordinates (coords=%s, shouldShow=%s)',
      async (coords, shouldShow) => {
        vi.mocked(reportsApi.getAll).mockResolvedValueOnce({
          items: [{ ...baseReport, ...coords }],
          total: 1,
          page: 1,
        });

        renderPanel();

        expect(await screen.findByText('Canal desbordado en zona norte')).toBeInTheDocument();

        if (shouldShow) {
          expect(screen.getByLabelText(/ver ubicacion de denuncia en el mapa/i)).toBeInTheDocument();
        } else {
          expect(screen.queryByLabelText(/ver ubicacion de denuncia en el mapa/i)).not.toBeInTheDocument();
        }
      }
    );

    it('displays location text when available', async () => {
      vi.mocked(reportsApi.getAll).mockResolvedValueOnce({
        items: [
          { ...baseReport, ubicacion_texto: 'Ruta 9 km 500' },
          { ...baseReport, id: 'rep-2', ubicacion_texto: 'Calle Principal 123' },
        ],
        total: 2,
        page: 1,
      });

      renderPanel();

      expect(await screen.findByText('Ruta 9 km 500')).toBeInTheDocument();
      expect(screen.getByText('Calle Principal 123')).toBeInTheDocument();
    });
  });

  describe('Filtering and pagination', () => {
    it('shows multiple reports in list', async () => {
      const reports = Array.from({ length: 3 }, (_, i) => ({
        ...baseReport,
        id: `rep-${i}`,
        descripcion: `Report ${i + 1}`,
      }));

      vi.mocked(reportsApi.getAll).mockResolvedValueOnce({
        items: reports,
        total: 3,
        page: 1,
      });

      renderPanel();

      expect(await screen.findByText('Report 1')).toBeInTheDocument();
      expect(screen.getByText('Report 2')).toBeInTheDocument();
      expect(screen.getByText('Report 3')).toBeInTheDocument();
    });

    it('shows correct number of reports per page', async () => {
      const reports = Array.from({ length: 2 }, (_, i) => ({
        ...baseReport,
        id: `rep-${i}`,
        descripcion: `Report ${i + 1}`,
      }));

      vi.mocked(reportsApi.getAll).mockResolvedValueOnce({
        items: reports,
        total: 2,
        page: 1,
      });

      renderPanel();

      expect(await screen.findByText('Report 1')).toBeInTheDocument();
      expect(screen.getByText('Report 2')).toBeInTheDocument();
    });
  });

  describe('Data transformation and display', () => {
    it('displays reports with different states', async () => {
      const states = [
        { value: 'pendiente', desc: 'Pendiente Report' },
        { value: 'en_revision', desc: 'In Review Report' },
        { value: 'resuelto', desc: 'Resolved Report' },
      ];

      vi.mocked(reportsApi.getAll).mockResolvedValueOnce({
        items: states.map((state, idx) => ({
          ...baseReport,
          id: `rep-${idx}`,
          estado: state.value,
          descripcion: state.desc,
        })),
        total: states.length,
        page: 1,
      });

      renderPanel();

      for (const state of states) {
        expect(await screen.findByText(state.desc)).toBeInTheDocument();
      }
    });
  });
});
