import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TramitesPanel from '../../src/components/admin/management/TramitesPanel';
import contracts from '../fixtures/admin-api-contracts.json';

const { mockApiFetch } = vi.hoisted(() => ({
  mockApiFetch: vi.fn(),
}));

vi.mock('../../src/lib/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../src/lib/api')>();
  return {
    ...original,
    apiFetch: mockApiFetch,
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

const tramite = contracts.tramites.detail;

function renderPanel() {
  return render(
    <MantineProvider>
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
    mockApiFetch.mockImplementation(async (path: string, options?: RequestInit) => {
      if (path === '/tramites' && !options) return { items: [tramite], total: 1 };
      if (path === `/tramites/${tramite.id}` && !options) return tramite;
      if (path === '/tramites' && options?.method === 'POST') {
        return { id: '44444444-4444-4444-8444-444444444444', message: 'ok', estado: 'ingresado' };
      }
      if (path === `/tramites/${tramite.id}/seguimiento` && options?.method === 'POST') {
        return { ...tramite.seguimiento[0], id: '55555555-5555-4555-8555-555555555555' };
      }
      return [];
    });
  });

  it('renders backend-shaped tramite list fields', async () => {
    renderPanel();

    expect(await screen.findByText('Gestion de Tramites')).toBeInTheDocument();
    expect(screen.getByText(tramite.titulo)).toBeInTheDocument();
    expect(screen.getByText('INGRESADO')).toBeInTheDocument();
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

  it('renders seguimiento from tramite detail and posts a real follow-up', async () => {
    const user = userEvent.setup();
    renderPanel();

    const row = await screen.findByRole('row', { name: new RegExp(tramite.titulo, 'i') });
    await user.click(within(row).getByRole('button', { name: /ver seguimiento/i }));

    const modal = await screen.findByRole('dialog', { name: /seguimiento del tramite/i });
    expect(within(modal).getByText(contracts.tramites.seguimiento_create.comentario)).toBeInTheDocument();
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
  });

});
