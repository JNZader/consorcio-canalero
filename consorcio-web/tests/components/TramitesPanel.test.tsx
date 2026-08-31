import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TramitesPanel from '../../src/components/admin/management/TramitesPanel';
import { API_URL, getAuthToken } from '../../src/lib/api';
import contracts from '../fixtures/admin-api-contracts.json';

const { mockApiFetch, mockGetAuthToken } = vi.hoisted(() => ({
  mockApiFetch: vi.fn(),
  mockGetAuthToken: vi.fn(),
}));

vi.mock('../../src/lib/api', () => ({
  API_URL: 'http://localhost:8000',
  apiFetch: mockApiFetch,
  getAuthToken: mockGetAuthToken,
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

const tramite = contracts.tramites.detail;

function renderPanel() {
  return render(
    <MantineProvider env="test">
      <TramitesPanel />
    </MantineProvider>
  );
}

async function chooseOption(input: HTMLElement, name: string) {
  const user = userEvent.setup();
  await user.selectOptions(input, name);
}

describe('TramitesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetAuthToken.mockResolvedValue('token');
    Object.defineProperty(window.URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:tramite-pdf'),
    });
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(HTMLAnchorElement.prototype, 'click', {
      configurable: true,
      value: vi.fn(),
    });
    mockApiFetch.mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/tramites' && !options) return { items: [tramite], total: 1 };
      if (path === `/tramites/${tramite.id}` && !options) return tramite;
      if (path === '/tramites' && options?.method === 'POST') {
        return { id: '44444444-4444-4444-8444-444444444444', message: 'ok', estado: 'ingresado' };
      }
      if (path === `/tramites/${tramite.id}/seguimiento` && options?.method === 'POST') {
        const body = JSON.parse(String(options.body)) as { comentario: string };
        return {
          ...tramite.seguimiento[0],
          id: '55555555-5555-4555-8555-555555555555',
          comentario: body.comentario,
          created_at: '2026-03-03T10:00:00Z',
        };
      }
      return [];
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders backend-shaped tramite list fields', async () => {
    renderPanel();

    expect(await screen.findByText('Gestion de Tramites')).toBeInTheDocument();
    expect(screen.getByText(tramite.titulo)).toBeInTheDocument();
    expect(screen.getByText('Ingresado')).toBeInTheDocument();
    expect(screen.getByText(/obra · consorcio canalero/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: new RegExp(`ver seguimiento.*${tramite.titulo}`, 'i') })
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /abrir expediente externo/i })).not.toBeInTheDocument();
  });

  it('creates a tramite with the shared backend contract', async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole('button', { name: /nuevo tramite/i }));
    const modal = await screen.findByRole('dialog', { name: /registrar nuevo tramite/i });

    await chooseOption(within(modal).getByLabelText(/^tipo/i), 'obra');
    await user.type(
      within(modal).getByLabelText(/titulo del tramite/i),
      contracts.tramites.create.titulo
    );
    await user.type(
      within(modal).getByLabelText(/descripcion/i),
      contracts.tramites.create.descripcion
    );
    await user.type(
      within(modal).getByLabelText(/solicitante/i),
      contracts.tramites.create.solicitante
    );
    fireEvent.change(within(modal).getByLabelText(/fecha de ingreso/i), {
      target: { value: contracts.tramites.create.fecha_ingreso },
    });
    await user.click(within(modal).getByRole('button', { name: /crear tramite/i }));

    await waitFor(() => {
      const postCall = mockApiFetch.mock.calls.find(
        ([path, options]) => path === '/tramites' && options?.method === 'POST'
      );
      expect(JSON.parse(String(postCall?.[1]?.body))).toEqual(contracts.tramites.create);
    });
    expect(mockApiFetch.mock.calls.filter(([path, options]) => path === '/tramites' && !options)).toHaveLength(2);
  });

  it('validates backend-required tramite fields before posting', async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByRole('button', { name: /nuevo tramite/i }));
    const modal = await screen.findByRole('dialog', { name: /registrar nuevo tramite/i });
    await user.click(within(modal).getByRole('button', { name: /crear tramite/i }));

    await waitFor(() => {
      expect(within(modal).getByLabelText(/titulo del tramite/i)).toHaveAttribute(
        'aria-invalid',
        'true'
      );
      expect(within(modal).getByLabelText(/descripcion/i)).toHaveAttribute('aria-invalid', 'true');
      expect(within(modal).getByLabelText(/solicitante/i)).toHaveAttribute('aria-invalid', 'true');
    });
    expect(mockApiFetch).not.toHaveBeenCalledWith(
      '/tramites',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('prepends a newly posted follow-up to the existing backend history', async () => {
    const user = userEvent.setup();
    renderPanel();

    const row = await screen.findByRole('row', { name: new RegExp(tramite.titulo, 'i') });
    await user.click(within(row).getByRole('button', { name: /ver seguimiento/i }));

    const modal = await screen.findByRole('dialog', { name: /seguimiento del tramite/i });
    const existingComment = contracts.tramites.seguimiento_create.comentario;
    expect(within(modal).getByText(existingComment)).toBeInTheDocument();
    expect(mockApiFetch).toHaveBeenCalledWith(`/tramites/${tramite.id}`);

    const newComment = 'Se adjunto el informe tecnico';
    await user.type(within(modal).getByLabelText(/nuevo seguimiento/i), newComment);
    await user.click(within(modal).getByRole('button', { name: /agregar seguimiento/i }));

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(`/tramites/${tramite.id}/seguimiento`, {
        method: 'POST',
        body: JSON.stringify({ comentario: newComment }),
      });
    });

    const newEntry = await within(modal).findByText(newComment);
    const previousEntry = within(modal).getByText(existingComment);
    expect(newEntry.compareDocumentPosition(previousEntry) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('downloads the authenticated tramite PDF with loading state and cleanup', async () => {
    const user = userEvent.setup();
    let resolveResponse: ((response: Response) => void) | undefined;
    const responsePromise = new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    });
    const fetchMock = vi.fn(() => responsePromise);
    vi.stubGlobal('fetch', fetchMock);

    renderPanel();
    const row = await screen.findByRole('row', { name: new RegExp(tramite.titulo, 'i') });
    await user.click(within(row).getByRole('button', { name: /ver seguimiento/i }));
    const modal = await screen.findByRole('dialog', { name: /seguimiento del tramite/i });
    const downloadButton = within(modal).getByRole('button', { name: /descargar pdf/i });
    const appendSpy = vi.spyOn(document.body, 'appendChild');

    await user.click(downloadButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `${API_URL}/api/v2/tramites/${tramite.id}/export-pdf`,
        {
          headers: {
            Accept: 'application/pdf',
            Authorization: 'Bearer token',
          },
        }
      );
    });
    expect(downloadButton).toBeDisabled();
    expect(getAuthToken).toHaveBeenCalledTimes(1);

    resolveResponse?.(
      new Response(new Blob(['pdf'], { type: 'application/pdf' }), {
        status: 200,
        headers: { 'Content-Type': 'application/pdf' },
      })
    );

    await waitFor(() => {
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'PDF descargado', color: 'green' })
      );
      expect(downloadButton).toBeEnabled();
    });

    const appendedAnchor = appendSpy.mock.calls
      .map(([node]) => node)
      .find((node): node is HTMLAnchorElement => node instanceof HTMLAnchorElement);
    expect(appendedAnchor?.download).toBe(`tramite-${tramite.id}.pdf`);
    expect(appendedAnchor?.href).toContain('blob:tramite-pdf');
    expect(window.URL.createObjectURL).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:tramite-pdf'), {
      timeout: 1600,
    });
    appendSpy.mockRestore();
  });

  it('reports a truthful error when the tramite PDF cannot be downloaded', async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'unavailable' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    );

    renderPanel();
    const row = await screen.findByRole('row', { name: new RegExp(tramite.titulo, 'i') });
    await user.click(within(row).getByRole('button', { name: /ver seguimiento/i }));
    const modal = await screen.findByRole('dialog', { name: /seguimiento del tramite/i });
    await user.click(within(modal).getByRole('button', { name: /descargar pdf/i }));

    await waitFor(() => {
      expect(notifications.show).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'No se pudo descargar el tramite',
          message: expect.stringContaining('503'),
          color: 'red',
        })
      );
    });
    expect(window.URL.createObjectURL).not.toHaveBeenCalled();
  });
});
