// @ts-nocheck
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
  });

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
});
