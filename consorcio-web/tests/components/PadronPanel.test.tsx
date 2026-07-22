import { MantineProvider } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PadronPanel from '../../src/components/admin/management/PadronPanel';
import { apiFetch } from '../../src/lib/api';
import { isValidCUIT } from '../../src/lib/validators';
import contracts from '../fixtures/admin-api-contracts.json';

const { mockUserRole } = vi.hoisted(() => ({
  mockUserRole: vi.fn(),
}));

vi.mock('../../src/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('../../src/lib/errorHandler', () => ({ handleError: vi.fn() }));
vi.mock('../../src/lib/validators', () => ({ isValidCUIT: vi.fn(() => true) }));
vi.mock('../../src/stores/authStore', () => ({ useUserRole: mockUserRole }));
vi.mock('@mantine/notifications', () => ({ notifications: { show: vi.fn() } }));

const consorcista = {
  id: '11111111-1111-4111-8111-111111111111',
  nombre: 'Ana',
  apellido: 'Perez',
  cuit: '20-12345678-6',
  email: null,
  telefono: null,
  localidad: null,
  parcela: null,
  hectareas: null,
  categoria: null,
  estado: 'activo',
  created_at: '2026-07-17T12:00:00Z',
};

const renderPanel = () =>
  render(
    <MantineProvider>
      <PadronPanel />
    </MantineProvider>
  );

describe('PadronPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUserRole.mockReturnValue('admin');
    vi.mocked(isValidCUIT).mockReturnValue(true);
    vi.mocked(apiFetch).mockImplementation(async (path: string) => {
      if (path.startsWith('/padron?search=')) return [consorcista];
      return {};
    });
  });

  it('shows payments as unavailable without calling nonexistent routes', async () => {
    renderPanel();

    expect(await screen.findByText('Padrón de Consorcistas')).toBeInTheDocument();
    expect(screen.getByText('Perez, Ana')).toBeInTheDocument();
    expect(
      screen.getByText(/la gestion de pagos y cuotas no esta disponible en esta version/i)
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pagos|cuotas/i })).not.toBeInTheDocument();
    expect(
      vi.mocked(apiFetch).mock.calls.some(([path]) => String(path).includes('/pagos'))
    ).toBe(false);
  });

  it('connects new consorcista validation errors to required fields', async () => {
    const user = userEvent.setup();
    vi.mocked(isValidCUIT).mockReturnValue(false);
    renderPanel();
    await screen.findByText('Padrón de Consorcistas');

    await user.click(screen.getByRole('button', { name: /nuevo consorcista/i }));
    const dialog = await screen.findByRole('dialog', { name: /registrar nuevo consorcista/i });
    await user.click(within(dialog).getByRole('button', { name: /guardar en padrón/i }));

    await waitFor(() => {
      expect(within(dialog).getByLabelText(/nombre/i)).toHaveAttribute('aria-invalid', 'true');
      expect(within(dialog).getByLabelText(/apellido/i)).toHaveAttribute('aria-invalid', 'true');
      expect(within(dialog).getByLabelText(/cuit/i)).toHaveAttribute('aria-invalid', 'true');
    });
    expect(apiFetch).not.toHaveBeenCalledWith('/padron', expect.objectContaining({ method: 'POST' }));
  });

  it('creates a new consorcista from modal form', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('Padrón de Consorcistas');

    await user.click(screen.getByRole('button', { name: /nuevo consorcista/i }));
    const dialog = await screen.findByRole('dialog', { name: /registrar nuevo consorcista/i });
    await user.type(within(dialog).getByLabelText(/nombre/i), 'Carlos');
    await user.type(within(dialog).getByLabelText(/apellido/i), 'Gomez');
    await user.type(within(dialog).getByLabelText(/cuit/i), '20-99887766-1');
    await user.type(within(dialog).getByLabelText(/email/i), 'carlos@example.com');
    await user.type(within(dialog).getByLabelText(/teléfono/i), '+54 9 261 555 0101');
    await user.click(within(dialog).getByRole('button', { name: /guardar en padrón/i }));

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/padron', {
        method: 'POST',
        body: JSON.stringify({
          nombre: 'Carlos',
          apellido: 'Gomez',
          cuit: '20-99887766-1',
          email: 'carlos@example.com',
          telefono: '+54 9 261 555 0101',
        }),
      });
    });
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Consorcista registrado', color: 'green' })
    );
  });

  it('imports padron records with the backend created and skipped semantics', async () => {
    const user = userEvent.setup();
    vi.mocked(apiFetch).mockImplementation(async (path: string, options?: RequestInit) => {
      if (path.startsWith('/padron?search=')) return [consorcista];
      if (path === '/padron/import' && options?.method === 'POST') {
        return contracts.padron.import_result;
      }
      return {};
    });

    renderPanel();
    await screen.findByText('Padrón de Consorcistas');
    await user.click(screen.getByRole('button', { name: /importar csv\/xls/i }));
    const dialog = await screen.findByRole('dialog', { name: /importar padron desde archivo/i });
    expect(
      within(dialog).getByText(/los cuit nuevos se crean; los existentes o duplicados se omiten/i)
    ).toBeInTheDocument();

    const file = new File(['cuit,nombre'], 'padron.csv', { type: 'text/csv' });
    await user.upload(dialog.querySelector('input[type="file"]') as HTMLInputElement, file);
    await user.click(within(dialog).getByRole('button', { name: /procesar importacion/i }));

    expect(await within(dialog).findByText('Archivo: padron.csv')).toBeInTheDocument();
    expect(within(dialog).getByText('Filas procesadas: 3')).toBeInTheDocument();
    expect(within(dialog).getByText('Registros creados: 2')).toBeInTheDocument();
    expect(within(dialog).getByText('Filas omitidas: 1')).toBeInTheDocument();
    expect(within(dialog).getByText(/fila 2: CUIT invalido/i)).toBeInTheDocument();
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Importacion completada',
        message: 'Procesadas 3 filas; registros creados: 2; filas omitidas: 1',
        color: 'yellow',
      })
    );
  });

  it('keeps search and viewing available to operadores without exposing the admin import flow', async () => {
    const user = userEvent.setup();
    mockUserRole.mockReturnValue('operador');
    renderPanel();

    expect(await screen.findByText('Padrón de Consorcistas')).toBeInTheDocument();
    expect(screen.getByText('Perez, Ana')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /importar csv\/xls/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: /importar padron/i })).not.toBeInTheDocument();

    const search = screen.getByRole('textbox', { name: /buscar consorcistas/i });
    await user.type(search, 'Ana');

    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/padron?search=Ana');
    });
    expect(screen.getByText('Perez, Ana')).toBeInTheDocument();
  });
});
