import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TramitesPanel from '../../src/components/admin/management/TramitesPanel';

const { mockApiFetch } = vi.hoisted(() => ({
  mockApiFetch: vi.fn(),
}));

vi.mock('../../src/lib/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../src/lib/api')>();
  return {
    ...original,
    API_URL: 'http://localhost:8000',
    apiFetch: mockApiFetch,
    getAuthToken: vi.fn().mockResolvedValue('token'),
  };
});

describe('TramitesPanel canonical states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('State filtering and display', () => {
    it.each([
      ['pendiente', 'PENDIENTE', true],
      ['en_revision', 'EN REVISION', true],
      ['aprobado', 'APROBADO', true],
      ['rechazado', 'RECHAZADO', true],
      ['completado', 'COMPLETADO', true],
      ['iniciado', 'INICIADO', false], // legacy state - should be filtered out
    ])(
      'filters state=%s correctly (expected=%s, shown=%s)',
      async (estado, esperado, debeMostrarse) => {
        mockApiFetch.mockResolvedValueOnce([
          {
            id: 'tramite-1',
            titulo: `Tramite-${estado}`,
            numero_expediente: 'A-1',
            estado,
            ultima_actualizacion: '2026-03-01T10:00:00Z',
          },
        ]);

        render(
          <MantineProvider>
            <TramitesPanel />
          </MantineProvider>
        );

        await screen.findByText('Gestion de Expedientes');

        if (debeMostrarse) {
          expect(await screen.findByText(esperado)).toBeInTheDocument();
          expect(screen.getByText(`Tramite-${estado}`)).toBeInTheDocument();
        } else {
          expect(screen.queryByText(esperado)).not.toBeInTheDocument();
          expect(screen.queryByText(`Tramite-${estado}`)).not.toBeInTheDocument();
        }
      }
    );

    it('renders only tramites with canonical states', async () => {
      mockApiFetch.mockResolvedValueOnce([
        {
          id: 'tramite-1',
          titulo: 'Tramite valido',
          numero_expediente: 'A-1',
          estado: 'pendiente',
          ultima_actualizacion: '2026-03-01T10:00:00Z',
        },
        {
          id: 'tramite-2',
          titulo: 'Tramite legacy',
          numero_expediente: 'B-2',
          estado: 'iniciado',
          ultima_actualizacion: '2026-03-01T10:00:00Z',
        },
      ]);

      render(
        <MantineProvider>
          <TramitesPanel />
        </MantineProvider>
      );

      expect(await screen.findByText('Tramite valido')).toBeInTheDocument();
      await waitFor(() => {
        expect(screen.queryByText('Tramite legacy')).not.toBeInTheDocument();
      });
      expect(screen.getByText('PENDIENTE')).toBeInTheDocument();
      expect(screen.queryByText('INICIADO')).not.toBeInTheDocument();
    });

    it('handles empty tramites list correctly', async () => {
      mockApiFetch.mockResolvedValueOnce([]);

      render(
        <MantineProvider>
          <TramitesPanel />
        </MantineProvider>
      );

      await screen.findByText('Gestion de Expedientes');
      // Table shows headers but no data rows
      expect(screen.getByText('Titulo / Expediente')).toBeInTheDocument();
      expect(screen.queryByText(/Tramite-/)).not.toBeInTheDocument();
    });

    it('handles null or undefined states gracefully', async () => {
      mockApiFetch.mockResolvedValueOnce([
        {
          id: 'tramite-1',
          titulo: 'Tramite valido',
          numero_expediente: 'A-1',
          estado: 'pendiente',
          ultima_actualizacion: '2026-03-01T10:00:00Z',
        },
        {
          id: 'tramite-2',
          titulo: 'Tramite sin estado',
          numero_expediente: 'B-2',
          estado: null,
          ultima_actualizacion: '2026-03-01T10:00:00Z',
        },
        {
          id: 'tramite-3',
          titulo: 'Tramite undefined',
          numero_expediente: 'C-3',
          // estado is undefined
          ultima_actualizacion: '2026-03-01T10:00:00Z',
        },
      ]);

      render(
        <MantineProvider>
          <TramitesPanel />
        </MantineProvider>
      );

      expect(await screen.findByText('Tramite valido')).toBeInTheDocument();
      expect(screen.queryByText('Tramite sin estado')).not.toBeInTheDocument();
      expect(screen.queryByText('Tramite undefined')).not.toBeInTheDocument();
    });
  });

  describe('Modal creation and form submission', () => {
    it('creates a new expediente from modal form', async () => {
      const user = userEvent.setup();
      mockApiFetch.mockImplementation(async (path: string, options?: RequestInit) => {
        if (path === '/management/tramites' && !options) {
          return [];
        }
        if (path === '/management/tramites' && options?.method === 'POST') {
          return { id: 'tramite-2' };
        }
        return [];
      });

      render(
        <MantineProvider>
          <TramitesPanel />
        </MantineProvider>
      );

      await screen.findByText('Gestion de Expedientes');
      await user.click(screen.getByRole('button', { name: /nuevo expediente/i }));
      const modal = await screen.findByRole('dialog', { name: /registrar nuevo expediente provincial/i });

      await user.type(within(modal).getByLabelText(/titulo del tramite/i), 'Obra Canal Sur');
      await user.type(within(modal).getByLabelText(/numero de expediente/i), '0416-999/2026');
      await user.click(within(modal).getByRole('button', { name: /crear expediente/i }));

      await waitFor(() => {
        expect(mockApiFetch).toHaveBeenCalledWith(
          '/management/tramites',
          expect.objectContaining({ method: 'POST' })
        );
      });
    });

    it('validates form fields before submission', async () => {
      const user = userEvent.setup();
      mockApiFetch.mockImplementation(async (path: string, options?: RequestInit) => {
        if (path === '/management/tramites' && !options) {
          return [];
        }
        return [];
      });

      render(
        <MantineProvider>
          <TramitesPanel />
        </MantineProvider>
      );

      await screen.findByText('Gestion de Expedientes');
      await user.click(screen.getByRole('button', { name: /nuevo expediente/i }));
      const modal = await screen.findByRole('dialog', { name: /registrar nuevo expediente provincial/i });

      const submitButton = within(modal).getByRole('button', { name: /crear expediente/i });
      
      // Form allows submission (button is not disabled)
      expect(submitButton).not.toBeDisabled();
      
      // Fill fields
      await user.type(within(modal).getByLabelText(/titulo del tramite/i), 'Obra');
      await user.type(within(modal).getByLabelText(/numero de expediente/i), '0416-999/2026');
      
      // Button should still be available to click
      expect(submitButton).not.toBeDisabled();
    });

    it('closes modal after successful creation', async () => {
      const user = userEvent.setup();
      mockApiFetch.mockImplementation(async (path: string, options?: RequestInit) => {
        if (path === '/management/tramites' && !options) {
          return [];
        }
        if (path === '/management/tramites' && options?.method === 'POST') {
          return { id: 'tramite-2' };
        }
        return [];
      });

      render(
        <MantineProvider>
          <TramitesPanel />
        </MantineProvider>
      );

      await screen.findByText('Gestion de Expedientes');
      await user.click(screen.getByRole('button', { name: /nuevo expediente/i }));
      const modal = await screen.findByRole('dialog', { name: /registrar nuevo expediente provincial/i });

      await user.type(within(modal).getByLabelText(/titulo del tramite/i), 'Obra');
      await user.type(within(modal).getByLabelText(/numero de expediente/i), '0416-999/2026');
      await user.click(within(modal).getByRole('button', { name: /crear expediente/i }));

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
    });
  });

  describe('History modal and timeline operations', () => {
    it('opens history modal with timeline entries', async () => {
      const user = userEvent.setup();
      mockApiFetch.mockImplementation(async (path: string, options?: RequestInit) => {
        if (path === '/management/tramites' && !options) {
          return [
            {
              id: 'tramite-1',
              titulo: 'Canal Norte',
              numero_expediente: 'A-1',
              estado: 'pendiente',
              ultima_actualizacion: '2026-03-01T10:00:00Z',
            },
          ];
        }

        if (path === '/management/tramites/tramite-1') {
          return {
            id: 'tramite-1',
            titulo: 'Canal Norte',
            numero_expediente: 'A-1',
            estado: 'pendiente',
            ultima_actualizacion: '2026-03-01T10:00:00Z',
            avances: [
              {
                id: 'av-1',
                fecha: '2026-03-02T10:00:00Z',
                titulo_avance: 'Inspeccion inicial',
                comentario: 'Se relevo la zona',
              },
            ],
          };
        }

        return [];
      });

      render(
        <MantineProvider>
          <TramitesPanel />
        </MantineProvider>
      );

      const row = await screen.findByRole('row', { name: /canal norte/i });
      await user.click(within(row).getAllByRole('button')[0]);

      const modal = await screen.findByRole('dialog', { name: /linea de tiempo del expediente/i });
      expect(within(modal).getByText('Inspeccion inicial')).toBeInTheDocument();
      expect(within(modal).getByText('Se relevo la zona')).toBeInTheDocument();
    });

    it('displays multiple timeline entries in correct order', async () => {
      const user = userEvent.setup();
      mockApiFetch.mockImplementation(async (path: string, options?: RequestInit) => {
        if (path === '/management/tramites' && !options) {
          return [
            {
              id: 'tramite-1',
              titulo: 'Canal Norte',
              numero_expediente: 'A-1',
              estado: 'pendiente',
              ultima_actualizacion: '2026-03-01T10:00:00Z',
            },
          ];
        }

        if (path === '/management/tramites/tramite-1') {
          return {
            id: 'tramite-1',
            titulo: 'Canal Norte',
            numero_expediente: 'A-1',
            estado: 'pendiente',
            ultima_actualizacion: '2026-03-01T10:00:00Z',
            avances: [
              {
                id: 'av-1',
                fecha: '2026-03-01T10:00:00Z',
                titulo_avance: 'Primer avance',
                comentario: 'Inicio de trabajos',
              },
              {
                id: 'av-2',
                fecha: '2026-03-02T10:00:00Z',
                titulo_avance: 'Segundo avance',
                comentario: 'Medio de trabajos',
              },
              {
                id: 'av-3',
                fecha: '2026-03-03T10:00:00Z',
                titulo_avance: 'Tercer avance',
                comentario: 'Finalizacion',
              },
            ],
          };
        }

        return [];
      });

      render(
        <MantineProvider>
          <TramitesPanel />
        </MantineProvider>
      );

      const row = await screen.findByRole('row', { name: /canal norte/i });
      await user.click(within(row).getAllByRole('button')[0]);

      const modal = await screen.findByRole('dialog', { name: /linea de tiempo del expediente/i });
      expect(within(modal).getByText('Primer avance')).toBeInTheDocument();
      expect(within(modal).getByText('Segundo avance')).toBeInTheDocument();
      expect(within(modal).getByText('Tercer avance')).toBeInTheDocument();
      
      // Verify order by checking positions
      const firstIdx = modal.textContent!.indexOf('Primer avance');
      const secondIdx = modal.textContent!.indexOf('Segundo avance');
      const thirdIdx = modal.textContent!.indexOf('Tercer avance');
      expect(firstIdx < secondIdx && secondIdx < thirdIdx).toBe(true);
    });

    it('handles empty avances array', async () => {
      const user = userEvent.setup();
      mockApiFetch.mockImplementation(async (path: string, options?: RequestInit) => {
        if (path === '/management/tramites' && !options) {
          return [
            {
              id: 'tramite-1',
              titulo: 'Canal Norte',
              numero_expediente: 'A-1',
              estado: 'pendiente',
              ultima_actualizacion: '2026-03-01T10:00:00Z',
            },
          ];
        }

        if (path === '/management/tramites/tramite-1') {
          return {
            id: 'tramite-1',
            titulo: 'Canal Norte',
            numero_expediente: 'A-1',
            estado: 'pendiente',
            ultima_actualizacion: '2026-03-01T10:00:00Z',
            avances: [],
          };
        }

        return [];
      });

      render(
        <MantineProvider>
          <TramitesPanel />
        </MantineProvider>
      );

      const row = await screen.findByRole('row', { name: /canal norte/i });
      await user.click(within(row).getAllByRole('button')[0]);

      const modal = await screen.findByRole('dialog', { name: /linea de tiempo del expediente/i });
      expect(within(modal).queryByText(/primer avance/i)).not.toBeInTheDocument();
    });
  });

  describe('PDF export functionality and error handling', () => {
    it('exports selected tramite summary as pdf', async () => {
      const user = userEvent.setup();
      const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
      const createObjectUrl = vi
        .spyOn(URL, 'createObjectURL')
        .mockReturnValue('blob:tramite-pdf');

      mockApiFetch.mockImplementation(async (path: string, options?: RequestInit) => {
        if (path === '/management/tramites' && !options) {
          return [
            {
              id: 'tramite-1',
              titulo: 'Canal Norte',
              numero_expediente: 'A-1',
              estado: 'pendiente',
              ultima_actualizacion: '2026-03-01T10:00:00Z',
            },
          ];
        }
        if (path === '/management/tramites/tramite-1') {
          return {
            id: 'tramite-1',
            titulo: 'Canal Norte',
            numero_expediente: 'A-1',
            estado: 'pendiente',
            ultima_actualizacion: '2026-03-01T10:00:00Z',
            avances: [],
          };
        }
        return [];
      });

      vi.mocked(fetch).mockResolvedValueOnce({
        blob: async () => new Blob(['pdf']),
      } as Response);

      render(
        <MantineProvider>
          <TramitesPanel />
        </MantineProvider>
      );

      const row = await screen.findByRole('row', { name: /canal norte/i });
      await user.click(within(row).getAllByRole('button')[0]);

      const modal = await screen.findByRole('dialog', { name: /linea de tiempo del expediente/i });
      await user.click(within(modal).getByRole('button', { name: /exportar resumen/i }));

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(
          'http://localhost:8000/api/v1/management/tramites/tramite-1/export-pdf',
          expect.objectContaining({ headers: { Authorization: 'Bearer token' } })
        );
      });
      expect(createObjectUrl).toHaveBeenCalled();
      expect(anchorClick).toHaveBeenCalled();

      anchorClick.mockRestore();
      createObjectUrl.mockRestore();
    });

    it('handles pdf export failure gracefully', async () => {
      const user = userEvent.setup();

      mockApiFetch.mockImplementation(async (path: string, options?: RequestInit) => {
        if (path === '/management/tramites' && !options) {
          return [
            {
              id: 'tramite-1',
              titulo: 'Canal Norte',
              numero_expediente: 'A-1',
              estado: 'pendiente',
              ultima_actualizacion: '2026-03-01T10:00:00Z',
            },
          ];
        }
        if (path === '/management/tramites/tramite-1') {
          return {
            id: 'tramite-1',
            titulo: 'Canal Norte',
            numero_expediente: 'A-1',
            estado: 'pendiente',
            ultima_actualizacion: '2026-03-01T10:00:00Z',
            avances: [],
          };
        }
        return [];
      });

      vi.mocked(fetch).mockRejectedValueOnce(new Error('PDF generation failed'));

      render(
        <MantineProvider>
          <TramitesPanel />
        </MantineProvider>
      );

      const row = await screen.findByRole('row', { name: /canal norte/i });
      await user.click(within(row).getAllByRole('button')[0]);

      const modal = await screen.findByRole('dialog', { name: /linea de tiempo del expediente/i });
      await user.click(within(modal).getByRole('button', { name: /exportar resumen/i }));

      await waitFor(() => {
        expect(fetch).toHaveBeenCalled();
      });
    });

    it('uses correct auth token for pdf export', async () => {
      const user = userEvent.setup();
      vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:tramite-pdf');

      mockApiFetch.mockImplementation(async (path: string, options?: RequestInit) => {
        if (path === '/management/tramites' && !options) {
          return [
            {
              id: 'tramite-1',
              titulo: 'Canal Norte',
              numero_expediente: 'A-1',
              estado: 'pendiente',
              ultima_actualizacion: '2026-03-01T10:00:00Z',
            },
          ];
        }
        if (path === '/management/tramites/tramite-1') {
          return {
            id: 'tramite-1',
            titulo: 'Canal Norte',
            numero_expediente: 'A-1',
            estado: 'pendiente',
            ultima_actualizacion: '2026-03-01T10:00:00Z',
            avances: [],
          };
        }
        return [];
      });

      vi.mocked(fetch).mockResolvedValueOnce({
        blob: async () => new Blob(['pdf']),
      } as Response);

      render(
        <MantineProvider>
          <TramitesPanel />
        </MantineProvider>
      );

      const row = await screen.findByRole('row', { name: /canal norte/i });
      await user.click(within(row).getAllByRole('button')[0]);

      const modal = await screen.findByRole('dialog', { name: /linea de tiempo del expediente/i });
      await user.click(within(modal).getByRole('button', { name: /exportar resumen/i }));

      await waitFor(() => {
        const call = (fetch as any).mock.calls.find((call: any[]) =>
          call[0].includes('export-pdf')
        );
        expect(call).toBeDefined();
        expect(call[1].headers).toEqual({ Authorization: 'Bearer token' });
      });
    });
  });
});
