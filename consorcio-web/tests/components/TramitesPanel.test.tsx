import { MantineProvider } from '@mantine/core';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import TramitesPanel from '../../src/components/admin/management/TramitesPanel';

const { mockApiFetch, mockGetAuthToken } = vi.hoisted(() => ({
  mockApiFetch: vi.fn(),
  mockGetAuthToken: vi.fn().mockResolvedValue('token'),
}));

vi.mock('../../src/lib/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../src/lib/api')>();
  return {
    ...original,
    API_URL: 'http://localhost:8000',
    apiFetch: mockApiFetch,
    getAuthToken: mockGetAuthToken,
  };
});

vi.mock('../../src/lib/logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}));

const canonicalTramite = {
  id: 'tramite-1',
  titulo: 'Canal Norte',
  numero_expediente: 'A-1',
  estado: 'pendiente',
  ultima_actualizacion: '2026-03-01T10:00:00Z',
};

function renderPanel() {
  return render(
    <MantineProvider>
      <TramitesPanel />
    </MantineProvider>
  );
}

describe('TramitesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetch).mockReset();
    mockGetAuthToken.mockResolvedValue('token');
    mockApiFetch.mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/tramites' && !options) {
        return { items: [canonicalTramite], total: 1 };
      }
      if (path === '/tramites/tramite-1') {
        return {
          ...canonicalTramite,
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
      if (path === '/tramites' && options?.method === 'POST') {
        return { id: 'tramite-2' };
      }
      return [];
    });
  });

  it('renders only canonical tramites and filters out legacy states', async () => {
    mockApiFetch.mockResolvedValueOnce({
      items: [
        canonicalTramite,
        {
          id: 'tramite-2',
          titulo: 'Tramite legacy',
          numero_expediente: 'B-2',
          estado: 'iniciado',
          ultima_actualizacion: '2026-03-01T10:00:00Z',
        },
      ],
      total: 2,
    });

    renderPanel();

    expect(await screen.findByText('Gestion de Expedientes')).toBeInTheDocument();
    expect(
      screen.getByRole('table', { name: /tabla de expedientes provinciales/i })
    ).toBeInTheDocument();
    expect(screen.getByText('Canal Norte')).toBeInTheDocument();
    expect(screen.getByText('PENDIENTE')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /ver historial del expediente a-1/i })).toBeInTheDocument();
    expect(screen.queryByText('Tramite legacy')).not.toBeInTheDocument();
    expect(screen.queryByText('INICIADO')).not.toBeInTheDocument();
  });

  it('handles an empty tramites response', async () => {
    mockApiFetch.mockResolvedValueOnce({ items: [], total: 0 });

    renderPanel();

    expect(await screen.findByText('Gestion de Expedientes')).toBeInTheDocument();
    expect(screen.getByText('Titulo / Expediente')).toBeInTheDocument();
    expect(screen.queryByText('Canal Norte')).not.toBeInTheDocument();
  });

  it('creates a new expediente from the modal form and reloads the list', async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole('button', { name: /nuevo expediente/i }));
    const modal = await screen.findByRole('dialog', { name: /registrar nuevo expediente provincial/i });

    await user.type(within(modal).getByLabelText(/titulo del tramite/i), 'Obra Canal Sur');
    await user.type(within(modal).getByLabelText(/numero de expediente/i), '0416-999/2026');
    await user.type(within(modal).getByLabelText(/descripcion inicial/i), 'Objetivo del tramite');
    await user.click(within(modal).getByRole('button', { name: /crear expediente/i }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/tramites',
        expect.objectContaining({ method: 'POST' })
      );
    });

    const postCall = mockApiFetch.mock.calls.find(
      ([path, options]) => path === '/tramites' && options?.method === 'POST'
    );
    expect(JSON.parse(String(postCall?.[1]?.body))).toMatchObject({
      titulo: 'Obra Canal Sur',
      numero_expediente: '0416-999/2026',
      descripcion: 'Objetivo del tramite',
      prioridad: 'normal',
    });

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(mockApiFetch.mock.calls.filter(([path, options]) => path === '/tramites' && !options).length).toBe(2);
  });

  it('opens the history modal with timeline entries from detalle', async () => {
    const user = userEvent.setup();
    renderPanel();

    const row = await screen.findByRole('row', { name: /canal norte/i });
    await user.click(within(row).getAllByRole('button')[0]);

    const modal = await screen.findByRole('dialog', { name: /linea de tiempo del expediente/i });
    expect(within(modal).getByText('Canal Norte')).toBeInTheDocument();
    expect(within(modal).getByText('Inspeccion inicial')).toBeInTheDocument();
    expect(within(modal).getByText('Se relevo la zona')).toBeInTheDocument();
    expect(mockApiFetch).toHaveBeenCalledWith('/tramites/tramite-1');
  });

  it('shows the export action and downloads the PDF with auth token', async () => {
    const user = userEvent.setup();
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const createObjectUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:tramite-pdf');

    vi.mocked(fetch).mockResolvedValueOnce({
      blob: async () => new Blob(['pdf']),
    } as Response);

    renderPanel();
    const row = await screen.findByRole('row', { name: /canal norte/i });
    await user.click(within(row).getAllByRole('button')[0]);

    const modal = await screen.findByRole('dialog', { name: /linea de tiempo del expediente/i });
    await user.click(within(modal).getByRole('button', { name: /exportar resumen/i }));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v2/tramites/tramite-1/export-pdf',
        expect.objectContaining({ headers: { Authorization: 'Bearer token' } })
      );
    });

    expect(mockGetAuthToken).toHaveBeenCalledTimes(1);
    expect(createObjectUrl).toHaveBeenCalled();
    expect(anchorClick).toHaveBeenCalled();

    anchorClick.mockRestore();
    createObjectUrl.mockRestore();
  });

  it('handles PDF export failure gracefully', async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockRejectedValueOnce(new Error('PDF generation failed'));

    renderPanel();
    const row = await screen.findByRole('row', { name: /canal norte/i });
    await user.click(within(row).getAllByRole('button')[0]);

    const modal = await screen.findByRole('dialog', { name: /linea de tiempo del expediente/i });
    await user.click(within(modal).getByRole('button', { name: /exportar resumen/i }));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalled();
    });
  });
});
